#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Переименование скачанных файлов по локальному CSV (1_Youtube).

Ожидаемая структура 1_Youtube.csv:
- Колонка A: новое имя файла (Cell)
- Колонка B: ссылка (URL)
- Колонка C: текущее имя файла / название для сопоставления (Title)

Логика:
- Сопоставляем файл по названию из колонки C (нечёткий матч по имени файла).
- Новое имя берём из колонки A.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz, process

from sheet_cache import csv_path_for_sheet, prompt_project_context, read_csv_rows


DEFAULT_MATCH_THRESHOLD = 90


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
        print("Значение не может быть пустым. Повторите ввод.")


def parse_spreadsheet_id(value: str) -> str:
    value = value.strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", value):
        return value
    die("Не удалось извлечь Spreadsheet ID. Передайте ссылку на таблицу или сам ID.")


def slugify_filename(name: str) -> str:
    value = name.strip()
    value = value.replace(" ", "_")
    value = re.sub(r"[^A-Za-z0-9_.-]", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("._")


def ensure_target_filename(new_name: str, source_path: Path) -> str:
    candidate = new_name.strip()
    if not candidate:
        base = source_path.stem
        ext = source_path.suffix
        safe_base = slugify_filename(base) or "file"
        return safe_base + ext

    candidate_path = Path(candidate)
    ext = candidate_path.suffix or source_path.suffix
    stem = candidate_path.stem if candidate_path.suffix else candidate

    safe_stem = slugify_filename(stem) or slugify_filename(source_path.stem) or "file"
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return safe_stem + (ext or "")


class FileRegistry:
    """Удобное сопоставление имён файлов (с учётом регистра и расширений)."""

    def __init__(self, root: Path) -> None:
        self.by_name: Dict[str, List[Path]] = {}
        self.by_stem: Dict[str, List[Path]] = {}
        for path in root.rglob("*"):
            if path.is_file():
                self._register(path)

    def _register(self, path: Path) -> None:
        name_key = path.name.lower()
        stem_key = path.stem.lower()
        self.by_name.setdefault(name_key, []).append(path)
        self.by_stem.setdefault(stem_key, []).append(path)

    def _unregister(self, path: Path) -> None:
        name_key = path.name.lower()
        stem_key = path.stem.lower()
        self._remove_from_map(self.by_name, name_key, path)
        self._remove_from_map(self.by_stem, stem_key, path)

    @staticmethod
    def _remove_from_map(mapping: Dict[str, List[Path]], key: str, path: Path) -> None:
        items = mapping.get(key)
        if not items:
            return
        try:
            items.remove(path)
        except ValueError:
            return
        if not items:
            del mapping[key]

    def take(self, lookup_name: str, min_score: int) -> Optional[Path]:
        candidate = Path(lookup_name).name.strip()
        if not candidate:
            return None

        key = candidate.lower()
        if key in self.by_name and self.by_name[key]:
            path = sorted(self.by_name[key])[0]
            self._unregister(path)
            return path

        stem_key = Path(candidate).stem.lower()
        if stem_key in self.by_stem and self.by_stem[stem_key]:
            path = sorted(self.by_stem[stem_key])[0]
            self._unregister(path)
            return path

        fuzzy_path = self._take_fuzzy(candidate.lower(), min_score)
        if fuzzy_path:
            return fuzzy_path

        return None

    def add(self, path: Path) -> None:
        self._register(path)

    def _take_fuzzy(self, candidate: str, min_score: int) -> Optional[Path]:
        if not self.by_name:
            return None

        names = list(self.by_name.keys())
        match = process.extractOne(candidate, names, scorer=fuzz.token_set_ratio)
        if match and match[1] >= min_score and self.by_name.get(match[0]):
            path = sorted(self.by_name[match[0]])[0]
            self._unregister(path)
            return path

        stems = list(self.by_stem.keys())
        stem_match = process.extractOne(Path(candidate).stem, stems, scorer=fuzz.token_set_ratio)
        if stem_match and stem_match[1] >= min_score and self.by_stem.get(stem_match[0]):
            path = sorted(self.by_stem[stem_match[0]])[0]
            self._unregister(path)
            return path

        return None

def get_rows(values: List[List[str]]) -> List[Tuple[int, str, str]]:
    rows: List[Tuple[int, str, str]] = []
    for idx, row in enumerate(values, start=1):
        if idx == 1 and row and row[0].strip().lower() == "cell":
            continue
        new_name = row[0].strip() if len(row) > 0 else ""
        match_title = row[2].strip() if len(row) > 2 else ""
        if not match_title:
            continue
        rows.append((idx, new_name, match_title))
    return rows


def main() -> None:
    print("=== Переименование по 1_Youtube.csv ===")

    try:
        project = prompt_project_context("Проект (Enter = последняя): ")
    except Exception as exc:
        die(f"Ошибка: {exc}")

    folder = Path(input_nonempty("Путь к папке с видео", str(project.video_dir))).expanduser().resolve()
    if not folder.is_dir():
        die(f"Папка не найдена: {folder}")

    worksheet_name = "1_Youtube"
    csv_path = csv_path_for_sheet(project, worksheet_name)
    values = read_csv_rows(csv_path)
    if not values:
        die(f"Локальный CSV для '{worksheet_name}' пуст или не найден.")
    rows = get_rows(values)

    if not rows:
        print("В 1_Youtube.csv нет строк с URL.")
        return

    registry = FileRegistry(folder)
    if not registry.by_name:
        print("Папка пуста — нечего переименовывать.")
        return

    threshold_default = DEFAULT_MATCH_THRESHOLD
    threshold_input = input(
        f"Порог совпадения имени (0-100) [{threshold_default}]: "
    ).strip()
    if threshold_input.isdigit():
        match_threshold = max(0, min(100, int(threshold_input)))
    else:
        match_threshold = threshold_default

    renamed = 0
    skipped_same = 0
    not_found = 0
    conflicts = 0
    errors: List[str] = []

    for row_idx, new_name, match_title in rows:
        source = registry.take(match_title, match_threshold)
        if source is None:
            label = match_title or "<unknown>"
            print(f"[MISS] {label} (row {row_idx}) не найден")
            errors.append(f"{row_idx}: не найден файл '{label}'")
            not_found += 1
            continue

        base_title = new_name or source.stem
        target_name = ensure_target_filename(base_title, source)
        target_path = source.with_name(target_name)

        if target_path == source:
            print(f"[SKIP] {source.name} — имя уже соответствует")
            registry.add(source)
            skipped_same += 1
            continue

        if target_path.exists():
            print(f"[CONFLICT] {target_path.name} уже существует. Пропуск.")
            registry.add(source)
            conflicts += 1
            errors.append(f"{row_idx}: конфликт имени '{target_path.name}'")
            continue

        try:
            source.rename(target_path)
            registry.add(target_path)
            renamed += 1
            print(f"[RENAME] {source.name} → {target_path.name}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR] Не удалось переименовать '{source.name}': {exc}")
            registry.add(source)
            errors.append(f"{row_idx}: ошибка переименования '{source.name}' → '{target_name}'")

    print("\n=== Итог ===")
    print(f"Переименовано: {renamed}")
    print(f"Без изменений: {skipped_same}")
    print(f"Не найдено:   {not_found}")
    print(f"Конфликтов:   {conflicts}")

    if errors:
        log_path = folder / "Change_name_errors.txt"
        try:
            log_path.write_text("\n".join(errors), encoding="utf-8")
            print(f"Лог ошибок: {log_path}")
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Не удалось записать лог: {exc}")


if __name__ == "__main__":
    main()
