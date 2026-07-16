import atexit, subprocess, threading
from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import datetime

from .models import init_db, insert_price, get_today_prices, get_daily_prices_for_chart, get_latest_price
from .gold_price import get_current_price, calculate_pnl
from .config import load_config, save_config
from .notifier import push_all, push_qq, build_price_alert_content, build_pnl_content
from .chat import parse_chat_command
from .version import VERSION, GITHUB_REPO, IMAGE_NAME

app = Flask(__name__)

scheduler = BackgroundScheduler()
last_alert_price = {"price": None}
_update_status = {"checking": False, "available": False, "latest": "", "updating": False, "message": ""}

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

@app.route("/api/version")
def api_version():
    return jsonify({
        "current": VERSION,
        "latest": _update_status.get("latest", ""),
        "available": _update_status.get("available", False),
        "updating": _update_status.get("updating", False),
        "message": _update_status.get("message", ""),
    })

@app.route("/api/update/check", methods=["POST"])
def api_update_check():
    if _update_status["checking"]:
        return jsonify({"ok": False, "msg": "正在检查..."})
    _update_status["checking"] = True
    _update_status["message"] = "检查更新中..."
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            timeout=10,
            headers={"Accept": "application/vnd.github.v3+json"}
        )
        if resp.status_code == 200:
            data = resp.json()
            tag = data.get("tag_name", "").lstrip("v")
            _update_status["latest"] = tag
            _update_status["available"] = tag != VERSION
            _update_status["message"] = f"最新版本: {tag}" if tag != VERSION else "已是最新版本"
        else:
            _update_status["message"] = "检查失败"
    except Exception as e:
        _update_status["message"] = f"检查出错: {e}"
    finally:
        _update_status["checking"] = False
    return jsonify({"ok": True, "msg": _update_status["message"]})

@app.route("/api/update/apply", methods=["POST"])
def api_update_apply():
    if _update_status["updating"]:
        return jsonify({"ok": False, "msg": "更新中..."})
    if not _update_status["available"]:
        return jsonify({"ok": False, "msg": "没有可用更新"})

    _update_status["updating"] = True
    _update_status["message"] = "正在拉取新镜像..."

    def do_update():
        try:
            tag = _update_status["latest"] or "latest"
            full_image = f"{IMAGE_NAME}:{tag}"

            print(f"[Update] 拉取镜像: {full_image}")
            result = subprocess.run(
                ["docker", "pull", full_image],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                _update_status["message"] = f"拉取失败: {result.stderr[:200]}"
                _update_status["updating"] = False
                return

            _update_status["message"] = "重启容器中..."
            print("[Update] 重启容器...")

            container_name = os.environ.get("HOSTNAME", "gold-monitor")
            subprocess.run(["docker", "stop", container_name], timeout=30)
            subprocess.run(["docker", "rm", container_name], timeout=30)

            cfg = load_config()
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

            run_cmd = [
                "docker", "run", "-d",
                "--name", container_name,
                "-p", "5000:5000",
                "-v", f"{data_dir}:/app/data",
                "--restart", "unless-stopped",
                full_image
            ]
            subprocess.run(run_cmd, timeout=60)

            _update_status["message"] = "更新完成，重启中..."
            print("[Update] 更新完成")

        except Exception as e:
            _update_status["message"] = f"更新失败: {e}"
            print(f"[Update] Error: {e}")
        finally:
            _update_status["updating"] = False

    threading.Thread(target=do_update, daemon=True).start()
    return jsonify({"ok": True, "msg": "开始更新..."})

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
                "weight": float(data.get("weight", 0)),
                "amount": float(data.get("amount", 0)),
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
            "weight": p.get("weight", 0),
            "amount": p.get("amount", 0),
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
        print(f"[配置] 推送设置已保存")

        if "qq_bot" in data:
            try:
                from .qqbot import qqbot
                qqbot.restart()
                print(f"[配置] QQBot已重启")
            except Exception as e:
                print(f"[配置] QQBot重启失败: {e}")

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
    print(f"\n[推送测试] 渠道: {channel}")

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
        print(f"[推送测试] 未知渠道: {channel}")
        return jsonify({"ok": False, "msg": "未知渠道"})

    print(f"[推送测试] 结果: ok={ok}, msg={msg}")
    return jsonify({"ok": ok, "msg": msg})

def _shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)

@app.route("/webhook/qq", methods=["POST"])
def qq_webhook():
    print(f"\n[QQ Webhook] ========== 收到Webhook回调 ==========")
    print(f"[QQ Webhook] Method: {request.method}")
    print(f"[QQ Webhook] Headers: {dict(request.headers)}")
    data = request.json
    print(f"[QQ Webhook] Body: {json.dumps(data, ensure_ascii=False)[:2000]}")

    if not data:
        print(f"[QQ Webhook] Body为空")
        return jsonify({})

    op = data.get("op")
    print(f"[QQ Webhook] op: {op}")

    if op == 0:
        print(f"[QQ Webhook] 回复心跳")
        return jsonify({"op": 1})

    print(f"[QQ Webhook] 转发给处理器...")
    try:
        from .qqbot import handle_qq_message
        handle_qq_message(data)
    except Exception as e:
        print(f"[QQ Webhook] 处理异常: {e}")
        import traceback
        traceback.print_exc()

    print(f"[QQ Webhook] ========== 处理完成 ==========")
    return jsonify({})

@app.route("/api/config/qq", methods=["GET", "POST"])
def api_config_qq():
    cfg = load_config()
    qq = cfg.get("push_channels", {}).get("qq_bot", {})
    if request.method == "POST":
        data = request.json
        qq.update(data)
        cfg.setdefault("push_channels", {})["qq_bot"] = qq
        save_config(cfg)
        print(f"[QQ配置] 已保存: {json.dumps(qq, ensure_ascii=False)}")
        return jsonify({"ok": True})
    return jsonify(qq)

def create_app():
    init_db()
    cfg = load_config()
    interval = cfg.get("fetch_interval", 60)
    scheduler.add_job(scheduled_fetch, "interval", seconds=interval, id="fetch_gold")
    scheduler.start()
    scheduled_fetch()
    atexit.register(_shutdown_scheduler)

    try:
        from .qqbot import start_bot
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        if qq.get("app_id") and qq.get("token"):
            start_bot()
            print("[App] QQBot已启动")
    except Exception as e:
        print(f"[App] QQBot启动失败: {e}")

    return app

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=False)
