"""桌面图标定位上传分辨率。"""
from core.screen_utils import (
    get_locate_upload_max_side,
    is_desktop_icon_step,
)


class TestLocateUploadSide:
    def test_desktop_chrome_uses_1920_min(self):
        text = "点击 Google Chrome 桌面快捷方式"
        assert is_desktop_icon_step(text)
        assert get_locate_upload_max_side(text) >= 1920

    def test_generic_step_uses_config(self):
        text = "点击保存按钮"
        assert not is_desktop_icon_step(text)
        side = get_locate_upload_max_side(text)
        assert 720 <= side <= 1920

    def test_recycle_bin_desktop(self):
        text = "双击桌面回收站图标"
        assert is_desktop_icon_step(text)
        assert get_locate_upload_max_side(text) >= 1920
