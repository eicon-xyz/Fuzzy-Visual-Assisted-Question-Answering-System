#!/usr/bin/env python3
"""确定性闸门 —— 提交前必须绿的唯一入口。

设计原则（与 AGENTS.md「Agent skills」段一致）：
  能被机器判定的规则，不写进散文让 agent 记住。
  新增违规 = 失败；修掉一条 = 提示收紧基线。只降不升。

三层检查：
  compile  所有 git 跟踪的 .py 能被 compile() 解析
           （比 py_compile 快，且能覆盖 ruff 排除目录里的脚本）
  lint     ruff 计数棘轮：按规则号与基线比对，只拦增量
  refs     已删概念的残留引用（:8010 / deployment_mode / a_end_url …）

用法：
  python scripts/gates.py                    # 全部
  python scripts/gates.py --only lint        # 单层
  python scripts/gates.py --update-baseline  # 收紧 lint 基线（只降不升）
  python scripts/gates.py --install-hooks    # 让 .githooks/pre-commit 生效

退出码：0 通过 / 1 失败 / 2 环境未就绪（工具链缺失，不是代码问题）
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "gates_baseline.json"
REFS = ROOT / "scripts" / "gates_refs.json"
RUFF_CONFIG = ROOT / "ruff.toml"


# ────────────────────────── 公共 ──────────────────────────


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失败：{r.stderr.strip()}")
    return r.stdout


def _excluded_dirs() -> list[str]:
    """从 ruff.toml 读排除目录 —— 单一事实源，不在这里重复一份清单。"""
    if not RUFF_CONFIG.exists():
        return []
    cfg = tomllib.loads(RUFF_CONFIG.read_text(encoding="utf-8"))
    return list(cfg.get("extend-exclude") or [])


def _tracked(suffixes: set[str] | None = None) -> list[str]:
    """git 跟踪的文件，已按 ruff 的排除目录过滤。"""
    excluded = _excluded_dirs()
    out = []
    for rel in _git("ls-files").splitlines():
        if not rel.strip():
            continue
        if suffixes and Path(rel).suffix.lower() not in suffixes:
            continue
        parts = Path(rel).parts
        if any(parts[: len(Path(e).parts)] == Path(e).parts for e in excluded if not e.startswith(".")):
            continue
        if any(e in parts for e in excluded if e.startswith(".")):
            continue
        if (ROOT / rel).exists():
            out.append(rel)
    return out


def _ruff() -> list[str]:
    for cand in (
        ROOT / ".venv-tools" / "Scripts" / "ruff.exe",
        ROOT / ".venv-tools" / "bin" / "ruff",
    ):
        if cand.exists():
            return [str(cand)]
    from shutil import which

    found = which("ruff")
    if found:
        return [found]
    print(
        "✗ 找不到 ruff。先建工具环境：\n"
        "    python -m venv .venv-tools\n"
        "    .venv-tools/Scripts/pip install -r requirements-dev.txt\n"
        "  （Windows 为 Scripts/，POSIX 为 bin/）",
        file=sys.stderr,
    )
    raise SystemExit(2)


# ────────────────────────── compile ──────────────────────────


def check_compile() -> int:
    bad = []
    files = _tracked({".py"})
    for rel in files:
        src = (ROOT / rel).read_text(encoding="utf-8-sig", errors="replace")
        try:
            compile(src, rel, "exec")
        except SyntaxError as e:
            bad.append(f"{rel}:{e.lineno}: {e.msg}")
    if bad:
        print(f"✗ compile：{len(bad)} 个文件无法解析")
        for b in bad[:20]:
            print(f"   {b}")
        return 1
    print(f"✓ compile：{len(files)} 个跟踪的 .py 全部可解析")
    return 0


# ────────────────────────── lint 棘轮 ──────────────────────────


def _lint_counts() -> tuple[dict[str, int], list[str]]:
    """返回 (按规则号计数, 原始违规行)。"""
    cmd = [*_ruff(), "check", ".", "--output-format", "concise", "--no-cache"]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    counts: dict[str, int] = {}
    lines = []
    for line in (r.stdout + r.stderr).splitlines():
        # 形态：path:line:col: CODE message —— 只有 3 个冒号，maxsplit=3
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        code = parts[3].strip()
        if not code or not code[0].isalpha():
            continue
        code = code.split()[0]
        counts[code] = counts.get(code, 0) + 1
        lines.append(line)
    return counts, lines


def _ruff_version() -> str:
    r = subprocess.run([*_ruff(), "--version"], capture_output=True, text=True, check=False)
    return r.stdout.strip()


def _load_baseline() -> dict:
    if not BASELINE.exists():
        return {}
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def check_lint(update: bool = False, reset: bool = False) -> int:
    counts, lines = _lint_counts()
    base = _load_baseline()
    base_counts = base.get("counts", {})
    version = _ruff_version()

    if reset or not base_counts:
        if not (update or reset):
            print("✗ lint：基线缺失。首次接线请跑 --reset-baseline")
            return 1
        BASELINE.write_text(
            json.dumps({"ruff": version, "counts": dict(sorted(counts.items()))},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"✓ lint：已建立基线（{sum(counts.values())} 项存量债，{len(counts)} 条规则）")
        return 0

    if base.get("ruff") and base["ruff"] != version:
        print(
            f"! lint：ruff 版本变了（基线 {base['ruff']}，当前 {version}）。"
            "规则集可能变化，先确认新增违规是否真实，再 --update-baseline"
        )

    increased = {c: n for c, n in counts.items() if n > base_counts.get(c, 0)}
    if increased:
        print(f"✗ lint：{sum(increased.values())} 项新增违规（{len(increased)} 条规则）")
        for code, n in sorted(increased.items(), key=lambda kv: -kv[1]):
            was = base_counts.get(code, 0)
            print(f"   {code}: {was} → {n}  (+{n - was})")
        shown = 0
        for line in lines:
            code = line.split(":", 3)[3].strip().split()[0]
            if code in increased:
                print(f"   {line}")
                shown += 1
                if shown >= 25:
                    print("   …（其余省略；直接跑 ruff check . 看全量）")
                    break
        print("\n  修掉后重跑；确实要接受这笔债，必须先改 scripts/gates_baseline.json 并写明理由。")
        return 1

    total = sum(counts.values())
    base_total = sum(base_counts.values())
    fixed = {c: base_counts[c] - counts.get(c, 0)
             for c in base_counts if counts.get(c, 0) < base_counts[c]}
    print(f"✓ lint：{total} 项存量债（基线 {base_total}，{len(counts)} 条规则）")
    if fixed and not update:
        n = sum(fixed.values())
        print(f"  可收紧 {n} 项：{' '.join(sorted(fixed))} → 跑 --update-baseline 固化")
    if update:
        merged = dict(base_counts)
        for c in list(merged):
            if c not in counts:
                del merged[c]
        merged.update(counts)
        BASELINE.write_text(
            json.dumps({"ruff": version, "counts": dict(sorted(merged.items()))},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"  基线已收紧：{base_total} → {sum(merged.values())}")
    return 0


# ────────────────────────── refs ──────────────────────────


def _import_roots(rel: str) -> list[tuple[int, str]]:
    """返回 (行号, import 的根模块名) 列表。解析失败由 compile 层负责，这里跳过。"""
    import ast

    src = (ROOT / rel).read_text(encoding="utf-8-sig", errors="replace")
    try:
        tree = ast.parse(src, filename=rel)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((node.lineno, alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相对 import 不跨包边界
                continue
            if node.module:
                out.append((node.lineno, node.module.split(".")[0]))
    return out


def check_refs() -> int:
    if not REFS.exists():
        print("✓ refs：无禁用清单（scripts/gates_refs.json 不存在）")
        return 0
    cfg = json.loads(REFS.read_text(encoding="utf-8"))
    rc = 0

    for rule in cfg.get("forbidden_imports", []):
        scope = rule["scope"].replace("\\", "/")
        roots = set(rule["roots"])
        bad = []
        for rel in _tracked({".py"}):
            if not rel.replace("\\", "/").startswith(scope + "/"):
                continue
            for lineno, root in _import_roots(rel):
                if root in roots:
                    bad.append((rel, lineno, root))
        if bad:
            rc = 1
            print(f"✗ refs：{scope} 里有 {len(bad)} 条 import 指向禁用根 {sorted(roots)}")
            print(f"   {rule['why']}")
            for rel, lineno, root in bad[:20]:
                print(f"   {rel}:{lineno}: 引用了 `{root}`")
            print("   修法：把真正需要的符号搬到本包内，而不是从死 fork 取。")
        else:
            print(f"✓ refs：{scope} 无指向 {sorted(roots)} 的 import")

    for rule in cfg.get("forbidden_paths", []):
        target = ROOT / rule["path"]
        if target.exists():
            rc = 1
            n = len(list(target.rglob("*"))) if target.is_dir() else 1
            print(f"✗ refs：{rule['path']} 仍然存在（{n} 项）")
            print(f"   {rule['why']}")
        else:
            print(f"✓ refs：{rule['path']} 已不存在")

    return rc



# ────────────────────────── hooks ──────────────────────────


def install_hooks() -> int:
    subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=ROOT, check=True)
    print("✓ 已启用 .githooks（core.hooksPath=.githooks）——提交前自动跑 compile/lint/refs")
    return 0


# ────────────────────────── main ──────────────────────────

CHECKS = {"compile": check_compile, "lint": check_lint, "refs": check_refs}


def main() -> int:
    ap = argparse.ArgumentParser(description="HAJIMI 确定性闸门")
    ap.add_argument("--only", default="compile,lint,refs",
                    help="逗号分隔：compile,lint,refs（默认全部）")
    ap.add_argument("--update-baseline", action="store_true",
                    help="把当前 lint 计数写成新基线（只降不升）")
    ap.add_argument("--reset-baseline", action="store_true",
                    help="无条件重建基线（仅首次接线或 ruff 大版本升级时用）")
    ap.add_argument("--install-hooks", action="store_true", help="启用 git hooks")
    args = ap.parse_args()

    if args.install_hooks:
        return install_hooks()

    rc = 0
    for name in [s.strip() for s in args.only.split(",") if s.strip()]:
        fn = CHECKS.get(name)
        if fn is None:
            print(f"✗ 未知检查项：{name}")
            return 2
        print(f"\n── {name} ──")
        rc |= (fn(update=args.update_baseline, reset=args.reset_baseline)
               if name == "lint" else fn())

    print(f"\n{'=' * 56}\n结果: {'PASS' if rc == 0 else 'FAIL'}\n{'=' * 56}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
