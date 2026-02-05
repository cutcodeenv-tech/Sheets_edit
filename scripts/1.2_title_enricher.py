#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Парсер заголовков (Title) для ссылок в локальном CSV (кэш таблицы).

Функционал повторяет GAS-пример:
- выбор листа источника (по имени),
- поиск столбца URL по заголовку "URL" (или колонка B по умолчанию),
- запись результата в столбец D (создаётся при необходимости),
- пакетная обработка, кеширование и логирование в CSV.
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import requests
from pathlib import Path

from sheet_cache import csv_path_for_sheet, read_csv_rows, resolve_project, write_csv_rows


DEFAULT_SETTINGS = {
    "batch_size": 150,
    "max_runtime_seconds": 5.5 * 60,
    "sleep_seconds": 0.12,
    "force_refresh": False,
    "log_to_sheet": True,
    "log_sheet_name": "Log",
    "use_cache": True,
    "cache_sheet_name": "Cache_Titles",
    "url_header": "URL",
    "write_column": "C",
    "write_header": "Title",
    "channel_header": "Channel",
}

REQUEST_TIMEOUT = 20
SESSION_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}


def column_label(index: int) -> str:
    label = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        label = chr(65 + remainder) + label
    return label or "A"


def column_index(letter: str) -> int:
    letter = letter.strip().upper()
    if not letter:
        return 4
    value = 0
    for char in letter:
        if not char.isalpha():
            raise ValueError(f"Некорректное имя столбца: {letter}")
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


@dataclass
class Settings:
    batch_size: int
    max_runtime_seconds: float
    sleep_seconds: float
    force_refresh: bool
    log_to_sheet: bool
    log_sheet_name: str
    use_cache: bool
    cache_sheet_name: str
    url_header: str
    write_column: int
    write_header: str
    channel_column: int
    channel_header: str


def read_settings_from_user() -> Settings:
    write_column = column_index(DEFAULT_SETTINGS["write_column"])
    channel_column = write_column + 1
    return Settings(
        batch_size=DEFAULT_SETTINGS["batch_size"],
        max_runtime_seconds=DEFAULT_SETTINGS["max_runtime_seconds"],
        sleep_seconds=DEFAULT_SETTINGS["sleep_seconds"],
        force_refresh=DEFAULT_SETTINGS["force_refresh"],
        log_to_sheet=DEFAULT_SETTINGS["log_to_sheet"],
        log_sheet_name=DEFAULT_SETTINGS["log_sheet_name"],
        use_cache=DEFAULT_SETTINGS["use_cache"],
        cache_sheet_name=DEFAULT_SETTINGS["cache_sheet_name"],
        url_header=DEFAULT_SETTINGS["url_header"],
        write_column=write_column,
        write_header=DEFAULT_SETTINGS["write_header"],
        channel_column=channel_column,
        channel_header=DEFAULT_SETTINGS["channel_header"],
    )


class SheetLogger:
    def __init__(self, log_path: Path, enabled: bool) -> None:
        self.enabled = enabled
        self.log_path = log_path
        self.buffer: List[List[str]] = []
        if self.enabled and not self.log_path.exists():
            write_csv_rows(self.log_path, [["Timestamp", "Level", "Message"]])

    def log(self, message: str, level: str = "INFO") -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{level}] {message}"
        print(line)
        if not self.enabled:
            return
        self.buffer.append([timestamp, level, message])
        if len(self.buffer) >= 25:
            self.flush()

    def flush(self) -> None:
        if not self.enabled or not self.buffer:
            return
        existing = read_csv_rows(self.log_path)
        existing.extend(self.buffer)
        write_csv_rows(self.log_path, existing)
        self.buffer.clear()


def load_cache(cache_path: Path, settings: Settings) -> Dict[str, Tuple[str, str]]:
    if not settings.use_cache:
        return {}
    values = read_csv_rows(cache_path)
    cache: Dict[str, Tuple[str, str]] = {}
    for idx, row in enumerate(values, start=1):
        if idx == 1 and row and row[0].strip().lower() == "url":
            continue
        url = row[0].strip() if len(row) > 0 else ""
        title = row[1].strip() if len(row) > 1 else ""
        channel = row[2].strip() if len(row) > 2 else ""
        if url:
            cache[url] = (title, channel)
    return cache


def save_cache(cache_path: Path, settings: Settings, cache: Dict[str, Tuple[str, str]]) -> None:
    if not settings.use_cache:
        return
    rows = [["URL", "Title", "Channel"]]
    rows.extend([[url, title, channel] for url, (title, channel) in cache.items()])
    write_csv_rows(cache_path, rows)


def ensure_headers(
    rows: List[List[str]],
    url_header: str,
    write_col: int,
    write_header: str,
    channel_col: int,
    channel_header: str,
) -> Tuple[int, int, int]:
    if not rows:
        rows.append([])
    header = rows[0]
    url_col = 0
    for idx, cell in enumerate(header, start=1):
        if cell.strip().lower() == url_header.strip().lower():
            url_col = idx
            break
    if url_col == 0:
        url_col = 2
    needed = max(url_col, write_col, channel_col)
    while len(header) < needed:
        header.append("")
    if not header[write_col - 1].strip():
        header[write_col - 1] = write_header
    if not header[channel_col - 1].strip():
        header[channel_col - 1] = channel_header
    return url_col, write_col, channel_col


def fetch_json(session: requests.Session, url: str) -> Optional[dict]:
    response = session.get(url, headers=SESSION_HEADERS, timeout=REQUEST_TIMEOUT)
    if response.status_code >= 400:
        return None
    try:
        return response.json()
    except json.JSONDecodeError:
        return None


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(
        url, headers=SESSION_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True
    )
    response.raise_for_status()
    return response.text


def parse_title_from_html(html: str) -> str:
    if not html:
        return ""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    raw = re.sub(r"\s+", " ", match.group(1)).strip()
    return raw


def parse_author_from_html(html: str) -> str:
    if not html:
        return ""
    match = re.search(
        r'<meta[^>]+name=["\']author["\'][^>]+content=["\'](.*?)["\']',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    raw = re.sub(r"\s+", " ", match.group(1)).strip()
    return raw


def clean_title_by_host(title: str, host: str) -> str:
    if not title:
        return ""
    host = host.lower()
    result = title
    substitutions = [
        (lambda h: "youtube.com" in h or h == "youtu.be", r"\s*-\s*YouTube\s*$"),
        (lambda h: h.endswith("vimeo.com"), r"\s*on\s*Vimeo\s*$"),
        (lambda h: h.endswith("ok.ru"), r"\s*—\s*OK\.ru\s*$"),
        (lambda h: h.endswith("vk.com"), r"\s*\|\s*VK\s*$"),
        (lambda h: h.endswith("dzen.ru") or h.endswith("zen.yandex.ru"), r"\s*—\s*Дзен\s*$"),
        (lambda h: h.endswith("motionarray.com"), r"\s*\|\s*Motion Array\s*$"),
        (lambda h: h.endswith("rutube.ru"), r"\s*—\s*RUTUBE\s*$"),
    ]
    for predicate, pattern in substitutions:
        if predicate(host):
            result = re.sub(pattern, "", result, flags=re.IGNORECASE).strip()
    return result


def parse_host(url: str) -> Tuple[str, str]:
    try:
        match = re.match(r"^https?://([^/]+)(/.*)?", url, flags=re.IGNORECASE)
        host = match.group(1).lower().replace("www.", "") if match else ""
        path = match.group(2).lower() if match and match.group(2) else ""
        return host, path
    except Exception:
        return "", ""


def get_video_info_for_url(session: requests.Session, url: str) -> Tuple[str, str]:
    host, _ = parse_host(url)
    if not host:
        return "", ""
    try:
        if "youtube.com" in host or host == "youtu.be":
            oembed_url = "https://www.youtube.com/oembed?format=json&url=" + requests.utils.quote(
                url, safe=""
            )
            payload = fetch_json(session, oembed_url)
            if payload and payload.get("title"):
                title = str(payload["title"]).strip()
                channel = str(payload.get("author_name") or "").strip()
                return title, channel
        elif host.endswith("vimeo.com"):
            oembed_url = "https://vimeo.com/api/oembed.json?url=" + requests.utils.quote(
                url, safe=""
            )
            payload = fetch_json(session, oembed_url)
            if payload and payload.get("title"):
                title = str(payload["title"]).strip()
                channel = str(payload.get("author_name") or "").strip()
                return title, channel
        elif host.endswith("rutube.ru"):
            oembed_url = "https://rutube.ru/api/oembed/?url=" + requests.utils.quote(
                url, safe=""
            )
            payload = fetch_json(session, oembed_url)
            if payload and payload.get("title"):
                title = str(payload["title"]).strip()
                channel = str(payload.get("author_name") or "").strip()
                return title, channel

        html = fetch_html(session, url)
        title = parse_title_from_html(html)
        channel = parse_author_from_html(html)
        return clean_title_by_host(title, host), channel
    except Exception:
        return "", ""


def enrich_titles(
    rows: List[List[str]],
    settings: Settings,
    logger: SheetLogger,
    cache: Dict[str, Tuple[str, str]],
) -> Tuple[int, int, int]:
    if len(rows) < 2:
        logger.log("Пустой лист (нет данных)", "WARN")
        return 0, 0, 0

    url_col, write_col, channel_col = ensure_headers(
        rows,
        settings.url_header,
        settings.write_column,
        settings.write_header,
        settings.channel_column,
        settings.channel_header,
    )

    session = requests.Session()
    processed = 0
    missing_after = 0
    missing_channel_after = 0
    start_time = time.time()

    for idx, row in enumerate(rows[1:], start=2):
        url = row[url_col - 1].strip() if len(row) >= url_col else ""
        if not url:
            continue
        current_value = row[write_col - 1].strip() if len(row) >= write_col else ""
        current_channel = (
            row[channel_col - 1].strip() if len(row) >= channel_col else ""
        )
        if current_value and current_channel and not settings.force_refresh:
            continue
        if url in cache:
            title, channel = cache[url]
        else:
            if processed >= settings.batch_size:
                break
            title, channel = get_video_info_for_url(session, url)
            cache[url] = (title, channel)
            processed += 1
            if settings.sleep_seconds > 0:
                time.sleep(settings.sleep_seconds)
            if processed % 25 == 0:
                logger.log(f"Получено заголовков: {processed}")
            if time.time() - start_time >= settings.max_runtime_seconds:
                logger.log("Достигнут лимит времени — остановка", "WARN")
                break
        if len(row) < max(write_col, channel_col):
            row.extend([""] * (max(write_col, channel_col) - len(row)))
        if settings.force_refresh or not current_value:
            row[write_col - 1] = title
        if settings.force_refresh or not current_channel:
            row[channel_col - 1] = channel

    for row in rows[1:]:
        value = row[write_col - 1].strip() if len(row) >= write_col else ""
        if not value:
            missing_after += 1
        channel_value = row[channel_col - 1].strip() if len(row) >= channel_col else ""
        if not channel_value:
            missing_channel_after += 1

    return processed, missing_after, missing_channel_after


def main() -> None:
    print("=== Парсер Title/Channel → соседние столбцы ===")
    try:
        project = resolve_project(None, allow_remote=False)
    except Exception as exc:
        print(f"Ошибка: {exc}")
        sys.exit(1)

    sheet_name = "1_Youtube"
    csv_path = csv_path_for_sheet(project, sheet_name)
    rows = read_csv_rows(csv_path)
    if not rows:
        print(f"Локальный CSV для '{sheet_name}' пуст или не найден.")
        sys.exit(1)

    settings = read_settings_from_user()
    log_path = project.data_dir / f"{settings.log_sheet_name}.csv"
    cache_path = project.data_dir / f"{settings.cache_sheet_name}.csv"
    logger = SheetLogger(log_path, settings.log_to_sheet)
    cache = load_cache(cache_path, settings)
    logger.log(f"Старт обработки листа '{sheet_name}'. Кеш: {len(cache)} записей.")

    processed, remaining, remaining_channels = enrich_titles(rows, settings, logger, cache)
    write_csv_rows(csv_path, rows)
    save_cache(cache_path, settings, cache)
    logger.log(
        "Готово: загружено заголовков: "
        f"{processed}. Осталось пустых (в {column_label(settings.write_column)}): "
        f"{remaining}. Осталось пустых (в {column_label(settings.channel_column)}): "
        f"{remaining_channels}."
    )
    logger.flush()

    print("\n=== Итог ===")
    print(f"Обновлено записей: {processed}")
    print(f"Пустых осталось:  {remaining}")
    print(f"Пустых каналов:   {remaining_channels}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Операция отменена пользователем.")
