import json, time, threading, re
import websocket
from .config import load_config
from .gold_price import get_current_price
from .chat import parse_chat_command
from .notifier import _qq_send_message, _strip_markdown, build_pnl_content
from .models import get_latest_price

WS_URL = "wss://api.sgroup.qq.com/websocket"
RECONNECT_DELAY = 5
HEARTBEAT_INTERVAL = 41

class QQBot:
    def __init__(self):
        self.ws = None
        self.thread = None
        self.running = False
        self.heartbeat_thread = None
        self.heartbeat_ack = True
        self._session_id = None
        self._seq = 0
        self._stop_event = threading.Event()

    def start(self):
        if self.running:
            return
        cfg = load_config()
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        app_id = qq.get("app_id", "").strip()
        token = qq.get("token", "").strip()
        if not app_id or not token:
            return
        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[QQBot] WebSocket连接已启动")

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _run(self):
        while self.running and not self._stop_event.is_set():
            try:
                self._connect()
            except Exception as e:
                print(f"[QQBot] 连接异常: {e}")
            if self.running and not self._stop_event.is_set():
                self._stop_event.wait(RECONNECT_DELAY)

    def _connect(self):
        cfg = load_config()
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        app_id = qq.get("app_id", "").strip()
        token = qq.get("token", "").strip()

        if not app_id or not token:
            print("[QQBot] AppID或Token未配置")
            return

        self.heartbeat_ack = True
        self._seq = 0

        self.ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws._app_id = app_id
        self.ws._token = token
        self.ws.run_forever(ping_interval=0, ping_timeout=0)

    def _on_open(self, ws):
        print("[QQBot] WebSocket已连接，等待Hello...")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except Exception:
            return

        op = data.get("op")
        s = data.get("s")
        if s:
            self._seq = s

        if op == 10:
            d = data.get("d", {})
            heartbeat_interval = d.get("heartbeat_interval", 41000) / 1000
            self._start_heartbeat(ws, heartbeat_interval)
            self._identify(ws)

        elif op == 11:
            self.heartbeat_ack = True

        elif op == 0:
            t = data.get("t")
            d = data.get("d", {})
            self._session_id = d.get("session_id", self._session_id)

            if t == "MESSAGE_CREATE" or t == "AT_MESSAGE_CREATE":
                self._handle_message(d)

    def _on_error(self, ws, error):
        print(f"[QQBot] WebSocket错误: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        print(f"[QQBot] WebSocket已断开: {close_status_code} {close_msg}")

    def _start_heartbeat(self, ws, interval):
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return

        def heartbeat():
            while self.running and self.ws == ws and not self._stop_event.is_set():
                if not self.heartbeat_ack:
                    print("[QQBot] 心跳超时，断开重连")
                    try:
                        ws.close()
                    except Exception:
                        pass
                    return
                self.heartbeat_ack = False
                try:
                    ws.send(json.dumps({"op": 1, "d": self._seq}))
                except Exception:
                    return
                self._stop_event.wait(interval)

        self.heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        self.heartbeat_thread.start()

    def _identify(self, ws):
        payload = {
            "op": 2,
            "d": {
                "token": ws._token,
                "intents": 513,
                "shard": [0, 1],
                "properties": {
                    "os": "linux",
                    "browser": "python",
                    "device": "gold-monitor"
                }
            }
        }
        try:
            ws.send(json.dumps(payload))
            print("[QQBot] Identify已发送")
        except Exception as e:
            print(f"[QQBot] Identify失败: {e}")

    def _handle_message(self, data):
        content = data.get("content", "").strip()
        author = data.get("author", {})
        user_id = author.get("id", "")
        user_name = author.get("username", "")
        guild_id = data.get("guild_id", "")
        channel_id = data.get("channel_id", "")
        group_id = data.get("group_id", "")

        if not content:
            return

        content = re.sub(r'<@!?\d+>', '', content).strip()
        if not content:
            return

        print(f"[QQBot] 收到消息: {content} (from {user_name})")

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

        cfg = load_config()
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        app_id = qq.get("app_id", "").strip()
        token = qq.get("token", "").strip()

        if not app_id or not token:
            return

        plain = _strip_markdown(response)

        if group_id:
            _qq_send_message(app_id, token, group_id, "group", plain)
        elif channel_id:
            _qq_send_message(app_id, token, channel_id, "channel", plain)
        elif user_id:
            _qq_send_message(app_id, token, user_id, "c2c", plain)

qqbot = QQBot()
