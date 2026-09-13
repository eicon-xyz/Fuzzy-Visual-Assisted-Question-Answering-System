"""单任务校准助手（calib）—— Windows 评测机上手工校准的加速器。

把 HOWTO_WINDOWS §2/§8.1 的"每条任务手敲 run_eval 命令 + 翻 results/*.jsonl"
压缩成三步短命令：--setup 造初始态 → 照 --show 人工做 → --check 现场判分；
两向皆过（真做 PASS、故意失败 FAIL）后 --calib-done 置位。

本工具是评测台的**纯消费者**：宏展开复用 run_eval.expand_macros、PS 执行复用
run_eval.run_ps（同一 powershell 构造/超时/env 传递）、现场读取复用 run_eval.WindowsProbe、
判分复用 oracle_eval.eval_oracle、任务加载复用 eval.load_tasks——不另造第二套实现。

用法（工作目录 server_A）:
    python -m eval.calib --list                              # 任务总表（跨平台）
    python -m eval.calib waa_notepad_draft_save --show       # 照单真做看这个（跨平台）
    python -m eval.calib waa_notepad_draft_save --setup      # 造初始态（Windows）
    python -m eval.calib waa_notepad_draft_save --check      # oracle 现场求值（Windows）
    python -m eval.calib waa_notepad_draft_save --calib-done # 置 calibrated:true
非 Windows 上 --check/--setup/--cleanup 拒跑（它们是评测机上的现场动作）；
--list/--show/--calib-done 跨平台可用。--check 不启动 Sidecar、不跑 agent。
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval import load_tasks  # noqa: E402
from eval.oracle_eval import eval_oracle  # noqa: E402
import eval.run_eval as runner  # noqa: E402

HERE = Path(__file__).resolve().parent
IS_WINDOWS = os.name == "nt"
EXIT_USAGE = 2

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
    t.oracle = runner.expand_macros(t.oracle, eval_dir)
    return t


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


def cmd_list(tasks_dir):
    try:
        tasks = load_tasks(Path(tasks_dir))
    except Exception as e:
        err(f"加载任务目录 {tasks_dir} 失败: {type(e).__name__}: {e}")
        return EXIT_USAGE
    out(f"{'#':>3}  {'id':<36}{'calibrated':<11}{'expect':<9}{'负向':<5}source")
    n_cal = 0
    for i, t in enumerate(tasks, 1):
        neg = "是" if t.expect_status == "fail" else "-"
        src = (t.source or "")[:44]
        out(f"{i:>3}  {t.id:<36}{str(t.calibrated).lower():<11}"
            f"{t.expect_status:<9}{neg:<4}  {src}")
        n_cal += bool(t.calibrated)
    out(f"共 {len(tasks)} 条；calibrated {n_cal}/{len(tasks)}（未校准的分数不计 KPI）")
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
    out(f"\n  注：脚本里 $env:EVAL_DIR 由 --setup/--cleanup 注入 = {eval_dir}")
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


def cmd_calib_done(tasks_dir, task_id, waa_source):
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
        return 0
    span = text[start:end]
    m = re.search(r'("calibrated"\s*:\s*)false', span)
    if m:  # 目标化单行改写：键序/缩进/其余字节全部原样 → git diff 只有一行
        new_span = span[:m.start()] + m.group(1) + "true" + span[m.end():]
        new_text = text[:start] + new_span + text[end:]
    else:  # 兜底：该任务对象没有 calibrated 行（schema 默认 false）→ 整档规范化回写
        data = json.loads(text)
        data[idx]["calibrated"] = True
        new_text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        err(f"[calib-done] {task_id} 在文件里无 'calibrated' 行，已整档规范化回写"
            f"（diff 会含格式化差异）")
    json.loads(new_text)  # 写前自检：坏 JSON 绝不出门
    with open(fp, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    out(f"[calib-done] {task_id}: calibrated false→true（文件 {fp.name}，"
        f"git diff 应只有这一行）")
    out("[calib-done] 提醒：置 true 的前提 = 本条两向皆过（真做→--check PASS，"
        "故意失败→--check FAIL）。单边过就标 = 自欺，按铁律该分数作废。")
    if waa_source:
        err("[calib-done] 警告：waa_pilot.json 由 eval/waa2seed.py 生成——重生成会把 "
            "calibrated 全部打回 false（丢校准位）。重生成后需再跑 --list 核对，"
            "并对已验证过的条目重新 --calib-done（见 HOWTO §8.1）。")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────


ACTIONS = (("list", "do_list"), ("show", "do_show"), ("setup", "do_setup"),
           ("cleanup", "do_cleanup"), ("check", "do_check"),
           ("calib-done", "do_calib_done"))


def build_argparser():
    ap = argparse.ArgumentParser(
        prog="python -m eval.calib",
        description="L5 评测台单任务校准助手（配套 HOWTO_WINDOWS §2 / §8.1 双向校准协议）",
        epilog="例: python -m eval.calib --list\n"
               "    python -m eval.calib waa_notepad_draft_save --show\n"
               "    python -m eval.calib waa_notepad_draft_save --setup   (Windows)\n"
               "    ...人工照 --show 的 INSTRUCTION 做一遍...\n"
               "    python -m eval.calib waa_notepad_draft_save --check   (Windows)\n"
               "    python -m eval.calib waa_notepad_draft_save --calib-done",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id", nargs="?", default=None,
                    help="任务 id（支持唯一前缀，如 waa_calc）；缺省=--list")
    ap.add_argument("--tasks", default=str(HERE / "tasks"), metavar="DIR",
                    help="任务目录（默认 eval/tasks）")
    ap.add_argument("--seed", default=None,
                    help="校准用 seed（默认=任务首个 seed；all=逐 seed 展开）")
    g = ap.add_mutually_exclusive_group()
    for name, attr in ACTIONS:
        g.add_argument(f"--{name}", action="store_true", dest=attr,
                       help={"list": "列全部任务（id|calibrated|expect|负向|source）",
                             "show": "打印展开后 instruction + setup/cleanup + oracle 谓词条目",
                             "setup": "跑该任务 setup_ps1（PowerShell，需 Windows）",
                             "cleanup": "跑该任务 cleanup_ps1（PowerShell，需 Windows）",
                             "check": "oracle 现场求值并逐谓词打 trace（需 Windows，核心动作）",
                             "calib-done": "把该任务 JSON 的 calibrated 置 true 回写"}[name])
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
        return cmd_list(tasks_dir)
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
    return cmd_calib_done(tasks_dir, task.id, str(task.source).startswith("waa:"))


if __name__ == "__main__":
    raise SystemExit(main())
