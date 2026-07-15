import asyncio
import botpy
from botpy import logging
from botpy.types.message import Message
from .config import load_config, save_config
from .gold_price import get_current_price
from .chat import parse_chat_command
from .notifier import _qq_send_message, _strip_markdown, build_pnl_content
from .models import get_latest_price

_logger = logging.get_logger()

class GoldBotClient(botpy.Client):
    async def on_ready(self):
        _logger.info(f"[QQBot] 机器人已上线: {self.robot.name}")

    async def on_at_message_create(self, message: Message):
        await self._handle(message)

    async def on_dms_create(self, message: Message):
        await self._handle(message)

    async def _handle(self, message: Message):
        content = message.content.strip()
        if not content:
            return

        guild_id = getattr(message, "guild_id", "")
        channel_id = getattr(message, "channel_id", "")
        user_id = getattr(message, "author", {}).get("id", "")
        user_name = getattr(message, "author", {}).get("username", "")

        _logger.info(f"[QQBot] 收到消息: {content} (from {user_name})")

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

        plain = _strip_markdown(response)

        try:
            if channel_id:
                await self.api.post_message(channel_id=channel_id, content=plain)
            elif user_id:
                await self.api.post_dms(user_id=user_id, content=plain)
        except Exception as e:
            _logger.error(f"[QQBot] 回复失败: {e}")

_bot_thread = None
_bot_loop = None
_bot_client = None

def _run_bot():
    global _bot_client
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except ImportError:
        pass

    cfg = load_config()
    qq = cfg.get("push_channels", {}).get("qq_bot", {})
    app_id = qq.get("app_id", "").strip()
    token = qq.get("token", "").strip()

    if not app_id or not token:
        _logger.warning("[QQBot] AppID或Token未配置")
        return

    intents = botpy.Intents(
        public_guild_messages=True,
        direct_message=True,
    )
    _bot_client = GoldBotClient(intents=intents)
    _bot_client.run(appid=app_id, token=token)

def start_bot():
    global _bot_thread
    if _bot_thread and _bot_thread.is_alive():
        return
    import threading
    _bot_thread = threading.Thread(target=_run_bot, daemon=True)
    _bot_thread.start()
    _logger.info("[QQBot] 启动线程已创建")

def stop_bot():
    if _bot_client:
        try:
            _bot_client.close()
        except Exception:
            pass
