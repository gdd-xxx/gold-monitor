import botpy
from botpy import logging
from botpy.types.message import Message
from .config import load_config, save_config
from .gold_price import get_current_price
from .chat import parse_chat_command
from .notifier import _strip_markdown, build_pnl_content
from .models import get_latest_price

_logger = logging.get_logger()

class GoldBotClient(botpy.Client):
    async def on_ready(self):
        _logger.info(f"[QQBot] 机器人已上线: {self.robot.name}")

    async def on_at_message_create(self, message: Message):
        _logger.info(f"[QQBot] on_at_message_create: {message.content}")
        await self._handle(message, "channel")

    async def on_message_create(self, message: Message):
        _logger.info(f"[QQBot] on_message_create: {message.content}")
        await self._handle(message, "channel")

    async def on_dms_create(self, message: Message):
        _logger.info(f"[QQBot] on_dms_create: {message.content}")
        await self._handle(message, "dms")

    async def on_c2c_message_create(self, message: Message):
        _logger.info(f"[QQBot] on_c2c_message_create: {message.content}")
        await self._handle(message, "c2c")

    async def on_group_at_message_create(self, message: Message):
        _logger.info(f"[QQBot] on_group_at_message_create: {message.content}")
        await self._handle(message, "group")

    async def _handle(self, message: Message, msg_type: str):
        content = message.content.strip()
        if not content:
            return

        channel_id = getattr(message, "channel_id", "") or ""
        user_id = getattr(message, "author", {}).get("id", "") or ""
        user_name = getattr(message, "author", {}).get("username", "") or ""
        msg_id = getattr(message, "id", "") or ""
        guild_id = getattr(message, "guild_id", "") or ""
        group_id = getattr(message, "group_openid", "") or ""

        _logger.info(f"[QQBot] msg_type={msg_type}, guild={guild_id}, channel={channel_id}, group={group_id}, user={user_name}({user_id})")

        cfg = load_config()
        qq = cfg.setdefault("push_channels", {}).setdefault("qq_bot", {})
        updated = False
        if channel_id and not qq.get("channel_id"):
            qq["channel_id"] = channel_id
            updated = True
            _logger.info(f"[QQBot] 自动记录频道ID: {channel_id}")
        if user_id and not qq.get("user_id"):
            qq["user_id"] = user_id
            updated = True
            _logger.info(f"[QQBot] 自动记录用户ID: {user_id}")
        if group_id and not qq.get("group_id"):
            qq["group_id"] = group_id
            updated = True
            _logger.info(f"[QQBot] 自动记录群ID: {group_id}")
        if updated:
            save_config(cfg)

        handled, response = parse_chat_command(content)
        if not handled:
            _logger.info(f"[QQBot] 命令未识别: {content}")
            return

        if response == "__QUERY_PRICE__":
            price, source = get_current_price()
            response = f"当前金价：{price}元/克"
        elif response == "__QUERY_PNL__":
            cfg = load_config()
            current = get_latest_price()
            cp = current["price"] if current else 0
            response = build_pnl_content(cfg.get("my_purchases", []), cp)

        plain = _strip_markdown(response)

        try:
            if msg_type == "channel" and channel_id:
                await self.api.post_message(channel_id=channel_id, content=plain, msg_id=msg_id)
            elif msg_type == "group" and group_id:
                await self.api.post_group_message(group_openid=group_id, content=plain, msg_id=msg_id)
            elif user_id:
                if msg_type == "dms":
                    await self.api.post_dms(user_id=user_id, content=plain, msg_id=msg_id)
                else:
                    await self.api.post_c2c_message(user_id=user_id, content=plain, msg_id=msg_id)
            _logger.info(f"[QQBot] 回复成功: {plain[:50]}")
        except Exception as e:
            _logger.error(f"[QQBot] 回复失败: {e}")

_bot_thread = None
_bot_client = None

def _run_bot():
    global _bot_client
    import asyncio

    cfg = load_config()
    qq = cfg.get("push_channels", {}).get("qq_bot", {})
    app_id = qq.get("app_id", "").strip()
    token = qq.get("token", "").strip()

    if not app_id or not token:
        _logger.warning("[QQBot] AppID或Token未配置")
        return

    _logger.info(f"[QQBot] 启动中... appid={app_id[:6]}...")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    intents = botpy.Intents(
        public_guild_messages=True,
        direct_message=True,
        guild_messages=True,
        group_messages=True,
    )
    _bot_client = GoldBotClient(intents=intents)

    try:
        _bot_client.run(appid=app_id, secret=token)
    except Exception as e:
        _logger.error(f"[QQBot] 运行异常: {e}")

def start_bot():
    global _bot_thread
    if _bot_thread and _bot_thread.is_alive():
        _logger.info("[QQBot] 已在运行")
        return
    import threading
    _bot_thread = threading.Thread(target=_run_bot, daemon=True, name="qqbot")
    _bot_thread.start()
    _logger.info("[QQBot] 线程已启动")

def stop_bot():
    if _bot_client:
        try:
            _bot_client.close()
        except Exception:
            pass
