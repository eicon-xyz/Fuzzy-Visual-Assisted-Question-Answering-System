"""Detect OmniParser device (cpu/cuda) with real CUDA kernel smoke test."""
from __future__ import annotations

import os
import sys


def _log(msg: str) -> None:
    print(f"[detect_omni_device] {msg}", file=sys.stderr)


def detect_omni_device() -> str:
    if os.environ.get("OMNI_FORCE_CPU") == "1":
        _log("OMNI_FORCE_CPU=1, using cpu")
        return "cpu"
    if os.environ.get("OMNI_FORCE_CUDA") == "1":
        _log("OMNI_FORCE_CUDA=1, using cuda (requires PyTorch cu128+ for RTX 50)")
        return "cuda"

    try:
        import torch
    except ImportError:
        _log("torch not installed, using cpu")
        return "cpu"

    if not torch.cuda.is_available():
        _log("CUDA not available, using cpu")
        return "cpu"

    cap = torch.cuda.get_device_capability(0)
    arch_list: list[str] = []
    try:
        arch_list = list(torch.cuda.get_arch_list() or [])
    except Exception:
        pass

    sm_tag = f"sm_{cap[0]}{cap[1]}"
    if cap[0] >= 12 and sm_tag not in arch_list:
        name = torch.cuda.get_device_name(0)
        _log(
            f"{name} ({sm_tag}) is not supported by current PyTorch "
            f"(arch list: {arch_list or 'unknown'}), forcing cpu"
        )
        _log(
            "Campus GPU: use intranet API (python scripts/b_group2_intranet_setup.py). "
            "Local GPU: scripts\\upgrade_omni_pytorch_cu128.bat"
        )
        return "cpu"

    try:
        torch.zeros(1, device="cuda").item()
        _log(f"CUDA kernel test passed on {torch.cuda.get_device_name(0)}, using cuda")
        return "cuda"
    except RuntimeError as exc:
        _log(f"CUDA kernel test failed ({exc}), forcing cpu")
        return "cpu"


def main() -> int:
    device = detect_omni_device()
    print(device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
