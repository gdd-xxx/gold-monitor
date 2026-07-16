import re, json
from .config import load_config, save_config
from .gold_price import get_current_price
from .chat import parse_chat_command
from .notifier import qq_send_message, build_pnl_content
from .models import get_latest_price

def handle_qq_message(data):
    """处理QQ推送过来的消息"""
    content = data.get("content", "").strip()
    if not content:
        return

    content = re.sub(r'<@!?\d+>', '', content).strip()
    if not content:
        return

    user_id = data.get("author", {}).get("id", "") or data.get("user_id", "")
    channel_id = data.get("channel_id", "")
    msg_id = data.get("id", "")

    print(f"[QQ] 收到消息: {content} (uid={user_id}, ch={channel_id})")

    cfg = load_config()
    qq = cfg.setdefault("push_channels", {}).setdefault("qq_bot", {})
    updated = False
    if user_id and not qq.get("user_id"):
        qq["user_id"] = user_id
        updated = True
        print(f"[QQ] 自动记录用户ID: {user_id}")
    if channel_id and not qq.get("channel_id"):
        qq["channel_id"] = channel_id
        updated = True
        print(f"[QQ] 自动记录频道ID: {channel_id}")
    if updated:
        save_config(cfg)

    handled, response = parse_chat_command(content)
    if not handled:
        return

    if response == "__QUERY_PRICE__":
        price, source = get_current_price()
        response = f"当前金价：{price}元/克"
    elif response == "__QUERY_PNL__":
        cfg = load_config()
        current = get_latest_price()
        cp = current["price"] if current else 0
        response = build_pnl_content(cfg.get("my_purchases", []), cp)

    plain = re.sub(r'\*\*(.+?)\*\*', r'\1', response)

    app_id = qq.get("app_id", "").strip()
    token = qq.get("token", "").strip()
    if app_id and token:
        if channel_id:
            qq_send_message(app_id, token, channel_id, "channel", plain)
        elif user_id:
            qq_send_message(app_id, token, user_id, "c2c", plain)
