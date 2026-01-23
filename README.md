# mariadb-reddit-helper
Finds MariaDB and MySQL Reddit posts/comments and suggests replies using GenAI.


## How to run


Create API-keys and add to `set_env.sh`
* Reddit: https://www.reddit.com/prefs/apps
* Claude: https://platform.claude.com

Run script with:

```shell
python -m venv .venv # set up virtual env
source .venv/bin/activate # start virtual env
pip install praw anthropic # install required packages
source set_env.sh # sets API keys
python mariadb-reddit-helper.py # runs script
```
