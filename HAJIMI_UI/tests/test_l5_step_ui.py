"""L5 step UI: StepCard rows, screenshot strip, SSE buffer."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

HAJIMI_ROOT = Path(__file__).resolve().parents[1]
if str(HAJIMI_ROOT) not in sys.path:
    sys.path.insert(0, str(HAJIMI_ROOT))

from ui.native.l5_step_row import L5StepRow
from ui.native.l5_timeline import L5StepTimelineWidget

# 1x1 PNG
TINY_PNG_B64 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def timeline(qapp):
    widget = L5StepTimelineWidget()
    yield widget
    widget.deleteLater()


def test_plan_fingerprint_stable():
    steps = [{"instruction": "打开记事本"}, {"instruction": "输入文字"}]
    assert L5StepTimelineWidget.plan_fingerprint(steps) == (
        "打开记事本",
        "输入文字",
    )


def test_reset_plan_preserves_rows_on_same_fingerprint(timeline):
    steps = [{"instruction": "步骤 A"}, {"instruction": "步骤 B"}]
    timeline.reset_plan(steps)
    timeline.handle_sse(
        "screenshot_updated",
        {"step_index": 1, "annotated_image": TINY_PNG_B64},
    )
    assert timeline._rows[0].screenshot_count == 1
    timeline.reset_plan(steps)
    assert timeline._rows[0].screenshot_count == 1
    assert timeline.total_steps == 2


def test_pending_sse_replayed_after_reset_plan(timeline):
    timeline.handle_sse(
        "screenshot_updated",
        {"step_index": 1, "annotated_image": TINY_PNG_B64},
    )
    timeline.reset_plan([{"instruction": "一步"}])
    assert timeline._rows[0].screenshot_count == 1


def test_screenshot_strip_hidden_without_images(qapp):
    row = L5StepRow(0, "测试步骤")
    assert row.screenshot_count == 0
    assert row._shot_frame.isHidden()
    row.deleteLater()


def test_multiple_screenshots_per_step(qapp):
    row = L5StepRow(0, "测试步骤")
    assert row.add_screenshot(TINY_PNG_B64)
    assert row.add_screenshot(TINY_PNG_B64)
    assert row.screenshot_count == 2
    assert not row._shot_frame.isHidden()
    row.deleteLater()


def test_sync_active_index_without_reset(timeline):
    steps = [{"instruction": "一"}, {"instruction": "二"}]
    timeline.reset_plan(steps)
    timeline.handle_sse("log", {"step_index": 1, "message": "first log"})
    timeline.sync_active_index(1)
    assert timeline._rows[0]._card.status == "done"
    assert timeline._rows[1]._card.status == "active"
    assert "first log" in timeline._rows[0]._log_area.toPlainText()


def test_no_screenshot_on_empty_b64(timeline):
    timeline.reset_plan([{"instruction": "一步"}])
    timeline.handle_sse("screenshot_updated", {"step_index": 1, "annotated_image": ""})
    assert timeline._rows[0].screenshot_count == 0
    assert timeline._rows[0]._shot_frame.isHidden()
