import requests, re, json
from .config import load_config

def fetch_jdjygold_price():
    """Fetch gold price from 京东黄金"""
    url = "https://api.jdjygold.com/gw2/generic/jrm/h5/m/stdLatestPrice"
    params = {"productSku": "1961543816"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://m.jd.com/",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        if "result" in data and "latestPrice" in data["result"]:
            return float(data["result"]["latestPrice"])
        if "result" in data and "price" in data["result"]:
            return float(data["result"]["price"])
        prices = re.findall(r'(\d{3,4}\.\d{2})', json.dumps(data))
        if prices:
            return float(prices[0])
    except Exception as e:
        print(f"[GoldPrice] JDJYGold error: {e}")
    return None

def fetch_czbank_price():
    """Fetch gold price from 浙商银行"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.czbank.com/",
    }
    alt_urls = [
        "https://www.czbank.com/gold/query",
        "https://www.czbank.com/channel/goldPrice",
        "https://gold.czbank.com/gold/query",
    ]
    for url in alt_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.encoding = "utf-8"
            prices = re.findall(r'(\d{3,4}\.\d{2})', resp.text)
            if prices:
                return float(prices[0])
        except Exception:
            continue
    return _fetch_fallback_price()

def _fetch_fallback_price():
    """Fallback: try SGE (上海黄金交易所)"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get("https://www.sge.com.cn/sjzx/mrhqsj", headers=headers, timeout=10)
        resp.encoding = "utf-8"
        prices = re.findall(r'(\d{3,4}\.\d{2})', resp.text)
        if prices:
            return float(prices[0])
    except Exception:
        pass
    return None

def fetch_custom_api_price(api_url):
    """Fetch price from user-provided API"""
    try:
        resp = requests.get(api_url, timeout=10)
        data = resp.json()
        if "price" in data:
            return float(data["price"])
        if "result" in data and "latestPrice" in data["result"]:
            return float(data["result"]["latestPrice"])
        if "data" in data and "price" in data["data"]:
            return float(data["data"]["price"])
        prices = re.findall(r'(\d{3,4}\.\d{2})', json.dumps(data))
        if prices:
            return float(prices[0])
        return None
    except Exception as e:
        print(f"[GoldPrice] Custom API error: {e}")
        return None

def get_current_price():
    cfg = load_config()
    if cfg.get("use_custom_api") and cfg.get("custom_api_url"):
        price = fetch_custom_api_price(cfg["custom_api_url"])
        if price:
            return price, "custom"

    price = fetch_jdjygold_price()
    if price:
        return price, "jdjygold"

    price = fetch_czbank_price()
    return price, "czbank"

def calculate_pnl(purchase_price, current_price, fee_percent=0):
    """Calculate profit/loss per gram"""
    cost = purchase_price * (1 + fee_percent / 100)
    pnl = current_price - cost
    pnl_percent = (pnl / cost) * 100
    return round(pnl, 2), round(pnl_percent, 2)
