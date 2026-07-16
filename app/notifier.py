import requests, json, re, datetime
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
        print(f"[QQ发送] 失败: 不支持的类型 {msg_type}")
        return False, f"不支持的类型: {msg_type}"

    headers = {
        "Authorization": f"QQBot {app_id}.{token}",
        "Content-Type": "application/json",
    }
    payload = {"msg_type": 0, "content": content}

    print(f"[QQ发送] 开始: type={msg_type}, chat_id={chat_id}, url={url}")
    print(f"[QQ发送] Authorization: QQBot {app_id[:6]}...{token[:10]}...")
    print(f"[QQ发送] Payload: {json.dumps(payload, ensure_ascii=False)[:200]}")

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"[QQ发送] 响应: status={resp.status_code}")
        print(f"[QQ发送] 响应体: {resp.text[:500]}")

        if resp.status_code in (200, 204):
            print(f"[QQ发送] 成功!")
            return True, "发送成功"

        try:
            err = resp.json()
            msg = err.get("message", err.get("msg", resp.text[:200]))
            code = err.get("code", resp.status_code)
            print(f"[QQ发送] 错误码: {code}, 消息: {msg}")
        except Exception:
            msg = resp.text[:200]
            print(f"[QQ发送] 解析响应失败")
        return False, f"({resp.status_code}) {msg}"
    except requests.exceptions.Timeout:
        print(f"[QQ发送] 超时")
        return False, "请求超时"
    except requests.exceptions.ConnectionError as e:
        print(f"[QQ发送] 连接失败: {e}")
        return False, f"连接失败: {e}"
    except Exception as e:
        print(f"[QQ发送] 异常: {e}")
        return False, str(e)

def push_wechat(title, content):
    cfg = load_config()
    webhook = cfg.get("push_channels", {}).get("wechat_webhook", "")
    if not webhook:
        print("[微信推送] 未配置")
        return False, "微信推送未配置"
    try:
        payload = {"msgtype": "markdown", "markdown": {"content": f"### {title}\n{content}"}}
        print(f"[微信推送] 发送中...")
        resp = requests.post(webhook, json=payload, timeout=10)
        result = resp.json()
        print(f"[微信推送] 响应: {result}")
        if result.get("errcode") == 0:
            return True, "推送成功"
        return False, result.get("errmsg", "推送失败")
    except Exception as e:
        print(f"[微信推送] 异常: {e}")
        return False, str(e)

def push_feishu(title, content):
    cfg = load_config()
    webhook = cfg.get("push_channels", {}).get("feishu_webhook", "")
    if not webhook:
        print("[飞书推送] 未配置")
        return False, "飞书推送未配置"
    try:
        payload = {
            "msg_type": "interactive",
            "card": {"header": {"title": {"tag": "plain_text", "content": title}}, "elements": [{"tag": "markdown", "content": content}]},
        }
        print(f"[飞书推送] 发送中...")
        resp = requests.post(webhook, json=payload, timeout=10)
        result = resp.json()
        print(f"[飞书推送] 响应: {result}")
        if result.get("code") == 0:
            return True, "推送成功"
        return False, result.get("msg", "推送失败")
    except Exception as e:
        print(f"[飞书推送] 异常: {e}")
        return False, str(e)

def push_qq(title, content):
    """推送消息到QQ"""
    print(f"\n[QQ推送] ========== 开始推送 ==========")
    print(f"[QQ推送] 标题: {title}")

    cfg = load_config()
    qq = cfg.get("push_channels", {}).get("qq_bot", {})
    app_id = qq.get("app_id", "").strip()
    token = qq.get("token", "").strip()

    print(f"[QQ推送] AppID: {app_id[:6]}... (长度={len(app_id)})")
    print(f"[QQ推送] Token: {token[:10]}... (长度={len(token)})")

    if not app_id or not token:
        print(f"[QQ推送] 失败: AppID或Token为空")
        return False, "QQ未配置(需AppID+Token)"

    plain = re.sub(r'\*\*(.+?)\*\*', r'\1', content)
    plain = re.sub(r'^###?\s+', '', plain, flags=re.MULTILINE)
    plain = f"【{title}】\n{plain}"

    user_id = qq.get("user_id", "").strip()
    channel_id = qq.get("channel_id", "").strip()

    print(f"[QQ推送] user_id: '{user_id}' (长度={len(user_id)})")
    print(f"[QQ推送] channel_id: '{channel_id}' (长度={len(channel_id)})")
    print(f"[QQ推送] 消息内容: {plain[:100]}...")

    if not user_id and not channel_id:
        print(f"[QQ推送] 失败: user_id和channel_id都为空!")
        print(f"[QQ推送] 请先在QQ上给机器人发一条消息以自动获取ID")
        return False, "QQ推送需要用户ID或频道ID(请先私聊机器人)"

    if user_id:
        print(f"[QQ推送] 尝试私聊推送 to user_id={user_id}")
        ok, msg = qq_send_message(app_id, token, user_id, "c2c", plain)
        print(f"[QQ推送] 私聊结果: ok={ok}, msg={msg}")
        if ok:
            print(f"[QQ推送] ========== 推送成功 ==========")
            return True, msg

    if channel_id:
        print(f"[QQ推送] 尝试频道推送 to channel_id={channel_id}")
        ok, msg = qq_send_message(app_id, token, channel_id, "channel", plain)
        print(f"[QQ推送] 频道结果: ok={ok}, msg={msg}")
        if ok:
            print(f"[QQ推送] ========== 推送成功 ==========")
            return True, msg

    print(f"[QQ推送] ========== 推送失败 ==========")
    return False, "QQ推送失败"

def push_all(title, content):
    cfg = load_config()
    channels = cfg.get("push_channels", {})
    results = {}
    if channels.get("wechat_webhook"):
        results["微信"] = push_wechat(title, content)
    if channels.get("feishu_webhook"):
        results["飞书"] = push_feishu(title, content)
    qq = channels.get("qq_bot", {})
    if qq.get("app_id") and qq.get("token"):
        results["QQ"] = push_qq(title, content)
    for ch, (ok, msg) in results.items():
        if not ok:
            print(f"[Push] {ch} failed: {msg}")
    return results

def build_price_alert_content(price, low, high):
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
