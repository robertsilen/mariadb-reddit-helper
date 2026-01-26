#!/usr/bin/env python3
"""
Reddit MariaDB/MySQL Mention Tracker

Searches all subreddits for posts and comments mentioning "mariadb" or "mysql"
from the past 24 hours and outputs results to a markdown file.

Requires Reddit API credentials. Set up at https://www.reddit.com/prefs/apps
"""

import praw
import anthropic
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load_prompt():
    """Load the active prompt from prompts.json."""
    prompts_file = Path(__file__).parent / "prompts.json"
    
    if not prompts_file.exists():
        raise FileNotFoundError(
            f"prompts.json not found at {prompts_file}\n"
            "Please create a prompts.json file with your prompts."
        )
    
    with open(prompts_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for prompt_config in data['prompts']:
        if prompt_config.get('use', False):
            return prompt_config['prompt'], prompt_config.get('name', 'unnamed')
    
    raise ValueError("No prompt with 'use': true found in prompts.json")


def get_reddit_client():
    """Initialize Reddit API client using environment variables."""
    client_id = os.environ.get('REDDIT_CLIENT_ID')
    client_secret = os.environ.get('REDDIT_CLIENT_SECRET')
    user_agent = os.environ.get('REDDIT_USER_AGENT', 'MariaDB/MySQL Mention Tracker v1.0')
    
    if not client_id or not client_secret:
        raise ValueError(
            "Reddit API credentials not found.\n"
            "Please set the following environment variables:\n"
            "  REDDIT_CLIENT_ID - Your Reddit app client ID\n"
            "  REDDIT_CLIENT_SECRET - Your Reddit app client secret\n"
            "\nTo create credentials:\n"
            "1. Go to https://www.reddit.com/prefs/apps\n"
            "2. Click 'Create App' or 'Create Another App'\n"
            "3. Select 'script' as the app type\n"
            "4. Fill in name and redirect URI (can be http://localhost)\n"
            "5. Copy the client ID (under app name) and secret"
        )
    
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent
    )


def get_anthropic_client():
    """Initialize Anthropic API client using environment variables."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    
    if not api_key:
        raise ValueError(
            "Anthropic API key not found.\n"
            "Please set the ANTHROPIC_API_KEY environment variable."
        )
    
    return anthropic.Anthropic(api_key=api_key)


def generate_ai_suggestion(client, prompt, title, body):
    """Generate an AI suggested comment for a Reddit post/comment."""
    content = f"Title: {title}\n\n{body}" if body else f"Title: {title}"
    
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": f"{prompt}\n\n{content}"}
            ]
        )
        return message.content[0].text
    except Exception as e:
        return f"Error generating suggestion: {e}"


def format_timestamp(utc_timestamp):
    """Format Unix timestamp to readable datetime."""
    dt = datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def truncate_content(body, url, max_chars=1500):
    """Truncate long content and add a link to read more."""
    if not body or len(body) <= max_chars:
        return body
    
    # Find a good breaking point (end of sentence or paragraph)
    truncated = body[:max_chars]
    
    # Try to break at paragraph
    last_para = truncated.rfind('\n\n')
    if last_para > max_chars * 0.5:
        truncated = truncated[:last_para]
    else:
        # Try to break at sentence
        last_sentence = max(truncated.rfind('. '), truncated.rfind('! '), truncated.rfind('? '))
        if last_sentence > max_chars * 0.5:
            truncated = truncated[:last_sentence + 1]
    
    return truncated.strip() + f"\n\n*[... Click to read whole post/comment]({url})*"


def format_body_as_blockquote(body):
    """Format body text as markdown blockquote."""
    lines = []
    for line in body.split('\n'):
        lines.append(f"> {line}")
    return '\n'.join(lines)


def search_reddit_for_keyword(reddit, keyword, hours=24):
    """Search Reddit for all mentions of a keyword in the past specified hours."""
    results = {
        'posts': []
    }
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_timestamp = cutoff_time.timestamp()
    
    print(f"Searching for '{keyword}' mentions since {cutoff_time.strftime('%Y-%m-%d %H:%M UTC')}...")
    
    # Search for posts containing the keyword
    print("\nSearching posts...")
    try:
        for submission in reddit.subreddit("all").search(keyword, sort="new", time_filter="day", limit=None):
            if submission.created_utc >= cutoff_timestamp:
                # Check if keyword is in title or selftext
                title_mentions = keyword.lower() in submission.title.lower()
                body_mentions = submission.selftext and keyword.lower() in submission.selftext.lower()
                
                if title_mentions or body_mentions:
                    results['posts'].append({
                        'title': submission.title,
                        'url': f"https://reddit.com{submission.permalink}",
                        'subreddit': submission.subreddit.display_name,
                        'timestamp': submission.created_utc,
                        'body': submission.selftext or ""
                    })
                    print(f"  Found post in r/{submission.subreddit.display_name}: {submission.title[:50]}...")
    except Exception as e:
        print(f"  Error searching posts: {e}")
    
    return results


def extract_category(suggestion):
    """Extract the category from an AI suggestion response."""
    # The category should be the first line
    first_line = suggestion.strip().split('\n')[0].strip()
    
    # List of valid categories
    valid_categories = [
        "Technical Support", "Bug Report", "Migration Question", 
        "Performance Issue", "General Discussion", "Job Posting", 
        "Spam", "Other"
    ]
    
    for category in valid_categories:
        if category.lower() in first_line.lower():
            return category
    
    return "Other"


def count_categories(items):
    """Count occurrences of each category."""
    counts = {}
    for item in items:
        category = item.get('category', 'Other')
        counts[category] = counts.get(category, 0) + 1
    return counts


def format_category_counts(counts):
    """Format category counts as a string."""
    if not counts:
        return "none"
    parts = [f"{count} {cat}" for cat, count in sorted(counts.items(), key=lambda x: -x[1])]
    return ", ".join(parts)


def generate_markdown(mariadb_results, mysql_results, anthropic_client):
    """Generate markdown content from search results."""
    
    # Load the active prompt
    ai_prompt, prompt_name = load_prompt()
    
    # Generate AI suggestions for all items first
    print("\nGenerating AI suggestions for MariaDB posts...")
    for i, post in enumerate(mariadb_results['posts']):
        print(f"  MariaDB post {i+1}/{len(mariadb_results['posts'])}...")
        suggestion = generate_ai_suggestion(anthropic_client, ai_prompt, post['title'], post['body'])
        post['ai_suggestion'] = suggestion
        post['category'] = extract_category(suggestion)
    
    print("\nGenerating AI suggestions for MySQL posts...")
    for i, post in enumerate(mysql_results['posts']):
        print(f"  MySQL post {i+1}/{len(mysql_results['posts'])}...")
        suggestion = generate_ai_suggestion(anthropic_client, ai_prompt, post['title'], post['body'])
        post['ai_suggestion'] = suggestion
        post['category'] = extract_category(suggestion)
    
    # Count categories
    mariadb_post_categories = count_categories(mariadb_results['posts'])
    mysql_post_categories = count_categories(mysql_results['posts'])
    
    # Find posts that mention both MariaDB and MySQL
    mariadb_post_urls = {p['url'] for p in mariadb_results['posts']}
    mysql_post_urls = {p['url'] for p in mysql_results['posts']}
    both_posts = mariadb_post_urls & mysql_post_urls
    
    lines = [
        "# Reddit Database Mentions",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | Last 24 hours*",
        "",
        f"* **MariaDB:** {len(mariadb_results['posts'])} posts",
        f"  * {format_category_counts(mariadb_post_categories)}",
        f"* **MySQL:** {len(mysql_results['posts'])} posts",
        f"  * {format_category_counts(mysql_post_categories)}",
        f"* **Both MariaDB and MySQL:** {len(both_posts)} posts",
        "",
        f"**AI prompt ({prompt_name}):** {ai_prompt}",
        "",
        "---",
        "",
    ]
    
    # MariaDB Posts
    lines.append("## MariaDB: Posts")
    lines.append("")
    
    if mariadb_results['posts']:
        sorted_posts = sorted(mariadb_results['posts'], key=lambda x: x['timestamp'], reverse=True)
        for post in sorted_posts:
            lines.append(f"### [r/{post['subreddit']}](https://reddit.com/r/{post['subreddit']}) – [{post['title']}]({post['url']})")
            lines.append(f"{format_timestamp(post['timestamp'])}")
            lines.append("")
            if post['body']:
                truncated_body = truncate_content(post['body'], post['url'])
                lines.append(format_body_as_blockquote(truncated_body))
                lines.append("")
            lines.append(f"**AI suggested comment:** {post['ai_suggestion']}")
            lines.append("")
    else:
        lines.append("*No posts found.*")
        lines.append("")
    
    # MySQL Posts
    lines.append("---")
    lines.append("")
    lines.append("## MySQL: Posts")
    lines.append("")
    
    if mysql_results['posts']:
        sorted_posts = sorted(mysql_results['posts'], key=lambda x: x['timestamp'], reverse=True)
        for post in sorted_posts:
            lines.append(f"### [r/{post['subreddit']}](https://reddit.com/r/{post['subreddit']}) – [{post['title']}]({post['url']})")
            lines.append(f"{format_timestamp(post['timestamp'])}")
            lines.append("")
            if post['body']:
                truncated_body = truncate_content(post['body'], post['url'])
                lines.append(format_body_as_blockquote(truncated_body))
                lines.append("")
            lines.append(f"**AI suggested comment:** {post['ai_suggestion']}")
            lines.append("")
    else:
        lines.append("*No posts found.*")
        lines.append("")
    
    return "\n".join(lines)


def main():
    """Main function to run the Reddit MariaDB/MySQL search."""
    # Initialize Reddit client
    print("Initializing Reddit API client...")
    reddit = get_reddit_client()
    
    # Initialize Anthropic client
    print("Initializing Anthropic API client...")
    anthropic_client = get_anthropic_client()
    
    # Search for MariaDB mentions
    print("\n" + "="*50)
    print("SEARCHING FOR MARIADB")
    print("="*50)
    mariadb_results = search_reddit_for_keyword(reddit, "mariadb")
    
    # Search for MySQL mentions
    print("\n" + "="*50)
    print("SEARCHING FOR MYSQL")
    print("="*50)
    mysql_results = search_reddit_for_keyword(reddit, "mysql")
    
    # Generate markdown content with AI suggestions
    print("\n" + "="*50)
    print("GENERATING AI SUGGESTIONS")
    print("="*50)
    markdown_content = generate_markdown(mariadb_results, mysql_results, anthropic_client)
    
    # Create output directory
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    # Generate filename with current timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    output_file = output_dir / f"{timestamp}.md"
    
    # Write to file
    output_file.write_text(markdown_content, encoding='utf-8')
    
    print(f"\n✓ Results saved to: {output_file}")
    print(f"  MariaDB: {len(mariadb_results['posts'])} posts")
    print(f"  MySQL: {len(mysql_results['posts'])} posts")


if __name__ == "__main__":
    main()