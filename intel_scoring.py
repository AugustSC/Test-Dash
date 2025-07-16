import re
import yaml

CONFIG_FILE = 'config/config.yaml'

# Load keyword and bot configs
with open(CONFIG_FILE, 'r') as f:
    config = yaml.safe_load(f)

watchlist_patterns = [re.compile(p, re.IGNORECASE) for p in config.get("watchlist_keywords", [])]
ignored_bots = set(config.get("ignore_bots", []))

def is_rsi_handle(text):
    match = re.search(r"https:\/\/robertsspaceindustries\.com\/en\/citizens\/([a-zA-Z0-9_]+)", text)
    return match.group(1) if match else None

def score_text(text):
    """Return how many watchlist terms matched
