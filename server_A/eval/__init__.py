"""L5 私有回归评测台 —— 任务 schema 与加载校验（纯 stdlib，Linux 可跑校验，Windows 可跑执行）。

设计对齐调研报告 §四 P2-2.4：任务自带「配置化初始状态 setup + 机器可判 oracle」，
不靠 LLM 自评。oracle 优先文件系统/注册表副作用，其次 UIA 谓词，禁视觉比对。

一个任务实例展开为 (instruction, seeds 各值) 的多次 run，供 All-Pass@4 / 种子方差统计。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# oracle 谓词类型 → 必需字段（file/registry 类是跨会话稳定副作用，优先）
ORACLE_TYPES = {
    "file_exists": ["path"],
    "file_not_exists": ["path"],
    "file_content_contains": ["path", "needle"],
    "file_content_equals": ["path", "text"],
    "file_glob_min_count": ["glob", "min"],
    "registry_value": ["hive", "key", "name"],  # 可选 expect
    "uia_window_title_contains": ["needle"],    # 任一顶层窗口标题含 needle → 真
    "uia_window_not_exists": ["needle"],        # 无任何窗口标题含 needle → 真
    "uia_element_exists": ["name_contains"],    # 可选 type / window_title_contains
    "clipboard_contains": ["needle"],
}

# 路径宏：runner 在执行前展开（{EVAL_DIR} → %LOCALAPPDATA%\HAJIMI\eval）
PATH_MACROS = ("{EVAL_DIR}",)

# 已知 P0 项（用于覆盖率完整性检查）
P0_ITEMS = ["0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8"]

EXPECT_STATUSES = {"success", "fail"}

CATEGORIES = {
    "editor", "file", "settings", "browser", "menu", "dialog",
    "multi-window", "list", "form", "negative",
}


class TaskValidationError(ValueError):
    pass


@dataclass
class Task:
    id: str
    name: str
    category: str
    instruction: str
    seeds: list
    p0_coverage: list
    setup_ps1: list = field(default_factory=list)
    cleanup_ps1: list = field(default_factory=list)
    oracle: dict = field(default_factory=dict)
    max_wall_s: int = 300
    requires: list = field(default_factory=list)
    notes: str = ""
    source: str = ""  # 溯源：handcrafted / user-failure:<日期> / waa:<task名>
    # 期望终态：success=任务应完成且 oracle 为真；fail=任务应正确放弃
    # （agent 走 infeasible/ask_user 或 oracle 为负向谓词，如弹窗已关/无错删）
    expect_status: str = "success"
    # oracle 是否已在 Windows 上人工两向校准（真做→PASS、故意失败→FAIL）。
    # 未校准任务不得计入正式 KPI，只能试跑。
    calibrated: bool = False

    def render(self, seed: str) -> "Task":
        """把一个 seed 代入 {seed} 占位，返回具体化的新实例。"""
        def _sub(obj):
            if isinstance(obj, str):
                return obj.replace("{seed}", seed)
            if isinstance(obj, list):
                return [_sub(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _sub(v) for k, v in obj.items()}
            return obj

        return Task(
            id=f"{self.id}", name=self.name, category=self.category,
            instruction=_sub(self.instruction), seeds=[seed],
            p0_coverage=list(self.p0_coverage),
            setup_ps1=_sub(self.setup_ps1), cleanup_ps1=_sub(self.cleanup_ps1),
            oracle=_sub(self.oracle), max_wall_s=self.max_wall_s,
            requires=list(self.requires), notes=self.notes, source=self.source,
            expect_status=self.expect_status, calibrated=self.calibrated,
        )


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise TaskValidationError(msg)


def _validate_oracle(oracle: dict, tid: str) -> None:
    _require(isinstance(oracle, dict) and bool(oracle), f"{tid}: oracle 不能为空")
    _require(
        ("all" in oracle) or ("any" in oracle),
        f"{tid}: oracle 需含 all 或 any 谓词列表",
    )
    for group in ("all", "any"):
        for chk in oracle.get(group, []):
            _require(isinstance(chk, dict) and "type" in chk, f"{tid}: oracle 谓词缺 type")
            t = chk["type"]
            # 机器判据不得是 LLM 自评或视觉（显式禁用，先于未知类型检查）
            _require(
                t not in {"screenshot_match", "llm_judge", "image_diff"},
                f"{tid}: 禁用非确定性 oracle '{t}'",
            )
            _require(
                t in ORACLE_TYPES,
                f"{tid}: 未知 oracle 类型 '{t}'（可选：{sorted(ORACLE_TYPES)}）",
            )
            for k in ORACLE_TYPES[t]:
                _require(k in chk, f"{tid}: oracle {t} 缺字段 '{k}'")


def validate_task(raw: dict, src: str = "?") -> Task:
    tid = raw.get("id", "<无id>")
    _require(isinstance(raw, dict), f"{src}: 任务必须是对象")
    for k in ("id", "name", "category", "instruction", "oracle"):
        _require(k in raw, f"{tid}: 缺字段 '{k}'")
    _require(
        raw["category"] in CATEGORIES,
        f"{tid}: category '{raw['category']}' 不在允许集合",
    )
    seeds = raw.get("seeds") or []
    _require(len(seeds) >= 1, f"{tid}: seeds 至少 1 个（评测建议 ≥3）")
    cov = raw.get("p0_coverage") or []
    _require(
        all(c in P0_ITEMS for c in cov),
        f"{tid}: p0_coverage 含未知项 {cov}",
    )
    _validate_oracle(raw["oracle"], tid)
    expect_status = raw.get("expect_status", "success")
    _require(
        expect_status in EXPECT_STATUSES,
        f"{tid}: expect_status '{expect_status}' 非法（应为 success/fail）",
    )
    return Task(
        id=raw["id"], name=raw["name"], category=raw["category"],
        instruction=raw["instruction"], seeds=list(seeds),
        p0_coverage=list(cov),
        setup_ps1=list(raw.get("setup_ps1") or []),
        cleanup_ps1=list(raw.get("cleanup_ps1") or []),
        oracle=raw["oracle"], max_wall_s=int(raw.get("max_wall_s", 300)),
        requires=list(raw.get("requires") or []),
        notes=raw.get("notes", ""), source=raw.get("source", "handcrafted"),
        expect_status=expect_status,
        calibrated=bool(raw.get("calibrated", False)),
    )


def load_tasks(tasks_dir: Path) -> list:
    """加载目录下所有 *.json 任务清单（每项是任务数组），返回列表。"""
    tasks: list = []
    seen_ids: set = set()
    for fp in sorted(Path(tasks_dir).glob("*.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        _require(isinstance(data, list), f"{fp.name}: 顶层须为任务数组")
        for raw in data:
            t = validate_task(raw, src=fp.name)
            _require(
                t.id not in seen_ids, f"重复任务 id: {t.id} ({fp.name})",
            )
            seen_ids.add(t.id)
            tasks.append(t)
    return tasks


def coverage_report(tasks: Iterable[Task]) -> dict:
    """P0 覆盖率：每项命中的任务 id 列表 + 缺口（每项至少 2 任务）+ 校准进度。"""
    tasks = list(tasks)
    by_item = {item: [] for item in P0_ITEMS}
    for t in tasks:
        for item in t.p0_coverage:
            by_item.setdefault(item, []).append(t.id)
    gaps = {k: v for k, v in by_item.items() if len(v) < 2}
    calibrated = [t.id for t in tasks if t.calibrated]
    return {
        "total_tasks": len(tasks),
        "by_p0": by_item,
        "undercovered": gaps,
        "calibrated_count": len(calibrated),
        "uncalibrated_count": len(tasks) - len(calibrated),
    }
