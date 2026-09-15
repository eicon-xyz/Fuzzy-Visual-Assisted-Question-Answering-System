"""oracle 谓词求值器（平台无关的纯逻辑；系统探测通过 probe 注入）。

runner 在 Windows 上注入真实 probe（file/glob/winreg/clipboard/uiautomation），
Linux 单测注入 FakeProbe —— 求值语义两平台一致。
"""
from __future__ import annotations

from typing import List, Tuple


class OracleEvaluationError(Exception):
    pass


def _fmt(v):
    return "" if v is None else str(v)


def eval_check(chk: dict, probe) -> Tuple[bool, str]:
    """求值单个谓词，返回 (是否成立, 人类可读说明)。"""
    t = chk.get("type")
    if t == "file_exists":
        p = chk["path"]
        ok = probe.file_exists(p)
        return ok, f"file_exists {p} -> {ok}"
    if t == "file_not_exists":
        p = chk["path"]
        ok = not probe.file_exists(p)
        return ok, f"file_not_exists {p} -> {ok}"
    if t == "file_content_contains":
        p, needle = chk["path"], _fmt(chk["needle"])
        text = probe.read_text(p)
        if text is None:
            return False, f"file_content_contains {p}: 文件不存在/不可读"
        ok = needle in text
        return ok, f"file_content_contains {p} {needle!r} -> {ok}"
    if t == "file_content_equals":
        p, want = chk["path"], _fmt(chk["text"])
        text = probe.read_text(p)
        ok = text is not None and text.strip() == want.strip()
        return ok, f"file_content_equals {p} -> {ok}"
    if t == "file_glob_min_count":
        g, m = chk["glob"], int(chk["min"])
        n = probe.glob_count(g)
        ok = n >= m
        return ok, f"glob {g} count={n} >= {m} -> {ok}"
    if t == "registry_value":
        val = probe.reg_value(chk["hive"], chk["key"], chk["name"])
        if "expect" not in chk:
            ok = val is not None
        else:
            ok = _fmt(val) == _fmt(chk["expect"])
        return ok, f"reg {chk['key']}\\{chk['name']}={val!r} -> {ok}"
    if t == "clipboard_contains":
        clip = probe.clipboard() or ""
        ok = _fmt(chk["needle"]) in clip
        return ok, f"clipboard_contains {chk['needle']!r} -> {ok}"
    if t == "uia_window_title_contains":
        needle = _fmt(chk["needle"]).lower()
        titles = probe.window_titles()
        ok = any(needle in (_fmt(x).lower()) for x in titles)
        return ok, f"window_title~{chk['needle']!r} -> {ok} (windows={len(titles)})"
    if t == "uia_window_not_exists":
        needle = _fmt(chk["needle"]).lower()
        titles = probe.window_titles()
        ok = not any(needle in (_fmt(x).lower()) for x in titles)
        return ok, f"no_window_title~{chk['needle']!r} -> {ok}"
    if t == "uia_element_exists":
        name = _fmt(chk["name_contains"]).lower()
        wneed = chk.get("window_title_contains")
        etype = chk.get("type")
        names = probe.element_names(
            window_title_contains=_fmt(wneed).lower() if wneed else None,
            element_type=etype,
        )
        ok = any(name in (_fmt(x).lower()) for x in names)
        return ok, f"element~{chk['name_contains']!r} -> {ok} (scanned={len(names)})"
    raise OracleEvaluationError(f"未知 oracle 类型: {t}")


def eval_oracle(oracle: dict, probe) -> Tuple[bool, List[str]]:
    """求值整个 oracle：all=全部成立；any=至少一个成立（两者都在则都要满足）。"""
    trace: List[str] = []
    all_ok = True
    for chk in oracle.get("all", []):
        ok, msg = eval_check(chk, probe)
        trace.append(msg)
        all_ok = all_ok and ok
    any_list = oracle.get("any")
    any_ok = True
    if any_list:
        any_ok = False
        for chk in any_list:
            ok, msg = eval_check(chk, probe)
            trace.append(msg)
            any_ok = any_ok or ok
    return (all_ok and any_ok), trace
