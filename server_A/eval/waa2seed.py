"""WAA(WindowsAgentArena) → HAJIMI 评测集移植器（WP-PILOT，可重跑）。

背景：把 microsoft/WindowsAgentArena 的任务 JSON 移植为 eval/tasks/*.json。
移植是「白名单 + 人工配方」而非全自动——每条 WAA evaluator 的机械翻译在
FUNC_MAP 与 RECIPES 里显式写死（含对人读过的原文断言），上游漂移会报错而不是
静默产出错误任务。红线：不为凑数发明 WAA 里不存在的任务；未映射 func 一律跳过并报告。

用法：
    python eval/waa2seed.py --offline /path/to/waa_cache            # 读本地缓存（测试/复现）
    python eval/waa2seed.py --out eval/tasks/waa_pilot.json        # 联网抓 GitHub
缓存目录兼容两种布局：
    <dir>/raw/<类别>__<id>.json    （本仓库调研缓存格式）
    <dir>/<类别>/<id>.json         （WAA 仓库 examples 原样目录）
类别白名单（正向）：notepad windows_calc settings microsoft_paint file_explorer vs_code；
负向（INF-*）额外允许 vlc（13 条 INF 只分布在 vlc/vs_code/libreoffice_writer，
libreoffice 因本机字处理器不确定而整体避开）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.github.com/repos/microsoft/WindowsAgentArena/contents/" + \
    "src/win-arena-container/client/evaluation_examples_windows/examples"
RAW = "https://raw.githubusercontent.com/microsoft/WindowsAgentArena/main/" + \
    "src/win-arena-container/client/evaluation_examples_windows/examples"
FILES_RAW = "https://raw.githubusercontent.com/rogeriobonatti/winarenafiles/main/task_files"

POS_CATEGORIES = {"notepad", "windows_calc", "settings", "microsoft_paint",
                  "file_explorer", "vs_code"}
NEG_CATEGORIES = POS_CATEGORIES | {"vlc"}  # INF-* 允许的类别

# ── 映射表（WAA evaluator (func, result.type) → 我们的谓词组合）─────────────
# 显式常量 = 「人读过 WAA 源码（evaluators/getters + metrics）后确认可机械翻译」的登记。
# 未登记的组合一律跳过并进报告。
FUNC_MAP = {
    ("exact_match", "is_file_saved_desktop"):
        "file_exists + file_content_contains(needle=textcontent)",
    ("exact_match", "vm_file_exists_in_vm_folder"):
        "file_exists",
    ("exact_match", "vm_folder_exists_in_documents"):
        "file_exists(目标位置) + file_not_exists(源位置)",
    ("exact_match", "is_all_docx_in_archive"):
        "file_exists×N(归档内) + file_not_exists×N(原位) + file_glob_min_count",
    ("exact_match", "system_notifications"):
        "registry_value(HKCU\\...\\PushNotifications\\ToastEnabled=0)",
    ("exact_match", "storage_sense_run_frequency"):
        "registry_value(StoragePolicy\\01=1) + registry_value(2048=7)",
    ("exact_match", "vm_active_window_title"):
        "uia_window_title_contains",
    # 文本比对类：cloud gold 内容已在移植时实测并内联为常量（漂移断言见各 recipe）
    ("compare_text_file", "vm_file"):
        "file_content_equals(cloud gold 移植时实测内联)",
    ("multi", "exact_match+compare_text_file#vm_file_exists_in_vm_folder+vm_file"):
        "file_exists + file_content_equals(cloud gold 移植时实测内联)",
    ("infeasible", None):
        'expect_status="fail" + 现场保护谓词（WAA 判分=agent 声明不可行）',
}

# raw_inf/<INF-id>.json 这类不带目录名的缓存布局：用 related_apps 反推类别
_RELATED_TO_CAT = {"vlc": "vlc", "vscode": "vs_code", "vs_code": "vs_code",
                   "libreoffice_writer": "libreoffice_writer"}


def _func_key(ev: dict):
    """取 (func, result.type) 映射键。多 func 列表返回 ('multi', 指纹)。"""
    fn = ev.get("func")
    res = ev.get("result")
    if isinstance(fn, list):
        return ("multi", "+".join(fn) + "#" + "+".join(
            r.get("type", "?") if isinstance(r, dict) else "?" for r in
            (res if isinstance(res, list) else [res])))
    rt = res.get("type") if isinstance(res, dict) else None
    return (fn, rt)


class WaaDriftError(Exception):
    """上游 WAA JSON 与移植时快照不一致。"""


def _must(cond: bool, msg: str):
    if not cond:
        raise WaaDriftError(msg)


# ── 任务配方（每条含对 WAA 原文的断言；翻译决策写进注释与 notes）────────────

def _sandbox(pid: str) -> str:
    """评测沙箱根：产物一律落 EVAL_DIR 下，不碰真实桌面/用户目录（WAA VM 语义的裸机替代）。
    oracle/instruction 用 {EVAL_DIR} 宏（runner 展开）；PS 行用 $env:EVAL_DIR（README 约定）。"""
    return "{EVAL_DIR}/waa_pilot/" + pid


def _ps(sb: str) -> str:
    return sb.replace("{EVAL_DIR}", "$env:EVAL_DIR")


def _dl(url: str, dst: str) -> str:
    return ('Invoke-WebRequest -UseBasicParsing -Uri "%s" -OutFile "%s"' % (url, dst))


def _setc(dst: str, value: str) -> str:
    """本地确定性生成文件（用于上游素材为 0 字节占位、或需 seed 标记的场景）。"""
    return ('Set-Content -Path "%s" -Value "%s" -Force' % (dst, value))


def _mkdir(p: str) -> str:
    return 'New-Item -ItemType Directory -Force -Path "%s" | Out-Null' % p


def _rm(p: str) -> str:
    return 'Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "%s"' % p


def _kill(proc: str) -> str:
    return "Get-Process %s -ErrorAction SilentlyContinue | Stop-Process -Force" % proc


def _orig_snapshot(orig: dict) -> dict:
    return {k: orig.get(k) for k in
            ("id", "instruction", "config", "evaluator", "postconfig",
             "related_apps", "snapshot", "source")}


def _base(orig, tid, name, category, instruction, seeds, oracle, *,
          setup=None, cleanup=None, p0, requires, wall=300, notes,
          expect_status="success"):
    return {
        "id": tid, "name": name, "category": category,
        "instruction": instruction, "seeds": seeds, "p0_coverage": p0,
        "setup_ps1": setup or [], "cleanup_ps1": cleanup or [],
        "oracle": oracle, "max_wall_s": wall, "requires": requires,
        "expect_status": expect_status, "calibrated": False,
        "source": "waa:" + orig["id"], "notes": notes,
        "waa_orig": _orig_snapshot(orig),
    }


def recipe_draft_save(orig):  # notepad 366de66e
    ev = orig["evaluator"]
    _must(orig["id"] == "366de66e-cbae-4d72-b042-26390db2b145-WOS", "id 漂移")
    _must(ev.get("func") == ["exact_match", "compare_text_file"], "evaluator func 漂移")
    _must(ev["result"][0]["type"] == "vm_file_exists_in_vm_folder"
          and ev["result"][1]["type"] == "vm_file", "evaluator result 漂移")
    _must("366de66e" in ev["expected"][1]["path"], "gold 文件 URL 漂移")
    sb = _sandbox("notepad_draft")
    gold = "This is a draft."  # cloud gold 实测（winarenafiles eval/draft.txt，16B 无换行）
    return _base(
        orig, "waa_notepad_draft_save", "WAA移植-记事本新建草稿保存", "editor",
        "打开记事本，输入文字 " + gold + "（一字不差），另存为 " + sb +
        "_{seed}/draft.txt", ["a", "b", "c"],
        {"all": [
            {"type": "file_exists", "path": sb + "_{seed}/draft.txt"},
            {"type": "file_content_equals", "path": sb + "_{seed}/draft.txt",
             "text": gold},
        ]},
        setup=[_mkdir(_ps(sb) + "_{seed}"), _rm(_ps(sb) + "_{seed}/draft.txt"),
               _kill("notepad")],
        cleanup=[_kill("notepad"), _rm(_ps(sb) + "_{seed}")],
        p0=["0.1", "0.2", "0.3", "0.7"], requires=["notepad"],
        notes="WAA 原 evaluator: [exact_match(vm_file_exists_in_vm_folder Documents/draft.txt) + "
              "compare_text_file(gold=cloud draft.txt 相似度1.0)]。gold 内容实测 'This is a draft.'，"
              "已内联为 file_content_equals（strip 比较，容忍末换行）。产物路径改沙箱目录不碰真实"
              " Documents；{seed} 仅作隔离参数（WAA 原文文件名 draft.txt 保留）。",
    )


def recipe_count_example(orig):  # notepad a7d4b6c5
    ev = orig["evaluator"]
    _must(orig["id"] == "a7d4b6c5-569b-452e-9e1d-ffdb3d431d15-WOS", "id 漂移")
    _must(ev.get("func") == "compare_text_file", "func 漂移")
    url_cfg = orig["config"][0]["parameters"]["files"][0]["url"]
    _must("a7d4b6c5" in url_cfg and url_cfg.endswith("largefile.txt"), "config 下载 URL 漂移")
    sb = _sandbox("notepad_count")
    return _base(
        orig, "waa_notepad_count_example", "WAA移植-记事本查找计数写回", "editor",
        "打开记事本载入 " + sb + "/largefile.txt，统计单词 example 出现的次数，"
        "把次数结果（只写数字）另存为 " + sb + "/example_count.txt", ["default"],
        {"all": [
            {"type": "file_exists", "path": sb + "/example_count.txt"},
            {"type": "file_content_equals", "path": sb + "/example_count.txt",
             "text": "22"},
        ]},
        setup=[_mkdir(_ps(sb)), _rm(_ps(sb) + "/example_count.txt"),
               _dl(url_cfg, _ps(sb) + "/largefile.txt"), _kill("notepad")],
        cleanup=[_kill("notepad"), _rm(_ps(sb))],
        p0=["0.1", "0.2", "0.8"], requires=["notepad", "internet"],
        notes="WAA 原 evaluator: compare_text_file(vm example_count.txt vs cloud gold)。gold 实测"
              "内容 '22'（本机 grep -o example largefile.txt 复核=22），内联为 file_content_equals。"
              "seeds=[default]：语料与答案固定，{seed} 无参数化自由度。需查找功能计数（不逐屏数）。",
    )


def recipe_calc_days(orig):  # windows_calc 28b91a24-WOS-2
    ev = orig["evaluator"]
    _must(orig["id"] == "28b91a24-5d97-4c2a-891c-dccbd3820c62-WOS-2", "id 漂移")
    _must(_func_key(ev) == ("exact_match", "is_file_saved_desktop"), "evaluator 漂移")
    _must(ev["result"]["filename"] == "numdays.txt"
          and ev["result"]["textcontent"] == "230 days", "参数漂移")
    sb = _sandbox("calc_days")
    return _base(
        orig, "waa_calc_days_to_file", "WAA移植-计算器日期差写文件", "form",
        "打开计算器（用「日期计算」模式），算出 2024年1月3日 到 2024年8月20日 相差多少天，"
        "把结果按「X days」格式（如 230 days）保存到 " + sb + "/numdays.txt", ["default"],
        {"all": [
            {"type": "file_exists", "path": sb + "/numdays.txt"},
            {"type": "file_content_contains", "path": sb + "/numdays.txt",
             "needle": "230 days"},
        ]},
        setup=[_mkdir(_ps(sb)), _rm(_ps(sb) + "/numdays.txt"),
               _kill("CalculatorApp"), _kill("Calculator")],
        cleanup=[_kill("CalculatorApp"), _kill("Calculator"), _rm(_ps(sb))],
        p0=["0.1", "0.2", "0.3", "0.7"], requires=["calculator"],
        notes="WAA 原 evaluator: exact_match(is_file_saved_desktop numdays.txt contains '230 days')"
              "（getter 源码=文件存在且 textcontent in file，故用 file_content_contains 同语义）。"
              "seeds=[default]：同 base id 28b91a24 有 WOS/WOS-2/WOS-3 三个变体（不同日期对+不同"
              "答案串），WAA 自己拆成三个 JSON——答案随日期变，单 {seed} 宏无法联动，故只移 WOS-2"
              "一条，另两条算独立候选任务不混入。",
    )


def recipe_notifications(orig):  # settings 37e10fc4
    ev = orig["evaluator"]
    _must(orig["id"] == "37e10fc4-b4c5-4b02-a65c-bfae8bc51d3f-wos", "id 漂移")
    _must(_func_key(ev) == ("exact_match", "system_notifications"), "evaluator 漂移")
    key = r"Software\Microsoft\Windows\CurrentVersion\PushNotifications"
    return _base(
        orig, "waa_settings_notifications_off", "WAA移植-关闭系统通知", "settings",
        "打开 Windows 设置的「通知」页，把系统通知总开关关闭", ["default"],
        {"all": [{"type": "registry_value", "hive": "HKEY_CURRENT_USER",
                  "key": key, "name": "ToastEnabled", "expect": 0}]},
        setup=['reg add "HKCU\\%s" /v ToastEnabled /t REG_DWORD /d 1 /f' % key,
               _kill("SystemSettings")],
        cleanup=['reg delete "HKCU\\%s" /v ToastEnabled /f' % key],
        p0=["0.1", "0.3", "0.5"], requires=["settings"],
        notes="WAA 原 evaluator: exact_match(result=getter system_notifications, expected='True')。"
              "getter 源码（settings.py get_system_notifications）= HKCU\\...\\PushNotifications"
              "\\ToastEnabled 为 0 时返回 'True'（即已关闭）→ 直接映射 registry_value ToastEnabled"
              "=0。setup 先置 1（开启）造基线，cleanup 删除该值恢复系统默认。seeds=[default]："
              "机器级单值状态，无可参数化自由度。",
    )


def recipe_storage_sense(orig):  # settings e8f68f22
    ev = orig["evaluator"]
    _must(orig["id"] == "e8f68f22-1f6a-4cba-a97a-ac611bb4c67b-wos", "id 漂移")
    _must(_func_key(ev) == ("exact_match", "storage_sense_run_frequency"), "evaluator 漂移")
    _must(ev["expected"]["rules"]["expected"] == "7", "expected 漂移")
    key = r"Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy"
    return _base(
        orig, "waa_settings_storagesense_weekly", "WAA移植-存储感知每周运行", "settings",
        "打开设置里的「存储感知」（ms-settings:storagesense），开启存储感知，"
        "并把「检测磁盘空间的时间间隔」设置为每周", ["default"],
        {"all": [
            {"type": "registry_value", "hive": "HKEY_CURRENT_USER",
             "key": key, "name": "01", "expect": 1},
            {"type": "registry_value", "hive": "HKEY_CURRENT_USER",
             "key": key, "name": "2048", "expect": 7},
        ]},
        setup=['reg add "HKCU\\%s" /v 01 /t REG_DWORD /d 0 /f' % key,
               'reg add "HKCU\\%s" /v 2048 /t REG_DWORD /d 30 /f' % key,
               _kill("SystemSettings")],
        cleanup=['reg add "HKCU\\%s" /v 01 /t REG_DWORD /d 0 /f' % key],
        p0=["0.1", "0.2", "0.5"], requires=["settings"], wall=360,
        notes="WAA 原 evaluator: exact_match(result=getter storage_sense_run_frequency, "
              "expected='7')。getter 源码（settings.py）='01'==1（开启）且 '2048'==7 → 两个 "
              "registry_value 谓词组合。setup 造「关闭+每月」基线，cleanup 复位为关。seeds="
              "[default]：机器级单状态。存储感知在精简 Win11 可能被组策略禁用——requires 声明，"
              "校准不过则记环境不适用。",
    )


def recipe_move_folder(orig):  # file_explorer 1876fe7f
    ev = orig["evaluator"]
    _must(orig["id"] == "1876fe7f-6fdc-5dd6-c9e0-237d4c8411f0-WOS", "id 漂移")
    _must(_func_key(ev) == ("exact_match", "vm_folder_exists_in_documents"), "evaluator 漂移")
    _must(ev["result"]["folder_name"] == "MyFolder", "folder_name 漂移")
    sb = _sandbox("fe_move")
    return _base(
        orig, "waa_fe_move_myfolder", "WAA移植-桌面文件夹移动到文档", "file",
        "打开资源管理器，把 " + sb + "_{seed}/Desktop 下的 MyFolder 文件夹移动到同级 "
        "Documents 文件夹里", ["a", "b", "c"],
        {"all": [
            {"type": "file_exists", "path": sb + "_{seed}/Documents/MyFolder"},
            {"type": "file_not_exists", "path": sb + "_{seed}/Desktop/MyFolder"},
        ]},
        setup=[_mkdir(_ps(sb) + "_{seed}/Desktop/MyFolder"),
               _mkdir(_ps(sb) + "_{seed}/Documents"), _kill("explorer")],
        cleanup=[_rm(_ps(sb) + "_{seed}")],
        p0=["0.1", "0.2", "0.7"], requires=["explorer"],
        notes="WAA 原 evaluator: exact_match(vm_folder_exists_in_documents MyFolder, expected "
              "true)（config 于真实 Desktop 建 MyFolder）。裸机移植：桌面/文档改为沙箱目录两个"
              "子文件夹；补 file_not_exists(原位) 收紧为「移动而非复制」——WAA 的 folder_name "
              "语义就是 move，此收紧符合原意（其指令原文即 Move）。",
    )


def recipe_archive_docx(orig):  # file_explorer 0c9dda13
    ev = orig["evaluator"]
    _must(orig["id"] == "0c9dda13-428c-492b-900b-f48562111f93-WOS", "id 漂移")
    _must(_func_key(ev) == ("exact_match", "is_all_docx_in_archive"), "evaluator 漂移")
    # 保留上游 config 下载 URL 断言作漂移哨兵（父代理审查要求：若上游改了素材结构须报警），
    # 但不再据此下载——实测上游 Doc01/Doc02.docx 均为 0 字节空占位（HTTP 200 size=0），
    # WAA 原任务移的也是空文件，oracle 只认文件名/存在性，故改本地确定性生成。
    urls = [f["url"] for f in orig["config"][0]["parameters"]["files"]]
    _must(len(urls) == 2 and all("0c9dda13" in u for u in urls), "config 漂移")
    sb = _sandbox("fe_archive")
    return _base(
        orig, "waa_fe_archive_docx", "WAA移植-建归档夹并移入全部docx", "file",
        "打开资源管理器进入 " + sb + "_{seed}/Documents（内有若干 .docx 文件），"
        "新建名为 Archive 的文件夹，并把 Documents 里所有 .docx 文件移进 Archive",
        ["a", "b", "c"],
        {"all": [
            {"type": "file_exists", "path": sb + "_{seed}/Documents/Archive/Doc01.docx"},
            {"type": "file_exists", "path": sb + "_{seed}/Documents/Archive/Doc02.docx"},
            {"type": "file_not_exists", "path": sb + "_{seed}/Documents/Doc01.docx"},
            {"type": "file_not_exists", "path": sb + "_{seed}/Documents/Doc02.docx"},
        ]},
        setup=[_mkdir(_ps(sb) + "_{seed}/Documents"),
               _setc(_ps(sb) + "_{seed}/Documents/Doc01.docx",
                     "HAJIMI_WAA_fe_archive_{seed}_DOC01"),
               _setc(_ps(sb) + "_{seed}/Documents/Doc02.docx",
                     "HAJIMI_WAA_fe_archive_{seed}_DOC02"),
               _kill("explorer")],
        cleanup=[_rm(_ps(sb) + "_{seed}")],
        p0=["0.1", "0.2", "0.3", "0.7"], requires=["explorer"], wall=360,
        notes="WAA 原 evaluator: exact_match(is_all_docx_in_archive, expected true)（getter 源码"
              "=Documents 下所有 docx 均在 Archive 内）。机械翻译=建夹+两文件移入+原位清空四个"
              "谓词。waa_upstream_asset_defect: \"0-byte at source; setup switched to local "
              "generation\"——上游 winarenafiles 的 Doc01/Doc02.docx 实测均 0 字节空占位（GitHub "
              "API size:0 + curl 200/0B 双核），WAA 原任务移的也是空文件；oracle 只认文件名/存在性，"
              "故 setup 改 Set-Content 本地生成带 {seed} 标记的占位字节，文件名不变、oracle 四谓词不动。"
              "因不再下载，requires 去掉 internet。",
    )


def recipe_inf_vscode_arabic(orig):  # vs_code INF-7c4cc09e
    _must(orig["id"] == "INF-7c4cc09e-7a92-40dd-8338-b2286535c4ed-WOS", "id 漂移")
    _must(orig["evaluator"].get("func") == "infeasible", "func 漂移")
    return _base(
        orig, "waa_inf_vscode_arabic", "WAA移植负向-VSCode改阿拉伯语", "negative",
        "打开 VS Code，把它的显示语言（display language）改成阿拉伯语（Arabic）",
        ["default"],
        {"all": [
            {"type": "uia_window_title_contains", "needle": "Visual Studio Code"},
            {"type": "uia_window_not_exists", "needle": "Marketplace"},
        ]},
        setup=[_mkdir(_ps(_sandbox("inf_vscode_arabic"))), _kill("Code")],
        cleanup=[_kill("Code"), _rm(_ps(_sandbox("inf_vscode_arabic")))],
        p0=["0.4", "0.6", "0.7"], requires=["vscode"], wall=300,
        expect_status="fail",
        notes="负向。WAA 原 evaluator 原文: {\"func\": \"infeasible\"}；source 字段为空串（vs_code "
              "5 条 INF 均无出处链接，与 vlc/lo 的 8 条不同——调研报告 §2.1「附社区帖出处」对这条"
              "不适用）。不可行语义：换显示语言需装 Language Pack for Arabic 扩展/重启，WAA 判"
              "环境内做不到。attribution_class=app_present_capability_infeasible（装了 VS Code 的"
              "机器上测「知难而退」）；若评测机没装 VS Code，退化为 app_absent_env_infeasible——"
              "仍是有效的「不假成功」测试（report_infeasible→task_failed 判 pass，乱点装扩展或"
              "假 done 判 fail），归因不同而已。oracle=现场保护：VS Code 窗口还在且没陷入"
              "Marketplace 乱逛。",
    )


def recipe_inf_vlc_autoclose(orig):  # vlc INF-5ac2891a
    _must(orig["id"] == "INF-5ac2891a-eacd-4954-b339-98abba077adb-WOS", "id 漂移")
    _must(orig["evaluator"].get("func") == "infeasible", "func 漂移")
    src = orig.get("source", "")
    _must(src.startswith("https://superuser.com/questions/1412810"), "source 出处漂移")
    return _base(
        orig, "waa_inf_vlc_autoclose", "WAA移植负向-VLC播完不自动退出", "negative",
        "打开 VLC 媒体播放器，帮我设置成：视频播放结束后不要让 VLC 自动关闭/退出",
        ["default"],
        {"all": [
            {"type": "uia_window_title_contains", "needle": "VLC"},
            {"type": "uia_window_not_exists", "needle": "Media Information"},
        ]},
        setup=[_mkdir(_ps(_sandbox("inf_vlc_autoclose"))), _kill("vlc")],
        cleanup=[_kill("vlc"), _rm(_ps(_sandbox("inf_vlc_autoclose")))],
        p0=["0.4", "0.6", "0.7"], requires=["vlc"], wall=300,
        expect_status="fail",
        notes="负向。WAA 原 evaluator 原文: {\"func\": \"infeasible\"}；「做不到」出处=WAA JSON "
              "source 字段社区帖原文: " + src + "（VLC 无「播完保持窗口不退出」的设置项）。"
              "attribution_class=app_present_capability_infeasible；评测机没装 VLC 时退化为 "
              "app_absent_env_infeasible（仍是有效「不假成功」测试，归因不同）。oracle=现场保护"
              "（打开观察后放弃，未陷入设置迷宫）。",
    )


def recipe_inf_vlc_ab_replay(orig):  # vlc INF-d1ba14d0
    _must(orig["id"] == "INF-d1ba14d0-fef8-4026-8418-5b581dc68ca0-WOS", "id 漂移")
    _must(orig["evaluator"].get("func") == "infeasible", "func 漂移")
    src = orig.get("source", "")
    _must(src.startswith("https://superuser.com/questions/306154"), "source 出处漂移")
    return _base(
        orig, "waa_inf_vlc_ab_replay", "WAA移植负向-VLC只循环前半段", "negative",
        "打开 VLC 媒体播放器，让它反复循环播放视频的前半段（从开头到视频中点，不要播后半段）",
        ["default"],
        {"all": [
            {"type": "uia_window_title_contains", "needle": "VLC"},
        ]},
        setup=[_mkdir(_ps(_sandbox("inf_vlc_ab"))), _kill("vlc")],
        cleanup=[_kill("vlc"), _rm(_ps(_sandbox("inf_vlc_ab")))],
        p0=["0.4", "0.6", "0.7"], requires=["vlc"], wall=300,
        expect_status="fail",
        notes="负向。WAA 原 evaluator 原文: {\"func\": \"infeasible\"}；「做不到」出处=WAA JSON "
              "source 字段社区帖原文: " + src + "（VLC 的 A-B 循环需手动设终点，官方判「自动取"
              "中点循环」做不到）。attribution_class=app_present_capability_infeasible；无 VLC 的"
              "机器上退化为 app_absent_env_infeasible（仍为「不假成功」测试）。注意本条 oracle 只"
              "要求 VLC 窗口在场（正确路径=打开查看播放列表/循环控件后放弃）；校准若发现 agent 不开"
              "VLC 直接口头放弃也判 pass 太松，可收紧（如 needle 具体按钮不存在）。",
    )


# WAA id → 配方（唯一定稿的 10 条；其余白名单类别任务=「未入选」，未映射 func=「跳过」）
RECIPES = {
    "366de66e-cbae-4d72-b042-26390db2b145-WOS": recipe_draft_save,
    "a7d4b6c5-569b-452e-9e1d-ffdb3d431d15-WOS": recipe_count_example,
    "28b91a24-5d97-4c2a-891c-dccbd3820c62-WOS-2": recipe_calc_days,
    "37e10fc4-b4c5-4b02-a65c-bfae8bc51d3f-wos": recipe_notifications,
    "e8f68f22-1f6a-4cba-a97a-ac611bb4c67b-wos": recipe_storage_sense,
    "1876fe7f-6fdc-5dd6-c9e0-237d4c8411f0-WOS": recipe_move_folder,
    "0c9dda13-428c-492b-900b-f48562111f93-WOS": recipe_archive_docx,
    "INF-7c4cc09e-7a92-40dd-8338-b2286535c4ed-WOS": recipe_inf_vscode_arabic,
    "INF-5ac2891a-eacd-4954-b339-98abba077adb-WOS": recipe_inf_vlc_autoclose,
    "INF-d1ba14d0-fef8-4026-8418-5b581dc68ca0-WOS": recipe_inf_vlc_ab_replay,
}


# ── 抓取（在线）/ 读取（离线）────────────────────────────────────────────

def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "hajimi-waa2seed"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch_online(max_retry: int = 3) -> dict:
    """按类别白名单抓 WAA examples，返回 {waa_id: (category, json_dict)}。"""
    out = {}
    for cat in sorted(POS_CATEGORIES | NEG_CATEGORIES):
        listing = json.loads(_get(API + "/" + cat))
        for item in listing:
            if not item["name"].endswith(".json"):
                continue
            data = None
            for att in range(max_retry):
                try:
                    data = json.loads(_get(RAW + "/" + cat + "/" + item["name"]))
                    break
                except Exception:
                    if att == max_retry - 1:
                        print("[fetch-fail] %s/%s" % (cat, item["name"]),
                              file=sys.stderr)
            if data is not None:
                out[data["id"]] = (cat, data)
    return out


def _cat_of(data, hint=None):
    """类别：目录/文件名提示优先，否则用 related_apps 反推（WAA 目录名≈related_apps[0]）。"""
    if hint and hint not in ("raw", "raw_inf"):
        return hint
    ra = (data.get("related_apps") or [""])[0]
    return _RELATED_TO_CAT.get(ra, ra or "unknown")


def read_offline(d: Path) -> dict:
    """离线目录读缓存：支持 <dir>/raw/<cat>__<id>.json、<dir>/raw[_inf]/<id>.json
    与 <dir>/<cat>/<id>.json。"""
    out = {}
    files = []
    for sub in ("raw", "raw_inf"):
        sdir = d / sub
        if sdir.is_dir():
            files += [(p.name.split("__", 1)[0] if "__" in p.name else None, p)
                      for p in sorted(sdir.glob("*.json"))]
            files += [(p.parent.name, p) for p in sorted(sdir.glob("*/*.json"))]
    files += [(p.parent.name, p) for p in sorted(d.glob("*/*.json"))
              if p.parent.name not in ("raw", "raw_inf")]
    files += [(p.name.split("__", 1)[0], p) for p in sorted(d.glob("*.json"))
              if "__" in p.name]
    for hint, p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            print("[parse-skip] %s" % p, file=sys.stderr)
            continue
        if isinstance(data, dict) and "id" in data:
            out[data["id"]] = (_cat_of(data, hint), data)
    return out


# ── 转换主流程 ────────────────────────────────────────────────────────────

def convert(all_tasks: dict):
    """返回 (移植任务列表, 摘要行, 跳过报告行)。"""
    tasks, skipped = [], []
    for wid, (cat, orig) in sorted(all_tasks.items()):
        is_inf = wid.startswith("INF-")
        if cat not in (NEG_CATEGORIES if is_inf else POS_CATEGORIES):
            skipped.append((cat, wid, "类别不在白名单"))
            continue
        fn = orig.get("evaluator", {}).get("func")
        key = _func_key(orig.get("evaluator", {}))
        if key not in FUNC_MAP and not (is_inf and fn == "infeasible"):
            skipped.append((cat, wid, "evaluator func 未映射: %r" % (key,)))
            continue
        rid = RECIPES.get(wid)
        if rid is None:
            skipped.append((cat, wid,
                            "在映射白名单内但未入选本批（无移植配方）"))
            continue
        try:
            tasks.append(rid(orig))
        except WaaDriftError as e:
            skipped.append((cat, wid, "上游漂移，拒绝移植: %s" % e))
        except (KeyError, IndexError, TypeError) as e:
            skipped.append((cat, wid, "结构断言失败: %s" % e))
    return tasks, skipped


def summary_rows(tasks):
    rows = []
    for t in sorted(tasks, key=lambda x: (x["expect_status"], x["id"])):
        preds = "+".join(sorted({c["type"] for g in ("all", "any")
                                 for c in t["oracle"].get(g, [])})) or "-"
        rows.append((t["source"], t["id"], t["instruction"][:36] + "…", preds,
                     ",".join(t["seeds"]), t["expect_status"]))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="WAA→HAJIMI 评测任务移植器")
    ap.add_argument("--offline", default="", help="本地缓存目录（测试/复现用）")
    ap.add_argument("--out", default=str(HERE / "tasks" / "waa_pilot.json"))
    ap.add_argument("--report-skips", action="store_true",
                    help="打印完整跳过清单（默认只打印计数与未映射 func 明细）")
    args = ap.parse_args(argv)

    all_tasks = (read_offline(Path(args.offline)) if args.offline
                 else fetch_online())
    tasks, skipped = convert(all_tasks)

    pos = [t for t in tasks if t["expect_status"] == "success"]
    neg = [t for t in tasks if t["expect_status"] == "fail"]
    out = pos + neg
    Path(args.out).write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("## WAA→HAJIMI 移植摘要（%d 条 = 正向 %d + 负向 %d）" % (len(out), len(pos), len(neg)))
    print("| WAA 源 | 我们的 id | instruction 首句 | 谓词组合 | seeds | 期望 |")
    print("|---|---|---|---|---|---|")
    for r in summary_rows(out):
        print("| %s | %s | %s | %s | %s | %s |" % r)
    cat_skip = [s for s in skipped if "类别不在白名单" in s[2]]
    unmapped = [s for s in skipped if "未映射" in s[2]]
    drift = [s for s in skipped if "漂移" in s[2] or "断言" in s[2]]
    not_sel = [s for s in skipped if "未入选" in s[2]]
    print("- 拉取 %d 条；移植 %d；跳过 %d（类别不在白名单 %d、func 未映射 %d、"
          "已映射但未入选本批 %d、上游漂移/结构异常 %d）" % (
              len(all_tasks), len(out), len(skipped), len(cat_skip), len(unmapped),
              len(not_sel), len(drift)))
    if drift:
        print("!! 漂移/异常明细（须人工复核，不可带病跑分）:")
        for c, w, why in drift:
            print("   - %s/%s: %s" % (c, w, why))
    if args.report_skips:
        from collections import Counter
        cnt = Counter((c, re.sub(r"[:（].*$", "", why)) for c, w, why in skipped)
        for (c, why), n in cnt.most_common():
            print("   skip x%d  类别=%s  %s" % (n, c, why))
    print("输出 → %s" % args.out)
    return 0 if not drift else 2


if __name__ == "__main__":
    raise SystemExit(main())
