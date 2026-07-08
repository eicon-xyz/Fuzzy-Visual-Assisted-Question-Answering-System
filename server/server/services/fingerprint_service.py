"""
屏幕指纹服务

用于步骤执行过程中的屏幕状态比对，触发蓝图挂起/恢复。
比对策略：元素类型集合的 Jaccard 相似度 ≥ 80% → 匹配成功

参考：设计文档 §4.3.2 蓝图保护机制
"""

import hashlib
from typing import List, Optional


def compute_fingerprint_hash(window_title: str, element_types: List[str]) -> str:
    """
    计算屏幕指纹 SHA256 哈希。

    Args:
        window_title: 活动窗口标题
        element_types: UI 元素类型列表（如 ["button", "input", "icon"]）

    Returns:
        64 字符 hex 哈希
    """
    # 取出现频率最高的 5 种元素类型
    type_counts: dict[str, int] = {}
    for t in element_types:
        type_counts[t] = type_counts.get(t, 0) + 1

    top5 = sorted(type_counts, key=type_counts.get, reverse=True)[:5]  # type: ignore[arg-type]

    fingerprint_str = f"{window_title}|{','.join(top5)}"
    return hashlib.sha256(fingerprint_str.encode("utf-8")).hexdigest()


def compute_jaccard(old_types: List[str], new_types: List[str]) -> float:
    """
    计算两组元素类型的 Jaccard 相似度。

    Args:
        old_types: 旧屏幕的元素类型列表
        new_types: 新屏幕的元素类型列表

    Returns:
        0.0 ~ 1.0 的相似度
    """
    if not old_types and not new_types:
        return 1.0
    if not old_types or not new_types:
        return 0.0

    old_set = set(old_types)
    new_set = set(new_types)

    intersection = len(old_set & new_set)
    union = len(old_set | new_set)

    return intersection / union if union > 0 else 0.0


def should_suspend(
    old_types: List[str],
    new_types: List[str],
    match_threshold: float = 0.80,
) -> bool:
    """
    判断是否应触发挂起。

    Args:
        old_types: 上一步的元素类型列表
        new_types: 当前步骤的元素类型列表
        match_threshold: Jaccard 阈值，默认 0.80

    Returns:
        True → 应挂起；False → 继续推进
    """
    similarity = compute_jaccard(old_types, new_types)
    return similarity < match_threshold


def compare_screen_state(
    old_types: List[str],
    new_types: List[str],
    old_fingerprint_hash: Optional[str] = None,
    new_fingerprint_hash: Optional[str] = None,
    window_title: Optional[str] = "",
) -> dict:
    """
    综合屏幕状态比对，返回详细比对结果。

    Returns:
        {
            "match": bool,
            "jaccard": float,
            "threshold": float,
            "hash_match": bool or None,
            "recommendation": "advance" | "suspend" | "clarify"
        }
    """
    jaccard = compute_jaccard(old_types, new_types)

    hash_match = None
    if old_fingerprint_hash and new_fingerprint_hash:
        hash_match = old_fingerprint_hash == new_fingerprint_hash

    threshold = 0.80
    match = jaccard >= threshold

    if match:
        recommendation = "advance"
    elif jaccard >= 0.50:
        recommendation = "clarify"
    else:
        recommendation = "suspend"

    return {
        "match": match,
        "jaccard": round(jaccard, 4),
        "threshold": threshold,
        "hash_match": hash_match,
        "recommendation": recommendation,
    }
