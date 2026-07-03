"""
步骤风险评分（参考 OpenGuider trust-manager.js / browser/risk-scorer.js）
返回 1-5 的整数，1=安全/只读，5=不可逆/危险

纯同步函数，热路径安全
"""

# 高风险动作关键词 → 评 4
_HIGH_RISK_KEYWORDS = [
    "删除", "卸载", "格式化", "清空", "移除",
    "购买", "支付", "付款", "结账", "提交订单",
    "注销", "退出登录", "关闭账户", "解绑",
    "禁用", "停用", "清空缓存", "恢复出厂",
]

# 低风险动作关键词 → 评 1
_LOW_RISK_KEYWORDS = [
    "找到", "查看", "观察", "浏览", "阅读",
    "等待", "确认", "检查", "注意",
    "了解", "识别", "定位",
]


def score_step(action: str = "", description: str = "") -> int:
    """
    对单个步骤进行风险评分。

    Args:
        action: 步骤的动作描述（如 "点击下载"）
        description: 步骤的详细说明

    Returns:
        int: 1-5 的风险评分
    """
    text = f"{action} {description}".lower()

    # 高风险命中 → 4（暂不评 5，5 留给显式标记的不可逆操作）
    for kw in _HIGH_RISK_KEYWORDS:
        if kw in text:
            return 4

    # 低风险命中 → 1
    for kw in _LOW_RISK_KEYWORDS:
        if kw in text:
            return 1

    # 有明确操作动词 → 2（标准 UI 操作）
    return 2
