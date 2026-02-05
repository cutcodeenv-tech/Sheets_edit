#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Разбор ссылок с локального CSV и раскладка по четырём CSV:
- PullTube (YouTube + Instagram),
- Images,
- Footages (MotionArray),
- Other.

Скрипт реализует логику GAS-примера из ТЗ, но целиком на Python.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Sequence

from sheet_cache import csv_path_for_sheet, prompt_project_context, read_csv_rows, write_csv_rows


DEFAULT_HEADERS = ["Cell", "URL"]
DEFAULT_SOURCE_SHEET = "Лист1"
DEFAULT_YT_SHEET = "1_Youtube"
DEFAULT_IMG_SHEET = "2_Images"
DEFAULT_FTG_SHEET = "3_Footages"
DEFAULT_OTH_SHEET = "4_Other"


def input_nonempty(prompt: str, default: str | None = None) -> str:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("Значение не может быть пустым. Повторите ввод.")


def column_label(index: int) -> str:
    label = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        label = chr(65 + remainder) + label
    return label or "A"


def a1_label(row: int, col: int) -> str:
    return f"{column_label(col)}{row}"


def find_urls_in_text(text: str) -> List[str]:
    if not text:
        return []
    pattern = re.compile(r"\bhttps?://[^\s<>\"')\]]+", flags=re.I)
    urls: List[str] = []
    for match in pattern.finditer(text):
        candidate = match.group(0).rstrip("),].")
        urls.append(candidate)
    return urls


def extract_links_from_values(values: List[List[str]]) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    for r_idx, row in enumerate(values, start=1):
        for c_idx, cell in enumerate(row, start=1):
            labels = find_urls_in_text(cell)
            if not labels:
                continue
            a1 = a1_label(r_idx, c_idx)
            for idx, url in enumerate(labels, start=1):
                results.append({"a1": a1, "idx": idx, "url": url})
    return results


def detect_category(url: str) -> str:
    host_match = re.match(r"^https?://([^/]+)(/.*)?", url, flags=re.I)
    host = (host_match.group(1) if host_match else "").lower()
    path = (host_match.group(2) if host_match and host_match.group(2) else "").lower()

    is_youtube = "youtube.com" in host or host == "youtu.be"
    is_instagram = "instagram.com" in host or host == "instagr.am"
    if is_youtube or is_instagram:
        return "pulltube"

    if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|bmp|tif|tiff)(\?|#|$)", path, flags=re.I):
        return "image"

    if "motionarray.com" in host:
        return "footage"

    return "other"


def write_bucket_csv(
    project_root: Path,
    sheet_name: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
) -> None:
    out_rows: List[List[str]] = []
    if headers:
        out_rows.append(list(headers))
    out_rows.extend([list(r) for r in rows])
    safe_name = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", sheet_name).strip() or "sheet"
    csv_path = project_root / "01_data" / f"{safe_name}.csv"
    write_csv_rows(csv_path, out_rows)


def main() -> None:
    print("=== Парсер ссылок: раскладка по вкладкам ===")

    try:
        project = prompt_project_context("Проект (Enter = последняя): ")
    except Exception as exc:
        print(f"Ошибка: {exc}")
        sys.exit(1)

    source_sheet = project.meta.get("default_sheet") or DEFAULT_SOURCE_SHEET
    yt_sheet = DEFAULT_YT_SHEET
    img_sheet = DEFAULT_IMG_SHEET
    ftg_sheet = DEFAULT_FTG_SHEET
    other_sheet = DEFAULT_OTH_SHEET
    headers_raw = ",".join(DEFAULT_HEADERS)
    headers = [h.strip() for h in headers_raw.split(",") if h.strip()] or list(DEFAULT_HEADERS)

    src_csv = csv_path_for_sheet(project, source_sheet)
    values = read_csv_rows(src_csv)
    if not values:
        print(f"Локальный CSV для '{source_sheet}' пуст или не найден.")
        sys.exit(1)

    items = extract_links_from_values(values)
    if not items:
        print("Не найдено ссылок на исходном листе. Завершение.")
        return

    pull: List[List[str]] = []
    img: List[List[str]] = []
    ftg: List[List[str]] = []
    oth: List[List[str]] = []

    for item in items:
        label = f"{item['a1']}_{item['idx']}"
        url = item["url"]
        category = detect_category(url)
        if category == "pulltube":
            pull.append([label, url])
        elif category == "image":
            img.append([label, url])
        elif category == "footage":
            ftg.append([label, url])
        else:
            oth.append([label, url])

    write_bucket_csv(project.root_dir, yt_sheet, headers, pull)
    write_bucket_csv(project.root_dir, img_sheet, headers, img)
    write_bucket_csv(project.root_dir, ftg_sheet, headers, ftg)
    write_bucket_csv(project.root_dir, other_sheet, headers, oth)

    print("\n=== Готово ===")
    print(f"PullTube (YT+IG): {len(pull)} → {yt_sheet}.csv")
    print(f"Images:          {len(img)} → {img_sheet}.csv")
    print(f"Footages:        {len(ftg)} → {ftg_sheet}.csv")
    print(f"Other:           {len(oth)} → {other_sheet}.csv")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Операция отменена пользователем.")
