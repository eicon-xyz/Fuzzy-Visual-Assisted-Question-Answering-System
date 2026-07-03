"""
步骤完成度评估器（参考 OpenGuider evaluator-chain.js）

在 /step advance 时，可选地先截图评估用户是否真的完成了当前步骤。
通过环境变量 HAJIMI_EVALUATE_STEPS=1 启用。

输出: {status, confidence, rationale, suggested_action, assistant_response}
"""

import json
from typing import Optional

from server.config import settings
from server.services.llm.client import call_llm, parse_json_response

EVALUATOR_SYSTEM_PROMPT = (
    "你评估用户是否已完成当前 UI 操作步骤。"
    "保守判断：截图不能明确证明成功则判 not_done 或 uncertain。"
    "仅当明显偏离流程或卡住时才建议 replan。"
    "总是返回合法 JSON。"
)

EVALUATOR_TEMPLATE = """目标: {goal}
步骤标题: {step_title}
步骤指引: {instruction}
成功标准: {success_criteria}
用户备注: {user_note}

返回 JSON:
{{
  "status": "done|not_done|blocked|uncertain",
  "confidence": 0.0,
  "rationale": "简短理由",
  "suggested_action": "advance|repeat_guidance|replan",
  "assistant_response": "给用户的简短反馈"
}}
"""


class StepEvaluator:
    """步骤完成度评估器"""

    @staticmethod
    def evaluate(
        goal: str,
        step_title: str,
        instruction: str,
        success_criteria: str = "",
        user_note: str = "",
        image_base64: Optional[str] = None,
    ) -> dict:
        """
        评估用户是否完成了当前步骤。

        Args:
            goal: 蓝图目标
            step_title: 当前步骤标题
            instruction: 步骤指引
            success_criteria: 成功判断标准
            user_note: 用户备注
            image_base64: 当前截图 Base64

        Returns:
            评估结果字典。失败时默认返回 done（不阻塞用户）。
        """
        if not settings.EVALUATE_STEPS or not image_base64:
            return _fallback_result()

        prompt = EVALUATOR_TEMPLATE.format(
            goal=goal,
            step_title=step_title,
            instruction=instruction,
            success_criteria=success_criteria or "由评估器自行判断",
            user_note=user_note or "无",
        )

        try:
            content = call_llm(
                query=prompt,
                image_base64=image_base64,
                system_prompt=EVALUATOR_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=500,
            )

            if isinstance(content, str):
                parsed = parse_json_response(content)
                if parsed and "status" in parsed:
                    return {
                        "status": parsed.get("status", "uncertain"),
                        "confidence": float(parsed.get("confidence", 0.5)),
                        "rationale": parsed.get("rationale", ""),
                        "suggested_action": parsed.get("suggested_action", "advance"),
                        "assistant_response": parsed.get("assistant_response", ""),
                    }
        except Exception:
            pass

        return _fallback_result()


def _fallback_result() -> dict:
    """默认通过，不阻塞用户"""
    return {
        "status": "done",
        "confidence": 0.8,
        "rationale": "evaluator 未启用或调用失败，默认通过",
        "suggested_action": "advance",
        "assistant_response": "",
    }
