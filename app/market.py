import requests, re, json, time
from .config import load_config, save_config

SINA_HQ_URL = "https://hq.sinajs.cn/list="
TIANFUND_URL = "https://fundgz.1234567.com.cn/js/{code}.js"

SINA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn",
}

TIANFUND_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fund.eastmoney.com",
}

FUTURES_EXCHANGES = {
    "SHFE": "上期所", "DCE": "大商所", "CZCE": "郑商所",
    "CFFEX": "中金所", "INE": "上期能源", "GFEX": "广期所",
}

FUTURES_POPULAR = [
    {"code": "AU0", "name": "黄金主力", "exchange": "SHFE"},
    {"code": "AG0", "name": "白银主力", "exchange": "SHFE"},
    {"code": "CU0", "name": "沪铜主力", "exchange": "SHFE"},
    {"code": "AL0", "name": "沪铝主力", "exchange": "SHFE"},
    {"code": "ZN0", "name": "沪锌主力", "exchange": "SHFE"},
    {"code": "RB0", "name": "螺纹钢主力", "exchange": "SHFE"},
    {"code": "I0", "name": "铁矿石主力", "exchange": "DCE"},
    {"code": "M0", "name": "豆粕主力", "exchange": "DCE"},
    {"code": "Y0", "name": "豆油主力", "exchange": "DCE"},
    {"code": "P0", "name": "棕榈油主力", "exchange": "DCE"},
    {"code": "CF0", "name": "棉花主力", "exchange": "CZCE"},
    {"code": "SR0", "name": "白糖主力", "exchange": "CZCE"},
    {"code": "TA0", "name": "PTA主力", "exchange": "CZCE"},
    {"code": "MA0", "name": "甲醇主力", "exchange": "CZCE"},
    {"code": "SC0", "name": "原油主力", "exchange": "INE"},
    {"code": "IF0", "name": "沪深300主力", "exchange": "CFFEX"},
    {"code": "IC0", "name": "中证500主力", "exchange": "CFFEX"},
    {"code": "IH0", "name": "上证50主力", "exchange": "CFFEX"},
    {"code": "IM0", "name": "中证1000主力", "exchange": "CFFEX"},
    {"code": "NR0", "name": "20号胶主力", "exchange": "INE"},
    {"code": "RU0", "name": "橡胶主力", "exchange": "SHFE"},
    {"code": "BU0", "name": "沥青主力", "exchange": "SHFE"},
    {"code": "HC0", "name": "热卷主力", "exchange": "SHFE"},
    {"code": "SS0", "name": "不锈钢主力", "exchange": "SHFE"},
    {"code": "NI0", "name": "沪镍主力", "exchange": "SHFE"},
    {"code": "SN0", "name": "沪锡主力", "exchange": "SHFE"},
    {"code": "PB0", "name": "沪铅主力", "exchange": "SHFE"},
    {"code": "FU0", "name": "燃油主力", "exchange": "SHFE"},
    {"code": "SP0", "name": "纸浆主力", "exchange": "SHFE"},
    {"code": "EB0", "name": "苯乙烯主力", "exchange": "DCE"},
    {"code": "EG0", "name": "乙二醇主力", "exchange": "DCE"},
    {"code": "PP0", "name": "聚丙烯主力", "exchange": "DCE"},
    {"code": "L0", "name": "塑料主力", "exchange": "DCE"},
    {"code": "V0", "name": "PVC主力", "exchange": "DCE"},
    {"code": "A0", "name": "豆一主力", "exchange": "DCE"},
    {"code": "B0", "name": "豆二主力", "exchange": "DCE"},
    {"code": "C0", "name": "玉米主力", "exchange": "DCE"},
    {"code": "CS0", "name": "玉米淀粉主力", "exchange": "DCE"},
    {"code": "JD0", "name": "鸡蛋主力", "exchange": "DCE"},
    {"code": "LH0", "name": "生猪主力", "exchange": "DCE"},
    {"code": "OI0", "name": "菜油主力", "exchange": "CZCE"},
    {"code": "RM0", "name": "菜粕主力", "exchange": "CZCE"},
    {"code": "FG0", "name": "玻璃主力", "exchange": "CZCE"},
    {"code": "SA0", "name": "纯碱主力", "exchange": "CZCE"},
    {"code": "AP0", "name": "苹果主力", "exchange": "CZCE"},
    {"code": "CJ0", "name": "红枣主力", "exchange": "CZCE"},
    {"code": "UR0", "name": "尿素主力", "exchange": "CZCE"},
    {"code": "PF0", "name": "短纤主力", "exchange": "CZCE"},
]

def _sina_code_to_market(code):
    code = code.strip().upper()
    if code.startswith("SH") or code.startswith("SZ") or code.startswith("BJ"):
        return code.lower()
    if code.startswith("HK"):
        return code.lower()
    digits = re.sub(r'[^0-9]', '', code)
    if not digits:
        return None
    if len(digits) == 6:
        if digits.startswith("6"):
            return f"sh{digits}"
        elif digits.startswith("0") or digits.startswith("3"):
            return f"sz{digits}"
        elif digits.startswith("8") or digits.startswith("4"):
            return f"bj{digits}"
    if len(digits) == 5:
        return f"hk{digits}"
    return None

def _futures_code_to_sina(code):
    code = code.strip().upper()
    if re.match(r'^[A-Z]{1,3}\d{1,2}$', code):
        return code
    return None

def _parse_sina_hq(raw):
    m = re.search(r'"(.+)"', raw)
    if not m:
        return None
    fields = m.group(1).split(",")
    if len(fields) < 4:
        return None
    return fields

def fetch_a_stock(code):
    sina_code = _sina_code_to_market(code)
    if not sina_code:
        return None
    try:
        resp = requests.get(f"{SINA_HQ_URL}{sina_code}", headers=SINA_HEADERS, timeout=10)
        resp.encoding = "gbk"
        fields = _parse_sina_hq(resp.text)
        if not fields or not fields[3]:
            return None
        name = fields[0]
        current = float(fields[3])
        open_price = float(fields[1]) if fields[1] else current
        high = float(fields[4]) if fields[4] else current
        low = float(fields[5]) if fields[5] else current
        prev_close = float(fields[2]) if fields[2] else current
        volume = float(fields[8]) if len(fields) > 8 and fields[8] else 0
        change_pct = round((current - prev_close) / prev_close * 100, 2) if prev_close else 0
        return {
            "name": name, "code": code, "type": "a_stock",
            "price": current, "open": open_price, "high": high, "low": low,
            "prev_close": prev_close, "change_pct": change_pct,
            "volume": volume, "source": "sina",
        }
    except Exception as e:
        print(f"[Market] A股获取失败 {code}: {e}")
        return None

def fetch_hk_stock(code):
    sina_code = _sina_code_to_market(code)
    if not sina_code:
        return None
    try:
        resp = requests.get(f"{SINA_HQ_URL}{sina_code}", headers=SINA_HEADERS, timeout=10)
        resp.encoding = "gbk"
        fields = _parse_sina_hq(resp.text)
        if not fields or not fields[6]:
            return None
        name = fields[1]
        current = float(fields[6])
        open_price = float(fields[2]) if fields[2] else current
        high = float(fields[4]) if fields[4] else current
        low = float(fields[5]) if fields[5] else current
        prev_close = float(fields[3]) if fields[3] else current
        change_pct = round((current - prev_close) / prev_close * 100, 2) if prev_close else 0
        return {
            "name": name, "code": code, "type": "hk_stock",
            "price": current, "open": open_price, "high": high, "low": low,
            "prev_close": prev_close, "change_pct": change_pct,
            "volume": 0, "source": "sina",
        }
    except Exception as e:
        print(f"[Market] 港股获取失败 {code}: {e}")
        return None

def fetch_fund(code):
    code = code.strip()
    try:
        resp = requests.get(TIANFUND_URL.format(code=code), headers=TIANFUND_HEADERS, timeout=10)
        resp.encoding = "utf-8"
        m = re.search(r'jsonpgz\((.+)\)', resp.text)
        if not m:
            return None
        data = json.loads(m.group(1))
        name = data.get("name", "")
        current = float(data.get("dwjz", 0))
        change_pct = float(data.get("gszzl", 0))
        gsz = float(data.get("gsz", 0))
        return {
            "name": name, "code": code, "type": "fund",
            "price": current, "estimated": gsz, "change_pct": change_pct,
            "source": "tianfund",
        }
    except Exception as e:
        print(f"[Market] 基金获取失败 {code}: {e}")
        return None

def fetch_futures(code):
    sina_code = _futures_code_to_sina(code)
    if not sina_code:
        return None
    try:
        resp = requests.get(f"{SINA_HQ_URL}{sina_code}", headers=SINA_HEADERS, timeout=10)
        resp.encoding = "gbk"
        raw = resp.text
        if '=""' in raw or not re.search(r'"[^"]+"', raw):
            return None
        fields = _parse_sina_hq(raw)
        if not fields:
            return None
        name = fields[0]
        if not name:
            matched = [f for f in FUTURES_POPULAR if f["code"].upper() == code.upper()]
            name = matched[0]["name"] if matched else code
        current = float(fields[3]) if fields[3] else 0
        if current <= 0:
            return None
        open_price = float(fields[1]) if fields[1] else current
        high = float(fields[4]) if fields[4] else current
        low = float(fields[5]) if fields[5] else current
        prev_close = float(fields[2]) if fields[2] else current
        volume = float(fields[8]) if len(fields) > 8 and fields[8] else 0
        open_interest = float(fields[13]) if len(fields) > 13 and fields[13] else 0
        change_pct = round((current - prev_close) / prev_close * 100, 2) if prev_close else 0
        exchange = ""
        matched = [f for f in FUTURES_POPULAR if f["code"].upper() == code.upper()]
        if matched:
            exchange = FUTURES_EXCHANGES.get(matched[0].get("exchange", ""), "")
        return {
            "name": name, "code": code.upper(), "type": "futures",
            "price": current, "open": open_price, "high": high, "low": low,
            "prev_close": prev_close, "change_pct": change_pct,
            "volume": volume, "open_interest": open_interest,
            "exchange": exchange, "source": "sina",
        }
    except Exception as e:
        print(f"[Market] 期货获取失败 {code}: {e}")
        return None

def _search_futures_by_name(keyword):
    results = []
    kw = keyword.upper()
    for f in FUTURES_POPULAR:
        if kw in f["name"].upper() or kw in f["code"].upper():
            info = fetch_futures(f["code"])
            if info:
                results.append(info)
            if len(results) >= 5:
                break
    return results

def search_stock(keyword):
    keyword = keyword.strip()
    futures_by_name = _search_futures_by_name(keyword)
    if futures_by_name:
        return futures_by_name
    if re.match(r'^[0-9a-zA-Z]+$', keyword):
        fu = fetch_futures(keyword)
        if fu:
            return [fu]
        a = fetch_a_stock(keyword)
        if a:
            return [a]
        hk = fetch_hk_stock(keyword)
        if hk:
            return [hk]
        f = fetch_fund(keyword)
        if f:
            return [f]
        return []
    try:
        resp = requests.get(
            "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15,21,22,23,24,25,34,35&key=" + keyword,
            headers=SINA_HEADERS, timeout=10,
        )
        resp.encoding = "gbk"
        m = re.search(r'"(.+)"', resp.text)
        if not m:
            return []
        items = []
        for entry in m.group(1).split(";"):
            parts = entry.split(",")
            if len(parts) < 4:
                continue
            name = parts[1]
            code = parts[2]
            market = parts[0]
            if market.startswith("sh") or market.startswith("sz") or market.startswith("bj"):
                info = fetch_a_stock(code)
                if info:
                    items.append(info)
            elif market.startswith("hk"):
                info = fetch_hk_stock(code)
                if info:
                    items.append(info)
            if len(items) >= 5:
                break
        return items
    except Exception as e:
        print(f"[Market] 搜索失败: {e}")
        return []

def fetch_asset_price(asset):
    asset_type = asset.get("type", "")
    code = asset.get("code", "")
    if asset_type == "a_stock":
        return fetch_a_stock(code)
    elif asset_type == "hk_stock":
        return fetch_hk_stock(code)
    elif asset_type == "fund":
        return fetch_fund(code)
    elif asset_type == "futures":
        return fetch_futures(code)
    return None

def add_watch_item(cfg, item):
    watches = cfg.setdefault("watches", [])
    for w in watches:
        if w.get("code") == item.get("code") and w.get("type") == item.get("type"):
            return False, "已在监控列表中"
    watches.append(item)
    save_config(cfg)
    return True, "已添加"

def remove_watch_item(cfg, index):
    watches = cfg.get("watches", [])
    if 0 <= index < len(watches):
        removed = watches.pop(index)
        save_config(cfg)
        return True, removed
    return False, None

def list_watch_items(cfg):
    return cfg.get("watches", [])
