#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Create PNG overlays with transparent background from local CSV (columns A and D).

Text format is defined by TEXT_TEMPLATE.
Defaults: 621x50 px minimum, Montserrat Bold, output to project/05_channel-name.

Requires: Pillow.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from sheet_cache import csv_path_for_sheet, prompt_project_context, read_csv_rows

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # noqa: BLE001
    raise SystemExit(
        "Missing Pillow. Install it with: python -m pip install pillow"
    ) from exc


IMAGE_WIDTH = 621
IMAGE_HEIGHT = 50
PADDING_X = 8
PADDING_Y = 6
FONT_SIZE = 36
TEXT_COLOR = (255, 255, 255, 255)
SHADOW_COLOR = (0, 0, 0, 140)
SHADOW_OFFSETS = [(1, 1)]
FONT_LIST_PATH = Path(__file__).with_name("fonts_list.txt")

TEXT_TEMPLATE = (
    "\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a: "
    "Youtube-\u043a\u0430\u043d\u0430\u043b \u00ab{channel}\u00bb"
)
FOLDER_PREFIX = "\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0438"

HEADER_NAME_TOKENS = {
    "name",
    "title",
    "video",
    "\u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435",
    "\u0438\u043c\u044f",
    "\u0444\u0430\u0439\u043b",
}
HEADER_CHANNEL_TOKENS = {"channel", "source", "\u043a\u0430\u043d\u0430\u043b", "\u0438\u0441\u0442\u043e\u0447"}


def die(message: str, code: int = 1) -> None:
    print(f"[ERR] {message}", file=sys.stderr)
    sys.exit(code)


def input_nonempty(prompt: str, default: Optional[str] = None) -> str:
    while True:
        answer = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
        if answer:
            return answer
        if default is not None:
            return default
        print("\u0417\u043d\u0430\u0447\u0435\u043d\u0438\u0435 \u043d\u0435 \u043c\u043e\u0436\u0435\u0442 "
              "\u0431\u044b\u0442\u044c \u043f\u0443\u0441\u0442\u044b\u043c. \u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u0435 \u0432\u0432\u043e\u0434.")


def clean_channel_name(value: str) -> str:
    name = value.strip()
    if len(name) >= 2:
        pairs = [("\u00ab", "\u00bb"), ('"', '"'), ("\u201c", "\u201d"), ("'", "'")]
        for left, right in pairs:
            if name.startswith(left) and name.endswith(right):
                name = name[1:-1].strip()
                break
    return name


def extract_entries(values: Iterable[List[str]]) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    for idx, row in enumerate(values, start=1):
        name = row[0].strip() if len(row) > 0 else ""
        channel = row[3].strip() if len(row) > 3 else ""
        if not name or not channel:
            continue
        if idx == 1:
            name_lower = name.lower()
            channel_lower = channel.lower()
            if any(token in name_lower for token in HEADER_NAME_TOKENS) or any(
                token in channel_lower for token in HEADER_CHANNEL_TOKENS
            ):
                continue
        cleaned = clean_channel_name(channel)
        if cleaned:
            entries.append((name, cleaned))
    return entries


def default_output_dir() -> Path:
    date_stamp = datetime.now().strftime("%y%m%d")
    folder_name = f"{FOLDER_PREFIX} {date_stamp}"
    desktop = Path.home() / "Desktop"
    base = desktop if desktop.exists() else Path.home()
    return base / folder_name


def sanitize_filename(name: str, max_len: int = 120) -> str:
    value = name.strip()
    if not value:
        return ""
    value = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", value)
    if len(value) > max_len:
        value = value[:max_len]
    return value


def ensure_unique_path(folder: Path, base_name: str, suffix: str = ".png") -> Path:
    candidate = folder / f"{base_name}{suffix}"
    if not candidate.exists():
        return candidate
    for i in range(2, 1000):
        numbered = folder / f"{base_name}_{i}{suffix}"
        if not numbered.exists():
            return numbered
    die("Too many duplicate filenames.")
    return candidate


def filename_from_column_a(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    path = Path(raw)
    base = path.stem if path.suffix else raw
    return sanitize_filename(base)


def find_montserrat_bold() -> Optional[Path]:
    candidates = [
        "Montserrat-Bold.ttf",
        "Montserrat Bold.ttf",
        "Montserrat-Bold.otf",
    ]
    search_paths = [
        Path.home() / "Library" / "Fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
    ]
    for root in search_paths:
        for name in candidates:
            path = root / name
            if path.is_file():
                return path
    return None


def prompt_for_font_path() -> Path:
    while True:
        user_path = input(
            "\u041f\u0443\u0442\u044c \u043a \u0448\u0440\u0438\u0444\u0442\u0443 Montserrat Bold (.ttf/.otf): "
        ).strip()
        if not user_path:
            print("\u041f\u0443\u0442\u044c \u043d\u0435 \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u043f\u0443\u0441\u0442\u044b\u043c.")
            continue
        path = Path(user_path).expanduser().resolve()
        if not path.is_file():
            print("\u0424\u0430\u0439\u043b \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0441\u043d\u043e\u0432\u0430.")
            continue
        return path


def load_font_list(list_path: Path) -> List[Path]:
    if not list_path.exists():
        return []
    paths: List[Path] = []
    for line in list_path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        path = Path(value).expanduser().resolve()
        if path.is_file():
            paths.append(path)
        else:
            print(f"[WARN] Font file not found, skipping: {path}")
    return paths


def select_font_from_list(fonts: List[Path]) -> Optional[Path]:
    if not fonts:
        return None
    print("Выберите шрифт:")
    for idx, path in enumerate(fonts, start=1):
        print(f"{idx}. {path}")
    while True:
        choice = input("Номер шрифта: ").strip()
        if not choice:
            print("Нужно выбрать номер из списка.")
            continue
        if not choice.isdigit():
            print("Введите номер шрифта.")
            continue
        index = int(choice)
        if 1 <= index <= len(fonts):
            return fonts[index - 1]
        print("Неверный номер. Повторите ввод.")


def measure_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont
) -> Tuple[int, int, Tuple[int, int, int, int]]:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    return width, height, bbox


def render_text_image(text: str, font_path: Path) -> Image.Image:
    font = ImageFont.truetype(str(font_path), size=FONT_SIZE)
    scratch = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    scratch_draw = ImageDraw.Draw(scratch)
    text_w, text_h, bbox = measure_text(scratch_draw, text, font)

    image_width = max(IMAGE_WIDTH, text_w + 2 * PADDING_X)
    image = Image.new("RGBA", (image_width, IMAGE_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Right-align within the canvas so placement is consistent across different text lengths.
    x = image_width - PADDING_X - text_w - bbox[0]
    y = (IMAGE_HEIGHT - text_h) / 2 - bbox[1]

    for dx, dy in SHADOW_OFFSETS:
        draw.text((x + dx, y + dy), text, font=font, fill=SHADOW_COLOR)
    draw.text((x, y), text, font=font, fill=TEXT_COLOR)
    return image


def load_rows(values: List[List[str]]) -> List[List[str]]:
    return values


def main() -> None:
    print("=== Channel PNG generator ===")
    try:
        project = prompt_project_context("\u041f\u0440\u043e\u0435\u043a\u0442 (Enter = \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u044f\u044f): ")
    except Exception as exc:
        die(f"\u041e\u0448\u0438\u0431\u043a\u0430: {exc}")
    worksheet_name = "1_Youtube"
    csv_path = csv_path_for_sheet(project, worksheet_name)
    values = read_csv_rows(csv_path)
    if not values:
        die(f"\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0439 CSV \u0434\u043b\u044f '{worksheet_name}' \u043f\u0443\u0441\u0442 \u0438\u043b\u0438 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.")

    entries = extract_entries(values)
    if not entries:
        die("\u041d\u0435\u0442 \u0441\u0442\u0440\u043e\u043a \u0441 \u0434\u0430\u043d\u043d\u044b\u043c\u0438 \u0432 \u043a\u043e\u043b\u043e\u043d\u043a\u0430\u0445 A \u0438 D.")

    font_list = load_font_list(FONT_LIST_PATH)
    font_path = select_font_from_list(font_list)
    if not font_path:
        font_path = find_montserrat_bold()
        if not font_path:
            print("Montserrat Bold not found in standard font folders.")
            font_path = prompt_for_font_path()

    out_dir = project.channel_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for idx, (raw_name, channel) in enumerate(entries, start=1):
        text = TEXT_TEMPLATE.format(channel=channel)
        image = render_text_image(text, font_path)

        base_name = filename_from_column_a(raw_name)
        if not base_name:
            base_name = f"channel_{idx:03d}"
        output_path = ensure_unique_path(out_dir, base_name)
        image.save(output_path, format="PNG")
        written += 1

    print(f"Saved {written} PNG files to: {out_dir}")


if __name__ == "__main__":
    main()
