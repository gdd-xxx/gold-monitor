import atexit, json, os, subprocess, threading
from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import datetime

from .models import init_db, insert_price, get_today_prices, get_daily_prices_for_chart, get_latest_price
from .models import insert_market_price, get_latest_market_price, get_today_market_prices, get_all_latest_market_prices
from .gold_price import get_current_price, calculate_pnl
from .market import fetch_asset_price, list_watch_items, add_watch_item, remove_watch_item, search_stock
from .config import load_config, save_config
from .notifier import push_all, push_qq, push_wechat, push_feishu, build_price_alert_content, build_pnl_content
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
            insert_price(now.date().isoformat(), now.strftime("%H:%M:%S"), price, source or "unknown")
            cfg = load_config()
            if cfg.get("alert_enabled"):
                low = cfg.get("alert_threshold_low", 0)
                high = cfg.get("alert_threshold_high", 9999)
                if price < low or price > high:
                    prev = last_alert_price.get("price")
                    if prev is None or (prev < low and price >= low) or (prev > high and price <= high) or (price < low and prev >= low) or (price > high and prev <= high):
                        content = build_price_alert_content(price, low, high)
                        results = push_all("金价预警", content)
                        for ch, (ok, msg) in results.items():
                            print(f"[Alert] {ch}: {'OK' if ok else msg}")
                        last_alert_price["price"] = price
            last_alert_price["price"] = price
            print(f"[{now.strftime('%H:%M:%S')}] Price: {price} ({source})")
    except Exception as e:
        print(f"[Scheduler] Gold Error: {e}")

    try:
        cfg = load_config()
        watches = list_watch_items(cfg)
        for item in watches:
            try:
                info = fetch_asset_price(item)
                if info and info.get("price"):
                    now = datetime.datetime.now()
                    extra = json.dumps({k: v for k, v in info.items() if k not in ("name", "code", "type", "price", "change_pct")}, ensure_ascii=False)
                    insert_market_price(info["type"], info["code"], info.get("name", item.get("name", "")), info["price"], info.get("change_pct", 0), extra)
                    print(f"[{now.strftime('%H:%M:%S')}] {info.get('name', info['code'])}: {info['price']} ({info.get('change_pct', 0)}%)")
            except Exception as e:
                print(f"[Scheduler] Market Error {item.get('code', '?')}: {e}")
    except Exception as e:
        print(f"[Scheduler] Watch Error: {e}")

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
    try:
        resp = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=10)
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

    tag = _update_status.get("latest") or "latest"
    full_image = f"{IMAGE_NAME}:{tag}"
    _update_status["updating"] = True

    def do_update():
        try:
            print(f"[Update] 拉取: {full_image}")
            result = subprocess.run(["docker", "pull", full_image], capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                _update_status["message"] = f"拉取失败: {result.stderr[:200]}"
                return
            container_name = os.environ.get("CONTAINER_NAME", "gold-monitor")
            script = f"#!/bin/sh\nsleep 3\ndocker stop {container_name} 2>/dev/null\ndocker rm {container_name} 2>/dev/null\ndocker run -d --name {container_name} -p 5000:5000 -v /app/data:/app/data --restart unless-stopped {full_image}\n"
            with open("/tmp/restart.sh", "w") as f:
                f.write(script)
            os.chmod("/tmp/restart.sh", 0o755)
            subprocess.Popen(["sh", "/tmp/restart.sh"])
            _update_status["message"] = "更新已触发，容器将重启"
        except Exception as e:
            _update_status["message"] = f"更新失败: {e}"
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
    results = []
    for p in cfg.get("my_purchases", []):
        pnl, pct = calculate_pnl(p["price"], current_price, p.get("fee", 0))
        results.append({
            "purchase_price": p["price"],
            "weight": p.get("weight", 0),
            "amount": p.get("amount", 0),
            "fee": p.get("fee", 0),
            "note": p.get("note", ""),
            "pnl": pnl, "pnl_percent": pct, "current_price": current_price,
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
    return jsonify({k: v for k, v in cfg.items() if k not in ("push_channels", "my_purchases")})

@app.route("/api/purchases", methods=["GET"])
def api_purchases():
    return jsonify(load_config().get("my_purchases", []))

@app.route("/api/config/push", methods=["GET", "POST"])
def api_config_push():
    cfg = load_config()
    if request.method == "POST":
        data = request.json
        print(f"[配置] 收到: {json.dumps(data, ensure_ascii=False)}")
        push_channels = cfg.setdefault("push_channels", {})
        if "qq_bot" in data:
            push_channels["qq_bot"] = data["qq_bot"]
        if "wechat_webhook" in data:
            push_channels["wechat_webhook"] = data["wechat_webhook"]
        if "feishu_webhook" in data:
            push_channels["feishu_webhook"] = data["feishu_webhook"]
        save_config(cfg)
        try:
            from .qqbot import qqbot
            qqbot.restart()
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
    except:
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
        return jsonify({"handled": True, "response": f"当前金价：{price}元/克"})
    if response == "__QUERY_PNL__":
        cfg = load_config()
        current = get_latest_price()
        cp = current["price"] if current else 0
        return jsonify({"handled": True, "response": build_pnl_content(cfg.get("my_purchases", []), cp)})
    if response == "__QUERY_CHART__":
        return jsonify({"handled": True, "response": "__CHART_IMAGE__", "type": "chart"})
    if response == "__QUERY_WATCHLIST__":
        cfg = load_config()
        watches = list_watch_items(cfg)
        if not watches:
            return jsonify({"handled": True, "response": "监控列表为空\n发送「添加监控 贵州茅台」或「添加监控 600519」或「添加监控 黄金」添加"})
        lines = ["监控列表：\n"]
        for i, w in enumerate(watches):
            type_label = {"a_stock": "A股", "hk_stock": "港股", "fund": "基金", "futures": "期货"}.get(w.get("type", ""), w.get("type", ""))
            info = get_latest_market_price(w.get("code", ""))
            if info:
                pct = info.get("change_pct", 0)
                sign = "+" if pct >= 0 else ""
                lines.append(f"{i+1}. [{type_label}] {w.get('name', '')}({w.get('code', '')}) {info['price']} {sign}{pct}%")
            else:
                lines.append(f"{i+1}. [{type_label}] {w.get('name', '')}({w.get('code', '')}) -")
        lines.append("\n发送「删除监控1」删除，「行情 600519」查看行情")
        return jsonify({"handled": True, "response": "\n".join(lines)})
    if response.startswith("__SEARCH__"):
        keyword = response.replace("__SEARCH__", "")
        results = search_stock(keyword)
        if not results:
            return jsonify({"handled": True, "response": f"未找到「{keyword}」相关结果"})
        if len(results) == 1:
            item = results[0]
            cfg = load_config()
            ok, msg = add_watch_item(cfg, item)
            type_label = {"a_stock": "A股", "hk_stock": "港股", "fund": "基金", "futures": "期货"}.get(item.get("type", ""), item.get("type", ""))
            if ok:
                return jsonify({"handled": True, "response": f"已添加监控：{type_label} {item['name']}({item['code']})\n当前价：{item['price']}"})
            return jsonify({"handled": True, "response": msg})
        lines = [f"找到{len(results)}个结果，回复序号添加监控：\n"]
        for i, item in enumerate(results):
            type_label = {"a_stock": "A股", "hk_stock": "港股", "fund": "基金", "futures": "期货"}.get(item.get("type", ""), item.get("type", ""))
            pct = item.get("change_pct", 0)
            sign = "+" if pct >= 0 else ""
            lines.append(f"{i+1}. [{type_label}] {item['name']}({item['code']}) {item['price']} {sign}{pct}%")
        from .chat import _set_state
        _set_state({"step": "pick_search_result", "results": results})
        lines.append("\n回复序号添加，或回复取消退出")
        return jsonify({"handled": True, "response": "\n".join(lines)})
    return jsonify({"handled": True, "response": response})

@app.route("/api/push/test", methods=["POST"])
def api_push_test():
    data = request.json
    channel = data.get("channel", "wechat")
    title = "测试推送"
    content = f"测试消息 {datetime.datetime.now().strftime('%H:%M:%S')}"
    if channel == "wechat":
        ok, msg = push_wechat(title, content)
    elif channel == "feishu":
        ok, msg = push_feishu(title, content)
    elif channel == "qq":
        ok, msg = push_qq(title, content)
    else:
        return jsonify({"ok": False, "msg": "未知渠道"})
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/watches", methods=["GET", "POST", "DELETE"])
def api_watches():
    cfg = load_config()
    if request.method == "POST":
        data = request.json
        keyword = data.get("keyword", "")
        results = search_stock(keyword)
        return jsonify({"ok": True, "results": results})
    if request.method == "DELETE":
        idx = request.args.get("index", type=int)
        if idx is not None:
            ok, removed = remove_watch_item(cfg, idx)
            if ok:
                return jsonify({"ok": True, "removed": removed})
            return jsonify({"ok": False, "msg": "索引无效"})
    watches = list_watch_items(cfg)
    codes = [w.get("code") for w in watches]
    latest = get_all_latest_market_prices(codes)
    items = []
    for w in watches:
        info = latest.get(w.get("code"), {})
        items.append({**w, **info})
    return jsonify({"ok": True, "watches": items})

@app.route("/api/market/search")
def api_market_search():
    keyword = request.args.get("q", "")
    if not keyword:
        return jsonify({"ok": False, "msg": "请输入搜索关键词"})
    results = search_stock(keyword)
    return jsonify({"ok": True, "results": results})

@app.route("/api/market/quote/<code>")
def api_market_quote(code):
    asset_type = request.args.get("type", "a_stock")
    info = fetch_asset_price({"code": code, "type": asset_type})
    if info:
        return jsonify({"ok": True, "data": info})
    return jsonify({"ok": False, "msg": "获取行情失败"})

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
    try:
        from .qqbot import start_bot
        qq = cfg.get("push_channels", {}).get("qq_bot", {})
        if qq.get("app_id") and qq.get("token"):
            start_bot()
    except Exception as e:
        print(f"[App] QQBot启动失败: {e}")
    return app

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=False)
