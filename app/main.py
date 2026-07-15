import atexit, hashlib, hmac
from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import datetime

from .models import init_db, insert_price, get_today_prices, get_daily_prices_for_chart, get_latest_price
from .gold_price import get_current_price, calculate_pnl
from .config import load_config, save_config
from .notifier import push_all, push_qq, build_price_alert_content, build_pnl_content
from .chat import parse_chat_command

app = Flask(__name__)

scheduler = BackgroundScheduler()
last_alert_price = {"price": None}

def scheduled_fetch():
    try:
        price, source = get_current_price()
        if price:
            now = datetime.datetime.now()
            insert_price(now.date().isoformat(), now.strftime("%H:%M:%S"), price, source)
            cfg = load_config()
            if cfg.get("alert_enabled"):
                low = cfg.get("alert_threshold_low", 0)
                high = cfg.get("alert_threshold_high", 9999)
                if price < low or price > high:
                    prev = last_alert_price.get("price")
                    if prev is None or (prev < low and price >= low) or (prev > high and price <= high) or (price < low and prev >= low) or (price > high and prev <= high):
                        content = build_price_alert_content(price, low, high)
                        results = push_all("金价预警", content)
                        if results:
                            for ch, (ok, msg) in results.items():
                                print(f"[Alert] {ch}: {'OK' if ok else msg}")
                        last_alert_price["price"] = price
            last_alert_price["price"] = price
            print(f"[{now.strftime('%H:%M:%S')}] Price: {price} ({source})")
    except Exception as e:
        print(f"[Scheduler] Error: {e}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/price")
def api_price():
    price, source = get_current_price()
    return jsonify({"price": price, "source": source, "time": datetime.datetime.now().isoformat()})

@app.route("/api/today")
def api_today():
    return jsonify(get_today_prices())

@app.route("/api/chart")
def api_chart():
    days = request.args.get("days", 30, type=int)
    return jsonify(get_daily_prices_for_chart(days))

@app.route("/api/pnl", methods=["GET", "POST"])
def api_pnl():
    cfg = load_config()
    if request.method == "POST":
        data = request.json
        if "delete_index" in data:
            idx = data["delete_index"]
            if 0 <= idx < len(cfg.get("my_purchases", [])):
                cfg["my_purchases"].pop(idx)
                save_config(cfg)
                return jsonify({"ok": True})
        else:
            purchase = {
                "price": float(data["price"]),
                "fee": float(data.get("fee", 0)),
                "note": data.get("note", ""),
            }
            cfg.setdefault("my_purchases", []).append(purchase)
            save_config(cfg)
            return jsonify({"ok": True})

    current = get_latest_price()
    current_price = current["price"] if current else 0
    purchases = cfg.get("my_purchases", [])
    results = []
    for p in purchases:
        pnl, pct = calculate_pnl(p["price"], current_price, p.get("fee", 0))
        results.append({
            "purchase_price": p["price"],
            "fee": p.get("fee", 0),
            "note": p.get("note", ""),
            "pnl": pnl,
            "pnl_percent": pct,
            "current_price": current_price,
        })
    return jsonify({"current_price": current_price, "purchases": results})

@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    cfg = load_config()
    if request.method == "POST":
        data = request.json
        for k, v in data.items():
            if k in cfg:
                if isinstance(cfg[k], dict) and isinstance(v, dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        save_config(cfg)
        return jsonify({"ok": True})
    safe = {k: v for k, v in cfg.items() if k not in ("push_channels", "my_purchases")}
    return jsonify(safe)

@app.route("/api/purchases", methods=["GET"])
def api_purchases():
    cfg = load_config()
    return jsonify(cfg.get("my_purchases", []))

@app.route("/api/config/push", methods=["GET", "POST"])
def api_config_push():
    cfg = load_config()
    if request.method == "POST":
        data = request.json
        cfg.setdefault("push_channels", {}).update(data)
        save_config(cfg)
        return jsonify({"ok": True})
    return jsonify(cfg.get("push_channels", {}))

@app.route("/api/config/interval", methods=["POST"])
def api_config_interval():
    data = request.json
    interval = max(30, int(data.get("interval", 60)))
    cfg = load_config()
    cfg["fetch_interval"] = interval
    save_config(cfg)
    try:
        scheduler.reschedule_job("fetch_gold", trigger="interval", seconds=interval)
    except Exception:
        pass
    return jsonify({"ok": True, "interval": interval})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json
    text = data.get("message", "")
    handled, response = parse_chat_command(text)
    if not handled:
        return jsonify({"handled": False, "response": "无法识别的命令，输入'帮助'查看可用命令"})
    if response == "__QUERY_PRICE__":
        price, source = get_current_price()
        source_map = {"jdjygold": "京东黄金", "czbank": "浙商银行", "custom": "自定义"}
        return jsonify({"handled": True, "response": f"当前金价：{price}元/克（{source_map.get(source, source)}）"})
    if response == "__QUERY_PNL__":
        cfg = load_config()
        current = get_latest_price()
        cp = current["price"] if current else 0
        content = build_pnl_content(cfg.get("my_purchases", []), cp)
        return jsonify({"handled": True, "response": content})
    return jsonify({"handled": True, "response": response})

@app.route("/api/push/test", methods=["POST"])
def api_push_test():
    data = request.json
    channel = data.get("channel", "wechat")
    title = "测试推送"
    content = f"这是一条测试消息\n时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    from .notifier import push_wechat, push_feishu, push_qq
    if channel == "wechat":
        ok, msg = push_wechat(title, content)
    elif channel == "feishu":
        ok, msg = push_feishu(title, content)
    elif channel == "qq":
        ok, msg = push_qq(title, content)
    else:
        return jsonify({"ok": False, "msg": "未知渠道"})
    return jsonify({"ok": ok, "msg": msg})

@app.route("/webhook/qq", methods=["POST"])
def qq_webhook():
    data = request.json
    print(f"[QQ Webhook] {data}")

    if data.get("op") == 0:
        return jsonify({"op": 1})

    if data.get("type") == 0:
        msg_type = data.get("message_type", "")
        user_id = data.get("user_id", "")
        group_id = data.get("group_id", "")
        content = data.get("content", "").strip()

        handled, response = parse_chat_command(content)
        if not handled:
            return jsonify({})

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
        app_id = qq.get("app_id", "")
        app_secret = qq.get("app_secret", "")

        if app_id and app_secret:
            from .notifier import _get_qq_access_token
            access_token = _get_qq_access_token(app_id, app_secret)
            if access_token:
                from .notifier import _qq_send_message
                chat_id = group_id if group_id else user_id
                chat_type = "group" if group_id else "c2c"
                _qq_send_message(app_id, access_token, chat_id, chat_type, response)

    return jsonify({})

def _shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)

def create_app():
    init_db()
    cfg = load_config()
    interval = cfg.get("fetch_interval", 60)
    scheduler.add_job(scheduled_fetch, "interval", seconds=interval, id="fetch_gold")
    scheduler.start()
    scheduled_fetch()
    atexit.register(_shutdown_scheduler)
    return app

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=False)
