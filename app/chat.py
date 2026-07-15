import re
from .config import load_config, save_config
from .gold_price import get_current_price

def parse_chat_command(text):
    """Parse chat commands"""
    text = text.strip()
    cfg = load_config()

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

    m = re.search(r'(添加|买入|记录)\s*(\d+\.?\d*)\s*(元|块)?\s*(手续费\s*(\d+\.?\d*)%?)?', text)
    if m:
        price = float(m.group(2))
        fee = float(m.group(5)) if m.group(5) else 0
        cfg.setdefault("my_purchases", []).append({"price": price, "fee": fee})
        save_config(cfg)
        return True, f"已添加：{price}元/克，手续费{fee}%"

    m = re.search(r'删除\s*(\d+)', text)
    if m:
        idx = int(m.group(1)) - 1
        purchases = cfg.get("my_purchases", [])
        if 0 <= idx < len(purchases):
            removed = purchases.pop(idx)
            save_config(cfg)
            return True, f"已删除：买入价{removed['price']}元/克"
        return True, f"序号无效，当前共{len(purchases)}条记录"

    m = re.search(r'查询|当前[金价价格]|金价|报价', text)
    if m:
        return True, "__QUERY_PRICE__"

    m = re.search(r'盈亏|收益|我的|持仓', text)
    if m:
        return True, "__QUERY_PNL__"

    m = re.search(r'间隔\s*(\d+)', text)
    if m:
        interval = max(30, int(m.group(1)))
        cfg["fetch_interval"] = interval
        save_config(cfg)
        return True, f"查询间隔已设为{interval}秒"

    m = re.search(r'帮助|help|菜单|cmd', text, re.IGNORECASE)
    if m:
        return True, (
            "可用命令：\n"
            "金价/查询 → 查看当前金价\n"
            "盈亏/持仓 → 查看盈亏\n"
            "阈值870-900 → 设置推送阈值\n"
            "开启/关闭提醒\n"
            "添加870.5 手续费0.5% → 记录买入\n"
            "删除1 → 删除第1条记录\n"
            "间隔60 → 设置查询间隔(秒)\n"
            "帮助 → 显示此帮助"
        )

    return False, None
