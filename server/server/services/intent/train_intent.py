"""
SetFit 意图分类模型训练脚本

Usage:
    python server/services/intent/train_intent.py

环境:
    pip install setfit sentence-transformers

说明:
    - 从 intent_data.json 读取 9 类意图样本
    - 基于 paraphrase-multilingual-MiniLM-L12-v2 训练 SetFit 分类器
    - 模型保存到 server/config.py 中 INTENT_MODEL_PATH 指定的目录
"""

import json
import os
from pathlib import Path
from typing import List, Tuple

from server.config import settings

# 在中国大陆默认使用 Hugging Face 镜像，可通过环境变量覆盖
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# 用于训练的句子 Transformer（支持中文）
BASE_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def load_intent_data(path: str) -> Tuple[List[str], List[int], List[str]]:
    """
    加载意图样本并编码标签。

    Returns:
        texts: 训练文本列表
        labels: 对应整数标签列表
        label_names: 标签名称列表，与整数标签一一对应
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    label_names = [item["category"] for item in data["intents"]]
    label_to_id = {name: idx for idx, name in enumerate(label_names)}

    texts: List[str] = []
    labels: List[int] = []
    for item in data["intents"]:
        category = item["category"]
        for sample in item["samples"]:
            texts.append(sample)
            labels.append(label_to_id[category])

    return texts, labels, label_names


def train(model_path: str | None = None, data_path: str | None = None) -> None:
    """
    训练并保存 SetFit 意图分类模型。
    """
    model_path = model_path or settings.INTENT_MODEL_PATH
    data_path = data_path or str(Path(__file__).with_name("intent_data.json").resolve())

    texts, labels, label_names = load_intent_data(data_path)
    print(
        f"[train_intent] Loaded {len(texts)} samples across "
        f"{len(label_names)} classes: {label_names}"
    )

    # 延迟导入：没有安装 setfit 时训练脚本直接报错即可
    from setfit import SetFitModel

    model = SetFitModel.from_pretrained(
        BASE_MODEL_NAME,
        labels=label_names,
    )
    model.fit(
        texts,
        labels,
        num_epochs=10,
        batch_size=16,
        show_progress_bar=True,
    )

    output_dir = Path(model_path)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    print(f"[train_intent] Model saved to {output_dir}")


if __name__ == "__main__":
    train()
