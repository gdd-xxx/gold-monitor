import re
from .config import load_config, save_config

def parse_chat_command(text):
    """Parse chat commands like '阈值870-900'"""
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

    m = re.search(r'(添加|买入)\s*(\d+\.?\d*)\s*(元|块)?\s*(手续费\s*(\d+\.?\d*)%?)?', text)
    if m:
        price = float(m.group(2))
        fee = float(m.group(5)) if m.group(5) else 0
        cfg.setdefault("my_purchases", []).append({"price": price, "fee": fee})
        save_config(cfg)
        return True, f"已添加买入记录：{price}元/克，手续费{fee}%"

    m = re.search(r'查询|当前[金价价格]|金价', text)
    if m:
        return True, "__QUERY_PRICE__"

    m = re.search(r'盈亏|收益|我的', text)
    if m:
        return True, "__QUERY_PNL__"

    m = re.search(r'帮助|help', text, re.IGNORECASE)
    if m:
        return True, (
            "可用命令：\n"
            "阈值870-900 → 设置推送阈值\n"
            "开启/关闭提醒 → 控制推送\n"
            "添加870.5 手续费0.5% → 记录买入\n"
            "查询 → 查看当前金价\n"
            "盈亏 → 查看盈亏情况\n"
            "帮助 → 显示此帮助"
        )

    return False, None
