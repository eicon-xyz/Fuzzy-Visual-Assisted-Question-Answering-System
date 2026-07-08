"""Tests for spatial relation computation in OmniParser client."""

from server.services.omniparser_client import _compute_spatial_relations
from server.models.schemas import UIElement


def make_el(eid, x1, y1, x2, y2):
    return UIElement(
        element_id=str(eid),
        bbox=[x1, y1, x2, y2],
        element_type="text",
        text=f"el{eid}",
        confidence=0.9,
        center=[(x1 + x2) // 2, (y1 + y2) // 2],
    )


def test_same_row_detection():
    """Two elements on the same y-band should be mutual left/right neighbors."""
    e1 = make_el(1, 100, 100, 200, 150)  # y: 100-150
    e2 = make_el(2, 250, 105, 350, 155)  # y: 105-155, high y-overlap = same row
    _compute_spatial_relations([e1, e2])
    assert e1.right_elem_ids == ["2"]
    assert e2.left_elem_ids == ["1"]


def test_different_rows_no_horizontal_rel():
    """Elements far apart vertically should NOT be left/right neighbors."""
    e1 = make_el(1, 100, 100, 200, 150)
    e2 = make_el(2, 250, 500, 350, 550)  # completely different row
    _compute_spatial_relations([e1, e2])
    assert e1.right_elem_ids == []
    assert e2.left_elem_ids == []


def test_top_bottom_relations():
    """Elements in the same column (x-axis overlap) should get top/bottom relations."""
    e1 = make_el(1, 100, 50, 300, 120)
    e2 = make_el(2, 150, 150, 250, 250)
    _compute_spatial_relations([e1, e2])
    assert "2" in e1.bottom_elem_ids
    assert "1" in e2.top_elem_ids


def test_top_bottom_x_axis_overlap():
    """Top/bottom requires x-axis overlap (share horizontal space), not y-axis overlap.

    The implementation uses x-axis IoU >= 0.1, meaning elements must be in
    the same approximate column to be considered top/bottom neighbors. This
    test explicitly documents that criterion.
    """
    # Case 1: elements with x-overlap should be top/bottom neighbors
    e_top = make_el(1, 100, 50, 300, 120)     # spans x: 100-300
    e_bot = make_el(2, 150, 150, 250, 250)    # spans x: 150-250, x-overlap with e_top
    _compute_spatial_relations([e_top, e_bot])
    assert "2" in e_top.bottom_elem_ids
    assert "1" in e_bot.top_elem_ids

    # Case 2: elements with vertical overlap (share y-space) but NO x-overlap
    # should NOT be top/bottom neighbors — they are side-by-side, not above/below.
    e_left = make_el(3, 100, 100, 200, 300)    # y: 100-300
    e_right = make_el(4, 300, 100, 400, 300)   # y: 100-300, no x-overlap
    _compute_spatial_relations([e_left, e_right])
    assert e_left.top_elem_ids == []
    assert e_left.bottom_elem_ids == []
    assert e_right.top_elem_ids == []
    assert e_right.bottom_elem_ids == []


def test_capped_neighbors():
    """Neighbor lists should be capped at specified limits."""
    elements = []
    for i in range(10):
        elements.append(make_el(i, i * 80, 100, i * 80 + 60, 150))
    _compute_spatial_relations(elements)
    for el in elements:
        assert len(el.left_elem_ids) <= 5
        assert len(el.right_elem_ids) <= 5
    # Ensure at least one element has neighbors (regression guard)
    total_left = sum(len(el.left_elem_ids) for el in elements)
    total_right = sum(len(el.right_elem_ids) for el in elements)
    assert total_left > 0 or total_right > 0


def test_empty_elements():
    """Empty element list should not crash."""
    _compute_spatial_relations([])


def test_single_element():
    """Single element should have no neighbors."""
    e1 = make_el(1, 100, 100, 200, 150)
    _compute_spatial_relations([e1])
    assert e1.left_elem_ids == []
    assert e1.right_elem_ids == []
    assert e1.top_elem_ids == []
    assert e1.bottom_elem_ids == []


def test_degenerate_bbox_no_crash():
    """Element with zero-height bbox should not crash.

    The degenerate element is skipped, so e2 should have no left/right
    neighbors since e1 is the only other element."""
    e1 = make_el(1, 100, 100, 200, 100)  # zero height
    e2 = make_el(2, 250, 105, 350, 155)
    _compute_spatial_relations([e1, e2])  # should not raise
    assert e2.left_elem_ids == []
    assert e2.right_elem_ids == []


def test_element_id_strips_tilde():
    """parse_screenshot_full should strip ~ prefix from element IDs."""
    # This test requires mocking the HTTP call — see integration tests.
    pass  # placeholder for Task 9 integration test
