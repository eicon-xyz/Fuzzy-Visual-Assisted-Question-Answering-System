"""Tests for _filter_elements_for_llm — hides coordinates/scores from LLM context."""
from server.services.omniparser_client import _filter_elements_for_llm
from server.models.schemas import UIElement


def test_llm_filter_hides_coordinates():
    el = UIElement(element_id="3", bbox=[100, 200, 300, 400], element_type="icon",
                   text="search", confidence=0.95, center=[200, 300],
                   left_elem_ids=["2"], right_elem_ids=["5"],
                   top_elem_ids=[], bottom_elem_ids=["8"])
    result = _filter_elements_for_llm([el])
    assert len(result) == 1
    r = result[0]
    assert r["id"] == "3"
    assert r["content"] == "search"
    assert r["left_ids"] == ["2"]
    assert r["right_ids"] == ["5"]
    assert r["top_ids"] == []
    assert r["bottom_ids"] == ["8"]
    # MUST NOT contain:
    assert "bbox" not in r
    assert "center" not in r
    assert "element_id" not in r
    assert "score" not in r
    assert "confidence" not in r
    assert "element_type" not in r


def test_llm_filter_empty_list():
    """Should return empty list when given empty list."""
    result = _filter_elements_for_llm([])
    assert result == []


def test_llm_filter_handles_none_text():
    """Should convert None text to empty string."""
    el = UIElement(element_id="1", bbox=[0, 0, 10, 10], element_type="icon",
                   text=None, confidence=0.9, center=[5, 5])
    result = _filter_elements_for_llm([el])
    assert result[0]["content"] == ""
