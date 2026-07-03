"""
Post-LLM 坐标校验（参考 OpenGuider semantic-verifier.js）

双层验证：边界检查 + 元素语义匹配
纯 Python，不引入 embedding 模型。
热路径安全（纯同步，无 I/O）。
"""
from typing import List


def validate_coordinate(
    coord: List[int],
    elements: list,
    label: str = "",
    tolerance: int = 100,
) -> dict:
    """
    校验 LLM 输出引用的元素坐标是否合理。

    Args:
        coord: [cx, cy] 中心点坐标
        elements: 当前屏幕全部 UIElement 列表
        label: 目标元素文字标签，用于语义匹配
        tolerance: 临近判定半径（像素）

    Returns:
        {valid: bool, confidence: float (0.0-1.0), reason: str}
    """
    if not coord or len(coord) < 2:
        return {"valid": False, "confidence": 0.0, "reason": "无坐标"}

    x, y = coord[0], coord[1]

    # 1) 边界检查
    if x < 0 or y < 0:
        return {"valid": False, "confidence": 0.0, "reason": "坐标越界"}
    if x > 10000 or y > 10000:
        return {"valid": False, "confidence": 0.3, "reason": "坐标超出常识范围"}

    # 2) 元素临近检查
    nearby = []
    for e in elements:
        if not e.bbox or len(e.bbox) < 4:
            continue
        # 用 bbox 中心点
        cx = (e.bbox[0] + e.bbox[2]) // 2
        cy = (e.bbox[1] + e.bbox[3]) // 2
        dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        if dist <= tolerance:
            nearby.append((e, dist))

    if not nearby:
        return {
            "valid": True,
            "confidence": 0.6,
            "reason": "坐标附近无已知元素，使用 LLM 原始坐标",
        }

    # 3) 标签文本匹配（Jaccard on bigrams，替代 embedding）
    if label and len(label) >= 1:
        best = None
        for e, dist in sorted(nearby, key=lambda pair: pair[1]):
            text = (e.text or "").lower().strip()
            if not text:
                continue
            lbl = label.lower().strip()

            # 精确子串匹配
            if lbl in text or text in lbl:
                return {
                    "valid": True,
                    "confidence": 0.95,
                    "reason": f"标签精确匹配: {e.text}",
                }

            # Jaccard bigram 相似度
            sim = _bigram_similarity(lbl, text)
            if best is None or sim > best[0]:
                best = (sim, e, dist)

        if best and best[0] >= 0.5:
            return {
                "valid": True,
                "confidence": 0.85,
                "reason": f"标签模糊匹配: {best[1].text} (sim={best[0]:.2f})",
            }

    # 坐标在某个元素范围内 → 高置信
    for e, _ in nearby:
        if e.bbox[0] <= x <= e.bbox[2] and e.bbox[1] <= y <= e.bbox[3]:
            return {
                "valid": True,
                "confidence": 0.9,
                "reason": f"坐标在元素 {e.element_id} 边界内",
            }

    return {
        "valid": True,
        "confidence": 0.7,
        "reason": "坐标在已知元素附近",
    }


def _bigram_similarity(a: str, b: str) -> float:
    """Jaccard 相似度 on character bigrams。
    纯文本匹配，0 依赖，用于替代 embedding 模型。
    """
    if a == b:
        return 1.0
    if len(a) <= 1 and len(b) <= 1:
        return 1.0 if a == b else 0.0

    a_set = set(a[i:i + 2] for i in range(len(a) - 1)) if len(a) >= 2 else {a}
    b_set = set(b[i:i + 2] for i in range(len(b) - 1)) if len(b) >= 2 else {b}

    if not a_set or not b_set:
        return 0.0

    intersection = len(a_set & b_set)
    union = len(a_set | b_set)
    return intersection / union if union > 0 else 0.0
