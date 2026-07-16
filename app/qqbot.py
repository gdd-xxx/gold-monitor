import re, json
from .config import load_config, save_config
from .gold_price import get_current_price
from .chat import parse_chat_command
from .notifier import qq_send_message, build_pnl_content
from .models import get_latest_price

def handle_qq_message(data):
    """处理QQ推送过来的消息"""
    print(f"\n[QQ收到] ========== 收到消息 ==========")
    print(f"[QQ收到] 原始数据: {json.dumps(data, ensure_ascii=False)[:1000]}")

    content = data.get("content", "").strip()
    print(f"[QQ收到] content: '{content}'")

    if not content:
        print(f"[QQ收到] content为空，忽略")
        return

    content = re.sub(r'<@!?\d+>', '', content).strip()
    print(f"[QQ收到] 清理后: '{content}'")

    if not content:
        print(f"[QQ收到] 清理后为空，忽略")
        return

    user_id = data.get("author", {}).get("id", "") or data.get("user_id", "")
    channel_id = data.get("channel_id", "")
    msg_id = data.get("id", "")
    guild_id = data.get("guild_id", "")
    author = data.get("author", {})
    username = author.get("username", "")

    print(f"[QQ收到] user_id: {user_id}")
    print(f"[QQ收到] username: {username}")
    print(f"[QQ收到] channel_id: {channel_id}")
    print(f"[QQ收到] guild_id: {guild_id}")
    print(f"[QQ收到] msg_id: {msg_id}")

    cfg = load_config()
    qq = cfg.setdefault("push_channels", {}).setdefault("qq_bot", {})
    updated = False
    if user_id and not qq.get("user_id"):
        qq["user_id"] = user_id
        updated = True
        print(f"[QQ收到] 自动记录用户ID: {user_id}")
    if channel_id and not qq.get("channel_id"):
        qq["channel_id"] = channel_id
        updated = True
        print(f"[QQ收到] 自动记录频道ID: {channel_id}")
    if updated:
        save_config(cfg)
        print(f"[QQ收到] 配置已保存")

    print(f"[QQ收到] 解析命令: '{content}'")
    handled, response = parse_chat_command(content)
    print(f"[QQ收到] handled={handled}, response={response[:100] if response else 'None'}")

    if not handled:
        print(f"[QQ收到] 命令未识别，不回复")
        return

    if response == "__QUERY_PRICE__":
        price, source = get_current_price()
        response = f"当前金价：{price}元/克"
        print(f"[QQ收到] 查询金价: {response}")
    elif response == "__QUERY_PNL__":
        cfg = load_config()
        current = get_latest_price()
        cp = current["price"] if current else 0
        response = build_pnl_content(cfg.get("my_purchases", []), cp)
        print(f"[QQ收到] 查询盈亏")

    plain = re.sub(r'\*\*(.+?)\*\*', r'\1', response)
    print(f"[QQ收到] 回复内容: {plain[:200]}")

    app_id = qq.get("app_id", "").strip()
    token = qq.get("token", "").strip()
    print(f"[QQ收到] AppID: {app_id[:6] if app_id else '空'}...")
    print(f"[QQ收到] Token: {token[:10] if token else '空'}...")

    if not app_id or not token:
        print(f"[QQ收到] AppID或Token为空，无法回复")
        return

    if channel_id:
        print(f"[QQ收到] 回复到频道: {channel_id}")
        ok, msg = qq_send_message(app_id, token, channel_id, "channel", plain)
        print(f"[QQ收到] 回复结果: ok={ok}, msg={msg}")
    elif user_id:
        print(f"[QQ收到] 回复到私聊: {user_id}")
        ok, msg = qq_send_message(app_id, token, user_id, "c2c", plain)
        print(f"[QQ收到] 回复结果: ok={ok}, msg={msg}")
    else:
        print(f"[QQ收到] 无channel_id和user_id，无法回复")
