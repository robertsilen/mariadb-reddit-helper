# mariadb-reddit-helper
Searches for MariaDB and MySQL Reddit posts/comments from past 24 hours and suggests replies using GenAI. Saves each run in output folder. 

## Latest runs

* See the [output](https://github.com/robertsilen/mariadb-reddit-helper/tree/main/output) folder

## How to run manually

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

## Todo, wish list

* Set a Github action in the repo to run the script daily. Requires setting API-keys as secrets in the github repo.
* Tweak GenAI prompt to produce as usable prompt as possible. Possibly taking different type of context into account.