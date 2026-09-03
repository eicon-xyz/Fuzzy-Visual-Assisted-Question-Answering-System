# -*- coding: utf-8 -*-
"""检查 .bat 文件里「圆括号块内的 echo/REM 文本含未转义 ( )」的 CMD 语法炸弹。

背景：CMD 按字节匹配 if/for 块的圆括号，不认引号。块内 echo 文本里出现字面
`(...)` 时，第一个 `)` 会提前闭合块，剩余文本被当作命令解析，双击运行时报
「此时不应有 <某单词>」并直接崩溃（例：start_local_vision.bat 的 UNC 提示行）。

用法：
    python HAJIMI_UI\\scripts\\dev\\check_bat_parens.py [仓库根目录]
默认扫描脚本所在仓库（向上三级）。发现违规逐行输出并以退出码 1 结束。

规则为启发式：行级括号跟踪（行尾 `(` 视为开块、行首 `)` 视为收块，
`) else (` 收+开），只标记块内 echo/rem/:: 行中未被 `^` 转义的字面括号。
"""
import glob
import os
import sys


def decode(data: bytes) -> str:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return data.decode("latin-1")


def check_file(path: str):
    with open(path, "rb") as fh:
        lines = decode(fh.read()).splitlines()
    depth = 0
    problems = []
    for no, line in enumerate(lines, 1):
        stripped = line.strip()
        low = stripped.lower()
        if depth > 0 and (low.startswith("echo") or low.startswith("rem") or low.startswith("::")):
            for i, ch in enumerate(stripped):
                if ch in "()" and (i == 0 or stripped[i - 1] != "^"):
                    problems.append((no, stripped))
                    break
        closes = low.startswith(")")
        opens = line.rstrip().endswith("(")
        if closes:
            depth = max(0, depth - 1)
        if opens:
            depth += 1
    if depth != 0:
        problems.append((0, "WARN 括号块未闭合（行级启发式，depth=%d）" % depth))
    return problems


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
    total = 0
    for path in sorted(glob.glob(os.path.join(root, "**", "*.bat"), recursive=True)):
        if os.sep + ".git" + os.sep in path:
            continue
        for no, text in check_file(path):
            print("%s:%s: %s" % (path, no, text))
            total += 1
    print("--- flagged: %d (scanned from %s)" % (total, root))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
