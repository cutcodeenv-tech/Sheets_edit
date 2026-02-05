#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скачивает изображения из локального CSV (лист "2_Images").

Ожидаемая структура листа:
- Колонка A — имя файла (может содержать расширение).
- Колонка B — ссылка на изображение.
- Колонка C — статус (перезаписывается скриптом).

Поддерживаются ссылки на Instagram. Если пост — карусель, каждому файлу
добавляется суффикс `_1`, `_2`, ... При необходимости можно указать
`INSTAGRAM_SESSIONID` в `.env` для более стабильной работы.

Таблица берётся из локального кэша CSV (01_data).
"""

from __future__ import annotations

import html as html_unescape
import json
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from sheet_cache import csv_path_for_sheet, prompt_project_context, read_csv_rows, write_csv_rows


DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
}

INSTAGRAM_HEADERS: Dict[str, str] = {
    **DEFAULT_HEADERS,
    "Accept": "application/json,image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Referer": "https://www.instagram.com/",
    "X-IG-App-ID": "936619743392459",
}


def input_nonempty(prompt: str, default: Optional[str] = None) -> str:
    while True:
        answer = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
        if answer:
            return answer
        if default:
            return default
        print("Значение не может быть пустым. Попробуйте ещё раз.")


def _set_cell(rows: List[List[str]], row_idx: int, col_idx: int, value: str) -> None:
    while len(rows) < row_idx:
        rows.append([])
    row = rows[row_idx - 1]
    while len(row) < col_idx:
        row.append("")
    row[col_idx - 1] = value


def slugify_filename(name: str) -> str:
    value = name.strip()
    value = value.replace(" ", "_")
    value = re.sub(r"[^A-Za-z0-9_.-]", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("._")


def ensure_extension(base_name: str, url_path: str, content_type: Optional[str]) -> str:
    base_path = Path(base_name)
    stem = base_path.stem if base_path.suffix else base_name
    safe_stem = slugify_filename(stem) or datetime.now().strftime("image_%Y%m%d_%H%M%S")

    ext = base_path.suffix
    if not ext:
        ext = Path(url_path).suffix
    if not ext and content_type:
        ctype = content_type.split(";")[0].strip()
        guessed = mimetypes.guess_extension(ctype)
        if guessed:
            ext = guessed
    if not ext:
        ext = ".jpg"
    return safe_stem + ext


def iter_rows(values: List[List[str]]) -> Iterable[tuple[int, str, str]]:
    for idx, row in enumerate(values, start=1):
        name = row[0].strip() if len(row) > 0 else ""
        url = row[1].strip() if len(row) > 1 else ""
        yield idx, name, url


def shorten_error(msg: str, limit: int = 80) -> str:
    clean = msg.replace("\n", " ").strip()
    return clean if len(clean) <= limit else clean[: limit - 1] + "..."


def is_instagram_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    host = (parsed.netloc or "").lower()
    return host.endswith("instagram.com") or host.endswith("instagr.am")


def _pick_best_image_url(candidates: List[Dict]) -> Optional[str]:
    if not candidates:
        return None
    try:
        sorted_c = sorted(candidates, key=lambda c: int(c.get("width", 0)), reverse=True)
        return sorted_c[0].get("url")
    except Exception:  # noqa: BLE001
        return candidates[0].get("url")


def _extract_media_urls_from_item(item: Dict) -> List[str]:
    urls: List[str] = []

    if isinstance(item.get("carousel_media"), list):
        for media in item["carousel_media"]:
            if "image_versions2" in media and isinstance(media["image_versions2"].get("candidates"), list):
                url = _pick_best_image_url(media["image_versions2"]["candidates"])
                if url:
                    urls.append(url)
            elif isinstance(media.get("video_versions"), list) and media["video_versions"]:
                url = media["video_versions"][0].get("url")
                if url:
                    urls.append(url)
        return urls

    if "image_versions2" in item and isinstance(item["image_versions2"].get("candidates"), list):
        url = _pick_best_image_url(item["image_versions2"]["candidates"])
        if url:
            urls.append(url)
    elif isinstance(item.get("video_versions"), list) and item["video_versions"]:
        url = item["video_versions"][0].get("url")
        if url:
            urls.append(url)

    node = item.get("graphql") or item.get("xdt_api__v1__media__shortcode__web_info")
    if node:
        try:
            shortcode_media = node.get("shortcode_media") if "shortcode_media" in node else node
            if shortcode_media.get("__typename") == "XDTGraphSidecar":
                edges = shortcode_media.get("edge_sidecar_to_children", {}).get("edges", [])
                for edge in edges:
                    child = edge.get("node", {})
                    if child.get("is_video") and child.get("video_url"):
                        urls.append(child["video_url"])
                    elif isinstance(child.get("display_resources"), list) and child["display_resources"]:
                        urls.append(child["display_resources"][-1].get("src"))
            else:
                if shortcode_media.get("is_video") and shortcode_media.get("video_url"):
                    urls.append(shortcode_media["video_url"])
                elif isinstance(shortcode_media.get("display_resources"), list) and shortcode_media["display_resources"]:
                    urls.append(shortcode_media["display_resources"][-1].get("src"))
        except Exception:  # noqa: BLE001
            pass

    return [u for u in urls if isinstance(u, str) and u.startswith("http")]


def _extract_from_shared_data(data: Dict) -> List[str]:
    try:
        post_pages = (
            data.get("entry_data", {}).get("PostPage")
            or data.get("require", [{}])[0].get("args", [{}])[0].get("entry_data", {}).get("PostPage")
        )
        if isinstance(post_pages, list) and post_pages:
            node = {"graphql": post_pages[0].get("graphql", {})}
            return _extract_media_urls_from_item(node)
    except Exception:  # noqa: BLE001
        return []
    return []


def _extract_urls_from_html(html: str) -> List[str]:
    urls: List[str] = []
    text = html_unescape.unescape(html)

    match = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\']+)["\']',
        text,
        re.IGNORECASE,
    )
    if match:
        urls.append(match.group(1))

    for m in re.finditer(r'"display_url"\s*:\s*"(https?://[^"]+)"', text):
        urls.append(m.group(1).encode("utf-8").decode("unicode_escape"))
    for m in re.finditer(r'"video_url"\s*:\s*"(https?://[^"]+)"', text):
        urls.append(m.group(1).encode("utf-8").decode("unicode_escape"))

    for m in re.finditer(r'"candidates"\s*:\s*\[(.*?)\]', text, re.DOTALL):
        block = m.group(1)
        for u in re.findall(r'"url"\s*:\s*"(https?://[^"]+)"', block):
            urls.append(u.encode("utf-8").decode("unicode_escape"))

    seen = set()
    ordered: List[str] = []
    for url in urls:
        if url and url.startswith("http") and url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def fetch_instagram_media_urls(url: str) -> Tuple[Optional[str], List[str]]:
    session = requests.Session()
    session.headers.update(INSTAGRAM_HEADERS)

    load_dotenv(override=True)
    ig_sid = os.getenv("INSTAGRAM_SESSIONID")
    if ig_sid:
        session.cookies.set("sessionid", ig_sid, domain=".instagram.com")

    json_candidates = [
        url.rstrip("/") + "/?__a=1&__d=dis",
        url.rstrip("/") + "/?__a=1&amp;__d=dis",
    ]
    last_exc: Optional[Exception] = None

    for endpoint in json_candidates:
        try:
            response = session.get(endpoint, timeout=30)
            text = (response.text or "").strip()
            data: Optional[Dict] = None
            if text.startswith("{"):
                data = json.loads(text)
            elif response.headers.get("Content-Type", "").lower().startswith("application/json"):
                data = response.json()
            if data:
                if isinstance(data.get("items"), list) and data["items"]:
                    urls = _extract_media_urls_from_item(data["items"][0])
                    if urls:
                        return None, urls
                urls = _extract_media_urls_from_item(data)
                if urls:
                    return None, urls
        except Exception as exc:  # noqa: BLE001
            last_exc = exc

    try:
        oembed = session.get(
            "https://www.instagram.com/oembed/",
            params={"url": url, "omitscript": "true"},
            timeout=30,
        )
        oembed.raise_for_status()
        data = oembed.json()
        thumb = data.get("thumbnail_url")
        if thumb:
            return None, [thumb]
    except Exception as exc:  # noqa: BLE001
        last_exc = exc

    try:
        html_resp = session.get(url, timeout=30)
        html_resp.raise_for_status()
        html = html_resp.text

        shared_match = re.search(r"window\._sharedData\s*=\s*(\{.*?\});", html, re.DOTALL)
        if shared_match:
            try:
                shared_data = json.loads(shared_match.group(1))
                urls = _extract_from_shared_data(shared_data)
                if urls:
                    return None, urls
            except Exception as exc:  # noqa: BLE001
                last_exc = exc

        ld_match = re.search(
            r"<script[^>]*type=['\"]application/ld\+json['\"][^>]*>(.+?)</script>",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        if ld_match:
            try:
                ld = json.loads(html_unescape.unescape(ld_match.group(1)))
                image_field = ld.get("image")
                if isinstance(image_field, str):
                    return None, [image_field]
                if isinstance(image_field, list) and image_field:
                    return None, [image_field[0]]
            except Exception as exc:  # noqa: BLE001
                last_exc = exc

        scraped = _extract_urls_from_html(html)
        if scraped:
            return None, scraped
    except Exception as exc:  # noqa: BLE001
        last_exc = exc

    err = "Instagram: не удалось извлечь медиа"
    if last_exc:
        err += f" ({shorten_error(str(last_exc))})"
    return err, []


def _find_existing_file(base_path: Path) -> Optional[Path]:
    candidates = [
        base_path.with_suffix(ext)
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff")
    ]
    for path in candidates:
        if path.exists():
            return path
    if base_path.suffix and base_path.exists():
        return base_path
    return None


def download_image(url: str, destination: Path) -> Tuple[Optional[str], Optional[Path], bool]:
    existing = _find_existing_file(destination)
    if existing:
        return None, existing, True
    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=30, stream=True)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return f"Ошибка запроса: {shorten_error(str(exc))}", None, False

    filename = ensure_extension(destination.name, urlparse(url).path, response.headers.get("Content-Type"))
    target_path = destination.parent / filename

    try:
        with open(target_path, "wb") as fp:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    fp.write(chunk)
    except Exception as exc:  # noqa: BLE001
        return f"Ошибка записи файла: {shorten_error(str(exc))}", None, False

    return None, target_path, False


def download_instagram_media(url: str, destination_base: Path) -> Tuple[Optional[str], List[Path], int]:
    error, media_urls = fetch_instagram_media_urls(url)
    if error:
        return error, [], 0
    if not media_urls:
        return "Instagram: медиа не найдены", [], 0

    saved: List[Path] = []
    skipped = 0
    for index, media_url in enumerate(media_urls, start=1):
        suffix = f"_{index}" if len(media_urls) > 1 else ""
        dest = destination_base.parent / f"{destination_base.name}{suffix}"
        err, saved_path, was_skipped = download_image(media_url, dest)
        if err:
            for p in saved:
                try:
                    p.unlink()
                except Exception:  # noqa: BLE001
                    pass
            return err, [], skipped
        if was_skipped and saved_path:
            skipped += 1
            saved.append(saved_path)
        elif saved_path:
            saved.append(saved_path)

    return None, saved, skipped


def main() -> None:
    try:
        project = prompt_project_context("Проект (Enter = последняя): ")
    except Exception as exc:
        print(f"Ошибка: {exc}")
        return

    default_out = project.img_dir
    out_dir = Path(input_nonempty("Папка для сохранения", str(default_out))).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    worksheet_name = "2_Images"

    csv_path = csv_path_for_sheet(project, worksheet_name)
    values = read_csv_rows(csv_path)
    if not values:
        print(f"Локальный CSV для '{worksheet_name}' пуст или не найден.")
        return

    success_count = 0
    fail_count = 0
    skip_count = 0
    error_rows: List[tuple[int, str, str, str]] = []

    header_name_tokens = {"name", "filename", "title", "имя"}
    header_url_tokens = {"url", "link", "ссылка"}

    for row_idx, name, url in iter_rows(values):
        if not name and not url:
            continue

        saved_path: Optional[Path] = None

        if row_idx == 1 and (
            name.lower() in header_name_tokens or url.lower() in header_url_tokens
        ):
            continue

        if not name:
            status = "❌ Нет имени"
            fail_count += 1
            error_rows.append((row_idx, name, url, status))
        elif not url:
            status = "❌ Нет ссылки"
            fail_count += 1
            error_rows.append((row_idx, name, url, status))
        elif not re.match(r"^https?://", url, flags=re.I):
            status = "❌ Неверный формат URL"
            fail_count += 1
            error_rows.append((row_idx, name, url, status))
        else:
            file_stub = slugify_filename(name) or f"image_{row_idx}"
            destination = out_dir / file_stub
            if is_instagram_url(url):
                error, saved_paths, skipped = download_instagram_media(url, destination)
                if error:
                    status = f"❌ {error}"
                    fail_count += 1
                    error_rows.append((row_idx, name, url, status))
                else:
                    display_names = ", ".join(p.name for p in saved_paths[:5])
                    extra = "" if len(saved_paths) <= 5 else f", ...(+{len(saved_paths) - 5})"
                    if saved_paths and skipped == len(saved_paths):
                        status = "⏭️ Уже есть"
                    else:
                        status = f"✅ {datetime.now():%Y-%m-%d %H:%M} ({display_names}{extra})"
                    success_count += max(0, len(saved_paths) - skipped)
                    skip_count += skipped
                    saved_path = saved_paths[0]
            else:
                error, saved_path, was_skipped = download_image(url, destination)
                if error:
                    status = f"❌ {error}"
                    fail_count += 1
                    error_rows.append((row_idx, name, url, status))
                    saved_path = None
                elif was_skipped:
                    status = "⏭️ Уже есть"
                    skip_count += 1
                else:
                    status = f"✅ {datetime.now():%Y-%m-%d %H:%M} ({saved_path.name})"
                    success_count += 1

        _set_cell(values, row_idx, 3, status)
        if saved_path:
            print(f"[{row_idx}] {name or '<без имени>'} → {saved_path}")
        else:
            print(f"[{row_idx}] {name or '<без имени>'} -> {status}")

    write_csv_rows(csv_path, values)

    if error_rows:
        error_path = out_dir / "download_errors.txt"
        with error_path.open("w", encoding="utf-8") as f:
            for row_idx, name, url, status in error_rows:
                f.write(f"[{row_idx}] {name or '<без имени>'}\n")
                f.write(f"URL: {url}\n")
                f.write(f"ERROR: {status}\n")
                f.write("-" * 60 + "\n")

    print("\n=== Итог ===")
    print(f"Успешно: {success_count}")
    print(f"Ошибки:  {fail_count}")
    print(f"Пропущено (уже есть): {skip_count}")
    print(f"Путь:     {out_dir}")


if __name__ == "__main__":
    main()
