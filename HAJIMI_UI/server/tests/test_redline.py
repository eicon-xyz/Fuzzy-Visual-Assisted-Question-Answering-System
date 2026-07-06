"""
红线检测模块测试
"""

from server.services.redline_service import check_redline


class TestPhysicalOperationRedline:
    """物理操作红线"""

    def test_auto_click_rejected(self):
        r = check_redline("帮我自动点击下载按钮")
        assert r.triggered
        assert r.category == "physical_operation"
        assert r.action == "reject"

    def test_script_detection_rejected(self):
        r = check_redline("用脚本自动刷票")
        assert r.triggered
        assert r.category == "physical_operation"

    def test_auto_grab_rejected(self):
        r = check_redline("帮我抢票")
        assert r.triggered
        assert r.category == "physical_operation"

    def test_periodic_action_rejected(self):
        r = check_redline("每5秒自动点击一次确认按钮")
        assert r.triggered
        assert r.category == "physical_operation"

    def test_cheat_tool_rejected(self):
        r = check_redline("有没有破解软件的外挂")
        assert r.triggered
        assert r.category == "physical_operation"


class TestPrivacyRedline:
    """个人隐私红线"""

    def test_scan_disk_rejected(self):
        r = check_redline("帮我扫描硬盘里所有的照片")
        assert r.triggered
        assert r.category == "personal_privacy"
        assert r.action == "guided_reject"

    def test_read_chat_rejected(self):
        r = check_redline("帮我查看他的微信聊天记录")
        assert r.triggered
        assert r.category == "personal_privacy"

    def test_extract_password_rejected(self):
        r = check_redline("帮我获取这个网站的密码")
        assert r.triggered
        assert r.category == "personal_privacy"

    def test_monitor_keyboard_rejected(self):
        r = check_redline("帮我监控键盘输入")
        assert r.triggered
        assert r.category == "personal_privacy"


class TestDynamicContentRedline:
    """实时动态红线"""

    def test_live_stream_degraded(self):
        r = check_redline("这个直播画面怎么全屏")
        assert r.triggered
        assert r.category == "realtime_dynamic"
        assert r.action == "degrade"

    def test_stock_market_degraded(self):
        r = check_redline("股票行情怎么看")
        assert r.triggered
        assert r.category == "realtime_dynamic"


class TestNormalQueriesPass:
    """正常查询通过"""

    def test_install_software_passes(self):
        r = check_redline("怎么安装微信？")
        assert not r.triggered

    def test_save_file_passes(self):
        r = check_redline("怎么保存这个文档")
        assert not r.triggered

    def test_find_settings_passes(self):
        r = check_redline("设置在哪里")
        assert not r.triggered

    def test_empty_query_passes(self):
        r = check_redline("")
        assert not r.triggered

    def test_guided_operation_passes(self):
        """指引类操作（不是替操作）应通过"""
        r = check_redline("我该怎么下载这个文件？")
        assert not r.triggered
