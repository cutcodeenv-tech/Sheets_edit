#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Полуавтоматическое скачивание через браузер с использованием утилиты cliclick
и поиска кнопок через DOM (JavaScript) без использования компьютерного зрения.

Сценарий:
1. Читаем локальный CSV (лист по умолчанию «3_Footages»), берём значения из
   столбца A начиная со второй строки (название + ссылка).
2. Для каждой ссылки открываем новую вкладку в браузере Comet (можно выбрать Safari).
3. По таймингам выполняем клики cliclick:
   - переход в координаты Download и клик;
   - переход в координаты HD и клик;
   - вставка имени файла (через буфер обмена) и нажатие Enter.
4. Закрываем вкладку, в колонке C проставляем статус «Скачано».

Сохранение:
- Используется стандартная папка сохранения браузера.

Требования:
- macOS;
- утилита `cliclick` (brew install cliclick);
- браузер Safari (для DOM-поиска) или fallback по координатам;
- права на управление устройством и на запись экрана (Системные настройки → Конфиденциальность и безопасность);
- локальный кэш CSV (01_data).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple
from sheet_cache import csv_path_for_sheet, read_csv_rows, resolve_project, write_csv_rows
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
CLICLICK_BIN = shutil.which("cliclick")


@dataclass
class Entry:
    row_idx: int
    name: str
    url: str


def ensure_prerequisites() -> None:
    if sys.platform != "darwin":
        raise SystemExit("Скрипт работает только на macOS.")
    if CLICLICK_BIN is None:
        raise SystemExit("Не найден cliclick. Установите через `brew install cliclick`.")
    for tool in ("osascript", "pbcopy"):
        if shutil.which(tool) is None:
            raise SystemExit(f"Не найдена системная утилита '{tool}'.")


def _set_cell(rows: List[List[str]], row_idx: int, col_idx: int, value: str) -> None:
    while len(rows) < row_idx:
        rows.append([])
    row = rows[row_idx - 1]
    while len(row) < col_idx:
        row.append("")
    row[col_idx - 1] = value


def is_url(text: str) -> bool:
    return bool(URL_RE.search(text or ""))


def extract_url(text: str) -> str:
    if not text:
        return ""
    match = URL_RE.search(text)
    if not match:
        return ""
    url = match.group(0)
    return url.rstrip(").,]}")


def remove_urls(text: str) -> str:
    if not text:
        return ""
    cleaned = URL_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" \n\r\t-–—_:;|")


def sanitize_filename(value: str) -> str:
    if not value:
        return ""
    sanitized = value.strip()
    sanitized = sanitized.replace("\n", " ").replace("\r", " ")
    sanitized = re.sub(r'[\\/:"*?<>|]+', "_", sanitized)
    sanitized = re.sub(r"\s{2,}", " ", sanitized)
    return sanitized.strip(" .") or "download"


def parse_entry(row_idx: int, row: List[str]) -> Optional[Entry]:
    col_a = row[0].strip() if len(row) > 0 else ""
    col_b = row[1].strip() if len(row) > 1 else ""
    fallback = f"footage_{row_idx - 1:03d}"

    name_part = ""
    url_part = ""

    if col_b and is_url(col_b):
        url_part = extract_url(col_b)
        name_part = remove_urls(col_a)
    elif col_a and is_url(col_a) and not col_b:
        url_part = extract_url(col_a)
        name_part = ""
    else:
        url_part = extract_url(col_a) or extract_url(col_b)
        name_part = remove_urls(col_a or col_b)

    if not url_part:
        return None

    name = sanitize_filename(name_part) or fallback
    return Entry(row_idx=row_idx, name=name, url=url_part)


def read_entries(values: List[List[str]]) -> List[Entry]:
    entries: List[Entry] = []
    for idx, row in enumerate(values, start=1):
        if idx == 1:
            continue
        entry = parse_entry(idx, row)
        if entry:
            entries.append(entry)
    return entries


def parse_point(text: str, fallback: Tuple[int, int]) -> Tuple[int, int]:
    raw = text.replace(" ", "")
    parts = raw.split(",")
    if len(parts) != 2:
        return fallback
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return fallback


def ensure_wait(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def run_cliclick(args: Sequence[str]) -> None:
    if CLICLICK_BIN is None:
        raise RuntimeError("cliclick не найден.")
    cmd = [CLICLICK_BIN, *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or "Неизвестная ошибка cliclick"
        raise RuntimeError(f"cliclick завершился с ошибкой: {msg}")


def click_at(x: int, y: int) -> None:
    run_cliclick([f"m:{x},{y}", "w:80", "c:."])


def set_clipboard(text: str) -> None:
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    process.communicate(text.encode("utf-8"))
    if process.returncode not in (0, None):
        raise RuntimeError("pbcopy завершился с ошибкой.")


def run_applescript(script: str) -> bool:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.strip())
        return False
    return True


def run_applescript_with_result(script: str) -> Tuple[bool, str]:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        return False, message
    return True, result.stdout.strip()


def paste_and_confirm(delay_before_paste: float, delay_before_enter: float) -> bool:
    script = (
        'tell application "System Events"\n'
        f"    delay {max(delay_before_paste, 0):.2f}\n"
        '    keystroke "a" using {command down}\n'
        "    delay 0.05\n"
        '    keystroke "v" using {command down}\n'
        "    delay 0.1\n"
        '    keystroke "a" using {command down}\n'
        "    delay 0.05\n"
        '    keystroke "v" using {command down}\n'
        f"    delay {max(delay_before_enter, 0):.2f}\n"
        "    key code 36\n"
        "end tell"
    )
    return run_applescript(script)


def close_active_tab() -> None:
    script = (
        'tell application "System Events"\n'
        '    keystroke "w" using {command down}\n'
        "end tell"
    )
    run_applescript(script)


def escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"")


def execute_js_in_browser(browser: str, js_code: str) -> Optional[str]:
    if browser != "safari":
        return None

    escaped_js = escape_applescript_string(js_code)
    script = (
        'tell application "Safari"\n'
        "    if not (exists window 1) then return \"ERR:NO_WINDOW\"\n"
        "    tell window 1\n"
        "        if not (exists current tab) then return \"ERR:NO_TAB\"\n"
        "        try\n"
        f"            set jsResult to do JavaScript \"{escaped_js}\" in current tab\n"
        "            if jsResult is missing value then\n"
        "                return \"\"\n"
        "            else\n"
        "                return jsResult as string\n"
        "            end if\n"
        "        on error errMsg number errNum\n"
        "            return \"ERR:\" & errMsg\n"
        "        end try\n"
        "    end tell\n"
        "end tell"
    )
    success, output = run_applescript_with_result(script)
    if not success:
        return f"ERR:{output or 'osascript failed'}"
    return output


def build_dom_click_script(target_terms: List[str]) -> str:
    normalized = [term.strip().lower() for term in target_terms if term.strip()]
    targets_json = json.dumps(normalized, ensure_ascii=False)
    return (
        "(function() {\n"
        f"  const targets = {targets_json};\n"
        "  if (!Array.isArray(targets) || !targets.length) {\n"
        "    return 'NO_TERMS';\n"
        "  }\n"
        "  const candidates = Array.from(document.querySelectorAll(\n"
        "    'button, a, [role=\"button\"], [aria-label], [data-testid]'\n"
        "  ));\n"
        "  const match = candidates.find(el => {\n"
        "    if (!el || typeof el !== 'object') return false;\n"
        "    const text = (el.innerText || el.textContent || '').trim().toLowerCase();\n"
        "    if (text && targets.some(t => text.includes(t))) return true;\n"
        "    const aria = (el.getAttribute && (el.getAttribute('aria-label') || '')).trim().toLowerCase();\n"
        "    if (aria && targets.some(t => aria.includes(t))) return true;\n"
        "    const testId = (el.getAttribute && (el.getAttribute('data-testid') || '')).trim().toLowerCase();\n"
        "    if (testId && targets.some(t => testId.includes(t))) return true;\n"
        "    return false;\n"
        "  });\n"
        "  if (!match) {\n"
        "    return 'NOT_FOUND';\n"
        "  }\n"
        "  try {\n"
        "    if (match.scrollIntoView) {\n"
        "      match.scrollIntoView({behavior: 'instant', block: 'center'});\n"
        "    }\n"
        "    if (match.focus) {\n"
        "      match.focus({preventScroll: true});\n"
        "    }\n"
        "    match.click();\n"
        "    return 'OK';\n"
        "  } catch (err) {\n"
        "    return 'ERR:' + (err && err.message ? err.message : 'click failed');\n"
        "  }\n"
        "})();"
    )


def click_button_via_dom(
    browser: str,
    search_terms: List[str],
    label: str,
) -> Tuple[bool, str]:
    terms = [term.strip() for term in search_terms if term.strip()]
    if not terms:
        return False, "EMPTY_TERMS"
    js_code = build_dom_click_script(terms)
    result = execute_js_in_browser(browser, js_code)
    if result is None:
        return False, "UNSUPPORTED_BROWSER"
    result = (result or "").strip()
    if result == "OK":
        return True, "OK"
    if result == "NOT_FOUND":
        return False, "NOT_FOUND"
    if result == "NO_TERMS":
        return False, "EMPTY_TERMS"
    if result.startswith("ERR:You must enable 'Allow JavaScript from Apple Events'"):
        return False, "JSAE_DISABLED"
    return False, result or "UNKNOWN_RESULT"


def open_in_browser(url: str, browser: str) -> bool:
    escaped = escape_applescript_string(url)



    if browser == "safari":
        script = (
            'tell application "Safari"\n'
            "    activate\n"
            "    if not (exists window 1) then make new document\n"
            "    tell window 1\n"
            "        set current tab to (make new tab at end of tabs)\n"
            f"        set URL of current tab to \"{escaped}\"\n"
            "    end tell\n"
            "end tell"
        )
        return run_applescript(script)

    try:
        webbrowser.open(url, new=2)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  ↳ Не удалось открыть браузер для {url}: {exc}")
        return False


def process_entries(
    entries: Iterable[Entry],
    *,
    browser: str,
    first_click: Tuple[int, int],
    second_click: Tuple[int, int],
    delay_before_clicks: float,
    delay_between_clicks: float,
    delay_before_dialog: float,
    delay_after_enter: float,
    delay_between_paste_and_enter: float,
    fallback_on_fail: bool,
    download_terms: List[str],
    hd_terms: List[str],
    download_label: str,
    hd_label: str,
) -> List[Tuple[Entry, str]]:
    updates: List[Tuple[Entry, str]] = []

    for idx, entry in enumerate(entries, start=1):
        print(f"\n[{idx}] {entry.name} — {entry.url}")

        if not open_in_browser(entry.url, browser):
            status = "❌ Не удалось открыть ссылку"
            updates.append((entry, status))
            print(f"  ↳ {status}")
            continue

        ensure_wait(delay_before_clicks)

        try:
            dom_clicked = False
            dom_reason = ""
            try:
                dom_clicked, dom_reason = click_button_via_dom(
                    browser,
                    download_terms,
                    download_label,
                )
            except Exception as exc:  # noqa: BLE001
                dom_clicked = False
                dom_reason = f"ERR:{exc}"

            if dom_clicked:
                print(f"  ↳ Кнопка '{download_label}' нажата через DOM.")
            else:
                if dom_reason == "UNSUPPORTED_BROWSER":
                    print(f"  ↳ DOM-поиск недоступен для браузера '{browser}'.")
                elif dom_reason == "NOT_FOUND":
                    print(f"  ↳ DOM-поиск не нашёл кнопку '{download_label}'.")
                elif dom_reason == "EMPTY_TERMS":
                    print(f"  ↳ Не заданы варианты текста для кнопки '{download_label}'.")
                elif dom_reason == "JSAE_DISABLED":
                    print("  ↳ Safari заблокировал выполнение JavaScript через Apple Events. Включите "
                          "'Allow JavaScript from Apple Events' в настройках Safari → Advanced/Develop.")
                elif dom_reason and dom_reason != "UNKNOWN_RESULT":
                    print(f"  ↳ DOM-поиск кнопки '{download_label}' завершился: {dom_reason}")

            if not dom_clicked:
                if fallback_on_fail:
                    click_at(*first_click)
                    print(f"  ↳ Использую координаты для кнопки '{download_label}'.")
                else:
                    raise RuntimeError(f"Не удалось нажать кнопку {download_label} через DOM.")
        except Exception as exc:  # noqa: BLE001
            status = f"❌ Ошибка клика Download: {exc}"
            updates.append((entry, status))
            print(f"  ↳ {status}")
            continue

        ensure_wait(delay_between_clicks)

        try:
            dom_clicked = False
            dom_reason = ""
            try:
                dom_clicked, dom_reason = click_button_via_dom(
                    browser,
                    hd_terms,
                    hd_label,
                )
            except Exception as exc:  # noqa: BLE001
                dom_clicked = False
                dom_reason = f"ERR:{exc}"

            if dom_clicked:
                print(f"  ↳ Кнопка '{hd_label}' нажата через DOM.")
            else:
                if dom_reason == "UNSUPPORTED_BROWSER":
                    print(f"  ↳ DOM-поиск недоступен для браузера '{browser}'.")
                elif dom_reason == "NOT_FOUND":
                    print(f"  ↳ DOM-поиск не нашёл кнопку '{hd_label}'.")
                elif dom_reason == "EMPTY_TERMS":
                    print(f"  ↳ Не заданы варианты текста для кнопки '{hd_label}'.")
                elif dom_reason == "JSAE_DISABLED":
                    print("  ↳ Safari заблокировал выполнение JavaScript через Apple Events. Включите "
                          "'Allow JavaScript from Apple Events' в настройках Safari → Advanced/Develop.")
                elif dom_reason and dom_reason != "UNKNOWN_RESULT":
                    print(f"  ↳ DOM-поиск кнопки '{hd_label}' завершился: {dom_reason}")

            if not dom_clicked:
                if fallback_on_fail:
                    click_at(*second_click)
                    print(f"  ↳ Использую координаты для кнопки '{hd_label}'.")
                else:
                    raise RuntimeError(f"Не удалось нажать кнопку {hd_label} через DOM.")
        except Exception as exc:  # noqa: BLE001
            status = f"❌ Ошибка клика HD: {exc}"
            updates.append((entry, status))
            print(f"  ↳ {status}")
            continue

        ensure_wait(delay_before_dialog)

        try:
            set_clipboard(entry.name)
        except Exception as exc:  # noqa: BLE001
            status = f"⚠️ Не удалось скопировать имя: {exc}"
            updates.append((entry, status))
            print(f"  ↳ {status}")
            continue

        if not paste_and_confirm(delay_before_paste=0.3, delay_before_enter=delay_between_paste_and_enter):
            status = "⚠️ Ошибка при вставке имени/Enter"
            updates.append((entry, status))
            print(f"  ↳ {status}")
            continue

        ensure_wait(delay_after_enter)

        close_active_tab()
        status = "✅ Скачано"
        updates.append((entry, status))
        print("  ↳ Вкладка закрыта, отметка добавлена.")

    return updates


def update_statuses(rows: List[List[str]], updates: List[Tuple[Entry, str]]) -> None:
    for entry, status in updates:
        _set_cell(rows, entry.row_idx, 3, status)


def main() -> None:
    ensure_prerequisites()

    try:
        project = resolve_project(None, allow_remote=False)
    except Exception as exc:
        print(f"Ошибка: {exc}")
        return

    sheet_name = "3_Footages"
    browser_choice = "safari"
    first_click = (1568, 702)
    second_click = (1504, 800)

    delay_before_clicks = 2.5
    delay_between_clicks = 2.5
    delay_before_dialog = 7.0
    delay_between_paste_and_enter = 2.5
    delay_after_enter = 2.5

    download_label = "Download"
    hd_label = "Original"
    download_terms = ["Download"]
    hd_terms = ["Original"]
    fallback_on_fail = True

    csv_path = csv_path_for_sheet(project, sheet_name)
    values = read_csv_rows(csv_path)
    if not values:
        print(f"Не найден локальный CSV для листа '{sheet_name}'.")
        return
    entries = read_entries(values)

    if not entries:
        print("Не найдено строк с корректными ссылками в столбце A.")
        return

    print(f"Найдено записей: {len(entries)}. Скрипт продолжит работу автоматически.")
    print("Убедитесь, что соответствующий браузер активен и диалог сохранения появляется в том же окне.")

    updates = process_entries(
        entries,
        browser=browser_choice,
        first_click=first_click,
        second_click=second_click,
        delay_before_clicks=delay_before_clicks,
        delay_between_clicks=delay_between_clicks,
        delay_before_dialog=delay_before_dialog,
        delay_after_enter=delay_after_enter,
        delay_between_paste_and_enter=delay_between_paste_and_enter,
        fallback_on_fail=fallback_on_fail,
        download_terms=download_terms,
        hd_terms=hd_terms,
        download_label=download_label,
        hd_label=hd_label,
    )

    update_statuses(values, updates)
    write_csv_rows(csv_path, values)

    print("\nГотово.")


if __name__ == "__main__":
    main()
