"""Validate design_tokens.py against index.html :root (read-only)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "ui" / "web" / "index.html"
LAYOUT_TOKENS = ROOT / "ui" / "native" / "layout_tokens.py"
VISUAL_TOKENS = ROOT / "ui" / "native" / "visual_tokens.py"

VAR_MAP = {
    "--bg-primary": "BG_PRIMARY",
    "--accent": "ACCENT",
    "--danger": "DANGER",
    "--success": "SUCCESS",
    "--warning": "WARNING",
    "--text-primary": "TEXT_PRIMARY",
    "--text-secondary": "TEXT_SECONDARY",
    "--panel-width": "PANEL_WIDTH",
    "--drawer-w": "DRAWER_WIDTH",
    "--radius": "RADIUS",
}


def parse_html_root() -> dict[str, str]:
    text = HTML.read_text(encoding="utf-8")
    block = re.search(r":root\s*\{([^}]+)\}", text, re.DOTALL)
    if not block:
        raise SystemExit("Could not find :root in index.html")
    vars_: dict[str, str] = {}
    for line in block.group(1).splitlines():
        m = re.match(r"\s*(--[\w-]+)\s*:\s*([^;]+);", line)
        if m:
            vars_[m.group(1)] = m.group(2).strip()
    return vars_


def parse_tokens_py() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in (LAYOUT_TOKENS, VISUAL_TOKENS):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^([A-Z_]+)\s*=\s*([\"']?)([^\"'\n]+)\2", text, re.M):
            out[m.group(1)] = m.group(3).strip()
    return out


def main() -> int:
    html = parse_html_root()
    py = parse_tokens_py()
    errors = []
    for css_var, py_name in VAR_MAP.items():
        hv = html.get(css_var, "")
        pv = py.get(py_name, "")
        if css_var in ("--panel-width", "--drawer-w", "--radius"):
            try:
                if int(float(hv.replace("px", ""))) != int(pv):
                    errors.append(f"{py_name}: HTML {hv} != Python {pv}")
            except ValueError:
                errors.append(f"{py_name}: cannot compare {hv} vs {pv}")
        elif hv.lower() != pv.lower().replace(" ", ""):
            # loose compare for hex colors
            if hv.replace("#", "").lower() != pv.replace("#", "").lower():
                errors.append(f"{py_name}: HTML {hv} != Python {pv}")
    if errors:
        print("Token drift detected:")
        for e in errors:
            print(" ", e)
        return 1
    print("OK: layout_tokens.py + visual_tokens.py aligned with index.html :root")
    return 0


if __name__ == "__main__":
    sys.exit(main())
