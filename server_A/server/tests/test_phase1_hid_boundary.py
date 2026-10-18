"""Phase 1 架构闸门：系统级输入/像素只能有一个出口。

这组断言的全部价值在于"新增一个 X 档入口绕过许可"会立刻变红。
失败时**只许改代码**，不许改测试、不许加 noqa、不许加白名单。

约定
----
- 只有 ``services/executor/hid.py`` 可以 import pyautogui / pydirectinput /
  pyperclip —— 它们直接产生系统级输入事件。
- 只有 ``services/executor/screen_capture.py`` 可以 import mss —— 整屏像素。
- 测试目录豁免（monkeypatch 需要伪造这些模块）。
"""

from __future__ import annotations

import ast
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]  # server_A/server（== 包根 server/）
PKG_ROOT = SERVER_ROOT

HID_LIBS = {"pyautogui", "pydirectinput", "pyperclip"}
HID_OWNER = Path("services/executor/hid.py")
CAPTURE_LIBS = {"mss"}
CAPTURE_OWNER = Path("services/executor/screen_capture.py")


def _iter_py_files() -> list[Path]:
    out: list[Path] = []
    for p in PKG_ROOT.rglob("*.py"):
        rel = p.relative_to(SERVER_ROOT).as_posix()
        if rel.startswith("tests/"):
            continue
        out.append(p)
    return out


def _imported_roots(path: Path) -> set[str]:
    """返回该文件 import 的顶层模块名（含函数内 import）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相对 import，与第三方无关
                continue
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def _violations(libs: set[str], owner: Path) -> list[str]:
    bad: list[str] = []
    for path in _iter_py_files():
        rel = path.relative_to(SERVER_ROOT)
        hit = _imported_roots(path) & libs
        if hit and rel.as_posix() != owner.as_posix():
            bad.append(f"{rel.as_posix()} imports {sorted(hit)}")
    return sorted(bad)


def test_only_hid_imports_input_libraries() -> None:
    bad = _violations(HID_LIBS, HID_OWNER)
    assert not bad, (
        "系统级输入只能在 hid.py 里出现。以下文件绕过了唯一出口：\n  "
        + "\n  ".join(bad)
        + "\n把动作改成 hid.<verb>(permit, ...)；若确有新入口，先想清楚它属于哪个"
        "降级边界（指针/键盘/剪贴板/前台/整屏），再在 hid 里加带 permit 的函数。"
    )


def test_only_screen_capture_imports_mss() -> None:
    bad = _violations(CAPTURE_LIBS, CAPTURE_OWNER)
    assert not bad, (
        "整屏抓取只能在 screen_capture.py 里出现（它要求 FULLSCREEN_GRAB 许可）：\n  "
        + "\n  ".join(bad)
    )


_DEVICE_TOKENS = {
    "pydirectinput",
    "pyautogui",
    "pyperclip",
    "_move_raw",
    "_click_raw",
    "_hotkey_raw",
    "SetFocus",
    # W 档：投递窗口消息同样是"向别的进程注入输入"，必须持许可
    "PostMessage",
    "PostMessageW",
    "SendMessage",
}


def _touches_device(fn: ast.FunctionDef) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id in _DEVICE_TOKENS:
            return True
        if isinstance(node, ast.Attribute) and node.attr in _DEVICE_TOKENS:
            return True
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in _DEVICE_TOKENS:
                return True
    return False


def test_hid_device_functions_take_permit_first() -> None:
    """碰设备的每个 hid 公开函数，首参必须是 permit（漏传即 TypeError）。

    判据不是"函数名像不像动词"，而是"函数体里有没有设备调用"——
    新增一个 `triple_click` 只要碰 pydirectinput，就自动被这条规则覆盖。
    """
    hid_path = SERVER_ROOT / HID_OWNER
    tree = ast.parse(hid_path.read_text(encoding="utf-8"), filename=str(hid_path))
    offenders: list[str] = []
    covered: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
            continue
        if not _touches_device(node):
            continue
        covered.append(node.name)
        args = [a.arg for a in node.args.args]
        if not args or args[0] != "permit":
            offenders.append(node.name)

    assert not offenders, (
        "这些 hid 公开函数碰设备却没有把 permit 放在首位："
        + ", ".join(offenders)
        + "。没有 permit 参数 = 无授权也能注入输入。"
    )
    # 防止"把设备调用挪进私有函数"来骗过上面那条
    assert len(covered) >= 8, f"只覆盖到 {covered}，hid 的设备出口疑似被藏起来了"


def test_no_package_level_reexport_of_hid() -> None:
    """executor/__init__.py 不许再导出 HID 动词（那是第 15 个后门）。"""
    init_path = PKG_ROOT / "services" / "executor" / "__init__.py"
    src = init_path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(init_path))
    exported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                exported.add(elt.value)
    banned = {"click_at", "type_text", "press_keys", "execute_action", "click", "paste"}
    assert not (exported & banned), (
        "executor 包级不允许再导出 HID 动词：" + ", ".join(sorted(exported & banned))
    )
