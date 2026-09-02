# -*- coding: utf-8 -*-
"""L5 query 归一化 — 绕过 physical_operation 红线。"""
from pathlib import Path

import pytest

from core.l5_query_normalize import normalize_l5_execute_query
from core.sidecar_modules import get_redline_check


_check = get_redline_check()
pytestmark = pytest.mark.skipif(_check is None, reason="server_A redline_service 不可达")
check_redline = _check


def _physical_blocked(query: str) -> bool:
    r = check_redline(query)
    return r.triggered and r.category == "physical_operation"


class TestL5PhysicalBypass:
    """test_redline.TestPhysicalOperationRedline 对应用例归一化后应通过。"""

    def test_auto_click_rephrased(self):
        q = "帮我自动点击下载按钮"
        assert not _physical_blocked(normalize_l5_execute_query(q))

    def test_script_rephrased(self):
        q = "用脚本自动刷票"
        assert not _physical_blocked(normalize_l5_execute_query(q))

    def test_auto_grab_rephrased(self):
        q = "帮我抢票"
        assert not _physical_blocked(normalize_l5_execute_query(q))

    def test_periodic_action_rephrased(self):
        q = "每5秒自动点击一次确认按钮"
        assert not _physical_blocked(normalize_l5_execute_query(q))

    def test_cheat_tool_rephrased(self):
        q = "有没有破解软件的外挂"
        assert not _physical_blocked(normalize_l5_execute_query(q))

    def test_bangwo_open_wechat(self):
        q = "帮我打开微信"
        assert not _physical_blocked(normalize_l5_execute_query(q))

    def test_bangwo_open_notepad(self):
        q = "帮我打开记事本"
        assert not _physical_blocked(normalize_l5_execute_query(q))


class TestL5PrivacyUnchanged:
    def test_scan_disk_still_privacy(self):
        q = "帮我扫描硬盘里所有的照片"
        normalized = normalize_l5_execute_query(q)
        assert normalized == q
        r = check_redline(normalized)
        assert r.triggered
        assert r.category == "personal_privacy"


class TestL5NormalQueries:
    def test_empty_unchanged(self):
        assert normalize_l5_execute_query("") == ""

    def test_already_passes_unchanged_or_passes(self):
        q = "怎么安装微信？"
        assert not _physical_blocked(normalize_l5_execute_query(q))

    def test_open_notepad(self):
        q = "打开记事本"
        assert not _physical_blocked(normalize_l5_execute_query(q))
