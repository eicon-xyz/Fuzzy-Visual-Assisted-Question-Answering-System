"""覆盖层坐标：高 DPI 截图 → 逻辑屏幕 rect。"""
from core.annotation_mapper import to_overlay_items


def _build_annotation(cx: int, cy: int, half: int = 24) -> dict:
    return {
        "type": "arrow_highlight",
        "highlight_bbox": [cx - half, cy - half, cx + half, cy + half],
        "arrow_from": [max(0, cx - 120), max(0, cy - 80)],
        "arrow_to": [cx, cy],
        "label_position": [cx - half, max(0, cy - half - 36)],
        "label_text": "目标",
    }


class TestOverlayCoordsHighDpi:
    def test_physical_capture_maps_inside_logical_screen(self):
        """2560x1600 @ DPR=1.5 → mss 物理 3840x2400，overlay rect 应在逻辑屏内。"""
        capture_w, capture_h = 3840, 2400
        logical_w, logical_h = 2560, 1600
        metrics = {
            "logical_w": logical_w,
            "logical_h": logical_h,
            "dpr": 1.5,
            "physical_w": capture_w,
            "physical_h": capture_h,
        }
        ann = _build_annotation(1920, 1200, half=48)
        items = to_overlay_items(
            ann,
            step_index=1,
            screen_size=(capture_w, capture_h),
            ref_size=(capture_w, capture_h),
            screen_metrics=metrics,
        )
        assert items, "expected overlay box item"
        rect = items[0]["rect"]
        assert len(rect) == 4
        x1, y1, x2, y2 = rect
        assert 0 <= x1 < x2 <= logical_w
        assert 0 <= y1 < y2 <= logical_h
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        assert 1200 < cx < 1400
        assert 750 < cy < 850

    def test_l4_upload_to_capture_scaling(self):
        """L4：annotation 在 capture 空间，ref=capture，映射后仍在逻辑屏内。"""
        capture_w, capture_h = 3840, 2400
        upload_w, upload_h = 1280, 800
        logical_w, logical_h = 2560, 1600
        metrics = {
            "logical_w": logical_w,
            "logical_h": logical_h,
            "dpr": 1.5,
            "physical_w": capture_w,
            "physical_h": capture_h,
        }
        ann = _build_annotation(640, 400, half=24)
        items = to_overlay_items(
            ann,
            step_index=1,
            screen_size=(capture_w, capture_h),
            ref_size=(upload_w, upload_h),
            screen_metrics=metrics,
        )
        assert items
        x1, y1, x2, y2 = items[0]["rect"]
        assert 0 <= x1 < x2 <= logical_w
        assert 0 <= y1 < y2 <= logical_h

    def test_advance_ref_sync_to_capture_avoids_offset(self):
        """advance 后 ref=capture（L4 标注在 capture 空间），映射不应按 upload 尺寸缩放。"""
        capture_w, capture_h = 3840, 2400
        upload_w, upload_h = 1280, 800
        logical_w, logical_h = 2560, 1600
        metrics = {
            "logical_w": logical_w,
            "logical_h": logical_h,
            "dpr": 1.5,
            "physical_w": capture_w,
            "physical_h": capture_h,
        }
        ann = _build_annotation(1920, 1200, half=48)

        stale = to_overlay_items(
            ann,
            step_index=2,
            screen_size=(capture_w, capture_h),
            ref_size=(upload_w, upload_h),
            screen_metrics=metrics,
        )
        synced = to_overlay_items(
            ann,
            step_index=2,
            screen_size=(capture_w, capture_h),
            ref_size=(capture_w, capture_h),
            screen_metrics=metrics,
        )
        assert stale and synced
        stale_cx = sum(stale[0]["rect"][0::2]) // 2
        synced_cx = sum(synced[0]["rect"][0::2]) // 2
        assert abs(stale_cx - synced_cx) > 200
        assert 1200 < synced_cx < 1400
