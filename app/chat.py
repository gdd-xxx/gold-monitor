import re, json
from .config import load_config, save_config
from .gold_price import get_current_price
from .market import search_stock, add_watch_item, remove_watch_item, list_watch_items, fetch_asset_price

def _get_state():
    cfg = load_config()
    return cfg.setdefault("chat_state", {})

def _set_state(state):
    cfg = load_config()
    cfg["chat_state"] = state
    save_config(cfg)

def _clear_state():
    cfg = load_config()
    cfg["chat_state"] = {}
    save_config(cfg)

def parse_chat_command(text):
    text = text.strip()
    cfg = load_config()
    state = _get_state()

    if state.get("step"):
        return _handle_step(text, state, cfg)

    m = re.search(r'[阈阀]值\s*(\d+\.?\d*)\s*[-~至到]\s*(\d+\.?\d*)', text)
    if m:
        low, high = float(m.group(1)), float(m.group(2))
        cfg["alert_threshold_low"] = low
        cfg["alert_threshold_high"] = high
        cfg["alert_enabled"] = True
        save_config(cfg)
        return True, f"阈值已设置：低于{low}元或超过{high}元时推送"

    m = re.search(r'关闭[推提]醒', text)
    if m:
        cfg["alert_enabled"] = False
        save_config(cfg)
        return True, "提醒已关闭"

    m = re.search(r'开启[推提]醒', text)
    if m:
        cfg["alert_enabled"] = True
        save_config(cfg)
        return True, "提醒已开启"

    m = re.search(r'(添加|买入|记录)\s*(\d+\.?\d*)', text)
    if m:
        price = float(m.group(2))
        fee_match = re.search(r'手续费\s*(\d+\.?\d*)%?', text)
        amount_match = re.search(r'(\d+\.?\d*)\s*(元|块|¥)', text)
        weight_match = re.search(r'(\d+\.?\d*)\s*(克|g|G)', text)

        fee = float(fee_match.group(1)) if fee_match else 0
        amount = float(amount_match.group(1)) if amount_match else 0
        weight = float(weight_match.group(1)) if weight_match else 0

        if fee > 0 and (amount > 0 or weight > 0):
            if amount > 0 and weight == 0:
                weight = round(amount / price, 2)
            elif weight > 0 and amount == 0:
                amount = round(weight * price, 2)
            purchase = {"price": price, "fee": fee, "amount": amount, "weight": weight}
            cfg.setdefault("my_purchases", []).append(purchase)
            save_config(cfg)
            return True, f"已添加：{price}元/克，手续费{fee}%，{amount}元/{weight}克"

        _set_state({"step": "add_fee", "price": price, "fee": fee, "amount": amount, "weight": weight})
        if fee > 0:
            return True, f"买入价：{price}元/克，手续费：{fee}%\n买了多少元？（或多少克）"
        return True, f"买入价：{price}元/克\n手续费多少？（输入0跳过）"

    m = re.search(r'删除\s*(\d+)', text)
    if m:
        idx = int(m.group(1)) - 1
        purchases = cfg.get("my_purchases", [])
        if 0 <= idx < len(purchases):
            removed = purchases.pop(idx)
            save_config(cfg)
            return True, f"已删除：买入价{removed['price']}元/克"
        return True, f"序号无效，当前共{len(purchases)}条记录"

    m = re.search(r'推送[设配]置|推送[内模]容|推送[选选]', text)
    if m:
        _set_state({"step": "push_select"})
        push_items = cfg.get("push_items", {"price": True, "pnl": True, "chart": False})
        status = lambda k: "✓" if push_items.get(k) else "✗"
        return True, (
            f"当前推送内容：\n"
            f"1. 金价预警 {status('price')}\n"
            f"2. 盈亏情况 {status('pnl')}\n"
            f"3. 今日走势 {status('chart')}\n\n"
            f"回复数字切换，如：1,2 或 1,3\n"
            f"回复取消退出设置"
        )

    m = re.search(r'查询|当前[金价价格]|金价|报价', text)
    if m:
        return True, "__QUERY_PRICE__"

    m = re.search(r'盈亏|收益|我的|持仓', text)
    if m:
        return True, "__QUERY_PNL__"

    m = re.search(r'今日走势|走势图|折线图|图表', text)
    if m:
        return True, "__QUERY_CHART__"

    m = re.search(r'间隔\s*(\d+)', text)
    if m:
        interval = max(30, int(m.group(1)))
        cfg["fetch_interval"] = interval
        save_config(cfg)
        return True, f"查询间隔已设为{interval}秒"

    m = re.search(r'监控列表|自选列表|我的关注|关注列表', text)
    if m:
        return True, "__QUERY_WATCHLIST__"

    m = re.search(r'行情\s+(.+)', text)
    if m:
        keyword = m.group(1).strip()
        _set_state({"step": "search_result", "keyword": keyword})
        return True, f"__SEARCH__{keyword}"

    m = re.search(r'(添加监控|添加关注|监[控控]|关注)\s*(.+)', text)
    if m:
        keyword = m.group(2).strip()
        _set_state({"step": "search_result", "keyword": keyword})
        return True, f"__SEARCH__{keyword}"

    m = re.search(r'删除监控\s*(\d+)', text)
    if m:
        idx = int(m.group(1)) - 1
        ok, removed = remove_watch_item(cfg, idx)
        if ok:
            type_label = {"a_stock": "A股", "hk_stock": "港股", "fund": "基金", "futures": "期货"}.get(removed.get("type", ""), removed.get("type", ""))
            return True, f"已删除监控：{type_label} {removed.get('name', '')}({removed.get('code', '')})"
        watches = list_watch_items(cfg)
        return True, f"序号无效，当前共{len(watches)}条监控"

    m = re.search(r'帮助|help|菜单|cmd', text, re.IGNORECASE)
    if m:
        return True, (
            "可用命令：\n"
            "金价/查询 → 查看当前金价\n"
            "盈亏/持仓 → 查看盈亏\n"
            "今日走势 → 查看走势图\n"
            "阈值870-900 → 设置推送阈值\n"
            "开启/关闭提醒\n"
            "添加875 手续费0.4% 10000元\n"
            "添加875（进入引导）\n"
            "删除1 → 删除第1条记录\n"
            "推送设置 → 设置推送内容\n"
            "间隔60 → 设置查询间隔(秒)\n"
            "──── 股票/基金/期货 ────\n"
            "监控列表 → 查看关注列表\n"
            "添加监控 贵州茅台 → 搜索并添加\n"
            "添加监控 600519 → 按代码添加\n"
            "添加监控 黄金 → 搜索期货\n"
            "添加监控 AU0 → 添加期货主力\n"
            "行情 600519 → 查看行情\n"
            "删除监控1 → 删除第1条监控\n"
            "帮助 → 显示此帮助"
        )

    return False, None

def _handle_step(text, state, cfg):
    step = state.get("step")

    if text in ("取消", "退出", "q", "Q"):
        _clear_state()
        return True, "已取消"

    if step == "add_fee":
        m = re.search(r'(\d+\.?\d*)', text)
        if m:
            fee = float(m.group(1))
            state["fee"] = fee
            state["step"] = "add_amount"
            _set_state(state)
            price = state["price"]
            return True, f"买入价：{price}元/克，手续费：{fee}%\n买了多少元？（或多少克，如：10000元 或 11克）"
        return True, "请输入手续费百分比（如：0.4）"

    if step == "add_amount":
        price = state["price"]
        fee = state.get("fee", 0)

        amount_match = re.search(r'(\d+\.?\d*)\s*(元|块|¥)', text)
        weight_match = re.search(r'(\d+\.?\d*)\s*(克|g|G)', text)
        num_match = re.search(r'^(\d+\.?\d*)$', text)

        if amount_match:
            amount = float(amount_match.group(1))
            weight = round(amount / price, 2)
        elif weight_match:
            weight = float(weight_match.group(1))
            amount = round(weight * price, 2)
        elif num_match:
            amount = float(num_match.group(1))
            weight = round(amount / price, 2)
        else:
            return True, "请输入金额（如：10000元）或克数（如：11克）"

        purchase = {"price": price, "fee": fee, "amount": amount, "weight": weight}
        cfg.setdefault("my_purchases", []).append(purchase)
        save_config(cfg)
        _clear_state()
        return True, f"已添加：\n买入价：{price}元/克\n手续费：{fee}%\n金额：{amount}元\n数量：{weight}克"

    if step == "push_select":
        text = text.replace("，", ",").replace("、", ",").replace(" ", "")
        selections = re.findall(r'[123]', text)

        if not selections:
            return True, "请输入数字选择，如：1,2 或 1,3"

        push_items = cfg.get("push_items", {"price": True, "pnl": True, "chart": False})
        push_items["price"] = "1" in selections
        push_items["pnl"] = "2" in selections
        push_items["chart"] = "3" in selections
        cfg["push_items"] = push_items
        save_config(cfg)
        _clear_state()

        status = lambda k: "✓" if push_items.get(k) else "✗"
        return True, (
            f"推送设置已更新：\n"
            f"1. 金价预警 {status('price')}\n"
            f"2. 盈亏情况 {status('pnl')}\n"
            f"3. 今日走势 {status('chart')}"
        )

    if step == "search_result":
        keyword = state.get("keyword", "")
        _clear_state()
        results = search_stock(keyword)
        if not results:
            return True, f"未找到「{keyword}」相关结果，请检查名称或代码"
        if len(results) == 1:
            item = results[0]
            ok, msg = add_watch_item(cfg, item)
            type_label = {"a_stock": "A股", "hk_stock": "港股", "fund": "基金", "futures": "期货"}.get(item.get("type", ""), item.get("type", ""))
            if ok:
                return True, f"已添加监控：{type_label} {item['name']}({item['code']})\n当前价：{item['price']}"
            return True, msg
        lines = [f"找到{len(results)}个结果，回复序号添加监控：\n"]
        for i, item in enumerate(results):
            type_label = {"a_stock": "A股", "hk_stock": "港股", "fund": "基金", "futures": "期货"}.get(item.get("type", ""), item.get("type", ""))
            pct = item.get("change_pct", 0)
            sign = "+" if pct >= 0 else ""
            lines.append(f"{i+1}. [{type_label}] {item['name']}({item['code']}) {item['price']} {sign}{pct}%")
        _set_state({"step": "pick_search_result", "results": results})
        lines.append("\n回复序号添加，或回复取消退出")
        return True, "\n".join(lines)

    if step == "pick_search_result":
        results = state.get("results", [])
        _clear_state()
        m = re.match(r'^(\d+)$', text)
        if not m:
            return True, "请输入序号"
        idx = int(m.group(1)) - 1
        if idx < 0 or idx >= len(results):
            return True, f"序号无效，范围1-{len(results)}"
        item = results[idx]
        ok, msg = add_watch_item(cfg, item)
        type_label = {"a_stock": "A股", "hk_stock": "港股", "fund": "基金", "futures": "期货"}.get(item.get("type", ""), item.get("type", ""))
        if ok:
            return True, f"已添加监控：{type_label} {item['name']}({item['code']})\n当前价：{item['price']}"
        return True, msg

    _clear_state()
    return True, "对话已重置"
