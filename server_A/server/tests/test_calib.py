"""eval/calib.py（单任务校准助手）的 Linux 单测。

覆盖任务书六项：①--list 全表 30 行 + calibrated 列；②--show 宏展开真实路径 +
oracle 逐谓词人读；③任务 id 唯一前缀匹配 / 歧义 / 找不到近似候选；
④--calib-done 在 tmp 副本上置 true：键序不破坏、只动一行、幂等；
⑤--check 等非 Windows 拒跑（rc≠0 且提示含 Windows）；
⑥核心纯逻辑（oracle 宏展开 + trace 格式化）用 FakeProbe 注入测
（沿用 test_eval_tools 的 probe 注入惯例）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

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
    # calibrated 列：当前入库口径 = 全 false（铁律：新集必须未校准）
    assert all(" false " in l or l.split()[2] == "false" for l in rows)
    assert byid["waa_notepad_draft_save"].split()[2] == "false"
    assert byid["notepad_type_save"].split()[2] == "false"
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
    assert diff == [('    "calibrated": false,', '    "calibrated": true,')], \
        "git-diff 等价面：只许动 calibrated 这一行"
    data = json.loads(new)
    assert data[0]["calibrated"] is True
    assert list(data[0].keys()) == list(json.loads(orig)[0].keys()), "键序不破坏"
    assert all(t["calibrated"] is False for t in data[1:]), "不得误伤其他任务"
    # waa 重生成的坑必须警告；两向皆过提醒必须打印
    assert "重生成" in errtext and "两向皆过" in out

    # 幂等：再跑一次不改文件
    rc, out2, _ = _run(capsys, ["--tasks", str(d), "waa_fe_archive_docx", "--calib-done"])
    assert rc == 0 and "已是" in out2
    assert (d / "waa_pilot.json").read_text(encoding="utf-8") == new

    # 紧凑手写格式的 seed.json 同样只动一行
    sorig = (d / "seed.json").read_text(encoding="utf-8")
    rc, *_ = _run(capsys, ["--tasks", str(d), "notepad_type_save", "--calib-done"])
    assert rc == 0
    snew = (d / "seed.json").read_text(encoding="utf-8")
    sd = [(a, b) for a, b in zip(sorig.splitlines(), snew.splitlines()) if a != b]
    assert len(sd) == 1 and len(sorig.splitlines()) == len(snew.splitlines())

    # 回写后文件仍是 loader 认可的合法任务集，且校准计数正确
    tasks = load_tasks(d)
    assert len(tasks) == 30 and sum(t.calibrated for t in tasks) == 2


# ── ⑤ 非 Windows 动作闸 ─────────────────────────────────────────────────

def test_windows_only_actions_refuse_off_windows(capsys, monkeypatch):
    monkeypatch.setattr(calib, "IS_WINDOWS", False)  # 本机=Linux 也显式钉住，Windows 上跑测不翻转
    for act in ("--check", "--setup", "--cleanup"):
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
