import pytest
from unittest.mock import patch, MagicMock
from server.services.planning.planner import plan_steps, PlanningResult

MOCK_LLM_RESPONSE = '''```json
{
  "goal": "打开网易云音乐并播放周杰伦的歌",
  "steps": [
    {"step_index": 1, "instruction": "打开网易云音乐应用"},
    {"step_index": 2, "instruction": "在搜索框中搜索'周杰伦'"},
    {"step_index": 3, "instruction": "点击播放第一首歌曲"}
  ]
}
```'''

def test_plan_steps_returns_structured_output():
    with patch("server.services.planning.planner.call_llm", return_value=MOCK_LLM_RESPONSE):
        result = plan_steps("打开网易云音乐，搜索周杰伦，播放第一首")

    assert isinstance(result, PlanningResult)
    assert result.goal == "打开网易云音乐并播放周杰伦的歌"
    assert len(result.steps) == 3
    assert result.steps[0].step_index == 1
    assert result.steps[0].instruction == "打开网易云音乐应用"
    assert result.steps[1].instruction == "在搜索框中搜索'周杰伦'"
    assert result.steps[2].instruction == "点击播放第一首歌曲"

def test_plan_steps_retries_on_malformed_json():
    bad_response = "not json at all {"
    with patch("server.services.planning.planner.call_llm") as mock_llm:
        mock_llm.side_effect = [bad_response, MOCK_LLM_RESPONSE]
        result = plan_steps("open calculator")
    assert mock_llm.call_count == 2
    assert len(result.steps) > 0

def test_plan_steps_fails_after_two_retries():
    with patch("server.services.planning.planner.call_llm", return_value="garbage {{{"):
        with pytest.raises(ValueError, match="Planning Agent"):
            plan_steps("do something")
