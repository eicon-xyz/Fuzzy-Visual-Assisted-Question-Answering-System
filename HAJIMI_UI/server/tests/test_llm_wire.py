"""LLM wire API 单元测试。"""
from server.services.l4.point_parser import parse_point_tag
from server.services.llm.wire import extract_responses_text, resolve_wire_api


def test_resolve_wire_api_daseinai_auto():
    assert resolve_wire_api("https://www.daseinai.xyz/v1") == "responses"


def test_extract_responses_output_text():
    data = {"output_text": "hello", "output": []}
    assert extract_responses_text(data) == "hello"


def test_extract_responses_output_array():
    data = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "step 1"}],
            }
        ]
    }
    assert extract_responses_text(data) == "step 1"


def test_extract_responses_reasoning_with_point():
    data = {
        "output": [
            {
                "type": "reasoning",
                "summary": "Analyzing screenshot for save button",
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Found it [POINT:500,320:Save]",
                    }
                ],
            },
        ]
    }
    text = extract_responses_text(data)
    assert "Analyzing screenshot" in text
    assert "[POINT:500,320:Save]" in text
    _, coord, label = parse_point_tag(text)
    assert coord == {"x": 500.0, "y": 320.0}
    assert label == "Save"


def test_extract_responses_point_only_in_reasoning():
    data = {
        "output": [
            {
                "type": "reasoning",
                "content": [{"type": "text", "text": "Target at [POINT:120,800:Start]"}],
            },
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "Done."}],
            },
        ]
    }
    text = extract_responses_text(data)
    _, coord, _ = parse_point_tag(text)
    assert coord == {"x": 120.0, "y": 800.0}
