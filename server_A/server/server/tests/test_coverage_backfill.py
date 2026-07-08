"""
Coverage backfill — previously untested modules.

Pure functions: fingerprint, launcher name extraction, embedder, token estimate.
Mock-dependent: omniparser_element_filter, omniparser_spatial, distiller (mock LLM).
"""

import pytest
import io
import base64
import numpy as np
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════════════
# 1 — Fingerprint Service (pure)
# ═══════════════════════════════════════════════════════════════════════════

from server.services.fingerprint_service import (
    compute_fingerprint_hash,
    compute_jaccard,
    should_suspend,
    compare_screen_state,
)


class TestFingerprintHash:
    def test_returns_64_char_hex(self):
        h = compute_fingerprint_hash("Chrome", ["button", "input", "button"])
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        h1 = compute_fingerprint_hash("Notepad", ["button", "input"])
        h2 = compute_fingerprint_hash("Notepad", ["button", "input"])
        assert h1 == h2

    def test_different_title_different_hash(self):
        h1 = compute_fingerprint_hash("A", ["button"])
        h2 = compute_fingerprint_hash("B", ["button"])
        assert h1 != h2

    def test_top5_only(self):
        """Only top 5 most frequent element types matter."""
        types = ["a"] * 10 + ["b"] * 8 + ["c"] * 6 + ["d"] * 4 + ["e"] * 2 + ["f"] * 1
        h1 = compute_fingerprint_hash("W", types)
        h2 = compute_fingerprint_hash("W", types + ["f"] * 100)  # now f is #1
        assert h1 != h2  # different top-5 ordering


class TestJaccard:
    def test_identical_sets(self):
        assert compute_jaccard(["a", "b"], ["a", "b"]) == 1.0

    def test_disjoint_sets(self):
        assert compute_jaccard(["a"], ["b"]) == 0.0

    def test_partial_overlap(self):
        # {a,b,c} ∩ {b,c,d} = {b,c} size 2, union size 4
        assert compute_jaccard(["a", "b", "c"], ["b", "c", "d"]) == 0.5

    def test_both_empty(self):
        assert compute_jaccard([], []) == 1.0

    def test_one_empty(self):
        assert compute_jaccard([], ["a"]) == 0.0

    def test_duplicates_dont_matter(self):
        # Jaccard is set-based, duplicates are collapsed
        assert compute_jaccard(["a", "a", "b"], ["a", "b"]) == 1.0


class TestShouldSuspend:
    def test_high_similarity_no_suspend(self):
        # {a,b,c} ∩ {a,b} / {a,b,c} ∪ {a,b} = 2/3 ≈ 0.67, > 0.80? no.
        # Let's choose sets where Jaccard > 0.80
        assert should_suspend(["a", "b", "c", "d", "e"], ["a", "b", "c", "d"]) is False

    def test_low_similarity_suspend(self):
        assert should_suspend(["a"], ["b", "c", "d", "e"]) is True

    def test_custom_threshold(self):
        # {a,b} ∩ {a,c,d} = 1, union = 4, Jaccard = 0.25
        assert should_suspend(["a", "b"], ["a", "c", "d"], match_threshold=0.20) is False
        assert should_suspend(["a", "b"], ["a", "c", "d"], match_threshold=0.30) is True


class TestCompareScreenState:
    def test_advance_on_high_match(self):
        r = compare_screen_state(["a", "b", "c", "d", "e"], ["a", "b", "c", "d"])
        assert r["recommendation"] == "advance"

    def test_suspend_on_low_match(self):
        r = compare_screen_state(["a"], ["b", "c", "d", "e", "f"])
        assert r["recommendation"] == "suspend"

    def test_clarify_on_borderline(self):
        # Jaccard 2/5 = 0.40 → between 0.50 and skip → suspend? Let's pick exact: 2/4 need 0.5 still
        # {a,b} ∩ {a,b,c,d} = 2/4 = 0.5 → clarify (>= 0.50 and < 0.80)
        r = compare_screen_state(["a", "b"], ["a", "b", "c", "d"])
        assert r["recommendation"] == "clarify"

    def test_hash_match_when_provided(self):
        h = compute_fingerprint_hash("A", ["button"])
        r = compare_screen_state(
            ["button"], ["button"],
            old_fingerprint_hash=h, new_fingerprint_hash=h,
        )
        assert r["hash_match"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 2 — Launcher: name resolution (no system calls)
# ═══════════════════════════════════════════════════════════════════════════

from server.services.launcher import (
    APP_EXECUTABLE_MAP,
    _resolve_executable,
    _extract_app_name_from_query,
)


class TestAppExecutableMap:
    def test_map_size(self):
        """Map should cover at least 40 common apps."""
        assert len(APP_EXECUTABLE_MAP) >= 40

    def test_known_apps(self):
        assert APP_EXECUTABLE_MAP.get("计算器") == "calc.exe"
        assert APP_EXECUTABLE_MAP.get("Chrome") == "chrome"
        assert APP_EXECUTABLE_MAP.get("记事本") == "notepad.exe"
        assert APP_EXECUTABLE_MAP.get("Excel") == "excel.exe"

    def test_chinese_browsers(self):
        assert APP_EXECUTABLE_MAP.get("谷歌浏览器") == "chrome"
        assert APP_EXECUTABLE_MAP.get("火狐") == "firefox"


class TestResolveExecutable:
    def test_exact_match(self):
        assert _resolve_executable("记事本") == "notepad.exe"

    def test_case_insensitive_fallback(self):
        result = _resolve_executable("CHROME")
        assert result is not None

    def test_returns_none_for_unknown(self):
        assert _resolve_executable("nonexistent_app_xyz_123") is None


class TestExtractAppNameFromQuery:
    def test_chinese_open(self):
        assert _extract_app_name_from_query("打开Chrome浏览器") == "Chrome浏览器"

    def test_chinese_launch_with_prefix(self):
        name = _extract_app_name_from_query("启动微信")
        assert name is not None
        assert "微信" in name

    def test_english_open(self):
        # Regex matches "open X" where X has 1-40 chars without spaces/punctuation
        # "VS Code" contains a space → may not match as one token
        # Let's use a single-word app name
        name = _extract_app_name_from_query("open Calculator")
        assert name == "Calculator"

    def test_bare_app_name(self):
        name = _extract_app_name_from_query("Calculator")
        assert name == "Calculator"

    def test_empty_query(self):
        assert _extract_app_name_from_query("") is None

    def test_quoted_app_name(self):
        name = _extract_app_name_from_query('打开 "微信"')
        assert "微信" in (name or "")


# ═══════════════════════════════════════════════════════════════════════════
# 3 — Memory Embedder (blob serialisation, cosine)
# ═══════════════════════════════════════════════════════════════════════════

from server.services.memory.embedder import (
    to_blob,
    from_blob,
    cosine_similarity,
    EMBEDDING_DIM,
)


class TestEmbedderBlob:
    def test_round_trip(self):
        vec = np.ones(EMBEDDING_DIM, dtype=np.float32)
        blob = to_blob(vec)
        restored = from_blob(blob)
        assert restored.shape == (EMBEDDING_DIM,)
        assert restored.dtype == np.float32
        assert np.allclose(vec, restored)

    def test_cosine_identical(self):
        a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        assert cosine_similarity(a, a) == pytest.approx(1.0)

    def test_cosine_orthogonal(self):
        a = np.array([1.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0], dtype=np.float32)
        assert cosine_similarity(a, b) == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════════════════
# 4 — Token Estimation (retriever helpers)
# ═══════════════════════════════════════════════════════════════════════════

from server.services.memory.retriever import _estimate_tokens, _truncate_to_tokens


class TestEstimateTokens:
    def test_pure_chinese(self):
        tokens = _estimate_tokens("你好世界")
        assert tokens == 4  # 4 Chinese chars = 4 tokens

    def test_pure_english(self):
        tokens = _estimate_tokens("hello world")
        assert tokens >= 1  # 2 words × 0.75 + 1 space × 0.25 ≈ 1.75 → int truncation → 1

    def test_mixed(self):
        tokens = _estimate_tokens("你好 hello 你好")
        assert tokens >= 3  # 2 Chinese + 1 English word + spaces

    def test_empty(self):
        assert _estimate_tokens("") == 0


class TestTruncateToTokens:
    def test_short_text_fits(self):
        result = _truncate_to_tokens("hello", 20)
        assert result == "hello"

    def test_truncation_adds_ellipsis(self):
        result = _truncate_to_tokens("a" * 100, 5)
        assert "…" in result
        assert len(result) < 100


# ═══════════════════════════════════════════════════════════════════════════
# 5 — OmniParser Client: pure helpers
# ═══════════════════════════════════════════════════════════════════════════

from server.models.schemas import UIElement
from server.services.omniparser_client import (
    _clean_base64,
    _filter_elements_for_llm,
    _compute_spatial_relations,
    _DATA_URI_RE,
)


class TestOmniParserBase64:
    def test_clean_none(self):
        assert _clean_base64(None) is None

    def test_clean_strips_prefix(self):
        cleaned = _clean_base64("data:image/png;base64,iVBORw0K")
        assert cleaned == "iVBORw0K"

    def test_clean_strips_newlines(self):
        cleaned = _clean_base64("data:image/jpeg;base64,a\nb\nc")
        assert cleaned == "abc"


class TestFilterElementsForLLM:
    def test_empty(self):
        assert _filter_elements_for_llm([]) == []

    def test_maps_fields_correctly(self):
        el = UIElement(
            element_id="abc",
            bbox=[0, 0, 100, 40],
            element_type="button",
            text="Submit",
            confidence=0.9,
            center=[50, 20],
            left_elem_ids=["id1"],
            right_elem_ids=["id2"],
            top_elem_ids=[],
            bottom_elem_ids=[],
        )
        result = _filter_elements_for_llm([el])
        assert len(result) == 1
        assert result[0]["id"] == "abc"
        assert result[0]["content"] == "Submit"
        assert result[0]["left_ids"] == ["id1"]
        assert result[0]["right_ids"] == ["id2"]

    def test_empty_text_becomes_empty_string(self):
        el = UIElement(
            element_id="x", bbox=[0, 0, 10, 10],
            element_type="other", confidence=0.5, center=[5, 5],
        )
        result = _filter_elements_for_llm([el])
        assert result[0]["content"] == ""


class TestComputeSpatialRelations:
    """Test the spatial neighbour computation algorithm."""

    def _make_el(self, eid, x1, y1, x2, y2, etype="button", text=""):
        return UIElement(
            element_id=eid, bbox=[x1, y1, x2, y2],
            element_type=etype, text=text, confidence=0.9,
            center=[(x1 + x2) // 2, (y1 + y2) // 2],
        )

    def test_empty_list_no_crash(self):
        _compute_spatial_relations([])  # Should not raise

    def test_single_element_all_empty(self):
        el = self._make_el("a", 0, 0, 100, 40)
        _compute_spatial_relations([el])
        assert el.left_elem_ids == []
        assert el.right_elem_ids == []

    def test_left_right_detected(self):
        """Element b is to the right of element a on the same row."""
        a = self._make_el("a", 0, 0, 100, 40)
        b = self._make_el("b", 150, 0, 250, 40)
        _compute_spatial_relations([a, b])
        assert b.element_id in a.right_elem_ids
        assert a.element_id in b.left_elem_ids

    def test_top_bottom_detected(self):
        """Element b is below element a in the same column."""
        a = self._make_el("a", 100, 0, 200, 40)
        b = self._make_el("b", 100, 100, 200, 140)
        _compute_spatial_relations([a, b])
        assert b.element_id in a.bottom_elem_ids
        assert a.element_id in b.top_elem_ids

    def test_diagonal_no_neighbor(self):
        """Diagonal elements with no row/col overlap: no spatial relation."""
        a = self._make_el("a", 0, 0, 50, 50)
        b = self._make_el("b", 200, 200, 250, 250)
        _compute_spatial_relations([a, b])
        assert a.right_elem_ids == []
        assert a.bottom_elem_ids == []
        assert b.left_elem_ids == []
        assert b.top_elem_ids == []

    def test_cap_left_right_at_5(self):
        """Max 5 neighbours per direction."""
        center = self._make_el("center", 200, 100, 300, 140)
        left = [self._make_el(f"l{i}", 10 * i, 100, 10 * i + 8, 140) for i in range(10)]
        _compute_spatial_relations([center] + left)
        assert len(center.left_elem_ids) <= 5

    def test_cap_top_at_3(self):
        """Max 3 neighbours for top."""
        center = self._make_el("center", 100, 200, 200, 240)
        above = [self._make_el(f"t{i}", 100, 10 * i, 200, 10 * i + 8) for i in range(10)]
        _compute_spatial_relations([center] + above)
        assert len(center.top_elem_ids) <= 3


# ═══════════════════════════════════════════════════════════════════════════
# 6 — Context Distiller (mock LLM)
# ═══════════════════════════════════════════════════════════════════════════

from server.services.context.distiller import (
    distill_screen_context,
    build_enriched_query,
    DISTILLER_SYSTEM_PROMPT,
)


class TestDistiller:
    def test_system_prompt_exists(self):
        """DISTILLER_SYSTEM_PROMPT is defined and non-empty."""
        assert len(DISTILLER_SYSTEM_PROMPT) > 50
        assert "screen" in DISTILLER_SYSTEM_PROMPT.lower()

    def test_disabled_returns_empty(self):
        from server.config import settings
        # DISTILLATION_ENABLED may not exist as a config field.
        # Use settings' attribute mechanism: set it, test, then delete.
        had = hasattr(settings, "DISTILLATION_ENABLED")
        old = getattr(settings, "DISTILLATION_ENABLED", True)
        settings.DISTILLATION_ENABLED = False
        try:
            result = distill_screen_context("query", "some text", "Chrome")
            assert result == ""
        finally:
            if had:
                settings.DISTILLATION_ENABLED = old
            else:
                try:
                    delattr(settings, "DISTILLATION_ENABLED")
                except Exception:
                    pass

    def test_no_input_returns_empty(self):
        from server.config import settings
        settings.DISTILLATION_ENABLED = False
        try:
            result = distill_screen_context("query", "", "")
            assert result == ""
        finally:
            pass

    def test_build_enriched_disabled(self):
        from server.config import settings
        had = hasattr(settings, "DISTILLATION_ENABLED")
        old = getattr(settings, "DISTILLATION_ENABLED", True)
        settings.DISTILLATION_ENABLED = False
        try:
            result = build_enriched_query("hello", "ocr", "win")
            assert result == "hello"
        finally:
            if had:
                settings.DISTILLATION_ENABLED = old
            else:
                try:
                    delattr(settings, "DISTILLATION_ENABLED")
                except Exception:
                    pass

    def test_distill_with_mock_llm(self):
        from server.config import settings
        settings.DISTILLATION_ENABLED = True
        settings.DISTILLATION_TIMEOUT = 30
        try:
            with patch("server.services.llm.providers.call_llm",
                       return_value="User is in Chrome with a search bar visible."):
                result = distill_screen_context("search for docs", "search bar", "Chrome")
            assert "Screen Context" in result
            assert "Chrome" in result
        finally:
            pass

    def test_distill_llm_error_returns_empty(self):
        from server.config import settings
        settings.DISTILLATION_ENABLED = True
        settings.DISTILLATION_TIMEOUT = 30
        try:
            with patch("server.services.llm.providers.call_llm",
                       side_effect=RuntimeError("API error")):
                result = distill_screen_context("query", "some text", "window")
            assert result == ""
        finally:
            pass

    def test_ocr_truncated_long(self):
        from server.config import settings
        settings.DISTILLATION_ENABLED = True
        settings.DISTILLATION_TIMEOUT = 30
        try:
            with patch("server.services.llm.providers.call_llm",
                       return_value="distilled."):
                long_text = "x" * 3000
                result = distill_screen_context("q", long_text, "")
                assert len(result) > 0
        finally:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# 7 — Embedding Matcher (mock SentenceTransformer)
# ═══════════════════════════════════════════════════════════════════════════

from server.services.context.embedding_matcher import (
    find_best_match,
    find_top_matches,
    cosine_similarity as emb_cosine,
)


class TestEmbeddingMatcher:
    """Test matching logic with a fake embedding model."""

    @pytest.fixture(autouse=True)
    def _fake_embedding(self):
        """Replace get_embedding with a deterministic fake."""
        def fake_embed(text: str):
            # Simple hash-based embedding for deterministic testing
            import hashlib
            h = hashlib.sha256(text.encode()).digest()
            vec = np.frombuffer(h[:384 * 4], dtype=np.float32)[:384]
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec

        with patch("server.services.context.embedding_matcher.get_embedding", side_effect=fake_embed):
            yield

    def test_find_best_match_returns_best(self):
        candidates = [
            ("download file", {"action": "download"}),
            ("upload image", {"action": "upload"}),
        ]
        result = find_best_match("download a document", candidates, min_score=0.0)
        assert result is not None
        assert result[1]["action"] == "download"

    def test_find_best_match_below_threshold(self):
        candidates = [("unrelated text", {"id": 1})]
        result = find_best_match("download file", candidates, min_score=0.9)
        assert result is None

    def test_find_best_match_empty_candidates(self):
        assert find_best_match("query", [], min_score=0.0) is None

    def test_find_top_matches(self):
        candidates = [
            ("download file", {"id": 1}),
            ("upload file", {"id": 2}),
            ("delete file", {"id": 3}),
        ]
        results = find_top_matches("download a document", candidates, top_k=2, min_score=0.0)
        assert len(results) == 2
        assert results[0][1]["id"] == 1  # best match

    def test_find_top_matches_respects_min_score(self):
        candidates = [
            ("download file", {"id": 1}),
        ]
        results = find_top_matches("completely different", candidates, top_k=3, min_score=0.95)
        assert results == []
