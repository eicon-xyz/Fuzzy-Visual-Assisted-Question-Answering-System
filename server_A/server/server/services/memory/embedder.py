"""
Embedding 薄封装 — 复用 embedding_matcher 的编码 + DB blob 读写。

自动降级：优先使用 sentence-transformers (384-dim semantic)，
不可用时回退到 sklearn TF-IDF (256-dim count vector)。
全不可用时返回 None。
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

FALLBACK_DIM = 256
_target_dim = 384  # Will be updated after first successful encode


def get_target_dim() -> int:
    """Get the actual embedding dimension (may be 256 if using fallback)."""
    global _target_dim
    return _target_dim


# ── Primary: sentence-transformers / all-MiniLM-L6-v2 ─────────


def _try_sentence_transformers(text: str) -> Optional[np.ndarray]:
    """Try sentence-transformers (needs torch/onnx). Returns None if unavailable."""
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
        vec = _model.encode(text, normalize_embeddings=True)
        global _target_dim
        _target_dim = 384
        return vec
    except Exception as e:
        logger.debug("sentence-transformers unavailable: %s", e)
        return None


# ── Fallback: sklearn TF-IDF (pure Python, no native deps) ───


_sklearn_model = None
_sklearn_lock = threading.Lock()


def _get_sklearn_model():
    """Lazy-load the TF-IDF vectorizer as a simple embedding fallback."""
    global _sklearn_model
    if _sklearn_model is None:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            # Pre-train on a small corpus of common task phrases
            corpus = [
                "打开计算器 打开记事本 打开画图 打开设置",
                "关闭窗口 最小化 最大化 退出",
                "新建文件 打开文件 保存 另存为",
                "复制 粘贴 剪切 删除 撤销",
                "浏览器 Chrome Edge 网页搜索",
                "微信 QQ 钉钉 邮件 发送消息",
                "Word Excel WPS PDF 文档",
                "截图 录屏 录制 截屏",
                "下载 上传 导出 导入",
                "关机 重启 休眠 锁屏",
            ]
            _sklearn_model = TfidfVectorizer(
                max_features=FALLBACK_DIM,
                analyzer="char_wb",
                ngram_range=(2, 4),
                sublinear_tf=True,
            )
            _sklearn_model.fit(corpus)
            logger.info("TF-IDF fallback embedder loaded (dim=%d)", FALLBACK_DIM)
        except Exception as e:
            logger.warning("Failed to load sklearn TF-IDF: %s", e)
            _sklearn_model = False
    return _sklearn_model if _sklearn_model is not False else None


def encode(text: str) -> Optional[np.ndarray]:
    """Encode text to a normalized embedding vector.

    Tries sentence-transformers first (384-dim semantic).
    Falls back to sklearn TF-IDF (256-dim char-ngram).
    Returns None if both are unavailable.
    """
    # Try primary
    vec = _try_sentence_transformers(text)
    if vec is not None:
        return vec

    # Try fallback
    model = _get_sklearn_model()
    if model is not None:
        try:
            vec = model.transform([text]).toarray().astype(np.float32)[0]
            # Normalize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            global _target_dim
            _target_dim = FALLBACK_DIM
            return vec
        except Exception as e:
            logger.warning("TF-IDF embedding failed: %s", e)
            return None

    return None


def to_blob(vec: np.ndarray) -> bytes:
    """Serialize a float32 numpy array to bytes for DB storage."""
    return vec.astype(np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    """Deserialize bytes back to a float32 numpy array.

    Caches the dimension from the blob size so 256 and 384 dim vectors both work.
    """
    arr = np.frombuffer(blob, dtype=np.float32)
    dims = {
        384 * 4: 384,
        256 * 4: 256,
    }
    n = dims.get(len(blob))
    if n is None:
        n = len(arr)
    return arr.reshape(n)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two (already normalized) vectors."""
    return float(np.dot(a, b))
