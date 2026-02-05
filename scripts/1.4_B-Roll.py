#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Генерация идей медиаперекрытий для текста из локального CSV через DeepSeek API.
Запись выполняется в CSV сразу после генерации для каждой строки (или блоками заданного размера).
"""

import os
import re
import json
import time
from pathlib import Path
from typing import List, Optional, Tuple

import requests
from dotenv import load_dotenv

from sheet_cache import csv_path_for_sheet, prompt_project_context, read_csv_rows, write_csv_rows


# ====================== УТИЛИТЫ ======================

def input_nonempty(prompt: str, default: Optional[str] = None) -> str:
    while True:
        v = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
        if v:
            return v
        if default is not None:
            return default
        print("Значение не может быть пустым. Повторите ввод.")

def col_letter_to_index(letter: str) -> int:
    letter = letter.strip().upper()
    if not re.fullmatch(r"[A-Z]+", letter):
        raise ValueError(f"Некорректная буква столбца: {letter}")
    num = 0
    for c in letter:
        num = num * 26 + (ord(c) - ord('A') + 1)
    return num

def truncate(s: str, limit: int = 1200) -> str:
    s = (s or "").strip()
    return s if len(s) <= limit else s[:limit] + "…"


# ====================== LOCAL CSV ======================

def read_column(values: List[List[str]], col_letter: str) -> List[str]:
    idx = col_letter_to_index(col_letter)
    out: List[str] = []
    for row in values:
        out.append(row[idx - 1].strip() if len(row) >= idx else "")
    return out


def _set_cell(rows: List[List[str]], row_idx: int, col_idx: int, value: str) -> None:
    while len(rows) < row_idx:
        rows.append([])
    row = rows[row_idx - 1]
    while len(row) < col_idx:
        row.append("")
    row[col_idx - 1] = value


def write_cell(rows: List[List[str]], col_letter: str, row: int, value: str) -> None:
    idx = col_letter_to_index(col_letter)
    _set_cell(rows, row, idx, value)
    print(f"[WRITE] {col_letter}{row} ← {value[:60] + ('…' if len(value) > 60 else '')}")


def write_block(rows: List[List[str]], col_letter: str, values: List[Tuple[int, str]]) -> None:
    if not values:
        return
    idx = col_letter_to_index(col_letter)
    for row_idx, value in values:
        _set_cell(rows, row_idx, idx, value)
    first = min(v[0] for v in values)
    last = max(v[0] for v in values)
    print(f"[WRITE-BLOCK] {col_letter}{first}:{col_letter}{last} ({len(values)} шт.)")


# ====================== DEEPSEEK API ======================

def get_deepseek_conf() -> Tuple[str, str]:
    load_dotenv(override=True)
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Отсутствует DEEPSEEK_API_KEY в .env")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
    return api_key, model

def build_messages_ru(text: str, ideas_count: int) -> list:
    system = (
        "Ты — креативный редактор монтажа. По данному тексту предложи идеи медиаперекрытий: "
        "B-roll, скринкасты, графика/тайтлы, анимация, архив/стоки, предметные планы, "
        "экран сайта/соцсетей, карты/гео, таймлапсы, метафоры, инфографика, UI-демо и т.п. "
        "Делай идеи разнообразными, применимыми и безопасными юридически."
    )
    user = (
        f"Текст для перекрытия: «{text}»\n"
        f"Нужно {ideas_count} разных идей. "
        f"Верни СТРОГО JSON без пояснений: "
        f'{{"ideas": ["идея 1", "идея 2", "..."]}}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

def parse_deepseek_json_or_fallback(content: str, ideas_count: int) -> List[str]:
    try:
        data = json.loads(content)
        ideas = data.get("ideas", [])
        out = []
        for idea in ideas:
            if isinstance(idea, str):
                ii = idea.strip()
                if ii:
                    out.append(ii if len(ii) <= 220 else ii[:217] + "…")
        if out:
            return out
    except Exception:
        pass
    lines = [ln.strip("-•* \t") for ln in content.splitlines()]
    out = [ln for ln in lines if len(ln) > 3][:ideas_count]
    return out

def ask_deepseek(text: str, ideas_count: int, temperature: float, api_key: str, model: str) -> List[str]:
    url = "https://api.deepseek.com/v1/chat/completions"
    messages = build_messages_ru(text, ideas_count)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"}
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    r = requests.post(url, headers=headers, json=payload, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"DeepSeek API error {r.status_code}: {r.text}")
    data = r.json()
    if not data.get("choices"):
        return []
    content = (data["choices"][0]["message"]["content"] or "").strip()
    ideas = parse_deepseek_json_or_fallback(content, ideas_count)
    return ideas


# ====================== ОСНОВНОЙ СКРИПТ ======================

def main():
    print("=== Генерация идей медиаперекрытий через DeepSeek (построчная запись) ===")

    try:
        project = prompt_project_context("Проект (Enter = последняя): ")
    except Exception as e:
        print(f"Ошибка: {e}")
        return

    ws_name = project.meta.get("default_sheet") or next(iter(project.meta.get("worksheets", {})), None)
    src_col   = input_nonempty("Из какого столбца читать текст (A/B/C/...)", "A").upper()
    dst_col   = input_nonempty("В какой столбец писать идеи (напр. D/E/...)", "D").upper()
    start_row = int(input_nonempty("С какой строки писать? (1 = с первой, 2 = пропустить заголовок)", "2"))

    ideas_count   = int(input_nonempty("Сколько идей на строку", "7"))
    temperature   = float(input_nonempty("Температура (0.0–1.2)", "0.9"))
    overwrite     = input_nonempty("Перезаписывать, если целевая ячейка не пуста? (y/n)", "y").lower() in ("y","yes","д","да")
    dash_if_empty = input_nonempty("Если идей 0 — писать дефис «—»? (y/n)", "y").lower() in ("y","yes","д","да")
    batch_size    = int(input_nonempty("Размер блока записи (1 = писать по строке)", "1"))

    # Инициализация
    if ws_name:
        csv_path = csv_path_for_sheet(project, ws_name)
    else:
        ws_name = project.meta.get("default_sheet") or next(iter(project.meta.get("worksheets", {})), "")
        if not ws_name:
            print("Не удалось определить лист по умолчанию в кэше.")
            return
        csv_path = csv_path_for_sheet(project, ws_name)
    rows = read_csv_rows(csv_path)
    if not rows:
        print(f"Локальный CSV для '{ws_name}' пуст или не найден.")
        return

    try:
        api_key, model = get_deepseek_conf()
    except Exception as e:
        print(f"Ошибка конфигурации DeepSeek: {e}")
        return

    # Колонки
    src_vals = read_column(rows, src_col)
    dst_vals = read_column(rows, dst_col)

    # Выравниваем длину до максимума
    max_rows = max(len(src_vals), len(dst_vals))
    while len(src_vals) < max_rows: src_vals.append("")
    while len(dst_vals) < max_rows: dst_vals.append("")

    # Срез для прохода
    src_slice = src_vals[start_row-1:]
    dst_slice_existing = dst_vals[start_row-1:]

    # Лог JSONL
    log_path = Path.cwd() / "ideas_log.jsonl"
    log_f = log_path.open("a", encoding="utf-8")

    print("\nНачинаю генерацию...")
    print(f"[INFO] Лист: {ws_name} | Источник: {src_col} | Назначение: {dst_col} | Пишем с строки: {start_row} | batch={batch_size}")

    updated = 0
    skipped = 0
    block_buffer: List[Tuple[int, str]] = []  # (row_index, value)

    for idx, raw_text in enumerate(src_slice, start=start_row):
        src_text = (raw_text or "").strip()
        dst_existing = (dst_slice_existing[idx - start_row] or "").strip()

        print(f"[ROW {idx}] Текст: {src_text[:60] + ('…' if len(src_text)>60 else '')} | len={len(src_text)}")

        if not src_text:
            value = "" if not dash_if_empty else "—"
        else:
            if dst_existing and not overwrite:
                value = dst_existing
                print(f"[ROW {idx}] Уже есть значение, overwrite=FALSE → пропуск генерации.")
            else:
                try:
                    ideas = ask_deepseek(truncate(src_text, 1200), ideas_count, temperature, api_key, model)
                except Exception as e:
                    print(f"[ROW {idx}] Ошибка DeepSeek: {e}")
                    ideas = []

                if ideas:
                    value = "• " + "\n• ".join(ideas)
                else:
                    value = "—" if dash_if_empty else ""

                # лог
                log_f.write(json.dumps({
                    "row": idx, "source": src_text, "ideas_count": ideas_count,
                    "model": model, "temperature": temperature, "ideas": ideas
                }, ensure_ascii=False) + "\n")

                print(f"[ROW {idx}] Идей: {len(ideas)} → записываю {'пусто' if not value else 'строки'}")

        # === запись ===
        if batch_size <= 1:
            # пишем по одной строке сразу
            write_cell(rows, dst_col, idx, value)
            write_csv_rows(csv_path, rows)
        else:
            # копим блок
            block_buffer.append((idx, value))
            if len(block_buffer) >= batch_size:
                write_block(rows, dst_col, block_buffer)
                write_csv_rows(csv_path, rows)
                block_buffer.clear()

        updated += 1
        time.sleep(0.3)  # чуть бережём лимиты

    # остаток буфера (если batch > 1)
    if block_buffer:
        write_block(rows, dst_col, block_buffer)
        write_csv_rows(csv_path, rows)
        block_buffer.clear()

    log_f.close()

    print("\n=== ГОТОВО ===")
    print(f"Всего строк просмотрено: {len(src_slice)}")
    print(f"Обновлено (итераций):    {updated}")
    print(f"Пропущено:               {skipped}")
    print(f"Столбец-источник:        {src_col}")
    print(f"Столбец-назначение:      {dst_col}")
    print(f"Лог:                     {log_path}")

if __name__ == "__main__":
    main()
