import os, json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
DB_FILE = os.path.join(DATA_DIR, "gold.db")

os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "gold_api_url": "https://www.czbank.com/gold/query",
    "custom_api_url": "",
    "use_custom_api": False,
    "push_channels": {
        "wechat_webhook": "",
        "qq_bot": {"app_id": "", "app_secret": "", "group_id": ""},
        "feishu_webhook": "",
    },
    "alert_threshold_low": 0,
    "alert_threshold_high": 9999,
    "alert_enabled": False,
    "my_purchases": [],
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
