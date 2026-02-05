#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Плейсхолдеры + корректный FCPXML (Premiere Pro):
- Таблица (локальный CSV) -> генерим JPG 1920x1080.
- JSON расшифровки (text + timestamp "MM:SS-MM:SS" или "HH:MM-HH:MM") -> тайминг.
- Нечеткий матч текста (игнор пунктуации/регистра).
- FCPXML со всеми полями, которые любит Premiere:
  <rate> у clipitem, большой <duration> источника, <in>/<out> (делают длину клипа),
  <start>/<end> (позиция на таймлайне), pproTicksIn/pproTicksOut, pathurl=file://localhost/...
"""

import os
import re
import json
import string
import textwrap
import subprocess
import sys
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from sheet_cache import csv_path_for_sheet, prompt_project_context, read_csv_rows

from PIL import Image, ImageDraw, ImageFont
from rapidfuzz import fuzz

import xml.etree.ElementTree as ET

# ====== Константы для Premiere ======
# Кол-во тиков Premiere в секунду (стабильная величина у PPro)
PPRO_TICKS_PER_SECOND = 254_016_000_000  # => 1 кадр = PPRO_TICKS_PER_SECOND / fps
# Условная «бесконечная» длина источника (у стилей в PPro часто ~1080000 кадров)
STILL_SOURCE_FRAMES = 1_080_000

# ====== Утилиты ======
def input_nonempty(prompt: str, default: Optional[str] = None) -> str:
    while True:
        v = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
        if v:
            return v
        if default is not None:
            return default
        print("Значение не может быть пустым.")

def parse_spreadsheet_id(s: str) -> str:
    s = s.strip()
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9\-_]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-zA-Z0-9\-_]{20,}", s):
        return s
    raise ValueError("Не удалось извлечь Spreadsheet ID из ссылки/ID.")

def read_sheet_rows(values: List[List[str]]) -> List[Dict[str, Any]]:
    rows = []
    for i, row in enumerate(values, start=1):
        a = row[0] if len(row) > 0 else ""
        b = row[1] if len(row) > 1 else ""
        c = row[2] if len(row) > 2 else ""
        d = row[3] if len(row) > 3 else ""
        if any([a.strip(), b.strip(), c.strip(), d.strip()]):
            rows.append(
                {
                    "row_number": i,
                    "col_a": a.strip(),
                    "col_b": b.strip(),
                    "col_c": c.strip(),
                    "col_d": d.strip(),
                }
            )
    return rows

def load_font(font_size: int):
    tried = [
        "/System/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for f in tried:
        try:
            return ImageFont.truetype(f, font_size)
        except Exception:
            pass
    return ImageFont.load_default()

def calculate_font_size(t1: str, t2: str, t3: str, t4: str) -> int:
    total_chars = len((t1 + " " + t2 + " " + t3 + " " + t4).strip())
    if total_chars <= 100:
        return 60
    elif total_chars <= 300:
        return 50
    elif total_chars <= 600:
        return 40
    elif total_chars <= 1000:
        return 35
    elif total_chars <= 1500:
        return 30
    elif total_chars <= 2500:
        return 25
    else:
        return 20

def remove_links_from_text(text: str) -> str:
    """
    Удаляет ссылки из текста, оставляя только текст
    """
    if not text:
        return text
    url_pattern = r"https?://[^\s]+"
    text_without_links = re.sub(url_pattern, "", text)
    return " ".join(text_without_links.split())


def create_text_image(
    text1: str,
    text2: str,
    text3: str,
    text4: str,
    out_path: Path,
    *,
    row_number: Optional[int] = None,
):
    # Рассчитываем оптимальный размер шрифта
    font_size = calculate_font_size(text1, text2, text3, text4)

    # Создаем изображение
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(image)

    # Пытаемся загрузить шрифт из assets/font, если не получается - используем системные
    try:
        project_font_path = "/Users/theseus/Projects/osnovateli_doc_framework/assets/font/theater.bold-condensed.ttf"
        font = ImageFont.truetype(project_font_path, font_size)
        label_font = ImageFont.truetype(project_font_path, font_size + 10)
        index_font = ImageFont.truetype(project_font_path, font_size + 20)
        print("✓ Используется шрифт проекта: theater.bold-condensed.ttf")
    except Exception:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
            label_font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size + 10)
            index_font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size + 20)
            print("✓ Используется системный шрифт: Arial")
        except Exception:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
                label_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size + 10)
                index_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size + 20)
                print("✓ Используется системный шрифт: Helvetica")
            except Exception:
                font = ImageFont.load_default()
                label_font = ImageFont.load_default()
                index_font = ImageFont.load_default()
                print("✓ Используется стандартный шрифт")

    # Настройки текста
    text_color = (0, 0, 0)
    label_color = (100, 100, 100)
    index_color = (50, 50, 50)
    line_spacing = font_size * 1.2
    margin = 100
    max_width = width - 2 * margin

    # Рисуем номер строки в правом верхнем углу
    if row_number is not None:
        index_text = f"#{row_number}"
        bbox = draw.textbbox((0, 0), index_text, font=index_font)
        index_width = bbox[2] - bbox[0]
        index_x = width - margin - index_width
        index_y = margin
        draw.text((index_x, index_y), index_text, fill=index_color, font=index_font)

    def wrap_text(text: str, max_width: int):
        if not text:
            return []
        chars_per_line = max(10, max_width // max(1, (font_size // 2)))
        return textwrap.wrap(text, width=chars_per_line, break_long_words=False, break_on_hyphens=False)

    texts_and_labels = [
        (text1, "voiceover"),
        (remove_links_from_text(text2), "storyboard"),
        (text3, "mogrt"),
        (text4, "comment"),
    ]

    current_y = margin + font_size + 30
    for text, label in texts_and_labels:
        if text and text.strip():
            draw.text((margin, current_y), label.upper(), fill=label_color, font=label_font)
            current_y += line_spacing * 1.5
            lines = wrap_text(text.strip(), max_width)
            for line in lines:
                draw.text((margin, current_y), line, fill=text_color, font=font)
                current_y += line_spacing
            current_y += line_spacing * 0.8

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(out_path), "JPEG", quality=95)


# ====== Текст → нормализованный вид и матч ======
def clean_text(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(rf"[{re.escape(string.punctuation)}]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def parse_timestamp_str(ts: str) -> Tuple[Optional[float], Optional[float]]:
    """
    'MM:SS-MM:SS' или 'HH:MM-HH:MM' -> (start_sec, end_sec)
    """
    if not ts: return (None, None)
    m = re.match(r"^\s*(\d{1,2}:\d{2})(?:\.(\d{1,3}))?\s*-\s*(\d{1,2}:\d{2})(?:\.(\d{1,3}))?\s*$", ts)
    def to_sec(mmss: str, ms: Optional[str]) -> float:
        parts = mmss.split(":")
        if len(parts) == 2:
            mm, ss = parts
            h = 0
        else:
            h, mm, ss = parts[-3], parts[-2], parts[-1]
        sec = int(h)*3600 + int(mm)*60 + int(ss)
        if ms:
            sec += float(f"0.{ms}")
        return float(sec)
    if m:
        a_ms = m.group(2)
        b_ms = m.group(4)
        a = to_sec(m.group(1), a_ms)
        b = to_sec(m.group(3), b_ms)
        return (a, b)
    # попытка другого формата 'HH:MM:SS-HH:MM:SS'
    m2 = re.match(r"^\s*(\d{1,2}:\d{2}:\d{2})(?:\.(\d{1,3}))?\s*-\s*(\d{1,2}:\d{2}:\d{2})(?:\.(\d{1,3}))?\s*$", ts)
    if m2:
        def hms(s: str) -> float:
            hh, mm, ss = s.split(":")
            return int(hh)*3600 + int(mm)*60 + int(ss)
        a = hms(m2.group(1)); b = hms(m2.group(3))
        if m2.group(2): a += float(f"0.{m2.group(2)}")
        if m2.group(4): b += float(f"0.{m2.group(4)}")
        return (float(a), float(b))
    return (None, None)

def load_transcript_json(path: Path) -> List[Dict[str, Any]]:
    """
    Ожидает список объектов { "text": str, "timestamp": "MM:SS-MM:SS" | "HH:MM-HH:MM" }.
    Если вдруг встретятся поля start/end — тоже поддержим.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for it in data:
        if not isinstance(it, dict): continue
        text = str(it.get("text", "") or "")
        start = it.get("start"); end = it.get("end"); ts = it.get("timestamp")
        if ts and (start is None or end is None):
            s, e = parse_timestamp_str(ts)
            start, end = s, e
        if start is None or end is None:
            # пропустим неполные
            continue
        out.append({"text": text, "start": float(start), "end": float(end)})
    out.sort(key=lambda x: x["start"])
    return out

def best_match(phrase: str, segments: List[Dict[str, Any]]) -> Tuple[Optional[int], int]:
    """
    Возвращает индекс лучшего сегмента и его score (0..100)
    """
    q = clean_text(phrase)
    if not q: return (None, 0)
    best_i, best_s = None, -1
    for i, seg in enumerate(segments):
        s_text = clean_text(seg["text"])
        score = fuzz.partial_ratio(q, s_text)
        if score > best_s:
            best_s = score; best_i = i
    return (best_i, int(best_s))

# ====== FCPXML ======
def file_url_localhost(p: Path) -> str:
    # Делает "file://localhost/..." — как в экспортe Premiere (работает кроссплатформенно)
    posix = p.resolve().as_posix()
    if not posix.startswith("/"):
        posix = "/" + posix
    return "file://localhost" + posix

def seconds_to_frames(sec: float, fps: float) -> int:
    return max(0, int(round(sec * fps)))

def frames_to_ppro_ticks(frames: int, fps: float) -> int:
    # 1 кадр = 254_016_000_000 / fps тиков
    tpf = int(round(PPRO_TICKS_PER_SECOND / fps))
    return frames * tpf

def build_fcpxml(project_name: str,
                 fps: float,
                 width: int,
                 height: int,
                 placements: List[Dict[str, Any]],
                 out_xml: Path):
    """
    placements: [{row_number, start(float s), end(float s), path(Path)}]
    """
    # общая длина секвенции
    total_frames = 0
    for it in placements:
        total_frames = max(total_frames, seconds_to_frames(it["end"], fps))

    # root
    xmeml = ET.Element("xmeml", version="4")

    seq = ET.SubElement(xmeml, "sequence", id="PlaceholderSequence")
    ET.SubElement(seq, "name").text = project_name
    ET.SubElement(seq, "duration").text = str(total_frames)

    rate = ET.SubElement(seq, "rate")
    ET.SubElement(rate, "timebase").text = str(int(round(fps)))
    ET.SubElement(rate, "ntsc").text = "FALSE"

    media = ET.SubElement(seq, "media")
    video = ET.SubElement(media, "video")

    fmt = ET.SubElement(video, "format")
    sc = ET.SubElement(fmt, "samplecharacteristics")
    ET.SubElement(sc, "width").text = str(width)
    ET.SubElement(sc, "height").text = str(height)
    ET.SubElement(sc, "pixelaspectratio").text = "square"
    ET.SubElement(sc, "fielddominance").text = "none"
    sc_rate = ET.SubElement(sc, "rate")
    ET.SubElement(sc_rate, "timebase").text = str(int(round(fps)))
    ET.SubElement(sc_rate, "ntsc").text = "FALSE"

    track = ET.SubElement(video, "track")

    for it in placements:
        row = it["row_number"]
        start_f = seconds_to_frames(it["start"], fps)
        end_f   = seconds_to_frames(it["end"], fps)
        dur_f   = max(1, end_f - start_f)

        clip = ET.SubElement(track, "clipitem", id=f"clipitem-{row}")
        ET.SubElement(clip, "name").text = f"{row}.jpg"

        # ВАЖНО: duration — «длина источника», ставим большую «вечную» длительность
        ET.SubElement(clip, "duration").text = str(STILL_SOURCE_FRAMES)

        # Частота клипа
        c_rate = ET.SubElement(clip, "rate")
        ET.SubElement(c_rate, "timebase").text = str(int(round(fps)))
        ET.SubElement(c_rate, "ntsc").text = "FALSE"

        # Позиция на таймлайне:
        ET.SubElement(clip, "start").text = str(start_f)
        ET.SubElement(clip, "end").text = str(end_f)

        # Используемая часть источника (с 0-го кадра на длину dur_f)
        ET.SubElement(clip, "in").text = "0"
        ET.SubElement(clip, "out").text = str(dur_f)

        # Тики Premiere для in/out (как в XML из PPro)
        ET.SubElement(clip, "pproTicksIn").text  = str(0)
        ET.SubElement(clip, "pproTicksOut").text = str(frames_to_ppro_ticks(dur_f, fps))

        ET.SubElement(clip, "alphatype").text = "none"
        ET.SubElement(clip, "pixelaspectratio").text = "square"
        ET.SubElement(clip, "anamorphic").text = "FALSE"

        # Описание файла (внутри clipitem — так PPro тоже понимает)
        file_el = ET.SubElement(clip, "file", id=f"file-{row}")
        ET.SubElement(file_el, "name").text = f"{row}.jpg"
        ET.SubElement(file_el, "pathurl").text = file_url_localhost(it["path"])

        f_rate = ET.SubElement(file_el, "rate")
        ET.SubElement(f_rate, "timebase").text = str(int(round(fps)))
        ET.SubElement(f_rate, "ntsc").text = "FALSE"

        # timecode блока файла (NDF)
        tcode = ET.SubElement(file_el, "timecode")
        tc_rate = ET.SubElement(tcode, "rate")
        ET.SubElement(tc_rate, "timebase").text = str(int(round(fps)))
        ET.SubElement(tc_rate, "ntsc").text = "FALSE"
        ET.SubElement(tcode, "string").text = "00:00:00:00"
        ET.SubElement(tcode, "frame").text = "0"
        ET.SubElement(tcode, "displayformat").text = "NDF"

        media_file = ET.SubElement(file_el, "media")
        v = ET.SubElement(media_file, "video")
        vsc = ET.SubElement(v, "samplecharacteristics")
        ET.SubElement(vsc, "width").text = str(width)
        ET.SubElement(vsc, "height").text = str(height)
        ET.SubElement(vsc, "pixelaspectratio").text = "square"
        ET.SubElement(vsc, "fielddominance").text = "none"

        src = ET.SubElement(clip, "sourcetrack")
        ET.SubElement(src, "mediatype").text = "video"
        ET.SubElement(src, "trackindex").text = "1"

    out_xml.write_bytes(ET.tostring(xmeml, encoding="utf-8", xml_declaration=True))


def reveal_output_folder(path: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass


def cleanup_previous_outputs(ph_dir: Path, extra_files: List[Path]) -> None:
    """
    Удаляем старые результаты, чтобы не смешивать с новым прогоном.
    Чистим только рабочую папку и артефакты этого скрипта.
    """
    removed = 0
    if ph_dir.exists():
        for item in ph_dir.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
                removed += 1
            except Exception:
                # если не удалось удалить — просто идём дальше, чтобы не падать
                pass
    for f in extra_files:
        try:
            if f.exists():
                f.unlink()
                removed += 1
        except Exception:
            pass
    if removed:
        print(f"[INFO] Удалено старых файлов: {removed}")

# ====== Главная ======
def main():
    print("=== Плейсхолдеры + XML под Premiere ===")
    try:
        project = prompt_project_context("Проект (Enter = последняя): ")
    except Exception as e:
        print(f"Ошибка: {e}")
        return

    ws_name = project.meta.get("default_sheet") or next(iter(project.meta.get("worksheets", {})), None)

    need_xml_raw = input_nonempty("Нужен XML под Premiere? (y/n)", "y").strip().lower()
    need_xml = need_xml_raw in {"y", "yes", "да", "д", "true", "1"}

    col_letter = "A"
    fps = 25.0
    threshold = 70
    json_path: Optional[Path] = None

    if need_xml:
        col_letter = input_nonempty("Колонка с фразами для поиска (A/B/C/...)", "A").upper()
        fps = float(input_nonempty("FPS секвенции", "25"))
        threshold = int(input_nonempty("Порог совпадения (0-100)", "70"))

        json_path = Path(input_nonempty("Путь к JSON расшифровке")).expanduser().resolve()
        if not json_path.is_file():
            print(f"Файл не найден: {json_path}")
            return

    base_dir = project.placeholder_dir
    ph_dir = base_dir
    out_xml = base_dir / "placeholders.xml"
    warn_log = base_dir / "xml_placeholders_warnings.txt"
    align_dump = base_dir / "alignments.json"

    # 1) читаем таблицу и рисуем плейсхолдеры
    if ws_name:
        csv_path = csv_path_for_sheet(project, ws_name)
    else:
        ws_name = project.meta.get("default_sheet") or next(iter(project.meta.get("worksheets", {})), "")
        if not ws_name:
            print("Не удалось определить лист по умолчанию в кэше.")
            return
        csv_path = csv_path_for_sheet(project, ws_name)
    values = read_csv_rows(csv_path)
    rows = read_sheet_rows(values)
    if not rows:
        print("В таблице нет данных."); return

    base_dir.mkdir(parents=True, exist_ok=True)
    cleanup_previous_outputs(ph_dir, [out_xml, warn_log, align_dump])
    ph_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    for r in rows:
        p = ph_dir / f"{r['row_number']}.jpg"
        create_text_image(r["col_a"], r["col_b"], r["col_c"], r["col_d"], p, row_number=r["row_number"])
        created += 1
    print(f"✓ Создано JPG: {created}  →  {ph_dir}")

    if not need_xml:
        print("XML не запрашивали — завершили на этапе плейсхолдеров.")
        print("Файлы готовы: используйте их как статику или добавьте тайминг вручную при необходимости.")
        print(f"[INFO] Открываю папку с результатами: {base_dir}")
        reveal_output_folder(base_dir)
        return

    if json_path is None:
        raise RuntimeError("Внутренняя ошибка: не указан путь к JSON при активном режиме XML.")

    # 2) расшифровка
    segments = load_transcript_json(json_path)
    if not segments:
        print("Расшифровка пуста/не распознана."); return

    # 3) матч текста
    col_map = {"A":"col_a","1":"col_a","B":"col_b","2":"col_b","C":"col_c","3":"col_c"}
    key = col_map.get(col_letter, "col_a")

    aligns: List[Dict[str, Any]] = []
    warns: List[str] = []

    for r in rows:
        phrase = r.get(key, "") or ""
        idx, score = best_match(phrase, segments)
        if idx is None:
            warns.append(f"Строка {r['row_number']}: нет совпадения. Фраза: {phrase[:100]}")
            continue
        if score < threshold:
            warns.append(f"Строка {r['row_number']}: низкий score {score}. Фраза: {phrase[:100]}")

        seg = segments[idx]
        aligns.append({
            "row_number": r["row_number"],
            "text": phrase,
            "start": seg["start"],
            "end": seg["end"],
            "score": score,
            "path": ph_dir / f"{r['row_number']}.jpg",
        })

    if not aligns:
        print("Не удалось ни одну строку соотнести с расшифровкой — XML не создан.")
        if warns: warn_log.write_text("\n".join(warns), encoding="utf-8")
        return

    # 4) сортируем и делаем XML
    aligns.sort(key=lambda x: x["start"])

    # дамп для отладки
    align_dump.write_text(json.dumps([
        {"row_number":a["row_number"],"text":a["text"],"start":a["start"],"end":a["end"],"score":a["score"],"path":str(a["path"])}
        for a in aligns
    ], ensure_ascii=False, indent=2), encoding="utf-8")

    build_fcpxml(project, fps, 1920, 1080, aligns, out_xml)

    if warns:
        warn_log.write_text("\n".join(warns), encoding="utf-8")

    print("\n=== ГОТОВО ===")
    print(f"XML: {out_xml}")
    print("Импорт: Premiere → File → Import (XML). Если клипы всё ещё в нуле — проверь FPS секвенции и путь file://localhost/…")
    print(f"[INFO] Открываю папку с результатами: {base_dir}")
    reveal_output_folder(base_dir)

if __name__ == "__main__":
    main()
