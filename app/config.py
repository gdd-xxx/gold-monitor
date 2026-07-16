import os, json, tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _get_data_dir():
    primary = os.path.join(BASE_DIR, "data")
    try:
        os.makedirs(primary, exist_ok=True)
        test_file = os.path.join(primary, ".write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        print(f"[Config] 使用数据目录: {primary}")
        return primary
    except (PermissionError, OSError) as e:
        fallback = os.path.join(tempfile.gettempdir(), "gold-monitor-data")
        os.makedirs(fallback, exist_ok=True)
        print(f"[Config] data目录不可写({e})，使用临时目录: {fallback}")
        return fallback

DATA_DIR = _get_data_dir()
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
DB_FILE = os.path.join(DATA_DIR, "gold.db")

DEFAULT_CONFIG = {
    "gold_api_url": "https://api.jdjygold.com/gw2/generic/jrm/h5/m/stdLatestPrice?productSku=1961543816",
    "custom_api_url": "",
    "use_custom_api": False,
    "push_channels": {
        "wechat_webhook": "",
        "qq_bot": {"app_id": "", "token": "", "user_id": "", "channel_id": ""},
        "feishu_webhook": "",
    },
    "fetch_interval": 60,
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
        if "push_channels" in cfg:
            qq = cfg["push_channels"].get("qq_bot", {})
            if "app_secret" in qq and "token" not in qq:
                qq["token"] = qq.pop("app_secret")
        return cfg
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
