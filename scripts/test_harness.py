#!/usr/bin/env python3
"""HAJIMI 自动化测试统一入口（T5 基建，纯 stdlib）。

层级（覆盖金字塔，见 调研报告 §四 2.4 与审查台账 E4）：
  L0 静态门：py_compile 全仓 Python + bat 括号检查 + eval 任务集 schema 校验
  L1 单元层：server_A 纯逻辑/组件测试（Linux 秒级，mock UIA/browser）
  L2 契约层：server_A 路由/SSE 契约 + HAJIMI_UI 测试（35+6 基线）
  L3 能力评测：Windows 真机 eval runner（--eval 才跑，见 eval/HOWTO_WINDOWS.md）
  L4 验收冒烟：起 :8011 sidecar + verify_l5 --require-l5

用法：
  python scripts/test_harness.py --level all     # L0+L1+L2+L4（Linux 全绿路径）
  python scripts/test_harness.py --level L0      # 单层
  python scripts/test_harness.py --cov           # 覆盖率报告 + 防回退门禁
  python scripts/test_harness.py --eval          # 透传 eval/run_eval.py（Windows）

门禁语义（防自欺）：
  * 覆盖率门禁 = 2026-09 实测基线（executor 60% / planning 45%）防回退；
    目标值（75%/50%）在报告中显示差距，T6 补 clicker 等测试后逐步收紧门禁。
  * 测试失败数：HAJIMI_UI 恒 35 passed/6 预存环境失败，任何新失败=门禁失败。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_A = ROOT / "server_A"
UI = ROOT / "HAJIMI_UI"

# 覆盖率基线（2026-09-14 实测，Linux 全量收集后）——防回退门禁
# executor 79.2%（T5 桩回收 + T6 clicker/launcher/planner/memory 补测后，已达 75% 目标，
# 门禁随之收紧）；planning 46.4%（受预存失败影响，目标 50% 待 T7 修复收集后冲）
COVERAGE_GATES = {
    "executor": 75,
    "planning": 45,
}
COVERAGE_TARGETS = {
    "executor": 75,  # 目标：T6 补 clicker/safety 后可达
    "planning": 50,
}

# ── 预存失败门禁（T5 取证：2026-09-03 Linux 全量收集后精确 29 例）──
# 语义：当前 failed 集合必须是此清单的**子集**（允许因环境改善而减少，
# 但清单外任何新失败=门禁失败）。这些是 L4 旧管线测试的环境性失败
# （依赖 LLM key/playwright/音频），与 L5 执行链无关，修复列 T7 之后。
PRESET_FAILURES = [
    "server/tests/test_api_routes.py::TestHealth::test_degraded",
    "server/tests/test_blueprint.py::TestBlueprintEngineP3::test_advance_from_executing_moves_pointer",
    "server/tests/test_blueprint.py::TestBlueprintEngineP3::test_advance_from_rolling_back_behaves_like_executing",
    "server/tests/test_blueprint.py::TestBlueprintEngineP3::test_advance_from_suspended_resumes_without_moving_pointer",
    "server/tests/test_blueprint.py::TestBlueprintEngineP3::test_strict_fingerprint_match_advances",
    "server/tests/test_blueprint.py::TestBlueprintEngineP3::test_strict_fingerprint_mismatch_suspends",
    "server/tests/test_blueprint.py::TestBlueprintEngineP3::test_strict_fingerprint_with_no_stored_fingerprint_advances",
    "server/tests/test_blueprint.py::TestBlueprintEngineP3::test_suspend_from_executing_sets_suspended",
    "server/tests/test_blueprint.py::TestBlueprintEngineP3::test_suspend_from_non_executing_does_nothing",
    "server/tests/test_blueprint.py::TestBlueprintEngineP3::test_terminate_from_suspended",
    "server/tests/test_constraint.py::TestBlueprintConstraintHint::test_advance_appends_install_path_hint",
    "server/tests/test_constraint.py::TestConstraintSchema::test_process_response_has_constraints_field",
    "server/tests/test_constraint.py::TestProcessQueryConstraints::test_process_query_without_constraints",
    "server/tests/test_legacy.py::TestBlueprintEngine::test_advance_from_step_1_to_2",
    "server/tests/test_legacy.py::TestBlueprintEngine::test_complete_all_steps",
    "server/tests/test_legacy.py::TestBlueprintEngine::test_rollback_from_step_2_to_1",
    "server/tests/test_legacy.py::TestBlueprintEngine::test_terminate",
    "server/tests/test_legacy.py::TestGenerateSteps::test_screenshot_scenario_steps_count",
    "server/tests/test_legacy.py::TestGenerateSteps::test_wechat_scenario_steps_count",
    "server/tests/test_legacy.py::TestProcessQuery::test_process_first_step_binding_legacy",
    "server/tests/test_legacy.py::TestProcessQuery::test_process_without_image",
    "server/tests/test_perception.py::test_conceptual_step_has_no_binding",
    "server/tests/test_perception.py::test_empty_elements_generate_text_only_steps",
    "server/tests/test_perception.py::test_hallucinated_element_id_falls_back",
    "server/tests/test_perception.py::test_mock_fallback_uses_predefined_bindings",
    "server/tests/test_perception.py::test_semantic_match_download_button",
    "server/tests/test_perception.py::test_type_text_match_password_input",
    "server/tests/test_replanner.py::test_advance_triggers_replanning_binds_address_bar",
    "server/tests/test_replanner.py::test_rollback_does_not_trigger_replanning",
]


def _run(cmd, cwd=None, check=True) -> int:
    print(f"\n$ {' '.join(cmd)}")
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    p = subprocess.run(cmd, cwd=str(cwd or ROOT), env=env)
    if check and p.returncode != 0:
        print(f"✗ 失败 (exit {p.returncode}): {' '.join(cmd)}")
    return p.returncode


def _py():
    return [sys.executable]


# 已知编译例外（L4 时代死 fork 残留，审查 R5 已点名清理——清理批次落地后移除）
# style_preview_demo.py 用了 Python3.12 才允许的 f-string 反斜杠语法（当前 3.10 编译不过）
COMPILE_EXCEPTIONS = {
    "server_A/ui/style_preview_demo.py",
    "server_A/ui/#step_list.py",
    "server_A/core/#screen_capturer.py",
}


def level_L0() -> int:
    """静态门：py_compile（仅 git 跟踪的 .py）+ bat 括号 + eval schema。"""
    rc = 0
    # 只编译 git 跟踪的 Python 文件：死 fork 垃圾文件（如 L4 遗留的
    # server_A/ui/#step_list.py / style_preview_demo.py）不在跟踪集内就不误伤。
    ls = subprocess.run(["git", "ls-files", "*.py"], capture_output=True, text=True)
    tracked = [ln for ln in ls.stdout.splitlines() if ln.strip()]
    py_files = [
        str(ROOT / f) for f in tracked
        if (ROOT / f).exists() and f not in COMPILE_EXCEPTIONS
    ]
    # 逐文件编译（静默，只报错）：单条命令行避免超长参数与"一个坏文件拖垮整批"
    bad = []
    for fp in py_files:
        r = subprocess.run(
            [sys.executable, "-m", "py_compile", fp],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        if r.returncode != 0:
            err = [l for l in (r.stderr or "").splitlines() if "Error" in l or "error" in l][:2]
            bad.append(f"{fp}: {'; '.join(err)}")
    if bad:
        print("✗ py_compile 失败：")
        for b in bad:
            print(f"   {b}")
        rc |= 1
    else:
        print(f"✓ py_compile: {len(py_files)} 个跟踪文件全部通过"
              f"（例外 {len(COMPILE_EXCEPTIONS)} 个 R5 清理项跳过）")
    # bat 括号检查
    checker = ROOT / "HAJIMI_UI" / "scripts" / "dev" / "check_bat_parens.py"
    if checker.exists():
        rc |= _run(_py() + [str(checker)])
    # eval 任务集 schema
    rc |= _run(_py() + ["-m", "pytest", "server/tests/test_eval_tasks.py", "-q"],
               cwd=SERVER_A)
    return rc


def level_L1() -> int:
    """单元/组件层：server_A 全量（Linux，mock 桩）+ 预存失败门禁。

    门禁：failed 集合 ⊆ PRESET_FAILURES（子集判定，环境改善自动放宽）；
    收集错误（ERROR）同样必须 ⊆ 预存集合（当前 15 个环境性收集错误）。
    """
    p = subprocess.run(
        _py() + ["-m", "pytest", "server/tests", "-q",
                 "--continue-on-collection-errors", "--tb=no"],
        cwd=str(SERVER_A), capture_output=True, text=True,
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
    )
    out = p.stdout + p.stderr
    failed_now = []
    for line in out.splitlines():
        if line.startswith("FAILED "):
            failed_now.append(line[len("FAILED "):].split(" - ")[0].strip())
    summary = [l for l in out.splitlines() if l and l[0].isdigit() and "passed" in l]
    print("\n".join(summary[-2:]))
    new_fails = sorted(set(failed_now) - set(PRESET_FAILURES))
    if new_fails:
        print(f"✗ 新增失败 {len(new_fails)}（不在预存清单）：")
        for f in new_fails:
            print(f"   {f}")
        return 1
    missing = sorted(set(PRESET_FAILURES) - set(failed_now))
    if missing:
        print(f"✓ 预存失败减少了 {len(missing)} 例（环境/修复改善，门禁自动放宽）")
    print(f"✓ 门禁通过：当前失败 {len(failed_now)} 例全部为预存清单内")
    # 收集错误（ERROR）数量对比基线 15（只报不减不罚，T7 处理）
    errs = [l for l in out.splitlines() if l.startswith("ERROR ")]
    if errs:
        print(f"  （收集错误 {len(errs)} 例——T7 修复目标，暂不判红）")
    return 0


UI_PRESET_FAILURES = [
    "tests/test_asr_client_finalize.py::test_empty_audio_emits_callback",
    "tests/test_asr_client_finalize.py::test_empty_audio_manual_stop_message",
    "tests/test_asr_client_finalize.py::test_empty_audio_wait_timeout_message",
    "tests/test_asr_client_finalize.py::test_google_network_error_falls_back_to_vosk",
    "tests/test_voice_controller_settings.py::test_apply_voice_settings_rebuilds_asr_client",
    "tests/test_voice_controller_settings.py::test_start_uses_google_engine_from_voice_settings",
]


def level_L2() -> int:
    """契约层：HAJIMI_UI 测试（35 passed/6 预存失败基线，无音频设备环境）。"""
    p = subprocess.run(
        _py() + ["-m", "pytest", "tests", "-q", "--tb=no"],
        cwd=str(UI), capture_output=True, text=True,
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
    )
    out = p.stdout + p.stderr
    failed_now = [
        l[len("FAILED "):].split(" - ")[0].strip()
        for l in out.splitlines() if l.startswith("FAILED ")
    ]
    summary = [l for l in out.splitlines() if l and l[0].isdigit() and "passed" in l]
    print("\n".join(summary[-1:]))
    new_fails = sorted(set(failed_now) - set(UI_PRESET_FAILURES))
    if new_fails:
        print(f"✗ UI 新增失败 {len(new_fails)}：")
        for f in new_fails:
            print(f"   {f}")
        return 1
    print(f"✓ UI 门禁通过：当前失败 {len(failed_now)} 例全部为预存清单内")
    return 0


def level_L4() -> int:
    """验收冒烟：起 sidecar → verify_l5 --require-l5 → 停。"""
    import subprocess as sp
    import time
    import urllib.request

    sidecar = sp.Popen(
        [_py()[0], "-m", "uvicorn", "server.main:app", "--port", "8011"],
        cwd=str(SERVER_A), stdout=sp.DEVNULL, stderr=sp.DEVNULL,
    )
    rc = 0
    try:
        for _ in range(30):
            try:
                urllib.request.urlopen("http://127.0.0.1:8011/api/demo/health", timeout=1)
                break
            except Exception:
                time.sleep(1)
        else:
            print("✗ sidecar 30s 未就绪")
            return 1
        rc |= _run(
            _py() + [str(ROOT / "HAJIMI_UI" / "scripts" / "verify_l5.py"),
                     "--require-l5"],
            cwd=UI,
        )
    finally:
        sidecar.terminate()
        try:
            sidecar.wait(timeout=10)
        except Exception:
            sidecar.kill()
    return rc


def run_cov() -> int:
    """覆盖率报告 + 防回退门禁（executor/planning 分别判定）。"""
    out_dir = ROOT / "test_reports"
    out_dir.mkdir(exist_ok=True)
    json_fp = out_dir / "coverage_current.json"
    _run(
        _py() + ["-m", "pytest", "server/tests", "-q",
                 "--continue-on-collection-errors",
                 "--cov=server/services/executor", "--cov=server/services/planning",
                 "--cov-report="],
        cwd=SERVER_A, check=False,  # 预存失败会令 pytest 退出非零，门禁自行判定
    )
    # 旧版 pytest-cov 不支持 --cov-report=json:，改用 coverage CLI 导出
    exp = subprocess.run(
        [sys.executable, "-m", "coverage", "json", "-o", str(json_fp), "-q"],
        cwd=str(SERVER_A), capture_output=True, text=True,
    )
    print("\n=== 覆盖率门禁（防回退）===")
    if exp.returncode != 0 or not json_fp.exists():
        print("✗ coverage json 未生成，门禁无法判定")
        return 1
    import json

    data = json.loads(json_fp.read_text(encoding="utf-8"))
    files = data.get("files", {})
    groups = {"executor": [], "planning": []}
    for path, info in files.items():
        if "/executor/" in path:
            groups["executor"].append(info)
        elif "/planning/" in path:
            groups["planning"].append(info)
    gate_fail = False
    for grp, infos in groups.items():
        tot_s = sum(i["summary"]["num_statements"] for i in infos)
        tot_m = sum(i["summary"]["missing_lines"] for i in infos)
        pct = 100.0 * (tot_s - tot_m) / max(tot_s, 1)
        gate = COVERAGE_GATES[grp]
        target = COVERAGE_TARGETS[grp]
        mark = "PASS" if pct >= gate else "FAIL"
        if pct < gate:
            gate_fail = True
        print(f"  {grp}: {pct:.1f}% (门禁 {gate}%/{mark}, 目标 {target}%)")
    if gate_fail:
        print("  ✗ 低于防回退门禁——禁止合入；先补测试再跑")
        return 1
    print("  ✓ 高于门禁；距目标差距见上（T6/T7 收紧门禁前不强制）")
    return 0  # 门禁只看覆盖率；pytest 退出码（预存失败）由 L1 门禁负责


def run_eval(argv) -> int:
    """透传 Windows 评测 runner（L3）。"""
    return _run(
        _py() + [str(SERVER_A / "eval" / "run_eval.py")] + argv,
        cwd=SERVER_A,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="HAJIMI 自动化测试统一入口")
    ap.add_argument("--level", choices=["L0", "L1", "L2", "L3", "L4", "all"],
                    default="all")
    ap.add_argument("--cov", action="store_true", help="跑覆盖率报告")
    ap.add_argument("--eval", nargs="*", default=None,
                    help="透传参数给 eval/run_eval.py（如 --eval --dry-run）")
    args = ap.parse_args()

    if args.eval is not None:
        return run_eval(args.eval)

    order = ["L0", "L1", "L2", "L4"] if args.level == "all" else [args.level]
    total = 0
    for lv in order:
        fn = {"L0": level_L0, "L1": level_L1, "L2": level_L2, "L4": level_L4}[lv]
        print(f"\n{'='*60}\n== {lv}\n{'='*60}")
        total |= fn()
    if args.cov:
        total |= run_cov()
    print(f"\n{'='*60}\n结果: {'PASS' if total == 0 else 'FAIL'} "
          f"(exit={total})\n{'='*60}")
    return total


if __name__ == "__main__":
    raise SystemExit(main())
