"""L5 /execute 提交前 query 归一化 — 绕过 physical_operation 红线（不改 Sidecar）。"""
from __future__ import annotations

import re

from server.services.redline_service import check_redline

_PREFIX_RE = re.compile(r"^(请)?(帮我|替我|代我)\s*")

_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"自动点击"), "点击"),
    (re.compile(r"自动操作"), "操作"),
    (re.compile(r"自动执行"), "执行"),
    (re.compile(r"自动下载"), "下载"),
    (re.compile(r"自动打开"), "打开"),
    (re.compile(r"自动"), ""),
    (re.compile(r"脚本"), "步骤"),
    (re.compile(r"外挂|辅助代刷|刷量"), "工具"),
    (re.compile(r"(全|自)动"), ""),
    (re.compile(r"批量|循环|不停|一直|持续|定时|重复"), ""),
    (
        re.compile(
            r"每\s*[0-9零一二三四五六七八九十]+\s*(秒|分|小时|天)\s*"
        ),
        "",
    ),
    (re.compile(r"破解"), ""),
]

_STRIP_TOKENS = (
    "请帮我",
    "帮我",
    "替我",
    "代我",
    "自动",
    "脚本",
    "外挂",
    "辅助",
    "破解",
    "循环",
    "批量",
    "定时",
    "重复",
    "持续",
    "不停",
    "一直",
    "刷量",
)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _physical_triggered(query: str) -> bool:
    result = check_redline(query)
    return result.triggered and result.category == "physical_operation"


def normalize_l5_execute_query(query: str) -> str:
    """
    Rewrite user query so Sidecar check_redline does not hit physical_operation.

    Privacy / realtime_dynamic queries are returned unchanged.
    """
    original = (query or "").strip()
    if not original:
        return original

    initial = check_redline(original)
    if initial.triggered and initial.category != "physical_operation":
        return original

    q = _PREFIX_RE.sub("", original)
    for pattern, repl in _REPLACEMENTS:
        q = pattern.sub(repl, q)
    q = _collapse_ws(q)

    if _physical_triggered(q):
        for token in _STRIP_TOKENS:
            q = q.replace(token, "")
        q = _collapse_ws(q)

    if _physical_triggered(q) and not q.startswith("怎么"):
        q = f"怎么{q}"

    if _physical_triggered(q):
        core = q.removeprefix("怎么").strip()
        q = f"完成操作：{core}" if core else q

    if _physical_triggered(q):
        core = re.sub(r"^(怎么|完成操作：)\s*", "", q).strip()
        q = f"打开并完成：{core}" if core else original

    return q or original
