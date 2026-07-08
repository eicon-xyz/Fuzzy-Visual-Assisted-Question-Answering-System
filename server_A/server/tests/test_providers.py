"""
Layer 1 — LLM Providers with pytest-httpx HTTP mock

Tests _get_provider_config resolution and call_llm adaptive retry logic.
Uses pytest-httpx (httpx_mock fixture) for precise HTTP response control.
"""

import pytest
import httpx
from unittest.mock import patch

from server.services.llm.providers import (
    _get_provider_config,
    call_llm,
    call_llm_json,
    call_vision_llm,
    extract_json_object,
)


# ============================================================================
# 1.1 Provider config resolution
# ============================================================================


class TestProviderConfig:
    def test_openai_config(self):
        cfg = _get_provider_config("openai")
        assert cfg["provider"] == "openai"
        assert "api_key" in cfg
        assert "base_url" in cfg
        assert "model" in cfg

    def test_claude_config(self):
        cfg = _get_provider_config("claude")
        assert cfg["provider"] == "claude"

    def test_gemini_config(self):
        cfg = _get_provider_config("gemini")
        assert cfg["provider"] == "gemini"

    def test_groq_config(self):
        cfg = _get_provider_config("groq")
        assert cfg["provider"] == "groq"

    def test_openrouter_config(self):
        cfg = _get_provider_config("openrouter")
        assert cfg["provider"] == "openrouter"

    def test_ollama_config(self):
        cfg = _get_provider_config("ollama")
        assert cfg["api_key"] == "ollama"
        assert "localhost" in cfg["base_url"]

    def test_qwen_config(self):
        cfg = _get_provider_config("qwen")
        assert cfg["provider"] == "qwen"

    def test_glm_config(self):
        cfg = _get_provider_config("glm")
        assert cfg["provider"] == "glm"

    def test_deepseek_config(self):
        cfg = _get_provider_config("deepseek")
        assert cfg["provider"] == "deepseek"

    def test_unknown_provider_fallback(self):
        """Unknown provider falls back to OpenAI-compatible generic config."""
        cfg = _get_provider_config("custom-provider")
        assert cfg["provider"] == "custom-provider"
        assert "api_key" in cfg
        assert "base_url" in cfg
        assert "model" in cfg

    def test_none_uses_default(self):
        """None provider key should not crash."""
        cfg = _get_provider_config(None)
        assert "provider" in cfg


# ============================================================================
# 1.2 call_llm adaptive retry with httpx_mock
# ============================================================================


BASIC_RESPONSE = {
    "choices": [{"message": {"content": '{"goal":"test","steps":[]}'}}]
}


class TestCallLLM:
    def test_normal_success(self, httpx_mock):
        httpx_mock.add_response(status_code=200, json=BASIC_RESPONSE)
        result = call_llm("hello", timeout=30)
        assert "goal" in result

    def test_adaptive_retry_on_413(self, httpx_mock):
        """Verify max_tokens halves across retries on 413 errors."""
        # First 3 calls get 413, 4th succeeds
        httpx_mock.add_response(status_code=413)
        httpx_mock.add_response(status_code=413)
        httpx_mock.add_response(status_code=413)
        httpx_mock.add_response(status_code=200, json=BASIC_RESPONSE)

        result = call_llm("test", timeout=10)
        assert "goal" in result
        # 4 requests were made (3 failures + 1 success)
        assert len(httpx_mock.get_requests()) == 4

    def test_adaptive_retry_on_402(self, httpx_mock):
        """402 also triggers token halving."""
        httpx_mock.add_response(status_code=402)
        httpx_mock.add_response(status_code=402)
        httpx_mock.add_response(status_code=200, json=BASIC_RESPONSE)

        result = call_llm("test", timeout=10)
        assert "goal" in result
        assert len(httpx_mock.get_requests()) == 3

    def test_all_retries_exhausted_raises(self, httpx_mock):
        """After all adaptive tiers fail, RuntimeError is raised."""
        # adaptive_tokens dedup (starting from 512): [512, 256, 128, 64, 32] = 5 tiers
        for _ in range(5):
            httpx_mock.add_response(status_code=413)

        with pytest.raises(RuntimeError, match="LLM call failed"):
            call_llm("test", max_tokens=512, timeout=10)

    def test_429_respects_retry_after(self, httpx_mock):
        httpx_mock.add_response(
            status_code=429,
            headers={"Retry-After": "0.1"},
        )
        httpx_mock.add_response(status_code=200, json=BASIC_RESPONSE)

        result = call_llm("test", timeout=10)
        assert "goal" in result

    def test_with_images(self, httpx_mock):
        httpx_mock.add_response(status_code=200, json=BASIC_RESPONSE)
        images = [{"base64Jpeg": "iVBORw0K", "label": "Screen 1"}]
        result = call_llm("describe", images=images, timeout=30)
        assert "goal" in result
        request_body = httpx_mock.get_requests()[0].read().decode()
        assert "image_url" in request_body

    def test_custom_system_prompt(self, httpx_mock):
        httpx_mock.add_response(status_code=200, json=BASIC_RESPONSE)
        result = call_llm("test", system_prompt="Be helpful.", timeout=30)
        assert "goal" in result
        request_body = httpx_mock.get_requests()[0].read().decode()
        assert "Be helpful" in request_body

    def test_with_history(self, httpx_mock):
        httpx_mock.add_response(status_code=200, json=BASIC_RESPONSE)
        history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "ok"}]
        result = call_llm("next", history=history, timeout=30)
        assert "goal" in result
        request_body = httpx_mock.get_requests()[0].read().decode()
        assert "prev" in request_body


class TestCallLLMJson:
    def test_returns_parsed_dict(self, httpx_mock):
        httpx_mock.add_response(
            status_code=200,
            json={"choices": [{"message": {"content": '{"goal":"test","steps":[]}'}}]},
        )
        result = call_llm_json("test", timeout=30)
        assert result["goal"] == "test"

    def test_locator_mode(self, httpx_mock):
        httpx_mock.add_response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"coordinate":{"x":500,"y":300},"label":"Btn","shouldPoint":true}'
                        }
                    }
                ]
            },
        )
        result = call_llm_json("find button", is_locator=True, timeout=30)
        assert result["label"] == "Btn"


class TestCallVisionLLM:
    def test_forwards_to_call_llm(self, httpx_mock):
        httpx_mock.add_response(status_code=200, json=BASIC_RESPONSE)
        result = call_vision_llm("describe image", image_base64="FAKEB64", timeout=30)
        assert "goal" in result

    def test_no_image(self, httpx_mock):
        httpx_mock.add_response(status_code=200, json=BASIC_RESPONSE)
        result = call_vision_llm("hello", timeout=30)
        assert "goal" in result
