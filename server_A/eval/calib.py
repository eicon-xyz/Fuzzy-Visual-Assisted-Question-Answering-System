"""单任务校准助手（calib）—— Windows 评测机上手工校准的加速器。

把 HOWTO_WINDOWS §2/§8.1 的"每条任务手敲 run_eval 命令 + 翻 results/*.jsonl"
压缩成三步短命令：--setup 造初始态 → 照 --show 人工做 → --check 现场判分；
两向皆过（真做 PASS、故意失败 FAIL）后 --calib-done 置位（calibration_method:human）。
带 calib_gold 的正向任务另有机器快路：--selftest 五段自动验证（初始 FAIL→gold PASS→
cleanup 复位 FAIL）写状态戳 → 人审 gold 脚本 → --calib-done --via-gold（gold-v1）。

本工具是评测台的**纯消费者**：宏展开复用 run_eval.expand_macros、PS 执行复用
run_eval.run_ps（同一 powershell 构造/超时/env 传递）、现场读取复用 run_eval.WindowsProbe、
判分复用 oracle_eval.eval_oracle、任务加载复用 eval.load_tasks——不另造第二套实现。

用法（工作目录 server_A）:
    python -m eval.calib --list                              # 任务总表（跨平台）
    python -m eval.calib waa_notepad_draft_save --show       # 照单真做看这个（跨平台）
    python -m eval.calib waa_notepad_draft_save --setup      # 造初始态（Windows）
    python -m eval.calib waa_notepad_draft_save --check      # oracle 现场求值（Windows）
    python -m eval.calib waa_notepad_draft_save --calib-done # 置 calibrated:true
gold 自动校准（带 calib_gold 的正向任务，替代人工两向）:
    python -m eval.calib waa_notepad_draft_save --selftest        # Windows：五段自动化
    python -m eval.calib waa_notepad_draft_save --show            # 人审 gold 段（15 分钟批 7 条）
    python -m eval.calib waa_notepad_draft_save --calib-done --via-gold
非 Windows 上 --check/--setup/--cleanup/--selftest 拒跑（它们是评测机上的现场动作）；
--list/--show/--calib-done 跨平台可用。--check/--selftest 不启动 Sidecar、不跑 agent。
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval import load_tasks  # noqa: E402
from eval.oracle_eval import eval_oracle  # noqa: E402
import eval.run_eval as runner  # noqa: E402

HERE = Path(__file__).resolve().parent
IS_WINDOWS = os.name == "nt"
EXIT_USAGE = 2

# selftest 状态戳时限（天）：hash 匹配之外还须够新，防止"半年前验过的环境"蒙混过关
STAMP_TTL_DAYS = 7
STAMP_DIRNAME = ".calib_stamps"

# 谓词类型 → 人读含义（对齐 eval/__init__.py 的 ORACLE_TYPES 白名单）
PREDICATE_MEANING = {
    "file_exists": "文件必须存在",
    "file_not_exists": "文件必须不存在（防残留/防多做）",
    "file_content_contains": "文件内容必须包含 needle",
    "file_content_equals": "文件内容必须等于 text（strip 后比较）",
    "file_glob_min_count": "匹配 glob 的文件数必须 >= min",
    "registry_value": "注册表值必须为 expect（无 expect 则存在即真）",
    "clipboard_contains": "剪贴板文本必须包含 needle",
    "uia_window_title_contains": "必须存在标题含 needle 的窗口（大小写不敏感）",
    "uia_window_not_exists": "不得存在标题含 needle 的窗口",
    "uia_element_exists": "窗口内必须存在名称含 name_contains 的控件",
}


def out(msg=""):
    print(msg)


def err(msg):
    print(msg, file=sys.stderr)


def resolve_eval_dir() -> str:
    """与 run_eval.main 的 eval_dir 解析逐字一致（LOCALAPPDATA 缺失时回落家目录）。"""
    return os.path.join(os.getenv("LOCALAPPDATA") or os.path.expanduser("~"), "HAJIMI", "eval")


def find_task(tasks, query):
    """精确 id 优先，其次唯一前缀。返回 (task, None) 或 (None, 错误信息)。"""
    exact = [t for t in tasks if t.id == query]
    if exact:
        return exact[0], None
    pref = [t for t in tasks if t.id.startswith(query)]
    if len(pref) == 1:
        return pref[0], None
    if len(pref) > 1:
        return None, (f"任务 id 前缀 '{query}' 歧义，命中 {len(pref)} 条: "
                      + ", ".join(t.id for t in pref))
    cand = difflib.get_close_matches(query, [t.id for t in tasks], n=5, cutoff=0.4)
    hint = ("；近似候选: " + ", ".join(cand)) if cand else ""
    return None, f"找不到任务 '{query}'（--list 查看全部任务）{hint}"


def expand_task(task, seed, eval_dir):
    """runner 同款两跳展开：{seed}（Task.render）→ {EVAL_DIR}（expand_macros）。"""
    t = task.render(seed)
    t.instruction = runner.expand_macros(t.instruction, eval_dir)
    t.setup_ps1 = runner.expand_macros(t.setup_ps1, eval_dir)
    t.cleanup_ps1 = runner.expand_macros(t.cleanup_ps1, eval_dir)
    t.calib_gold = runner.expand_macros(t.calib_gold, eval_dir)
    t.oracle = runner.expand_macros(t.oracle, eval_dir)
    return t


# ── gold 校准状态戳（selftest 通过的机器凭据）────────────────────────────
# task_hash 覆盖 oracle+calib_gold+setup+cleanup+instruction：配方语义任何一处
# 变更（含 waa2seed 重生成后内容漂移）自动令旧戳失效——戳不撒谎。

def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def task_hash(task) -> str:
    payload = {"oracle": task.oracle, "calib_gold": list(task.calib_gold),
               "setup_ps1": list(task.setup_ps1),
               "cleanup_ps1": list(task.cleanup_ps1),
               "instruction": task.instruction}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def stamp_path(eval_dir, task_id) -> Path:
    return Path(eval_dir) / STAMP_DIRNAME / (task_id + ".json")


def write_stamp(task, eval_dir, phases) -> Path:
    fp = stamp_path(eval_dir, task.id)
    fp.parent.mkdir(parents=True, exist_ok=True)
    rec = {"task_id": task.id, "task_hash": task_hash(task),
           "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "phases": list(phases)}
    fp.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
    return fp


def stamp_status(task, eval_dir):
    """→ (有效?, 人读理由)。校验链：存在 → JSON 可解 → task_hash 匹配 → 时限。"""
    fp = stamp_path(eval_dir, task.id)
    if not fp.exists():
        return False, "无 selftest 状态戳——先在 Windows 评测机跑 --selftest"
    try:
        rec = json.loads(fp.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"状态戳不可读（{type(e).__name__}）：{fp}"
    want = task_hash(task)
    if rec.get("task_hash") != want:
        return False, ("状态戳 task_hash 不匹配——配方语义已变更（oracle/gold/setup/"
                       "cleanup/instruction 任一改动即失效），重跑 --selftest")
    try:
        ts = datetime.fromisoformat(str(rec.get("ts", "")))
    except Exception:
        return False, f"状态戳 ts 不可读：{rec.get('ts')!r}"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    if age > STAMP_TTL_DAYS * 86400:
        return False, (f"状态戳已过期（{age / 86400:.1f} 天 > {STAMP_TTL_DAYS} 天时限），"
                       f"重跑 --selftest")
    if age < -300:
        return False, f"状态戳时间异常（未来时间 {rec.get('ts')!r}）"
    return True, f"task_hash 匹配，{age / 3600:.1f}h 前 selftest 全过"


def resolve_seeds(task, requested):
    """--seed 解析：缺省=任务首个 seed；all=逐 seed；其他值原样用（给警告）。"""
    ids = list(task.seeds or ["default"])
    if requested == "all":
        return ids, None
    if requested:
        warn = None if requested in ids else (
            f"seed '{requested}' 不在任务 seeds {ids} 中（按给定值执行，产物落对应沙箱目录）")
        return [requested], warn
    return [ids[0]], None


def require_windows(action):
    """现场动作的平台闸。返回 None=放行，否则=退出码。"""
    if IS_WINDOWS:
        return None
    err(f"[{action}] 此动作需在 Windows 评测机上运行（要用真实 PowerShell / 注册表 / UIA / "
        f"剪贴板现场，当前系统 os.name={os.name!r} 非 Windows）。"
        f"--list / --show / --calib-done 跨平台可用。")
    return EXIT_USAGE


# ── 动作实现 ────────────────────────────────────────────────────────────


def method_cell(task, eval_dir):
    """--list 的 method 列：''/gold-v1/human；有有效戳但尚未置位 → gold✓。"""
    m = task.calibration_method
    if m:
        return m
    if task.calib_gold and not task.calibrated:
        valid, _why = stamp_status(task, eval_dir)
        if valid:
            return "gold✓"
    return ""


def cmd_list(tasks_dir, eval_dir=None):
    try:
        tasks = load_tasks(Path(tasks_dir))
    except Exception as e:
        err(f"加载任务目录 {tasks_dir} 失败: {type(e).__name__}: {e}")
        return EXIT_USAGE
    if eval_dir is None:
        eval_dir = resolve_eval_dir()
    out(f"{'#':>3}  {'id':<36}{'calibrated':<11}{'method':<9}{'expect':<9}{'负向':<5}source")
    n_cal = 0
    n_by_m = {}
    for i, t in enumerate(tasks, 1):
        neg = "是" if t.expect_status == "fail" else "-"
        src = (t.source or "")[:44]
        meth = method_cell(t, eval_dir)
        out(f"{i:>3}  {t.id:<36}{str(t.calibrated).lower():<11}{meth:<9}"
            f"{t.expect_status:<9}{neg:<4}  {src}")
        n_cal += bool(t.calibrated)
        if t.calibrated:
            n_by_m[t.calibration_method or "(旧数据:未标注)"] = \
                n_by_m.get(t.calibration_method or "(旧数据:未标注)", 0) + 1
    tail = ("；其中 " + "、".join(f"{k} {v}" for k, v in sorted(n_by_m.items()))
            if n_cal else "")
    out(f"共 {len(tasks)} 条；calibrated {n_cal}/{len(tasks)}（未校准的分数不计 KPI）"
        f"{tail}。method: gold-v1=selftest+人审 gold / human=人工两向 / gold✓=有戳待置位")
    return 0


def describe_predicate(chk):
    """单个谓词 → 人读一行（type + 参数 + 含义）。"""
    t = chk.get("type")
    args = " ".join(f"{k}={v!r}" for k, v in chk.items() if k != "type")
    meaning = PREDICATE_MEANING.get(t, "（未知谓词）")
    return f"{t} {args} —— {meaning}"


def cmd_show(task, seeds, eval_dir):
    cur = seeds[0]
    out(f"== {task.id} ==")
    out(f"name: {task.name}")
    out(f"category: {task.category}  expect_status: {task.expect_status}  "
        f"calibrated: {str(task.calibrated).lower()}  source: {task.source}")
    out(f"seeds: {', '.join(task.seeds)}（当前展示 seed={cur}，--seed 可换；all=逐个）  "
        f"requires: {', '.join(task.requires) or '-'}  max_wall_s: {task.max_wall_s}")
    if task.notes:
        out(f"notes: {task.notes}")
    t = expand_task(task, cur, eval_dir)
    out("\n-- INSTRUCTION（宏已展开=真实路径；人工照这条真做）--")
    out(f"  {t.instruction}")
    for title, lines in (("SETUP（--setup 将逐行 powershell 执行，可重跑）", t.setup_ps1),
                         ("CLEANUP（--cleanup 同上）", t.cleanup_ps1)):
        out(f"\n-- {title} --")
        if not lines:
            out("  （空）")
        for l in lines:
            out(f"  $ {l}")
    if t.calib_gold:
        out("\n-- CALIB_GOLD（--selftest 第③段执行的『直接落终态』脚本——人审对象）--")
        for l in t.calib_gold:
            out(f"  $ {l}")
    out(f"\n  注：脚本里 $env:EVAL_DIR 由 --setup/--cleanup/--selftest 注入 = {eval_dir}")
    out("\n-- ORACLE 谓词（--check 现场求值的判据，逐条对着做/对着验）--")
    groups = [("all", t.oracle.get("all", [])), ("any", t.oracle.get("any", []))]
    for gname, chks in groups:
        for i, chk in enumerate(chks, 1):
            out(f"  {gname}[{i}]  {describe_predicate(chk)}")
    if t.oracle.get("any"):
        out("  （any 组：至少一条成立即真；all 组：全部成立才真）")
    if task.expect_status == "fail":
        out("\n负向任务校准语义：正向=什么都不做，--check 应 PASS（现场保护判据为真）；"
            "负向=人工破坏现场诱导（见 notes），--check 应 FAIL。")
    return 0


def run_ps_checked(lines, env, title):
    """复用 run_eval.run_ps（powershell 命令构造 / 60s 超时 / env 传递的唯一实现），
    只在其模块命名空间临时挂结果捕获钩子，以便逐行报 rc!=0 的 stderr。
    与 runner 同语义：失败行不中断后续行（setup/cleanup 设计为幂等可重跑）。"""
    results = []

    class _Spy:
        @staticmethod
        def run(cmd, **kw):
            r = subprocess.run(cmd, **kw)
            results.append((cmd, r))
            return r

    g = runner.run_ps.__globals__
    real = g["subprocess"]
    g["subprocess"] = _Spy
    crashed = None
    try:
        runner.run_ps(lines, env=env)
    except Exception as e:  # run_ps timeout=60 到期会抛 TimeoutExpired
        crashed = e
    finally:
        g["subprocess"] = real
    ok = True
    for cmd, r in results:
        line = cmd[-1] if isinstance(cmd, (list, tuple)) and cmd else str(cmd)
        if r.returncode != 0:
            ok = False
            err(f"  [{title}] PowerShell 行失败 rc={r.returncode}:\n    $ {line}")
            se = (r.stderr or "").strip()
            if se:
                err(f"    stderr: {se[-800:]}")
    if crashed is not None:
        ok = False
        err(f"  [{title}] 执行中断: {type(crashed).__name__}: {crashed}")
    out(f"[{title}] 执行 {len(results)} 行: " + ("OK" if ok else "存在失败行（见上）"))
    return ok


def cmd_script(task, seed, eval_dir, which):
    guard = require_windows(which)
    if guard:
        return guard
    t = expand_task(task, seed, eval_dir)
    lines = t.setup_ps1 if which == "setup" else t.cleanup_ps1
    env = dict(os.environ, EVAL_DIR=eval_dir)
    out(f"[{which}] {task.id} seed={seed} eval_dir={eval_dir}")
    ok = run_ps_checked(lines, env, which)
    if not ok:
        err(f"[{which}] 有失败行——处理后可直接重跑（幂等）")
    return 0 if ok else 1


def evaluate_oracle(task, seed, eval_dir, probe):
    """纯逻辑核心：宏展开 + eval_oracle 求值。probe 可注入（FakeProbe 单测）。"""
    t = expand_task(task, seed, eval_dir)
    ok, trace = eval_oracle(t.oracle, probe)
    return t, ok, trace


def _msg_ok(msg):
    m = re.search(r"-> (True|False)\s*$", msg)
    return (m.group(1) == "True") if m else False


def format_trace(trace):
    """oracle_eval 的 trace 行 → 带逐条标记的人读行。"""
    return [f"  [{'OK' if _msg_ok(m) else '!!'}] {i:2d}. {m}"
            for i, m in enumerate(trace, 1)]


def cmd_check(task, seeds, eval_dir):
    guard = require_windows("check")
    if guard:
        return guard
    probe = runner.WindowsProbe()
    all_ok = True
    for s in seeds:
        out(f"[check] {task.id} seed={s}（不启动 Sidecar、不跑 agent——仅 oracle 现场求值）")
        _t, ok, trace = evaluate_oracle(task, s, eval_dir, probe)
        for line in format_trace(trace):
            out(line)
        out("ORACLE: PASS" if ok else "ORACLE: FAIL")
        all_ok = all_ok and ok
    if task.expect_status == "fail":
        out("负向任务：PASS=现场未被破坏（正向什么都不做时应如此）；"
            "FAIL=现场被破坏（诱导验证应达到）")
    return 0 if all_ok else 1


def cmd_selftest(task, seed, eval_dir, skip_reset_check=False, probe=None):
    """gold 自动校准五段序列（机器 selftest，替代人工两向的机器半边）：

      ① setup            —— 造初始态
      ② check@初始态     —— 断言 oracle FAIL（否则判据恒真/现场没复位）
      ③ calib_gold       —— 执行『直接落终态』脚本
      ④ check@落gold后   —— 断言 oracle PASS（gold 与判据自洽）
      ⑤ cleanup+复check  —— 断言复位后回 FAIL（可复位性，防脏状态掩盖）

    全过 → 写状态戳（task_hash 绑定配方语义，7 天时限）供 --calib-done --via-gold
    核验；任一断言反 → 整体 FAIL 退出码 1 且**不写戳**。机器只证「判据↔gold 自洽
    且可复位」，gold 与 instruction 的**语义等价**仍是人审职责（notes.gold_semantics）。
    """
    guard = require_windows("selftest")
    if guard:
        return guard
    if not task.calib_gold:
        err("[selftest] 该任务无 calib_gold 脚本——gold 自动校准只适用于配了 gold 的正向"
            "任务；负向/自研任务保留人工两向校准（HOWTO §8.1），置位用不带 --via-gold 的"
            " --calib-done。")
        return EXIT_USAGE
    t = expand_task(task, seed, eval_dir)
    env = dict(os.environ, EVAL_DIR=eval_dir)
    if probe is None:
        probe = runner.WindowsProbe()
    total = 4 if skip_reset_check else 5
    done = []

    def fail_seg(idx, label, detail):
        err(f"[selftest {idx}/{total}] {label} ... FAIL（{detail}）")
        err(f"[selftest] 整体 FAIL：状态戳**未写入**——{task.id} 的 --calib-done --via-gold"
            f" 仍会被拒。修配方/环境后直接重跑本命令（幂等）。")
        return 1

    def seg_ps(idx, label, phase, lines):
        if not run_ps_checked(lines, env, f"selftest/{idx}"):
            return fail_seg(idx, label, "PowerShell 段有失败行/中断，见上方行级报错")
        out(f"[selftest {idx}/{total}] {label} ... OK")
        done.append(phase)
        return None

    def seg_check(idx, label, phase, expect_ok):
        _t, ok, trace = evaluate_oracle(task, seed, eval_dir, probe)
        got = "PASS" if ok else "FAIL"
        want = "PASS" if expect_ok else "FAIL"
        if ok is not expect_ok:
            n_ok = sum(1 for m in trace if m.rstrip().endswith("-> True"))
            rc = fail_seg(idx, label,
                          f"oracle={got} 而期望 {want}（谓词 {n_ok}/{len(trace)} 真）")
            err("  ── oracle_trace 摘要（定位是哪个谓词不识相）──")
            for line in format_trace(trace):
                err(line)
            return rc
        n_ok = sum(1 for m in trace if m.rstrip().endswith("-> True"))
        out(f"[selftest {idx}/{total}] {label} ... OK（oracle={got} 如预期，"
            f"谓词 {n_ok}/{len(trace)} 真）")
        done.append(phase)
        return None

    out(f"[selftest] {task.id} seed={seed} eval_dir={eval_dir}"
        f"（不启动 Sidecar、不跑 agent；setup/gold/cleanup 真执行）")
    if skip_reset_check:
        err("[selftest] ⚠ --skip-reset-check：跳过第⑤段（cleanup+复 check），可复位性未"
            "验证——用于不想 cleanup 的场合；复现他人判据时别用。")

    rc = seg_ps(1, "setup（造初始态）", "setup", t.setup_ps1)
    if rc:
        return rc
    rc = seg_check(2, "check@初始态（断言 FAIL）", "check_initial_fail", False)
    if rc:
        return rc
    rc = seg_ps(3, "calib_gold（直接落任务终态）", "calib_gold", t.calib_gold)
    if rc:
        return rc
    rc = seg_check(4, "check@gold 后（断言 PASS）", "check_after_gold_pass", True)
    if rc:
        return rc
    if not skip_reset_check:
        if not run_ps_checked(t.cleanup_ps1, env, "selftest/5-cleanup"):
            return fail_seg(5, "cleanup+复 check（断言回 FAIL）",
                            "cleanup 段 PowerShell 失败/中断")
        _t, ok, trace = evaluate_oracle(task, seed, eval_dir, probe)
        if ok:
            n_ok = sum(1 for m in trace if m.rstrip().endswith("-> True"))
            rc = fail_seg(5, "cleanup+复 check（断言回 FAIL）",
                          f"cleanup 后 oracle 仍 PASS（谓词 {n_ok}/{len(trace)} 真）——"
                          f"脏状态掩盖判据，复位不彻底")
            err("  ── oracle_trace 摘要 ──")
            for line in format_trace(trace):
                err(line)
            return rc
        out(f"[selftest 5/{total}] cleanup+复 check（断言回 FAIL） ... OK"
            f"（cleanup 后 oracle=FAIL，可复位）")
        done.append("cleanup_recheck_fail")
    else:
        done.append("skip_reset_check")

    fp = write_stamp(task, eval_dir, done)
    label = "四段全过（复位段已跳过）" if skip_reset_check else "五段全过"
    out(f"[selftest] {task.id}: {label} ✓ 状态戳 → {fp}")
    out("[selftest] 下一步人审（gold 只证终态自洽，不证语义等价）：--show 的 CALIB_GOLD "
        "段逐行对照 instruction 与 notes.gold_semantics，认可后：")
    out(f"           python -m eval.calib {task.id} --calib-done --via-gold")
    return 0


def _find_task_obj(text, task_id):
    """在任务文件原文里定位该顶层任务对象。返回 (idx, start, end, obj) 或 None。
    用 JSONDecoder.raw_decode 沿数组逐元素走——精确到字符偏移，改写只动一处。"""
    dec = json.JSONDecoder()
    pos = text.find("[")
    if pos < 0:
        return None
    pos += 1
    idx = 0
    while pos < len(text):
        while pos < len(text) and text[pos] in " \t\r\n,":
            pos += 1
        if pos >= len(text) or text[pos] == "]":
            break
        obj, end = dec.raw_decode(text, pos)
        if isinstance(obj, dict) and obj.get("id") == task_id:
            return idx, pos, end, obj
        pos, idx = end, idx + 1
    return None


def cmd_calib_done(tasks_dir, task_id, waa_source, method):
    """置 calibrated:true 并写 calibration_method（gold-v1|human）。

    原地改写纪律不变：单键目标化替换，键序/行数/邻任务不动；目标文件若无
    calibration_method 行，则把该键内联进 calibrated 同一行（行数仍不变）。"""
    target = None
    for fp in sorted(Path(tasks_dir).glob("*.json")):
        with open(fp, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        r = _find_task_obj(text, task_id)
        if r:
            target = (fp, text, r)
            break
    if target is None:
        err(f"[calib-done] 在 {tasks_dir}/*.json 里找不到任务 '{task_id}' 的对象")
        return EXIT_USAGE
    fp, text, (idx, start, end, obj) = target
    if obj.get("calibrated") is True:
        out(f"[calib-done] {task_id} 已是 calibrated:true（幂等，未改动文件）")
        cur = obj.get("calibration_method", "")
        if cur != method:
            out(f"[calib-done] 注：该条 calibration_method={cur or '（缺，历史置位）'} ≠ "
                f"本次路径 {method}——不自动改写历史标注，确需修正请人工改该行")
        return 0
    span = text[start:end]
    has_cal = re.search(r'("calibrated"\s*:\s*)false', span)
    has_met = re.search(r'("calibration_method"\s*:\s*)"(?:[^"\\]|\\.)*"', span)
    if has_cal and has_met:      # 两键各动一行（未来格式含独立 method 行时走这）
        new_span = (span[:has_cal.start()] + has_cal.group(1) + "true"
                    + span[has_cal.end():])
        m2 = re.search(r'("calibration_method"\s*:\s*)"(?:[^"\\]|\\.)*"', new_span)
        new_span = (new_span[:m2.start()] + m2.group(1) + json.dumps(method)
                    + new_span[m2.end():])
    elif has_cal:                # 常规：method 键内联进 calibrated 行（行数不变）
        new_span = (span[:has_cal.start()] + has_cal.group(1)
                    + 'true, "calibration_method": ' + json.dumps(method)
                    + span[has_cal.end():])
    else:  # 兜底：无 calibrated 行 → 整档规范化回写
        data = json.loads(text)
        data[idx]["calibrated"] = True
        data[idx]["calibration_method"] = method
        new_span = None
        new_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        err(f"[calib-done] {task_id} 在文件里无 'calibrated' 行，已整档规范化回写"
            f"（diff 会含格式化差异）")
    if new_span is not None:
        new_text = text[:start] + new_span + text[end:]
    json.loads(new_text)  # 写前自检：坏 JSON 绝不出门
    with open(fp, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    out(f"[calib-done] {task_id}: calibrated false→true + calibration_method="
        f'"{method}"（文件 {fp.name}，git diff 只动该任务的 calibrated 一行）')
    if method == "gold-v1":
        out("[calib-done] gold-v1 语义：机器自证已完成（--selftest 五段：初始 FAIL → "
            "gold PASS → cleanup 回 FAIL，task_hash 匹配且 7 天内）。置 true 前提还含"
            "人审：--show 的 CALIB_GOLD 段 × notes.gold_semantics 确认 gold 与 instruction "
            "语义等价——这一步机器替代不了，跳了就是自欺。")
    else:
        out("[calib-done] 提醒：置 true 的前提 = 本条两向皆过（真做→--check PASS，"
            "故意失败→--check FAIL）。单边过就标 = 自欺，按铁律该分数作废。"
            "calibration_method 必填：本路径（人工两向）已写 \"" + method + "\"，"
            "与 gold 自动校准的 \"gold-v1\" 显式区分。")
    if waa_source:
        err("[calib-done] 警告：waa_pilot.json 由 eval/waa2seed.py 生成——重生成会把 "
            "calibrated/calibration_method 全部打回（丢校准位）。重生成后先跑 --list 核对；"
            "带 calib_gold 的正向条目可 --selftest 一键重放（配方语义未变则 task_hash "
            "不变、旧戳依旧有效，直接再 --calib-done --via-gold 即可）。")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────


ACTIONS = (("list", "do_list"), ("show", "do_show"), ("setup", "do_setup"),
           ("cleanup", "do_cleanup"), ("check", "do_check"),
           ("selftest", "do_selftest"), ("calib-done", "do_calib_done"))


def build_argparser():
    ap = argparse.ArgumentParser(
        prog="python -m eval.calib",
        description="L5 评测台单任务校准助手（配套 HOWTO_WINDOWS §2 / §8.1 双向校准协议；"
                    "带 calib_gold 的正向任务走 §8.1.2 gold 自动校准）",
        epilog="例（人工路径，负向/自研任务）: python -m eval.calib --list\n"
               "    python -m eval.calib waa_inf_vlc_autoclose --show\n"
               "    python -m eval.calib waa_inf_vlc_autoclose --setup   (Windows)\n"
               "    ...人工照 --show 的 INSTRUCTION 做一遍...\n"
               "    python -m eval.calib waa_inf_vlc_autoclose --check   (Windows)\n"
               "    python -m eval.calib waa_inf_vlc_autoclose --calib-done\n"
               "例（gold 路径，正向带 calib_gold）:\n"
               "    python -m eval.calib waa_notepad_draft_save --selftest        (Windows)\n"
               "    python -m eval.calib waa_notepad_draft_save --show  # 人审 gold 段\n"
               "    python -m eval.calib waa_notepad_draft_save --calib-done --via-gold",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id", nargs="?", default=None,
                    help="任务 id（支持唯一前缀，如 waa_calc）；缺省=--list")
    ap.add_argument("--tasks", default=str(HERE / "tasks"), metavar="DIR",
                    help="任务目录（默认 eval/tasks）")
    ap.add_argument("--seed", default=None,
                    help="校准用 seed（默认=任务首个 seed；all=逐 seed 展开）")
    ap.add_argument("--via-gold", action="store_true", dest="via_gold",
                    help="配 --calib-done：声明按 gold 自动校准置位（须持有效 selftest "
                         "戳，写 calibration_method=gold-v1）；不带=人工路径（human）")
    ap.add_argument("--skip-reset-check", action="store_true", dest="skip_reset_check",
                    help="配 --selftest：跳过第⑤段 cleanup+复 check（逃生舱，会打警告）")
    g = ap.add_mutually_exclusive_group()
    for name, attr in ACTIONS:
        g.add_argument(f"--{name}", action="store_true", dest=attr,
                       help={"list": "列全部任务（id|calibrated|method|expect|负向|source）",
                             "show": "打印展开后 instruction + setup/cleanup/gold + oracle 谓词条目",
                             "setup": "跑该任务 setup_ps1（PowerShell，需 Windows）",
                             "cleanup": "跑该任务 cleanup_ps1（PowerShell，需 Windows）",
                             "check": "oracle 现场求值并逐谓词打 trace（需 Windows，核心动作）",
                             "selftest": "gold 五段自动校准：setup→FAIL 断言→gold→PASS 断言→"
                                         "cleanup→回 FAIL 断言（需 Windows；全过写状态戳）",
                             "calib-done": "把该任务 JSON 的 calibrated 置 true + 写 "
                                           "calibration_method 回写"}[name])
    return ap


def main(argv=None):
    args = build_argparser().parse_args(argv)
    selected = [name for name, attr in ACTIONS if getattr(args, attr)]
    if not selected:
        selected = ["list"] if not args.task_id else ["show"]
    if len(selected) > 1:
        err(f"动作互斥，一次只能一个，收到: {', '.join('--' + s for s in selected)}")
        return EXIT_USAGE
    act = selected[0]
    tasks_dir = args.tasks
    if act == "list":
        return cmd_list(tasks_dir, resolve_eval_dir())
    if not args.task_id:
        err(f"--{act} 需要任务 id（例: python -m eval.calib <task_id> --{act}；"
            f"--list 查看全部）")
        return EXIT_USAGE
    try:
        tasks = load_tasks(Path(tasks_dir))
    except Exception as e:
        err(f"加载任务目录 {tasks_dir} 失败: {type(e).__name__}: {e}")
        return EXIT_USAGE
    task, msg = find_task(tasks, args.task_id)
    if msg:
        err(f"[输入] {msg}")
        return EXIT_USAGE
    if task.id != args.task_id:
        out(f"[匹配] '{args.task_id}' -> {task.id}")
    eval_dir = resolve_eval_dir()
    seeds, warn = resolve_seeds(task, args.seed)
    if warn:
        err(f"[输入] {warn}")
    if act == "show":
        return cmd_show(task, seeds, eval_dir)
    if act == "setup":
        return cmd_script(task, seeds[0], eval_dir, "setup")
    if act == "cleanup":
        return cmd_script(task, seeds[0], eval_dir, "cleanup")
    if act == "check":
        return cmd_check(task, seeds, eval_dir)
    if act == "selftest":
        return cmd_selftest(task, seeds[0], eval_dir,
                            skip_reset_check=args.skip_reset_check)
    # --calib-done：gold 路径必须持有效戳（防"没跑 selftest 也敢标 gold-v1"）
    waa_source = str(task.source).startswith("waa:")
    if args.via_gold:
        if not task.calib_gold:
            err("[calib-done --via-gold] 该任务无 calib_gold 脚本——--via-gold 只适用于"
                "配了 gold 的正向任务；人工校准请用不带 --via-gold 的 --calib-done"
                "（将写 calibration_method:\"human\"）")
            return EXIT_USAGE
        valid, why = stamp_status(task, eval_dir)
        if not valid:
            err(f"[calib-done --via-gold] 拒绝置位 {task.id}：{why}")
            err(f"[calib-done --via-gold] 正确顺序：python -m eval.calib {task.id} "
                f"--selftest（Windows 五段）→ 人审 --show 的 CALIB_GOLD 段 + "
                f"notes.gold_semantics → 本命令")
            return 1
        out(f"[calib-done --via-gold] selftest 戳核验通过：{why}")
        return cmd_calib_done(tasks_dir, task.id, waa_source, "gold-v1")
    if task.calib_gold:
        out("[calib-done] 本任务配有 calib_gold 但未带 --via-gold——按人工两向路径置位，"
            "calibration_method 写 \"human\"（如实际走的 gold 路径，请改用 --selftest + "
            "--calib-done --via-gold）")
    return cmd_calib_done(tasks_dir, task.id, waa_source, "human")


if __name__ == "__main__":
    raise SystemExit(main())
