"""eval/calib.py（单任务校准助手）的 Linux 单测。

覆盖任务书六项：①--list 全表 30 行 + calibrated 列；②--show 宏展开真实路径 +
oracle 逐谓词人读；③任务 id 唯一前缀匹配 / 歧义 / 找不到近似候选；
④--calib-done 在 tmp 副本上置 true：键序不破坏、只动一行、幂等；
⑤--check 等非 Windows 拒跑（rc≠0 且提示含 Windows）；
⑥核心纯逻辑（oracle 宏展开 + trace 格式化）用 FakeProbe 注入测
（沿用 test_eval_tools 的 probe 注入惯例）。
gold 自动校准扩展：⑦--selftest 五段序列状态机（monkeypatch run_ps_checked +
FakeProbe 可编程 FAIL→PASS→FAIL，含三种断言反例=整体 FAIL 且不写戳）；
⑧task_hash 漂移→旧戳自动失效；⑨--calib-done --via-gold 无戳拒绝/有戳成功
（calibration_method 正确写入）；⑩--list 的 method 列。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # server_A/

from eval import load_tasks  # noqa: E402
import eval.calib as calib  # noqa: E402
import eval.run_eval as runner  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "eval" / "tasks"


class FakeProbe:
    """同 test_eval_tools 惯例：oracle_eval 需要的七个探测方法全实现。"""

    def __init__(self, files=None, texts=None, globs=None, windows=None,
                 elements=None, regs=None, clip=""):
        self.files = files or set()
        self.texts = texts or {}
        self.globs = globs or {}
        self.windows = windows or []
        self.elements = elements or []
        self.regs = regs or {}
        self.clip = clip

    def file_exists(self, p):
        return p in self.files

    def read_text(self, p):
        return self.texts.get(p)

    def glob_count(self, g):
        return self.globs.get(g, 0)

    def reg_value(self, hive, key, name):
        return self.regs.get(f"{hive}\\{key}\\{name}")

    def clipboard(self):
        return self.clip

    def window_titles(self):
        return self.windows

    def element_names(self, window_title_contains=None, element_type=None):
        out = self.elements
        if window_title_contains:
            out = [e for e in out if window_title_contains in e.get("w", "")]
        return [e["n"] for e in out]


def _run(capsys, argv):
    rc = calib.main(argv)
    o = capsys.readouterr()
    return rc, o.out, o.out + o.err


# ── ① --list ────────────────────────────────────────────────────────────

def test_list_shows_all_30_with_columns(capsys):
    rc, out, _ = _run(capsys, ["--list"])
    assert rc == 0
    rows = [l for l in out.splitlines() if re.match(r"^\s*\d+\s{2}\S", l)]
    assert len(rows) == 30, "eval/tasks 应为 20 自研 + 10 WAA pilot = 30 行"
    byid = {l.split()[1]: l for l in rows}
    # calibrated 列：WAA pilot 必须全未校准（铁律：新集必须未校准）；
    # 自研 B1 已校准 5 条允许 true，其余必须 false
    B1_CALIBRATED = {"notepad_type_save", "explorer_rename_file",
                     "explorer_new_folder", "notepad_type_chinese",
                     "notepad_click_nonexistent"}
    for l in rows:
        lid, cal = l.split()[1], l.split()[2]
        if lid in B1_CALIBRATED:
            assert cal == "true", lid
        else:
            assert cal == "false", f"{lid} 应未校准，实际 {cal}"
    assert byid["waa_notepad_draft_save"].split()[2] == "false"
    # expect_status + 负向标记列
    assert "fail" in byid["waa_inf_vscode_arabic"]
    assert "success" in byid["waa_fe_archive_docx"]
    neg = [i for i, l in enumerate(rows) if re.search(r"\bfail\b", l)]
    assert len(neg) == 5  # 实况：seed.json 2 条 + pilot 3 条负向
    assert "是" in byid["notepad_click_nonexistent"] and "是" in byid["waa_inf_vlc_autoclose"]


# ── ② --show ────────────────────────────────────────────────────────────

def test_show_expands_macros_and_lists_predicates(capsys):
    ed = calib.resolve_eval_dir()  # Linux 无 LOCALAPPDATA → 家目录回落（与 run_eval 同逻辑）
    rc, out, _ = _run(capsys, ["waa_notepad_draft_save", "--show"])
    assert rc == 0
    assert ed in out, "instruction 应展示宏展开后的真实 eval_dir"
    assert "notepad_draft_a" in out, "默认 seed = 任务首个 seed"
    assert "This is a draft." in out, "中文 instruction 原文可见"
    # setup/cleanup 脚本可见（$env:EVAL_DIR + 注入值注明）
    assert "New-Item -ItemType Directory" in out and "Get-Process notepad" in out
    assert ed in out.split("注：")[1], "PS 侧 $env:EVAL_DIR 的值也要可见"
    # oracle 逐谓词条目化：每行一个谓词 + 人读含义
    assert re.search(r"all\[1\]\s+file_exists .* —— 文件必须存在", out)
    assert re.search(r"all\[2\]\s+file_content_equals .* —— 文件内容必须等于", out)
    assert "{EVAL_DIR}" not in out.split("-- INSTRUCTION")[1], "展示区不得残留未展开宏"


# ── ③ 前缀匹配 / 歧义 / 找不到 ──────────────────────────────────────────

def test_id_prefix_unique_hit(capsys):
    rc, out, _err = _run(capsys, ["waa_calc"])  # 缺省动作=show
    assert rc == 0
    assert "'waa_calc' -> waa_calc_days_to_file" in out


def test_id_prefix_ambiguous_and_unknown(capsys):
    rc, _o, comb = _run(capsys, ["waa_notepad", "--show"])
    assert rc != 0
    assert "歧义" in comb
    assert "waa_notepad_draft_save" in comb and "waa_notepad_count_example" in comb
    rc, _o, comb = _run(capsys, ["waa_calc_days_to_filee", "--show"])  # 拼错的近似
    assert rc != 0
    assert "找不到" in comb and "waa_calc_days_to_file" in comb


# ── ④ --calib-done（tmp 副本上回写）─────────────────────────────────────

def test_calib_done_edits_one_line_keeps_order_and_idempotent(tmp_path, capsys):
    d = tmp_path / "tasks"
    d.mkdir()
    for f in ("waa_pilot.json", "seed.json"):
        shutil.copy(TASKS_DIR / f, d / f)
    orig = (d / "waa_pilot.json").read_text(encoding="utf-8")

    rc, out, errtext = _run(capsys, ["--tasks", str(d), "waa_fe_archive", "--calib-done"])
    assert rc == 0
    new = (d / "waa_pilot.json").read_text(encoding="utf-8")
    olines, nlines = orig.splitlines(), new.splitlines()
    assert len(olines) == len(nlines), "回写不得改变行数（目标化单行编辑）"
    diff = [(a, b) for a, b in zip(olines, nlines) if a != b]
    assert diff == [('    "calibrated": false,',
                     '    "calibrated": true, "calibration_method": "human",')], \
        "git-diff 等价面：只许动 calibrated 这一行（method 键内联同行，行数不变）"
    data = json.loads(new)
    assert data[0]["calibrated"] is True
    assert data[0]["calibration_method"] == "human"
    okeys = list(json.loads(orig)[0].keys())
    cut = okeys.index("calibrated") + 1
    assert list(data[0].keys()) == \
        okeys[:cut] + ["calibration_method"] + okeys[cut:], "既有键序不破坏，新键只内联在 calibrated 后"
    assert all(t["calibrated"] is False for t in data[1:]), "不得误伤其他任务"
    # waa 重生成的坑必须警告；两向皆过提醒必须打印；无 gold 走 human 必填提醒
    assert "重生成" in errtext and "两向皆过" in out

    # 幂等：再跑一次不改文件
    rc, out2, _ = _run(capsys, ["--tasks", str(d), "waa_fe_archive_docx", "--calib-done"])
    assert rc == 0 and "已是" in out2
    assert (d / "waa_pilot.json").read_text(encoding="utf-8") == new

    # 紧凑手写格式的 seed.json 同样只动一行
    # B1 后 notepad_type_save 已是 true——先在副本上复位为 false 构造可测初始态
    sp = d / "seed.json"
    sraw = sp.read_text(encoding="utf-8")
    sp.write_text(sraw.replace(
        '"calibrated": true, "calibration_method": "human",',
        '"calibrated": false,', 1), encoding="utf-8")
    sorig = sp.read_text(encoding="utf-8")
    assert '"calibrated": false,' in sorig
    rc, *_ = _run(capsys, ["--tasks", str(d), "notepad_type_save", "--calib-done"])
    assert rc == 0
    snew = (d / "seed.json").read_text(encoding="utf-8")
    sd = [(a, b) for a, b in zip(sorig.splitlines(), snew.splitlines()) if a != b]
    assert len(sd) == 1 and len(sorig.splitlines()) == len(snew.splitlines())

    # 回写后文件仍是 loader 认可的合法任务集，且校准计数正确
    tasks = load_tasks(d)
    assert len(tasks) == 30
    # B1 已校准 4 条（seed 中除被复位再置回的 notepad_type_save 外）+ waa 1 条 = 5
    cal_ids = {t.id for t in tasks if t.calibrated}
    assert cal_ids == {"notepad_type_save", "explorer_rename_file",
                       "explorer_new_folder", "notepad_type_chinese",
                       "notepad_click_nonexistent", "waa_fe_archive_docx"}


# ── ⑤ 非 Windows 动作闸 ─────────────────────────────────────────────────

def test_windows_only_actions_refuse_off_windows(capsys, monkeypatch):
    monkeypatch.setattr(calib, "IS_WINDOWS", False)  # 本机=Linux 也显式钉住，Windows 上跑测不翻转
    for act in ("--check", "--setup", "--cleanup", "--selftest"):
        rc, _o, comb = _run(capsys, ["waa_notepad_draft_save", act])
        assert rc != 0, f"{act} 在非 Windows 必须拒跑"
        assert "Windows" in comb, "提示须说明要在 Windows 评测机上跑"


# ── ⑥ 核心纯逻辑：宏展开 + eval_oracle + trace 格式化（FakeProbe 注入）──

def test_evaluate_oracle_and_format_trace():
    tasks = {t.id: t for t in load_tasks(TASKS_DIR)}
    ed = "C:/ev"  # 任意 eval_dir，验证宏展开贯穿到谓词参数
    t = tasks["waa_fe_archive_docx"]
    base = f"{ed}/waa_pilot/fe_archive_a/Documents"
    p_ok = FakeProbe(files={f"{base}/Archive/Doc01.docx", f"{base}/Archive/Doc02.docx"})
    _t, ok, trace = calib.evaluate_oracle(t, "a", ed, p_ok)
    assert ok and len(trace) == 4
    assert all("{EVAL_DIR}" not in m and "{seed}" not in m for m in trace), "宏必须全展开"
    lines = calib.format_trace(trace)
    assert sum("[OK]" in l for l in lines) == 4 and not any("[!!]" in l for l in lines)
    # 故意失败方向：文件没移动 → 4 条全不成立 → FAIL
    p_bad = FakeProbe(files={f"{base}/Doc01.docx", f"{base}/Doc02.docx"})
    _t, ok, trace = calib.evaluate_oracle(t, "a", ed, p_bad)
    assert not ok
    assert sum("[!!]" in l for l in calib.format_trace(trace)) == 4


def test_check_cli_wires_probe_and_exit_code(capsys, monkeypatch, tmp_path):
    d = tmp_path / "tasks"
    d.mkdir()
    shutil.copy(TASKS_DIR / "waa_pilot.json", d / "waa_pilot.json")
    ed = calib.resolve_eval_dir()
    base = f"{ed}/waa_pilot/fe_archive_a/Documents"
    probe = FakeProbe(files={f"{base}/Archive/Doc01.docx", f"{base}/Archive/Doc02.docx"})
    monkeypatch.setattr(calib, "IS_WINDOWS", True)          # 假装在评测机
    monkeypatch.setattr(runner, "WindowsProbe", lambda: probe)  # probe 注入（复用面不变）
    rc, out, _ = _run(capsys, ["--tasks", str(d), "waa_fe_archive_docx", "--check"])
    assert rc == 0 and "ORACLE: PASS" in out
    probe.files = set()
    rc, out, _ = _run(capsys, ["--tasks", str(d), "waa_fe_archive_docx", "--check"])
    assert rc == 1 and "ORACLE: FAIL" in out


def test_describe_predicate_covers_whitelist():
    from eval import ORACLE_TYPES
    for typ, fields in ORACLE_TYPES.items():
        chk = {"type": typ, **{k: f"<{k}>" for k in fields}}
        d = calib.describe_predicate(chk)
        assert typ in d and "——" in d and typ in calib.PREDICATE_MEANING, f"{typ} 缺人读含义"


# ── ⑦ --selftest 五段状态机（monkeypatch run_ps_checked + 可编程 FakeProbe）──

GOLD_ID = "waa_notepad_draft_save"
STAMP_DONE = ["setup", "check_initial_fail", "calib_gold",
              "check_after_gold_pass", "cleanup_recheck_fail"]


def _draft_path(ed):
    return f"{ed}/waa_pilot/notepad_draft_a/draft.txt"


def _selftest_env(tmp_path, monkeypatch, behavior=None):
    """共享布景：任务副本 + eval_dir 重定向 + 假 run_ps_checked（按调用次序走
    setup→gold→cleanup 状态迁移）+ FakeProbe 引用同一 files/texts。
    behavior 造三种断言反例：
      setup_no_reset   → setup 不复位，第②段（初始应 FAIL）翻转
      gold_no_effect   → gold 不落盘，第④段（gold 后应 PASS）翻转
      cleanup_no_reset → cleanup 不清场，第⑤段（复位应回 FAIL）翻转
    """
    d = tmp_path / "tasks"
    d.mkdir()
    shutil.copy(TASKS_DIR / "waa_pilot.json", d / "waa_pilot.json")
    ed = str(tmp_path / "evalroot")
    monkeypatch.setattr(calib, "IS_WINDOWS", True)
    monkeypatch.setattr(calib, "resolve_eval_dir", lambda: ed)
    # 假 probe 与 fake_ps 共享同一容器对象：FakeProbe 的 `files or set()` 会在传入
    # 空容器时换新对象——先带哨兵构造，构造完即从同一对象摘除哨兵
    files, texts, ps_calls = {"/dummy"}, {"/dummy": ""}, []
    p = _draft_path(ed)
    if behavior == "setup_no_reset":          # 脏现场：初始态就是 PASS
        files.add(p)
        texts[p] = "This is a draft.\r\n"
    probe = FakeProbe(files=files, texts=texts)
    files.discard("/dummy")
    texts.pop("/dummy", None)

    def fake_ps(lines, env, title):
        ps_calls.append((title, list(lines)))
        step = len(ps_calls)
        if (behavior == "setup_no_reset" and step == 1) or \
           (behavior == "gold_no_effect" and step == 2) or \
           (behavior == "cleanup_no_reset" and step == 3):
            return True                        # "跑了但没效果"——制造断言反
        if step == 2:                          # gold 段：直接落终态
            files.add(p)
            texts[p] = "This is a draft.\r\n"
        else:                                  # setup/cleanup 段：复位
            files.discard(p)
            texts.pop(p, None)
        return True

    monkeypatch.setattr(calib, "run_ps_checked", fake_ps)
    monkeypatch.setattr(runner, "WindowsProbe", lambda: probe)
    return d, ed, ps_calls


def test_selftest_five_segments_pass_and_stamp(capsys, monkeypatch, tmp_path):
    d, ed, ps_calls = _selftest_env(tmp_path, monkeypatch)
    rc, out, comb = _run(capsys, ["--tasks", str(d), GOLD_ID, "--selftest"])
    assert rc == 0, comb
    for i in range(1, 6):
        assert re.search(rf"\[selftest {i}/5\].*OK", out), f"第{i}段应 OK:\n{out}"
    # PS 执行次序 = setup → gold → cleanup（check 段不碰 PS）
    assert [t for t, _l in ps_calls] == ["selftest/1", "selftest/3",
                                         "selftest/5-cleanup"]
    all_lines = [l for _t, ls in ps_calls for l in ls]
    assert all("{EVAL_DIR}" not in l and "{seed}" not in l for l in all_lines), \
        "进 PS 的行必须两跳展开（同 --setup 语义）"
    assert any("$env:EVAL_DIR/waa_pilot/notepad_draft_a/draft.txt" in l
               for l in ps_calls[1][1]), \
        "gold 段目标=oracle 同一文件（{seed} 已代入；PS 侧路径按设计留 $env:EVAL_DIR）"
    assert "人审" in out and "--calib-done --via-gold" in out, "成功输出必须指路人审下一步"
    sp = Path(ed) / ".calib_stamps" / (GOLD_ID + ".json")
    rec = json.loads(sp.read_text(encoding="utf-8"))
    task = next(t for t in load_tasks(d) if t.id == GOLD_ID)
    assert rec["task_hash"] == calib.task_hash(task)
    assert rec["phases"] == STAMP_DONE
    datetime.fromisoformat(rec["ts"])
    assert calib.stamp_status(task, ed)[0] is True, "刚写的戳必须即刻有效"


@pytest.mark.parametrize("behavior,bad_seg,marker", [
    ("setup_no_reset", 2, "oracle=PASS 而期望 FAIL"),    # 初始态断言反
    ("gold_no_effect", 4, "oracle=FAIL 而期望 PASS"),    # gold 后断言反
    ("cleanup_no_reset", 5, "脏状态掩盖"),               # 复位断言反
])
def test_selftest_assertion_reversals_fail_and_no_stamp(
        capsys, monkeypatch, tmp_path, behavior, bad_seg, marker):
    d, ed, ps_calls = _selftest_env(tmp_path, monkeypatch, behavior)
    rc, out, comb = _run(capsys, ["--tasks", str(d), GOLD_ID, "--selftest"])
    assert rc == 1, f"{behavior} 必须整体 FAIL"
    assert f"[selftest {bad_seg}/5]" in comb and marker in comb
    assert "oracle_trace 摘要" in comb, "断言反例要打逐谓词 trace 供定位"
    assert "状态戳**未写入**" in comb
    assert not (_draft_path(ed) and (Path(ed) / ".calib_stamps" /
                                     (GOLD_ID + ".json")).exists())
    if behavior == "cleanup_no_reset":
        assert [t for t, _l in ps_calls] == ["selftest/1", "selftest/3",
                                             "selftest/5-cleanup"]


def test_selftest_skip_reset_check_escape_hatch(capsys, monkeypatch, tmp_path):
    d, ed, ps_calls = _selftest_env(tmp_path, monkeypatch)
    rc, out, comb = _run(capsys, ["--tasks", str(d), GOLD_ID, "--selftest",
                                  "--skip-reset-check"])
    assert rc == 0
    assert "跳过第⑤段" in comb, "逃生舱必须打警示"
    assert [t for t, _l in ps_calls] == ["selftest/1", "selftest/3"], \
        "skip 时不得执行 cleanup"
    assert not any("[selftest 5/" in out for _ in [0])
    rec = json.loads((Path(ed) / ".calib_stamps" / (GOLD_ID + ".json"))
                     .read_text(encoding="utf-8"))
    assert rec["phases"] == STAMP_DONE[:4] + ["skip_reset_check"]


def test_selftest_refused_for_task_without_gold(capsys, monkeypatch, tmp_path):
    d, ed, _ = _selftest_env(tmp_path, monkeypatch)
    rc, _o, comb = _run(capsys, ["--tasks", str(d), "waa_inf_vscode_arabic",
                                 "--selftest"])
    assert rc == 2 and "calib_gold" in comb and "人工" in comb


# ── ⑧ task_hash 漂移 → 旧戳自动失效 ──────────────────────────────────────

def test_task_hash_drift_invalidates_old_stamp(capsys, monkeypatch, tmp_path):
    d, ed, _ = _selftest_env(tmp_path, monkeypatch)
    rc, out, comb = _run(capsys, ["--tasks", str(d), GOLD_ID, "--selftest"])
    assert rc == 0, comb
    task = next(t for t in load_tasks(d) if t.id == GOLD_ID)
    assert calib.stamp_status(task, ed)[0] is True
    # 配方语义变更：gold 末行文本改一个字符 → hash 变、旧戳作废
    fp = d / "waa_pilot.json"
    data = json.loads(fp.read_text(encoding="utf-8"))
    obj = next(x for x in data if x["id"] == GOLD_ID)
    obj["calib_gold"][-1] = obj["calib_gold"][-1].replace(
        'This is a draft." ', 'This is a draft!\" ')
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
    task2 = next(t for t in load_tasks(d) if t.id == GOLD_ID)
    assert calib.task_hash(task2) != calib.task_hash(task)
    ok, why = calib.stamp_status(task2, ed)
    assert not ok and "task_hash" in why
    rc, _o, comb = _run(capsys, ["--tasks", str(d), GOLD_ID, "--calib-done",
                                 "--via-gold"])
    assert rc == 1 and "拒绝置位" in comb and "重跑 --selftest" in comb
    assert "calibration_method" not in json.dumps(
        [t for t in json.loads(fp.read_text(encoding="utf-8"))
         if t["id"] == GOLD_ID][0])  # 被拒后文件不得留下半截置位
    # 时限半边：把 ts 拨到 8 天前 → 过期拒；拨回 6 天前 → 有效
    sp = Path(ed) / ".calib_stamps" / (GOLD_ID + ".json")
    rec = json.loads(sp.read_text(encoding="utf-8"))
    for days, want_ok in ((8, False), (6, True)):
        rec["ts"] = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
            timespec="seconds")
        sp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        ok, why = calib.stamp_status(task, ed)
        assert ok is want_ok, f"{days} 天应为 {want_ok}: {why}"
        if not ok:
            assert "过期" in why and "7 天" in why


# ── ⑨ --calib-done --via-gold 核验矩阵 ───────────────────────────────────

def test_calib_done_via_gold_requires_valid_stamp(capsys, monkeypatch, tmp_path):
    d = tmp_path / "tasks"
    d.mkdir()
    shutil.copy(TASKS_DIR / "waa_pilot.json", d / "waa_pilot.json")
    ed = str(tmp_path / "evalroot")
    monkeypatch.setattr(calib, "resolve_eval_dir", lambda: ed)
    orig = (d / "waa_pilot.json").read_text(encoding="utf-8")

    # 无戳 → 拒绝 + 指路 --selftest，文件不动
    rc, _o, comb = _run(capsys, ["--tasks", str(d), "waa_fe_move", "--calib-done",
                                 "--via-gold"])
    assert rc == 1 and "无 selftest 状态戳" in comb and "--selftest" in comb
    assert (d / "waa_pilot.json").read_text(encoding="utf-8") == orig

    # 无 calib_gold 的任务用 --via-gold → 用法错
    rc, _o, comb = _run(capsys, ["--tasks", str(d), "waa_inf_vscode_arabic",
                                 "--calib-done", "--via-gold"])
    assert rc == 2 and "无 calib_gold" in comb

    # 有戳 → 成功，calibrated:true + calibration_method:gold-v1，行数不变
    task = next(t for t in load_tasks(d) if t.id == "waa_fe_move_myfolder")
    calib.write_stamp(task, ed, STAMP_DONE)
    rc, out, comb = _run(capsys, ["--tasks", str(d), "waa_fe_move", "--calib-done",
                                  "--via-gold"])
    assert rc == 0 and "戳核验通过" in out, comb
    new = (d / "waa_pilot.json").read_text(encoding="utf-8")
    assert len(new.splitlines()) == len(orig.splitlines())
    diff = [(a, b) for a, b in zip(orig.splitlines(), new.splitlines()) if a != b]
    assert diff == [('    "calibrated": false,',
                     '    "calibrated": true, "calibration_method": "gold-v1",')]
    obj = next(x for x in json.loads(new) if x["id"] == "waa_fe_move_myfolder")
    assert obj["calibrated"] is True and obj["calibration_method"] == "gold-v1"
    assert "gold-v1 语义" in out and "人审" in out
    # 幂等再跑不动文件
    rc, out2, _ = _run(capsys, ["--tasks", str(d), "waa_fe_move_myfolder",
                                "--calib-done", "--via-gold"])
    assert rc == 0 and "已是" in out2
    assert (d / "waa_pilot.json").read_text(encoding="utf-8") == new


# ── ⑩ --list 的 method 列 ────────────────────────────────────────────────

def test_list_method_column_states(capsys, monkeypatch, tmp_path):
    d = tmp_path / "tasks"
    d.mkdir()
    shutil.copy(TASKS_DIR / "waa_pilot.json", d / "waa_pilot.json")
    ed = str(tmp_path / "evalroot")
    monkeypatch.setattr(calib, "resolve_eval_dir", lambda: ed)
    tasks = {t.id: t for t in load_tasks(d)}
    # 有戳未置位 → gold✓
    calib.write_stamp(tasks["waa_fe_move_myfolder"], ed, STAMP_DONE)
    # gold-v1 置位
    calib.write_stamp(tasks["waa_notepad_draft_save"], ed, STAMP_DONE)
    rc, out, _ = _run(capsys, ["--tasks", str(d), "waa_notepad_draft_save",
                               "--calib-done", "--via-gold"])
    assert rc == 0
    # human 置位（无 gold 的负向走人工路径）
    rc, out, _ = _run(capsys, ["--tasks", str(d), "waa_inf_vscode_arabic",
                               "--calib-done"])
    assert rc == 0
    rc, out, _ = _run(capsys, ["--tasks", str(d), "--list"])
    assert rc == 0
    header = out.splitlines()[0]
    assert "calibrated" in header and "method" in header and "expect" in header
    rows = {l.split()[1]: l for l in out.splitlines()
            if re.match(r"^\s*\d+\s{2}\S", l)}
    assert len(rows) == 10  # tmp 目录只放了 waa_pilot.json
    assert "gold-v1" in rows["waa_notepad_draft_save"]
    assert "gold✓" in rows["waa_fe_move_myfolder"]
    assert "human" in rows["waa_inf_vscode_arabic"]
    for tid in ("waa_calc_days_to_file", "waa_notepad_count_example",
                "waa_fe_archive_docx"):  # 有 gold 无戳/未置位 → 该列为空
        cells = rows[tid].split()
        assert cells[2] == "false" and cells[3] in ("success", "fail"), \
            f"{tid}: method 列应为空（{rows[tid]!r}）"
    assert "gold✓" in out.splitlines()[-1], "表尾图例必须解释 gold✓"
