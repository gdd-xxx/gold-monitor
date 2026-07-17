import json, time, threading, re, requests
import websocket
from .config import load_config, save_config
from .gold_price import get_current_price
from .chat import parse_chat_command
from .notifier import qq_send_message, build_pnl_content
from .models import get_latest_price

WS_URL = "wss://api.sgroup.qq.com/websocket"
RECONNECT_DELAY = 5

def _get_access_token(app_id, app_secret):
    """获取QQ Bot access_token"""
    try:
        resp = requests.post("https://bots.qq.com/app/getAppAccessToken", json={
            "appId": app_id,
            "clientSecret": app_secret,
        }, timeout=10)
        data = resp.json()
        token = data.get("access_token")
        if token:
            print(f"[QQBot] access_token获取成功")
            return token
        print(f"[QQBot] access_token获取失败: {data}")
        return None
    except Exception as e:
        print(f"[QQBot] 获取token异常: {e}")
        return None

class QQBot:
    def __init__(self):
        self.ws = None
        self.running = False
        self.thread = None
        self._session_id = None
        self._seq = 0
        self._heartbeat_interval = 41
        self._stop_event = threading.Event()
        self._heartbeat_ack = True

    def start(self):
        if self.running:
            return
        cfg = load_config()
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        if not qq.get("app_id") or not qq.get("token"):
            print("[QQBot] AppID或Token未配置")
            return
        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        print("[QQBot] 启动线程")

    def restart(self):
        print("[QQBot] 重启中...")
        self.stop()
        time.sleep(2)
        self.start()

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

    def _run(self):
        while self.running and not self._stop_event.is_set():
            try:
                self._connect()
            except Exception as e:
                print(f"[QQBot] 连接异常: {e}")
            if self.running and not self._stop_event.is_set():
                print(f"[QQBot] {RECONNECT_DELAY}秒后重连...")
                self._stop_event.wait(RECONNECT_DELAY)

    def _connect(self):
        cfg = load_config()
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        app_id = qq.get("app_id", "").strip()
        app_secret = qq.get("token", "").strip()
        if not app_id or not app_secret:
            print("[QQBot] AppID或Token为空")
            return

        access_token = _get_access_token(app_id, app_secret)
        if not access_token:
            print("[QQBot] 获取access_token失败，5秒后重试")
            time.sleep(5)
            return

        print(f"[QQBot] 连接WebSocket...")

        self.ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws._app_id = app_id
        self.ws._access_token = access_token
        self._heartbeat_ack = True
        self._seq = 0
        self.ws.run_forever(ping_interval=self._heartbeat_interval, ping_timeout=10)

    def _on_open(self, ws):
        print("[QQBot] WebSocket已连接，等待Hello...")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except:
            return

        op = data.get("op")
        s = data.get("s")
        if s:
            self._seq = s

        if op == 10:
            d = data.get("d", {})
            self._heartbeat_interval = d.get("heartbeat_interval", 41000) // 1000
            print(f"[QQBot] 收到Hello, 心跳间隔: {self._heartbeat_interval}秒")
            self._start_heartbeat(ws)
            self._identify(ws)

        elif op == 11:
            self._heartbeat_ack = True

        elif op == 0:
            t = data.get("t")
            d = data.get("d", {})
            if t == "READY":
                self._session_id = d.get("session_id")
                print(f"[QQBot] 鉴权成功! session_id={self._session_id}")
            elif t in ("MESSAGE_CREATE", "AT_MESSAGE_CREATE", "DIRECT_MESSAGE_CREATE", "C2C_MESSAGE_CREATE", "GROUP_AT_MESSAGE_CREATE"):
                print(f"[QQBot] 收到消息事件: {t}")
                self._handle_message(d)

    def _on_error(self, ws, error):
        print(f"[QQBot] WebSocket错误: {error}")

    def _on_close(self, ws, close_status, close_msg):
        print(f"[QQBot] WebSocket已断开: {close_status}")

    def _start_heartbeat(self, ws):
        interval = self._heartbeat_interval
        print(f"[QQBot] 启动心跳, 间隔{interval}秒")
        def heartbeat():
            while self.running and self.ws == ws and not self._stop_event.is_set():
                try:
                    ws.send(json.dumps({"op": 1, "d": self._seq}))
                except Exception as e:
                    print(f"[QQBot] 心跳发送失败: {e}")
                    return
                self._stop_event.wait(interval)
        threading.Thread(target=heartbeat, daemon=True).start()

    def _identify(self, ws):
        app_id = ws._app_id
        access_token = ws._access_token
        payload = {
            "op": 2,
            "d": {
                "token": f"QQBot {access_token}",
                "intents": 33554945,
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
            print(f"[QQBot] Identify已发送 (appid={app_id[:6]}..., intents=33554945)")
        except Exception as e:
            print(f"[QQBot] Identify失败: {e}")

    def _handle_message(self, data):
        content = data.get("content", "").strip()
        if not content:
            return

        author = data.get("author", {})
        user_id = author.get("id", "")
        user_name = author.get("username", "")
        channel_id = data.get("channel_id", "")
        msg_id = data.get("id", "")

        print(f"[QQBot] 消息: {content} (from {user_name}, uid={user_id})")

        content = re.sub(r'<@!?\d+>', '', content).strip()
        if not content:
            return

        cfg = load_config()
        qq = cfg.setdefault("push_channels", {}).setdefault("qq_bot", {})
        updated = False
        if user_id and not qq.get("open_id"):
            qq["open_id"] = user_id
            updated = True
            print(f"[QQBot] 自动记录open_id: {user_id}")
        if channel_id and not qq.get("channel_id"):
            qq["channel_id"] = channel_id
            updated = True
            print(f"[QQBot] 自动记录频道ID: {channel_id}")
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
        elif response == "__QUERY_CHART__":
            # 发送今日走势文字版
            from .models import get_today_prices
            prices = get_today_prices()
            if prices:
                lines = ["今日金价走势：\n"]
                for p in prices[-10:]:  # 最近10条
                    lines.append(f"  {p['time']} → {p['price']}元/克")
                lines.append(f"\n共 {len(prices)} 条记录")
                response = "\n".join(lines)
            else:
                response = "今日暂无金价数据"

        plain = re.sub(r'\*\*(.+?)\*\*', r'\1', response)

        app_id = qq.get("app_id", "").strip()
        app_secret = qq.get("token", "").strip()
        if app_id and app_secret:
            access_token = _get_access_token(app_id, app_secret)
            if access_token:
                if channel_id:
                    qq_send_message(app_id, access_token, channel_id, "channel", plain)
                elif user_id:
                    qq_send_message(app_id, access_token, user_id, "c2c", plain)
            else:
                print("[QQBot] 获取access_token失败，无法回复")

qqbot = QQBot()

def start_bot():
    qqbot.start()

def stop_bot():
    qqbot.stop()
