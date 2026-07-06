#!/usr/bin/env python3
"""Preprocess orange cat UI icons: downscale + knock-out -> assets/.../icons/."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication

from ui.demo.maodiao.image_alpha import knock_out_background
from ui.demo.maodiao.image_pool import ICON_STEM_ALIASES, bundled_dir, bundled_icons_dir

_ICON_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

# UI icon outputs: stem -> max side (square canvas)
ICON_TARGETS: dict[str, int] = {
    "mark": 160,
    "menu": 128,
    "mic": 128,
    "send": 128,
    "badge": 96,
    "avatar": 128,
    "guide": 128,
    "steps": 128,
    "blueprint": 128,
    "notifications": 128,
    "settings": 128,
    "compact": 128,
    "logout": 128,
    "ai": 128,
}

# Also write avatar.png when source is AI.*
_AVATAR_ALIASES = ("avatar", "ai")


def _find_source(source_dir: Path, stems: tuple[str, ...]) -> Path | None:
    if not source_dir.is_dir():
        return None
    for stem in stems:
        for ext in _ICON_EXTS:
            path = source_dir / f"{stem}{ext}"
            if path.is_file():
                return path
        stem_lower = stem.lower()
        for entry in source_dir.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in _ICON_EXTS:
                continue
            if entry.stem.lower() == stem_lower:
                return entry
    return None


def _scale_to_square(image: QImage, size: int) -> QImage:
    if image.isNull() or size <= 0:
        return image
    scaled = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    canvas = QImage(size, size, QImage.Format_ARGB32)
    canvas.fill(0)
    x = (size - scaled.width()) // 2
    y = (size - scaled.height()) // 2
    from PyQt5.QtGui import QPainter

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.drawImage(x, y, scaled)
    painter.end()
    return canvas


def _process_file(src: Path, dest: Path, size: int, *, dry_run: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"  [dry-run] {src.name} -> {dest.name} ({size}px)")
        return
    image = QImage(str(src))
    if image.isNull():
        raise RuntimeError(f"failed to load {src}")
    square = _scale_to_square(image, size)
    out = knock_out_background(square)
    if not out.save(str(dest), "PNG"):
        raise RuntimeError(f"failed to save {dest}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocess orange cat UI icons.")
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Source folder (default: assets/themes/orange_cat/photos)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output icons folder (default: assets/themes/orange_cat/icons)",
    )
    parser.add_argument("--size", type=int, default=0, help="Override default size for all icons")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    app = QApplication(sys.argv)

    source = (args.source or bundled_dir()).resolve()
    out_dir = (args.out or bundled_icons_dir()).resolve()

    print(f"Source: {source}")
    print(f"Output: {out_dir}")
    if args.dry_run:
        print("(dry-run)")

    done: list[str] = []
    missing: list[str] = []

    for stem, default_size in ICON_TARGETS.items():
        size = args.size or default_size
        aliases = ICON_STEM_ALIASES.get(stem, (stem,))
        src = _find_source(source, aliases)
        if src is None and stem == "ai":
            src = _find_source(source, _AVATAR_ALIASES)
        if src is None:
            missing.append(stem)
            continue
        dest = out_dir / f"{stem}.png"
        try:
            _process_file(src, dest, size, dry_run=args.dry_run)
            done.append(f"{stem} <- {src.name} ({size}px)")
        except RuntimeError as exc:
            print(f"  ERROR {stem}: {exc}", file=sys.stderr)

    # avatar.png from AI/avatar if not already written
    if "avatar" in missing or not (out_dir / "avatar.png").exists():
        src = _find_source(source, _AVATAR_ALIASES)
        if src is not None:
            size = args.size or ICON_TARGETS["avatar"]
            dest = out_dir / "avatar.png"
            if not args.dry_run and not dest.exists():
                _process_file(src, dest, size, dry_run=False)
                done.append(f"avatar <- {src.name} ({size}px)")
            elif args.dry_run:
                _process_file(src, dest, size, dry_run=True)

    print("\nProcessed:")
    for line in done:
        print(f"  + {line}")
    if missing:
        print("\nMissing source (skipped):")
        for stem in missing:
            if stem == "ai" and any("ai" in d for d in done):
                continue
            print(f"  - {stem}")

    return 0 if not missing or done else 1


if __name__ == "__main__":
    raise SystemExit(main())
