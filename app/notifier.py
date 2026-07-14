import requests, datetime
from .config import load_config
from .gold_price import calculate_pnl

QQ_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"

def _get_qq_access_token(app_id, app_secret):
    """Get QQ Bot OAuth2 access token"""
    try:
        resp = requests.post(QQ_TOKEN_URL, json={
            "appId": app_id,
            "clientSecret": app_secret,
        }, timeout=10)
        data = resp.json()
        return data.get("access_token")
    except Exception as e:
        print(f"[Push] QQ token refresh error: {e}")
        return None

def _strip_markdown(text):
    """Strip markdown formatting for plain-text channels (QQ)"""
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'^###?\s+', '', text, flags=re.MULTILINE)
    return text

def push_wechat(title, content):
    cfg = load_config()
    webhook = cfg.get("push_channels", {}).get("wechat_webhook", "")
    if not webhook:
        return False, "微信推送未配置"
    try:
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": f"### {title}\n{content}"},
        }
        resp = requests.post(webhook, json=payload, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            return True, "推送成功"
        return False, result.get("errmsg", "推送失败")
    except Exception as e:
        return False, str(e)

def push_feishu(title, content):
    cfg = load_config()
    webhook = cfg.get("push_channels", {}).get("feishu_webhook", "")
    if not webhook:
        return False, "飞书推送未配置"
    try:
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [{"tag": "markdown", "content": content}],
            },
        }
        resp = requests.post(webhook, json=payload, timeout=10)
        result = resp.json()
        if result.get("code") == 0:
            return True, "推送成功"
        return False, result.get("msg", "推送失败")
    except Exception as e:
        return False, str(e)

def push_qq(title, content):
    cfg = load_config()
    qq = cfg.get("push_channels", {}).get("qq_bot", {})
    app_id = qq.get("app_id", "")
    app_secret = qq.get("app_secret", "")
    group_id = qq.get("group_id", "")
    if not all([app_id, app_secret, group_id]):
        return False, "QQ推送未配置"

    access_token = _get_qq_access_token(app_id, app_secret)
    if not access_token:
        return False, "QQ token获取失败"

    try:
        url = f"https://api.sgroup.qq.com/v2/groups/{group_id}/messages"
        headers = {
            "Authorization": f"QQBot {app_id}.{access_token}",
            "Content-Type": "application/json",
        }
        plain_content = _strip_markdown(f"【{title}】\n{content}")
        payload = {
            "msg_type": 0,
            "content": plain_content,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 204):
            return True, "推送成功"
        return False, resp.text[:200]
    except Exception as e:
        return False, str(e)

def push_all(title, content):
    cfg = load_config()
    channels = cfg.get("push_channels", {})
    results = {}
    if channels.get("wechat_webhook"):
        results["微信"] = push_wechat(title, content)
    if channels.get("feishu_webhook"):
        results["飞书"] = push_feishu(title, content)
    if channels.get("qq_bot", {}).get("app_id"):
        results["QQ"] = push_qq(title, content)
    for ch, (ok, msg) in results.items():
        if not ok:
            print(f"[Push] {ch} failed: {msg}")
    return results

def build_price_alert_content(price, low, high):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    direction = "突破上限" if price >= high else "跌破下限"
    return (
        f"当前金价：**{price}元/克**\n"
        f"触发条件：{direction}（{low}-{high}）\n"
        f"时间：{now}"
    )

def build_pnl_content(purchases, current_price):
    lines = [f"当前金价：**{current_price}元/克**\n"]
    for p in purchases:
        pnl, pct = calculate_pnl(p["price"], current_price, p.get("fee", 0))
        status = "盈利" if pnl >= 0 else "亏损"
        sign = "+" if pnl >= 0 else ""
        lines.append(
            f"- 购入价 {p['price']}元/克（手续费{p.get('fee',0)}%）→ "
            f"{status} **{sign}{pnl}元/克**（{sign}{pct}%）"
        )
    return "\n".join(lines)
