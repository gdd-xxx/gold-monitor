import requests, json, re
from .config import load_config, save_config

QQ_API_BASE = "https://api.sgroup.qq.com"

def qq_send_message(app_id, token, chat_id, msg_type, content):
    """发送QQ消息"""
    url_map = {
        "c2c": f"{QQ_API_BASE}/v2/users/{chat_id}/messages",
        "channel": f"{QQ_API_BASE}/channels/{chat_id}/messages",
        "group": f"{QQ_API_BASE}/v2/groups/{chat_id}/messages",
    }
    url = url_map.get(msg_type)
    if not url:
        return False, f"不支持的类型: {msg_type}"

    headers = {
        "Authorization": f"QQBot {app_id}.{token}",
        "Content-Type": "application/json",
    }
    payload = {"msg_type": 0, "content": content}

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"[QQ] 发送: {resp.status_code} {resp.text[:200]}")
        if resp.status_code in (200, 204):
            return True, "发送成功"
        try:
            err = resp.json()
            msg = err.get("message", err.get("msg", resp.text[:200]))
        except:
            msg = resp.text[:200]
        return False, f"({resp.status_code}) {msg}"
    except Exception as e:
        return False, str(e)

def push_qq(title, content):
    """推送消息到QQ"""
    cfg = load_config()
    qq = cfg.get("push_channels", {}).get("qq_bot", {})
    app_id = qq.get("app_id", "").strip()
    token = qq.get("token", "").strip()

    if not app_id or not token:
        return False, "QQ未配置(需AppID+Token)"

    plain = re.sub(r'\*\*(.+?)\*\*', r'\1', content)
    plain = re.sub(r'^###?\s+', '', plain, flags=re.MULTILINE)
    plain = f"【{title}】\n{plain}"

    user_id = qq.get("user_id", "").strip()
    channel_id = qq.get("channel_id", "").strip()

    if user_id:
        ok, msg = qq_send_message(app_id, token, user_id, "c2c", plain)
        if ok:
            return True, msg
    if channel_id:
        ok, msg = qq_send_message(app_id, token, channel_id, "channel", plain)
        if ok:
            return True, msg

    if user_id:
        return qq_send_message(app_id, token, user_id, "c2c", plain)
    if channel_id:
        return qq_send_message(app_id, token, channel_id, "channel", plain)

    return False, "QQ推送需要用户ID或频道ID"

def build_price_alert_content(price, low, high):
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    direction = "突破上限" if price >= high else "跌破下限"
    return f"当前金价：**{price}元/克**\n触发条件：{direction}（{low}-{high}）\n时间：{now}"

def build_pnl_content(purchases, current_price):
    from .gold_price import calculate_pnl
    lines = [f"当前金价：**{current_price}元/克**\n"]
    for p in purchases:
        pnl, pct = calculate_pnl(p["price"], current_price, p.get("fee", 0))
        status = "盈利" if pnl >= 0 else "亏损"
        sign = "+" if pnl >= 0 else ""
        lines.append(f"- 购入价 {p['price']}元/克 → {status} **{sign}{pnl}元/克**（{sign}{pct}%）")
    return "\n".join(lines)
