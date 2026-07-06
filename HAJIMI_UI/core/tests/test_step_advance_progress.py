from core.step_advance_progress import advance_locate_message


class TestStepAdvanceProgress:
    def test_l4_advance_vision(self):
        msg = advance_locate_message("L4", "advance")
        assert "Vision" in msg

    def test_l3_deferred_advance_vision(self):
        msg = advance_locate_message("L3_DEFERRED", "advance")
        assert "Vision" in msg

    def test_l3_advance_omniparser(self):
        msg = advance_locate_message("L3", "advance")
        assert "OmniParser" in msg

    def test_l2_advance_generic(self):
        msg = advance_locate_message("L2", "advance")
        assert msg == "步骤推进中…"

    def test_rollback_no_vision(self):
        msg = advance_locate_message("L4", "rollback")
        assert "Vision" not in msg
        assert "OmniParser" not in msg
        assert msg == "步骤推进中…"

    def test_advance_without_screenshot_generic(self):
        msg = advance_locate_message("L4", "advance", has_screenshot=False)
        assert msg == "步骤推进中…"

    def test_unknown_route_generic(self):
        msg = advance_locate_message(None, "advance")
        assert msg == "步骤推进中…"
