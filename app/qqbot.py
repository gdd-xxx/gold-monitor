import json, time, threading
import websocket
from .config import load_config
from .gold_price import get_current_price
from .chat import parse_chat_command
from .notifier import _get_qq_access_token, _qq_send_message, _strip_markdown, build_pnl_content
from .models import get_latest_price

WS_URL = "wss://api.sgroup.qq.com/webmark"
RECONNECT_DELAY = 5
HEARTBEAT_INTERVAL = 30

class QQBot:
    def __init__(self):
        self.ws = None
        self.thread = None
        self.running = False
        self.heartbeat_thread = None
        self.heartbeat_ack = True
        self._session_id = None
        self._seq = None

    def start(self):
        if self.running:
            return
        cfg = load_config()
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        app_id = qq.get("app_id", "").strip()
        app_secret = qq.get("app_secret", "").strip()
        if not app_id or not app_secret:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[QQBot] WebSocket连接已启动")

    def stop(self):
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _run(self):
        while self.running:
            try:
                self._connect()
            except Exception as e:
                print(f"[QQBot] 连接异常: {e}")
            if self.running:
                time.sleep(RECONNECT_DELAY)

    def _connect(self):
        cfg = load_config()
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        app_id = qq.get("app_id", "").strip()
        app_secret = qq.get("app_secret", "").strip()

        access_token = _get_qq_access_token(app_id, app_secret)
        if not access_token:
            print("[QQBot] Token获取失败，5秒后重试")
            return

        self.heartbeat_ack = True
        self._seq = None

        self.ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.app_id = app_id
        self.ws.access_token = access_token
        self.ws.run_forever(ping_interval=HEARTBEAT_INTERVAL, ping_timeout=10)

    def _on_open(self, ws):
        print("[QQBot] WebSocket已连接，等待握手...")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except Exception:
            return

        op = data.get("op")
        self._seq = data.get("s") or self._seq

        if op == 10:
            heartbeat_interval = data.get("d", {}).get("heartbeat_interval", HEARTBEAT_INTERVAL) / 1000
            self._start_heartbeat(ws, heartbeat_interval)
            self._handshake(ws)

        elif op == 11:
            self.heartbeat_ack = True

        elif op == 0:
            t = data.get("t")
            d = data.get("d", {})
            if t == "MESSAGE_CREATE" or t == "AT_MESSAGE_CREATE":
                self._handle_message(ws, d)

    def _on_error(self, ws, error):
        print(f"[QQBot] WebSocket错误: {error}")

    def _on_close(self, ws, close_status, close_msg):
        print(f"[QQBot] WebSocket已断开: {close_status} {close_msg}")

    def _start_heartbeat(self, ws, interval):
        def heartbeat():
            while self.running and self.ws == ws:
                if not self.heartbeat_ack:
                    print("[QQBot] 心跳超时，断开重连")
                    try:
                        ws.close()
                    except Exception:
                        pass
                    return
                self.heartbeat_ack = False
                try:
                    ws.send(json.dumps({"op": 1}))
                except Exception:
                    return
                time.sleep(interval)

        if self.heartbeat_thread:
            self.heartbeat_thread.daemon = True
        self.heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        self.heartbeat_thread.start()

    def _handshake(self, ws):
        cfg = load_config()
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        app_id = qq.get("app_id", "").strip()
        payload = {
            "op": 2,
            "d": {
                "token": f"QQBot {app_id}.{ws.access_token}",
                "intents": 513,
            }
        }
        if self._session_id:
            payload["d"]["session_id"] = self._session_id
        try:
            ws.send(json.dumps(payload))
            print("[QQBot] 握手已发送")
        except Exception as e:
            print(f"[QQBot] 握手失败: {e}")

    def _handle_message(self, ws, data):
        msg_type = data.get("message_type", "")
        content = data.get("content", "").strip()
        guild_id = data.get("guild_id", "")
        channel_id = data.get("channel_id", "")
        group_id = data.get("group_id", "")
        user_id = data.get("author", {}).get("id", "")

        if not content:
            return

        print(f"[QQBot] 收到消息: {content}")

        handled, response = parse_chat_command(content)
        if not handled:
            return

        if response == "__QUERY_PRICE__":
            price, source = get_current_price()
            response = f"当前金价：{price}元/克"
        elif response == "__QUERY_PNL__":
            from .config import load_config as _load
            cfg = _load()
            current = get_latest_price()
            cp = current["price"] if current else 0
            response = build_pnl_content(cfg.get("my_purchases", []), cp)

        cfg = load_config()
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        app_id = qq.get("app_id", "").strip()
        app_secret = qq.get("app_secret", "").strip()
        access_token = _get_qq_access_token(app_id, app_secret)

        if not access_token:
            return

        plain = _strip_markdown(response)

        if group_id:
            _qq_send_message(app_id, access_token, group_id, "group", plain)
        elif channel_id:
            _qq_send_message(app_id, access_token, channel_id, "channel", plain)
        elif user_id:
            _qq_send_message(app_id, access_token, user_id, "c2c", plain)

qqbot = QQBot()
