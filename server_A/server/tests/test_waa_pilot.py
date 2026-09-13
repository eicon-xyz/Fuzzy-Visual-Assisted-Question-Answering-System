"""WP-PILOT：WAA 移植任务集（tasks/waa_pilot.json）与移植器 waa2seed 的 Linux 单测。

覆盖任务书四类断言：①loader 能加载 30 条（自研 20 + WAA 10）且新集全未校准；
②移植器离线 fixture（2 条真实 WAA JSON）映射后的 oracle/setup 结构；
③谓词白名单（waa_pilot 每个 oracle 谓词 ∈ ORACLE_TYPES）；④负向 expect_status。
另加：任务文件与移植器输出的一致性（可重跑=当前文件）。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # server_A/

from eval import ORACLE_TYPES, load_tasks, validate_task  # noqa: E402
from eval import waa2seed  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "eval" / "tasks"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "waa"
PILOT_FILE = TASKS_DIR / "waa_pilot.json"


def _pilot_tasks():
    data = json.loads(PILOT_FILE.read_text(encoding="utf-8"))
    return [validate_task(r, src="waa_pilot.json") for r in data]


def test_loader_accepts_full_set_of_30():
    """① 零改 loader：eval/tasks 下 20 自研 + 10 WAA = 30 条全部通过校验。"""
    tasks = load_tasks(TASKS_DIR)
    assert len(tasks) == 30, f"应为 30 条，实际 {len(tasks)}"
    waa = [t for t in tasks if t.source.startswith("waa:")]
    hand = [t for t in tasks if not t.source.startswith("waa:")]
    assert len(waa) == 10 and len(hand) == 20
    # 自研 seed.json 一条不许被动过（红线）
    assert {t.id for t in hand} == {
        "notepad_type_save", "notepad_menu_font_dialog", "settings_display_search",
        "explorer_rename_file", "explorer_new_folder", "calculator_add",
        "notepad_find_dialog_type", "wordpad_bold_via_menu",
        "browser_search_result_expect", "browser_form_fill_login",
        "notepad_click_nonexistent", "notepad_repeated_dead_click",
        "notepad_close_popup_dialog", "mspaint_open_via_start",
        "notepad_settings_zoom_via_menu", "taskmgr_sort_column",
        "notepad_type_chinese", "explorer_select_all_delete",
        "browser_tab_switch", "control_panel_power_plan"}
    # 未校准不计 KPI 的纪律：新入集必须 calibrated:false
    assert all(t.calibrated is False for t in waa)
    # 溯源完整：每条 source 指回 WAA 原任务 id
    for t in waa:
        assert t.source.startswith("waa:") and len(t.source) > 6


def test_pilot_file_matches_converter_output():
    """移植器可重跑：当前 waa_pilot.json == 离线缓存重转结果（审计一致性）。"""
    all_tasks = waa2seed.read_offline(Path("/root/HAJIMI/.waa_cache"))
    if not all_tasks:
        pytest.skip("WAA 调研缓存不在本机，一致性检查跳过")
    converted, skipped = waa2seed.convert(all_tasks)
    on_disk = json.loads(PILOT_FILE.read_text(encoding="utf-8"))
    assert len(converted) == 10, f"应移植 10 条（跳过原因见 skipped）: " \
        f"{[s for s in skipped if '漂移' in s[2] or '断言' in s[2]]}"
    # 同 id 集 + 逐条内容一致（入库顺序=正向在前，比对时排序消除顺序噪声）
    assert sorted(t["id"] for t in converted) == sorted(t["id"] for t in on_disk)
    key = lambda t: t["id"]
    assert sorted(converted, key=key) == sorted(on_disk, key=key), \
        "移植器输出与入库文件不一致（漂移？）"


def test_converter_fixture_maps_expected_structure():
    """② 真实 WAA JSON fixture → 映射后的 oracle/setup 结构逐字段断言。"""
    fixtures = waa2seed.read_offline(FIXTURE_DIR)
    assert len(fixtures) == 2
    tasks, skipped = waa2seed.convert(fixtures)
    assert skipped == []
    by_src = {t["source"]: t for t in tasks}

    # 记事本草稿：WAA [exact_match(存在) + compare_text_file(gold)] → exists + equals
    draft = by_src["waa:366de66e-cbae-4d72-b042-26390db2b145-WOS"]
    preds = draft["oracle"]["all"]
    assert [p["type"] for p in preds] == ["file_exists", "file_content_equals"]
    assert preds[0]["path"].startswith("{EVAL_DIR}/waa_pilot/")
    assert "draft.txt" in preds[0]["path"] and "{seed}" in preds[0]["path"]
    assert preds[1]["text"] == "This is a draft."          # gold 内容内联（实测 16B）
    assert draft["seeds"] == ["a", "b", "c"]
    assert draft["expect_status"] == "success"
    assert draft["calibrated"] is False
    assert any("New-Item" in s for s in draft["setup_ps1"])      # 幂等建沙箱
    assert any("Stop-Process" in s for s in draft["cleanup_ps1"])
    # 溯源：notes + waa_orig 保留 WAA 原 evaluator
    assert "exact_match" in draft["notes"] and "compare_text_file" in draft["notes"]
    assert draft["waa_orig"]["evaluator"]["func"] == ["exact_match", "compare_text_file"]

    # 计算器日期差：is_file_saved_desktop(contains 语义) → exists + contains "230 days"
    calc = by_src["waa:28b91a24-5d97-4c2a-891c-dccbd3820c62-WOS-2"]
    preds = calc["oracle"]["all"]
    assert [p["type"] for p in preds] == ["file_exists", "file_content_contains"]
    assert preds[1]["needle"] == "230 days"
    assert calc["seeds"] == ["default"]                      # 三变体不可 {seed} 参数化（notes 说明）
    assert "28b91a24" in calc["notes"]
    assert calc["requires"] == ["calculator"]


def test_pilot_predicate_whitelist():
    """③ 移植任务的 oracle 谓词全部 ∈ oracle_eval 支持集（十类，未扩谓词）。"""
    for t in _pilot_tasks():
        for group in ("all", "any"):
            for chk in t.oracle.get(group, []):
                assert chk["type"] in ORACLE_TYPES, \
                    f"{t.id}: 越界谓词 {chk['type']}"
                for k in ORACLE_TYPES[chk["type"]]:
                    assert k in chk, f"{t.id}: {chk['type']} 缺 {k}"


def test_negative_infeasible_expectation():
    """④ 3 条负向：expect_status=fail（loader 实况，无 infeasible 枚举）+ WAA 溯源。"""
    raw = {r["id"]: r for r in json.loads(PILOT_FILE.read_text(encoding="utf-8"))}
    neg = [t for t in _pilot_tasks() if t.expect_status == "fail"]
    assert len(neg) == 3
    for t in neg:
        assert t.id.startswith("waa_inf_") and t.source.startswith("waa:INF-")
        assert t.category == "negative"
        assert "infeasible" in t.notes, f"{t.id}: notes 缺 WAA 原 evaluator 溯源"
        assert "attribution_class" in t.notes, f"{t.id}: 缺归因标注"
        assert raw[t.id]["waa_orig"]["evaluator"]["func"] == "infeasible"
    # 归因标注两类语义存在（本批 3 条均为 capability 类，env 退化说明也须在）
    assert all("app_present_capability_infeasible" in t.notes for t in neg)
    assert all("app_absent_env_infeasible" in t.notes for t in neg)
    # vs_code ≥1（父代理指示：更可能真实在场）
    assert any("vscode" in t.requires for t in neg)


def test_no_predicates_or_loader_were_extended():
    """交付声明的机器化验证：未扩谓词、未动 loader 常量。"""
    assert len(ORACLE_TYPES) == 10
    src = (ROOT / "eval" / "__init__.py").read_text(encoding="utf-8")
    assert '"uia_window_title_contains"' in src and "clipboard_contains" in src
    # 谓词表内容钉死（若被悄悄加项，此断言炸）
    assert set(ORACLE_TYPES) == {
        "file_exists", "file_not_exists", "file_content_contains",
        "file_content_equals", "file_glob_min_count", "registry_value",
        "uia_window_title_contains", "uia_window_not_exists",
        "uia_element_exists", "clipboard_contains"}


def test_pilot_setup_paths_confined_to_eval_dir():
    """沙箱纪律：setup/cleanup 的目标路径全在 $env:EVAL_DIR 下（不污染真实桌面/user 目录）。"""
    data = json.loads(PILOT_FILE.read_text(encoding="utf-8"))
    for t in data:
        for line in t["setup_ps1"] + t["cleanup_ps1"]:
            if "Invoke-WebRequest" in line or "-Path" in line or "OutFile" in line:
                assert "$env:EVAL_DIR" in line or "HKCU" in line, \
                    f"{t['id']}: 越界副作用 {line!r}"
            for s in t["oracle"].get("all", []) + t["oracle"].get("any", []):
                p = s.get("path") or s.get("glob")
                if p:
                    assert p.startswith("{EVAL_DIR}"), f"{t['id']}: 判据越出沙箱 {p}"


def test_archive_docx_setup_local_generation_not_download():
    """审查回归钉（父代理 WP-PILOT 审查）：上游 Doc01/Doc02.docx 为 0 字节占位，
    setup 必须本地 Set-Content 生成（带 {seed} 标记）而非 Invoke-WebRequest 下载；
    oracle 四谓词与文件名不变；notes 带缺陷标注；不再声明 internet 依赖。
    （防止未来重跑生成器/改配方时回退到下载坏素材。）"""
    data = {r["id"]: r for r in json.loads(PILOT_FILE.read_text(encoding="utf-8"))}
    t = data["waa_fe_archive_docx"]
    assert not any("Invoke-WebRequest" in l and ".docx" in l for l in t["setup_ps1"]), \
        "0 字节上游素材不应再作下载源"
    setc = [l for l in t["setup_ps1"]
            if l.startswith("Set-Content") and ".docx" in l]
    assert len(setc) == 2, "两个 docx 应本地生成"
    for l, name in zip(setc, ("Doc01", "Doc02")):
        assert name in l and "{seed}" in l and "$env:EVAL_DIR" in l
    # 文件名与 oracle 四谓词不变
    assert [p["type"] for p in t["oracle"]["all"]] == [
        "file_exists", "file_exists", "file_not_exists", "file_not_exists"]
    oracle_txt = json.dumps(t["oracle"], ensure_ascii=False)
    assert "Doc01.docx" in oracle_txt and "Doc02.docx" in oracle_txt
    # 溯源与缺陷标注
    assert "waa_upstream_asset_defect" in t["notes"]
    assert "internet" not in t["requires"]
    # 生成器层同步钉（waa2seed 源码不得残留 docx 下载配方）
    src = (ROOT / "eval" / "waa2seed.py").read_text(encoding="utf-8")
    seg = src[src.index("def recipe_archive_docx"):src.index("def recipe_inf_vscode_arabic")]
    assert "_dl(" not in seg and "_setc(" in seg


# ── gold 脚本自动校准：正向七条的离线可校准声明 + 单源一致性 + 初始态 FAIL ──

POS_IDS = {
    "waa_notepad_draft_save", "waa_notepad_count_example", "waa_calc_days_to_file",
    "waa_settings_notifications_off", "waa_settings_storagesense_weekly",
    "waa_fe_move_myfolder", "waa_fe_archive_docx",
}
GOLD_TEXT_IDS = {"waa_notepad_draft_save", "waa_notepad_count_example",
                 "waa_calc_days_to_file"}
GOLD_REG_IDS = {"waa_settings_notifications_off", "waa_settings_storagesense_weekly"}


def _raw_by_id():
    return {r["id"]: r for r in json.loads(PILOT_FILE.read_text(encoding="utf-8"))}


def test_positive_seven_have_offline_gold():
    """7 条正向各配 calib_gold；gold 无 Invoke-WebRequest/不启动 GUI（离线可校准声明）。"""
    raw = _raw_by_id()
    pos = [t for t in _pilot_tasks() if t.expect_status == "success"]
    assert len(pos) == 7 and {t.id for t in pos} == POS_IDS
    for t in pos:
        assert t.calib_gold, f"{t.id}: 正向任务缺 calib_gold"
        assert t.calibration_method == "", f"{t.id}: 未校准前 method 必须空"
        joined = "\n".join(t.calib_gold)
        assert "Invoke-WebRequest" not in joined, \
            f"{t.id}: gold 不得依赖网络（离线校准是硬要求）"
        assert "Start-Process" not in joined and ".exe" not in joined.lower(), \
            f"{t.id}: gold 不得启动 GUI"
        for l in t.calib_gold:
            if l.startswith("reg add"):
                assert l.startswith('reg add "HKCU\\'), f"{t.id}: 只许写 HKCU: {l}"
            else:
                assert "$env:EVAL_DIR/waa_pilot/" in l, \
                    f"{t.id}: gold 文件副作用必须锁在 EVAL_DIR 沙箱: {l}"
        # 幂等原语白名单：只允许建/写/删这三类命令（-Force / -ErrorAction 兜底）
        verbs = {l.split()[0] for l in t.calib_gold}
        assert verbs <= {"New-Item", "Set-Content", "Remove-Item", "reg"}, \
            f"{t.id}: gold 出现非幂等/越界原语 {verbs}"


def test_negative_three_have_no_gold():
    """3 条负向保留人工校准路径：不带 calib_gold 键，loader 默认 []。"""
    raw = _raw_by_id()
    neg = [t for t in _pilot_tasks() if t.expect_status == "fail"]
    assert len(neg) == 3
    for t in neg:
        assert "calib_gold" not in raw[t.id], f"{t.id}: 负向不该带 gold 键"
        assert t.calib_gold == [] and t.calibration_method == ""


def test_gold_oracle_single_source():
    """单源一致：oracle 的字面期望必须原样出现在 gold 里；waa2seed 源码里每个
    gold 常量只许定义一次（禁止两处手抄——漂移断言与谓词全部引用常量）。"""
    raw = _raw_by_id()
    # 文件类：oracle text/needle 字面值 = gold Set-Content 的 -Value
    for tid in GOLD_TEXT_IDS:
        t = raw[tid]
        gold = "\n".join(t["calib_gold"])
        lits = [p.get("text") or p.get("needle") for p in t["oracle"]["all"]
                if p["type"] in ("file_content_equals", "file_content_contains")]
        assert lits, tid
        for lit in lits:
            assert f'-Value "{lit}"' in gold, \
                f"{tid}: oracle 字面量 {lit!r} 未单源进 gold"
    # 注册表类：gold 写的 (键, 值) 必须逐条等于 oracle registry_value 谓词
    for tid in GOLD_REG_IDS:
        t = raw[tid]
        gold = "\n".join(t["calib_gold"])
        import re as _re
        wrote = {(m.group(1), int(m.group(2)))
                 for m in _re.finditer(r'/v (\S+) /t REG_DWORD /d (\d+) /f', gold)}
        for p in t["oracle"]["all"]:
            assert p["type"] == "registry_value"
            assert p["key"] in gold, f"{tid}: oracle 键路径未进 gold"
            assert (p["name"], p["expect"]) in wrote, \
                f"{tid}: gold 缺 {p['name']}={p['expect']}（与 oracle 不同源）"
    # 源码级：gold 字面量/键路径只许出现在常量定义处一次
    src = (ROOT / "eval" / "waa2seed.py").read_text(encoding="utf-8")
    for lit in ('"This is a draft."', '"230 days"', '"22"',
                r"Software\Microsoft\Windows\CurrentVersion\PushNotifications",
                r"Software\Microsoft\Windows\CurrentVersion\StorageSense"
                r"\Parameters\StoragePolicy"):
        assert src.count(lit) == 1, f"gold 字面量 {lit!r} 出现 {src.count(lit)} 次（>1=手抄）"


def test_setup_guarantees_initial_state_fail():
    """负向半边自动化的前提：逐条钉「setup 后 oracle 必为 FAIL」的机制——
    文件类=setup 显式删掉 oracle 终态路径；注册表类=setup 预置反向值；
    move/archive=目标位不得被 setup 建出、原位必须由 setup 造出。"""
    raw = _raw_by_id()

    def setup_joined(tid):
        return "\n".join(raw[tid]["setup_ps1"])

    # 终态文件：setup 必须 Remove-Item 掉它
    for tid, target in (("waa_notepad_draft_save", "draft.txt"),
                        ("waa_notepad_count_example", "example_count.txt"),
                        ("waa_calc_days_to_file", "numdays.txt")):
        rm = [l for l in raw[tid]["setup_ps1"]
              if l.startswith("Remove-Item") and target in l]
        assert rm, f"{tid}: setup 缺对 {target} 的复位删除（初始态可能残留 PASS）"
    # 注册表反向预置：setup 写的值 ≠ oracle expect
    for tid in GOLD_REG_IDS:
        import re as _re
        s = setup_joined(tid)
        wrote = {(m.group(1), int(m.group(2)))
                 for m in _re.finditer(r'/v (\S+) /t REG_DWORD /d (\d+) /f', s)}
        for p in raw[tid]["oracle"]["all"]:
            got = [v for (n, v) in wrote if n == p["name"]]
            assert got and all(v != p["expect"] for v in got), \
                f"{tid}: setup 未把 {p['name']} 预置成反向值 → {got}"
    # move：Desktop 源造出、Documents 目标位显式清空
    mv = raw["waa_fe_move_myfolder"]
    assert any("MyFolder" in l and "Desktop" in l and l.startswith("New-Item")
               for l in mv["setup_ps1"]), "Desktop/MyFolder 源应由 setup 造"
    assert any(l.startswith("Remove-Item") and "Documents/MyFolder" in l
               for l in mv["setup_ps1"]), "目标位 Documents/MyFolder 应显式清除"
    assert not any("Documents/MyFolder" in l and "Remove" not in l
                   for l in mv["setup_ps1"]), "setup 不得建 Documents/MyFolder"
    # archive：Archive 目录显式清除、两源文件造在原位
    ar = raw["waa_fe_archive_docx"]
    assert any(l.startswith("Remove-Item") and "Documents/Archive" in l
               for l in ar["setup_ps1"]), "Archive 不得先存在"
    assert len([l for l in ar["setup_ps1"] if l.startswith("Set-Content")
                and "Documents/Doc" in l]) == 2, "原位两 docx 应由 setup 造出"


def test_positive_gold_semantics_note_for_human_review():
    """人审聚焦条款：每条正向 notes 带 gold_semantics（gold 写了什么 × instruction 说什么）。"""
    for t in _pilot_tasks():
        if t.id in POS_IDS:
            assert "gold_semantics:" in t.notes, f"{t.id}: notes 缺人审锚点"
            assert "gold 写了" in t.notes and "人审点" in t.notes
        else:
            assert "gold_semantics" not in t.notes


def test_loader_defaults_keep_20_handcrafted_compatible():
    """30 条 load 兼容：seed.json 20 条无新字段，loader 默认值不破（calib_gold=[]/
    calibration_method=''），且渲染不丢新字段。"""
    tasks = load_tasks(TASKS_DIR)
    hand = [t for t in tasks if not t.source.startswith("waa:")]
    assert len(hand) == 20
    seed_raw = json.loads((TASKS_DIR / "seed.json").read_text(encoding="utf-8"))
    assert len(seed_raw) == 20 and all(
        "calib_gold" not in r and "calibration_method" not in r for r in seed_raw), \
        "seed.json 不重排不补键（铁律文件零触碰，靠 loader 默认值兼容）"
    assert all(t.calib_gold == [] and t.calibration_method == "" for t in hand)
    waa_pos = [t for t in tasks if t.id in POS_IDS]
    assert all(len(t.calib_gold) >= 1 for t in waa_pos)
    # render 传递新字段（gold 里 {seed} 代入）
    t = next(t for t in waa_pos if t.id == "waa_notepad_draft_save")
    r = t.render("b")
    assert r.calib_gold and any("notepad_draft_b/draft.txt" in l for l in r.calib_gold)
    assert r.calibration_method == t.calibration_method
