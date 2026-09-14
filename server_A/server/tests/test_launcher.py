"""T6 launcher.py 单元测试——测纯逻辑层（映射/解析/提取/启动决策），桩掉真实副作用。

launcher 是 Windows-only 运行时（os.startfile/pygetwindow），Linux 测试全部
monkeypatch 桩化；红线检查在 agent 层（_do_launch_app）而非 launcher 本身。
"""
from __future__ import annotations

import pytest

import server.services.launcher as lc


# ── 映射表与解析 ────────────────────────────────────────────────────────


def test_mapping_table_has_expected_entries():
    assert lc.APP_EXECUTABLE_MAP["计算器"] == "calc.exe"
    assert lc.APP_EXECUTABLE_MAP["记事本"] == "notepad.exe"
    assert lc.APP_EXECUTABLE_MAP["画图"] == "mspaint.exe"


def test_resolve_executable_mapping_exact():
    assert lc._resolve_executable("记事本") == "notepad.exe"
    assert lc._resolve_executable("计算器") == "calc.exe"


def test_resolve_executable_path_and_exe_suffix(monkeypatch):
    seen = []
    monkeypatch.setattr(lc.shutil, "which", lambda name: seen.append(name) or None)
    assert lc._resolve_executable("someapp") is None
    assert seen == ["someapp", "someapp.exe"]  # 裸名失败后补 .exe
    monkeypatch.setattr(lc.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert lc._resolve_executable("customapp") == "/usr/bin/customapp"


def test_resolve_executable_unknown_returns_none(monkeypatch):
    monkeypatch.setattr(lc.shutil, "which", lambda name: None)
    assert lc._resolve_executable("zzz_no_such_app_xyz") is None


# ── 自然语言查询提取 ─────────────────────────────────────────────────────


def test_extract_app_name_from_query():
    assert lc._extract_app_name_from_query("打开记事本") == "记事本"
    assert lc._extract_app_name_from_query("打开 记事本 并输入文字") == "记事本"
    assert lc._extract_app_name_from_query("启动计算器") == "计算器"
    assert lc._extract_app_name_from_query("运行mspaint") == "mspaint"
    assert lc._extract_app_name_from_query("打开微信") == "微信"
    assert lc._extract_app_name_from_query("") is None
    # 已知局限（宽松提取）：无启动动词的短句会被第 4 pattern 当应用名提取——
    # 这是 launch_app 层的现有行为，由上层调用方（agent）保证只在启动语境调用。
    assert lc._extract_app_name_from_query("帮我写段代码") == "帮我写段代码"


def test_extract_remaining_operation():
    # 需要显式分隔符（，然后/接着/再/，等）
    assert lc._extract_remaining_operation("打开记事本，然后输入hello", "记事本") == "输入hello"
    assert lc._extract_remaining_operation("打开记事本再输入hello", "记事本") == "输入hello"
    # 无分隔符时不做切分 → None
    assert lc._extract_remaining_operation("打开记事本输入hello", "记事本") is None
    assert lc._extract_remaining_operation("打开记事本", "记事本") is None


# ── launch_app 三级策略 ──────────────────────────────────────────────────


def test_launch_app_empty_name():
    r = lc.launch_app("")
    assert r["success"] is False and "empty" in r["error"]


def test_launch_app_tier1_direct(monkeypatch):
    """映射表命中 + Popen 成功 → tier 1 direct。"""
    started = []
    monkeypatch.setattr(lc.shutil, "which", lambda name: f"C:\\Windows\\{name}")
    monkeypatch.setattr(lc.subprocess, "Popen", lambda cmd, **k: started.append(cmd))
    monkeypatch.setattr(lc.time, "sleep", lambda s: None)
    monkeypatch.setattr(lc, "_force_window_foreground", lambda name: True)
    r = lc.launch_app("记事本")
    assert r["success"] is True
    assert r["method"] == "direct" and r["tier"] == 1
    assert started and "notepad.exe" in started[0][0].lower()


def test_launch_app_tier2_path(monkeypatch):
    """映射表外但 PATH 可解析 → tier 2 direct（用映射表外的名字避免 tier1 命中）。"""
    started = []
    monkeypatch.setattr(lc.shutil, "which", lambda name: "C:\\Tools\\blender.exe")
    monkeypatch.setattr(lc.subprocess, "Popen", lambda cmd, **k: started.append(cmd))
    monkeypatch.setattr(lc.time, "sleep", lambda s: None)
    monkeypatch.setattr(lc, "_force_window_foreground", lambda name: True)
    r = lc.launch_app("blender")
    assert r["success"] is True and r["tier"] == 2
    assert r["method"] == "direct"


def test_launch_app_tier3_win_search(monkeypatch):
    """direct 全部失败 → Win+Search 兜底。"""
    monkeypatch.setattr(lc.shutil, "which", lambda name: None)
    monkeypatch.setattr(lc, "_launch_win_search", lambda name: True)
    monkeypatch.setattr(lc.time, "sleep", lambda s: None)
    monkeypatch.setattr(lc, "_force_window_foreground", lambda name: True)
    r = lc.launch_app("某个UWP应用")
    assert r["success"] is True and r["method"] == "win_search" and r["tier"] == 3


def test_launch_app_all_tiers_fail(monkeypatch):
    monkeypatch.setattr(lc.shutil, "which", lambda name: None)
    monkeypatch.setattr(lc, "_launch_win_search", lambda name: False)
    r = lc.launch_app("绝对不存在的应用xyz")
    assert r["success"] is False
    assert "all 3 launch tiers failed" in r["error"]


def test_launch_direct_abs_path(monkeypatch):
    """绝对路径存在 → os.startfile 分支（Windows-only API，桩化）。"""
    calls = []
    monkeypatch.setattr(lc.os.path, "isabs", lambda p: True)
    monkeypatch.setattr(lc.os.path, "exists", lambda p: True)
    monkeypatch.setattr(lc.os, "startfile", lambda p: calls.append(p), raising=False)
    assert lc._launch_direct("C:\\x\\app.exe") is True
    assert calls == ["C:\\x\\app.exe"]


def test_launch_direct_missing_executable(monkeypatch):
    monkeypatch.setattr(lc.os.path, "isabs", lambda p: False)
    monkeypatch.setattr(lc.shutil, "which", lambda n: None)
    assert lc._launch_direct("x.exe") is False


def test_launch_direct_popen_exception(monkeypatch):
    monkeypatch.setattr(lc.os.path, "isabs", lambda p: False)
    monkeypatch.setattr(lc.shutil, "which", lambda n: "C:\\x.exe")
    monkeypatch.setattr(lc.subprocess, "Popen", lambda **k: (_ for _ in ()).throw(OSError("no")))
    assert lc._launch_direct("x.exe") is False
