#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials


DOWNLOAD_BASE_DIR = Path("/Volumes/01_Extreme SSD/[001] Projects/00_YT_Downloader")
DATA_DIR_NAME = "01_data"
SUBDIRS = [
    "01_data",
    "02_video",
    "03_img",
    "04_placeholder",
    "05_channel-name",
    "06_stock",
]
INDEX_PATH = DOWNLOAD_BASE_DIR / ".sheet_cache.json"


@dataclass
class ProjectContext:
    spreadsheet_id: str
    title: str
    root_dir: Path
    data_dir: Path
    video_dir: Path
    img_dir: Path
    placeholder_dir: Path
    channel_dir: Path
    stock_dir: Path
    meta: Dict


def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sanitize_fs_name(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\n\r\t]", "_", value or "").strip()
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("._") or "untitled_sheet"


def _looks_like_sheet_id(value: str) -> bool:
    if not value:
        return False
    if "/spreadsheets/d/" in value:
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9\-_]{20,}", value.strip()))


def parse_spreadsheet_id(value: str) -> str:
    value = (value or "").strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", value):
        return value
    raise ValueError("Не удалось извлечь Spreadsheet ID. Передайте ссылку или сам ID.")


def load_creds_from_env(readonly: bool = True) -> Credentials:
    load_dotenv(override=True)
    info = {
        "type": os.getenv("TYPE"),
        "project_id": os.getenv("PROJECT_ID"),
        "private_key_id": os.getenv("PRIVATE_KEY_ID"),
        "private_key": (os.getenv("PRIVATE_KEY") or "").replace("\\n", "\n"),
        "client_email": os.getenv("CLIENT_EMAIL"),
        "client_id": os.getenv("CLIENT_ID"),
        "auth_uri": os.getenv("AUTH_URI"),
        "token_uri": os.getenv("TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("AUTH_PROVIDER_X509_CERT_URL"),
        "client_x509_cert_url": os.getenv("CLIENT_X509_CERT_URL"),
        "universe_domain": os.getenv("UNIVERSE_DOMAIN"),
    }
    if not (info["type"] and info["private_key"] and info["client_email"]):
        raise RuntimeError("В .env нет данных сервисного аккаунта для Google API.")
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    if not readonly:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    return Credentials.from_service_account_info(info, scopes=scopes)


def _load_index() -> Dict:
    if INDEX_PATH.is_file():
        try:
            return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"projects": {}, "last_used_id": None}
    return {"projects": {}, "last_used_id": None}


def _save_index(index: Dict) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _meta_path(root_dir: Path) -> Path:
    return root_dir / DATA_DIR_NAME / "_meta.json"


def _load_meta(root_dir: Path) -> Dict:
    meta_path = _meta_path(root_dir)
    if meta_path.is_file():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_meta(root_dir: Path, meta: Dict) -> None:
    meta_path = _meta_path(root_dir)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_project_dirs(sheet_title: str) -> ProjectContext:
    safe_title = sanitize_fs_name(sheet_title)
    root_dir = DOWNLOAD_BASE_DIR / safe_title
    for name in SUBDIRS:
        (root_dir / name).mkdir(parents=True, exist_ok=True)
    meta = _load_meta(root_dir)
    return ProjectContext(
        spreadsheet_id=meta.get("spreadsheet_id", ""),
        title=sheet_title,
        root_dir=root_dir,
        data_dir=root_dir / "01_data",
        video_dir=root_dir / "02_video",
        img_dir=root_dir / "03_img",
        placeholder_dir=root_dir / "04_placeholder",
        channel_dir=root_dir / "05_channel-name",
        stock_dir=root_dir / "06_stock",
        meta=meta,
    )


def _unique_csv_name(existing: Dict[str, str], sheet_title: str) -> str:
    base = sanitize_fs_name(sheet_title) or "sheet"
    filename = f"{base}.csv"
    if filename not in existing.values():
        return filename
    for i in range(2, 200):
        candidate = f"{base}_{i}.csv"
        if candidate not in existing.values():
            return candidate
    return f"{base}_{int(datetime.now().timestamp())}.csv"


def write_csv_rows(path: Path, rows: Sequence[Sequence[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow(list(row))


def read_csv_rows(path: Path) -> List[List[str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        return [list(row) for row in reader]


def csv_path_for_sheet(project: ProjectContext, sheet_name: str) -> Path:
    sheet_name = (sheet_name or "").strip()
    if not sheet_name:
        raise ValueError("Пустое имя листа.")
    mapping = (project.meta or {}).get("worksheets", {})
    filename = mapping.get(sheet_name)
    if filename:
        candidate = project.data_dir / filename
        if candidate.exists():
            return candidate

    fallback = project.data_dir / f"{sanitize_fs_name(sheet_name)}.csv"
    if fallback.exists():
        return fallback

    pattern = sanitize_fs_name(sheet_name) + "*.csv"
    matches = sorted(project.data_dir.glob(pattern))
    if matches:
        return matches[0]

    filename = filename or f"{sanitize_fs_name(sheet_name)}.csv"
    return project.data_dir / filename


def cache_spreadsheet(
    raw_input: str,
    *,
    source_sheet: str = "Лист1",
    router_headers: Optional[Sequence[str]] = None,
) -> ProjectContext:
    spreadsheet_id = parse_spreadsheet_id(raw_input)
    creds = load_creds_from_env(readonly=True)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(spreadsheet_id)
    sheet_title = (spreadsheet.title or "").strip() or "untitled_sheet"

    project = ensure_project_dirs(sheet_title)

    worksheets_map: Dict[str, str] = {}
    first_sheet_name = ""
    for worksheet in spreadsheet.worksheets():
        values = worksheet.get_all_values()
        filename = _unique_csv_name(worksheets_map, worksheet.title)
        write_csv_rows(project.data_dir / filename, values)
        worksheets_map[worksheet.title] = filename
        if not first_sheet_name:
            first_sheet_name = worksheet.title

    # Optional: build link-router outputs into local CSV.
    if source_sheet:
        try:
            src_ws = spreadsheet.worksheet(source_sheet)
        except Exception:
            src_ws = None
        if not src_ws and first_sheet_name:
            try:
                src_ws = spreadsheet.worksheet(first_sheet_name)
            except Exception:
                src_ws = None
        if src_ws:
            try:
                router = build_router_outputs(src_ws, headers=router_headers)
                for sheet_name, rows in router.items():
                    if sheet_name in worksheets_map:
                        filename = worksheets_map[sheet_name]
                    else:
                        filename = _unique_csv_name(worksheets_map, sheet_name)
                    write_csv_rows(project.data_dir / filename, rows)
                    worksheets_map[sheet_name] = filename
            except Exception:
                pass

    meta = {
        "spreadsheet_id": spreadsheet_id,
        "title": sheet_title,
        "saved_at": _now_stamp(),
        "default_sheet": first_sheet_name,
        "worksheets": worksheets_map,
    }
    _save_meta(project.root_dir, meta)

    index = _load_index()
    index["projects"][spreadsheet_id] = {
        "title": sheet_title,
        "path": str(project.root_dir),
        "updated_at": _now_stamp(),
    }
    index["last_used_id"] = spreadsheet_id
    _save_index(index)

    project.meta = meta
    project.spreadsheet_id = spreadsheet_id
    project.title = sheet_title
    return project


def resolve_project(raw_input: str | None, *, allow_remote: bool = False) -> ProjectContext:
    raw = (raw_input or "").strip()

    if raw:
        if _looks_like_sheet_id(raw):
            if not allow_remote:
                raise ValueError(
                    "Ссылка на Google Sheets принимается только при создании кэша. "
                    "Запустите 0_cache_sheet.py один раз и далее работайте с локальными CSV."
                )
            return cache_spreadsheet(raw)

        direct = Path(raw).expanduser()
        if direct.is_dir():
            root_dir = direct
        else:
            root_dir = DOWNLOAD_BASE_DIR / raw

        if root_dir.is_dir():
            meta = _load_meta(root_dir)
            title = meta.get("title") or root_dir.name
            project = ProjectContext(
                spreadsheet_id=meta.get("spreadsheet_id", ""),
                title=title,
                root_dir=root_dir,
                data_dir=root_dir / "01_data",
                video_dir=root_dir / "02_video",
                img_dir=root_dir / "03_img",
                placeholder_dir=root_dir / "04_placeholder",
                channel_dir=root_dir / "05_channel-name",
                stock_dir=root_dir / "06_stock",
                meta=meta,
            )
            return project

        raise FileNotFoundError(f"Не найдена папка проекта: {root_dir}")

    index = _load_index()
    last_id = index.get("last_used_id")
    if last_id and last_id in index.get("projects", {}):
        info = index["projects"][last_id]
        root_dir = Path(info["path"])
        if root_dir.is_dir():
            meta = _load_meta(root_dir)
            title = meta.get("title") or info.get("title") or root_dir.name
            return ProjectContext(
                spreadsheet_id=meta.get("spreadsheet_id", last_id),
                title=title,
                root_dir=root_dir,
                data_dir=root_dir / "01_data",
                video_dir=root_dir / "02_video",
                img_dir=root_dir / "03_img",
                placeholder_dir=root_dir / "04_placeholder",
                channel_dir=root_dir / "05_channel-name",
                stock_dir=root_dir / "06_stock",
                meta=meta,
            )
    raise FileNotFoundError("Не найден кэш таблицы. Сначала укажите ссылку на Google Sheets.")


def prompt_project_context(prompt: str = "Проект (Enter = последняя): ") -> ProjectContext:
    raw = input(prompt).strip()
    return resolve_project(raw, allow_remote=False)


def prompt_remote_cache(
    prompt: str = "Ссылка на Google-таблицу для первичного кэша: ",
) -> ProjectContext:
    raw = input(prompt).strip()
    if not raw:
        raise ValueError("Нужна ссылка на Google Sheets для первичного кэша.")
    return resolve_project(raw, allow_remote=True)


# ===== Link-router logic copied for local CSV generation =====

DEFAULT_HEADERS = ["Cell", "URL"]
DEFAULT_YT_SHEET = "1_Youtube"
DEFAULT_IMG_SHEET = "2_Images"
DEFAULT_FTG_SHEET = "3_Footages"
DEFAULT_OTH_SHEET = "4_Other"


def _column_label(index: int) -> str:
    label = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        label = chr(65 + remainder) + label
    return label or "A"


def _a1_label(row: int, col: int) -> str:
    return f"{_column_label(col)}{row}"


def _normalize_url(url: str) -> str:
    return str(url or "").strip().replace("\u200b", "")


def _is_http_url(url: str) -> bool:
    return bool(re.match(r"^https?://[^/\\s]+\\.[^\\s]+", url, flags=re.I))


def _find_urls_in_text(text: str) -> List[str]:
    if not text:
        return []
    pattern = re.compile(r"\\bhttps?://[^\\s<>\\\"')\\]]+", flags=re.I)
    urls: List[str] = []
    for match in pattern.finditer(text):
        candidate = match.group(0).rstrip("),].")
        urls.append(candidate)
    return urls


def _extract_hyperlink_from_formula(formula: str) -> Optional[str]:
    if not formula:
        return None
    match = re.match(
        r"=\\s*(?:HYPERLINK|ГИПЕРССЫЛКА)\\s*\\(\\s*\\\"([^\\\"]+)\\\"",
        formula,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1)
    return None


def _extract_links_from_cell(cell: Dict) -> List[str]:
    urls: List[str] = []

    hyperlink = cell.get("hyperlink")
    if hyperlink:
        urls.append(hyperlink)

    for run in cell.get("textFormatRuns") or []:
        uri = ((run.get("format") or {}).get("link", {}) or {}).get("uri")
        if uri:
            urls.append(uri)

    formula = (cell.get("userEnteredValue") or {}).get("formulaValue")
    url_from_formula = _extract_hyperlink_from_formula(formula or "")
    if url_from_formula:
        urls.append(url_from_formula)

    formatted_value = cell.get("formattedValue") or ""
    urls.extend(_find_urls_in_text(formatted_value))

    string_value = (cell.get("userEnteredValue") or {}).get("stringValue")
    if string_value and string_value != formatted_value:
        urls.extend(_find_urls_in_text(string_value))

    seen = set()
    unique_urls: List[str] = []
    for raw in urls:
        normalized = _normalize_url(raw)
        if _is_http_url(normalized) and normalized not in seen:
            seen.add(normalized)
            unique_urls.append(normalized)
    return unique_urls


def _extract_links_from_sheet(ws: gspread.Worksheet) -> List[Dict[str, str]]:
    metadata = ws.spreadsheet.fetch_sheet_metadata(
        params={
            "ranges": ws.title,
            "includeGridData": True,
            "fields": "sheets(properties.sheetId,data.startRow,data.startColumn,data.rowData.values(formattedValue,userEnteredValue,textFormatRuns,hyperlink))",
        }
    )
    sheets = metadata.get("sheets", [])
    sheet_blocks: Sequence[Dict] = []
    for sheet in sheets:
        if sheet.get("properties", {}).get("sheetId") == ws.id:
            sheet_blocks = sheet.get("data", []) or []
            break

    results: List[Dict[str, str]] = []
    for block in sheet_blocks:
        start_row = block.get("startRow", 0)
        start_col = block.get("startColumn", 0)
        for r_idx, row in enumerate(block.get("rowData") or []):
            cells = row.get("values") or []
            for c_idx, cell in enumerate(cells):
                row_number = start_row + r_idx + 1
                col_number = start_col + c_idx + 1
                labels = _extract_links_from_cell(cell)
                if not labels:
                    continue
                a1 = _a1_label(row_number, col_number)
                for idx, url in enumerate(labels, start=1):
                    results.append({"a1": a1, "idx": idx, "url": url})
    return results


def _detect_category(url: str) -> str:
    host_match = re.match(r"^https?://([^/]+)(/.*)?", url, flags=re.I)
    host = (host_match.group(1) if host_match else "").lower()
    path = (host_match.group(2) if host_match and host_match.group(2) else "").lower()

    is_youtube = "youtube.com" in host or host == "youtu.be"
    is_instagram = "instagram.com" in host or host == "instagr.am"
    if is_youtube or is_instagram:
        return "pulltube"

    if re.search(r"\\.(jpg|jpeg|png|gif|webp|svg|bmp|tif|tiff)(\\?|#|$)", path, flags=re.I):
        return "image"

    if "motionarray.com" in host:
        return "footage"

    return "other"


def build_router_outputs(
    ws: gspread.Worksheet,
    *,
    headers: Optional[Sequence[str]] = None,
    yt_sheet: str = DEFAULT_YT_SHEET,
    img_sheet: str = DEFAULT_IMG_SHEET,
    ftg_sheet: str = DEFAULT_FTG_SHEET,
    oth_sheet: str = DEFAULT_OTH_SHEET,
) -> Dict[str, List[List[str]]]:
    header_row = list(headers or DEFAULT_HEADERS)
    results = _extract_links_from_sheet(ws)

    pull: List[List[str]] = [header_row]
    img: List[List[str]] = [header_row]
    ftg: List[List[str]] = [header_row]
    oth: List[List[str]] = [header_row]

    for item in results:
        row = [item.get("a1", ""), item.get("url", "")]
        category = _detect_category(item.get("url", ""))
        if category == "pulltube":
            pull.append(row)
        elif category == "image":
            img.append(row)
        elif category == "footage":
            ftg.append(row)
        else:
            oth.append(row)

    return {
        yt_sheet: pull,
        img_sheet: img,
        ftg_sheet: ftg,
        oth_sheet: oth,
    }
