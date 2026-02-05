#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Add source PNG overlays in DaVinci Resolve by matching filenames.

Workflow:
1) Ask for a folder with video files.
2) Ask for a folder with PNG overlays (same stem as video/column A).
3) Place video on V1, PNG on V2, stretch PNG to full video length,
   align PNG to the right edge of the 90% safe zone, and render.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VIDEO_EXTS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".mkv",
    ".avi",
    ".mxf",
    ".webm",
}
PNG_EXTS = {".png"}
SAFE_ZONE_FRACTION = 0.9


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


def normalize_name(value: str) -> str:
    return Path(value).stem.strip().lower()


def find_video_files(folder: Path) -> List[Path]:
    files: List[Path] = []
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
            files.append(path)
    return sorted(files)


def find_png_files(folder: Path) -> List[Path]:
    files: List[Path] = []
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in PNG_EXTS:
            files.append(path)
    return sorted(files)


def build_file_map(files: List[Path]) -> Tuple[Dict[str, Path], Dict[str, List[Path]]]:
    mapping: Dict[str, Path] = {}
    duplicates: Dict[str, List[Path]] = {}
    for path in files:
        key = normalize_name(path.name)
        if not key:
            continue
        if key in mapping:
            duplicates.setdefault(key, [mapping[key]]).append(path)
            continue
        mapping[key] = path
    return mapping, duplicates


def read_png_size(path: Path) -> Optional[Tuple[int, int]]:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
        if len(header) < 24:
            return None
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        if header[12:16] != b"IHDR":
            return None
        width = int.from_bytes(header[16:20], "big")
        height = int.from_bytes(header[20:24], "big")
        if width <= 0 or height <= 0:
            return None
        return width, height
    except Exception:
        return None


def load_resolve_script() -> Optional[object]:
    try:
        import DaVinciResolveScript as dvr_script  # type: ignore

        return dvr_script
    except ImportError:
        pass

    candidates = [
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
        "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Developer/Scripting/Modules",
        os.path.expanduser(
            "~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
        ),
        "/opt/resolve/Developer/Scripting/Modules",
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            sys.path.append(candidate)
            try:
                import DaVinciResolveScript as dvr_script  # type: ignore

                return dvr_script
            except ImportError:
                continue
    return None


def get_tool_by_name(comp: object, names: Tuple[str, ...]) -> Optional[object]:
    for name in names:
        try:
            tool = comp.FindTool(name)
        except Exception:
            tool = None
        if tool:
            return tool
    return None


def get_tool_by_reg_id(comp: object, reg_id: str) -> Optional[object]:
    try:
        tools = comp.GetToolList(False)
    except Exception:
        tools = {}
    if not isinstance(tools, dict):
        return None
    for tool in tools.values():
        try:
            attrs = tool.GetAttrs()
        except Exception:
            attrs = {}
        if attrs and attrs.get("TOOLS_RegID") == reg_id:
            return tool
        if getattr(tool, "ID", "") == reg_id:
            return tool
    return None


def get_tool(comp: object, names: Tuple[str, ...], reg_id: str) -> Optional[object]:
    tool = get_tool_by_name(comp, names)
    if tool:
        return tool
    return get_tool_by_reg_id(comp, reg_id)


def add_tool(comp: object, primary: str, fallback: Optional[str] = None) -> Optional[object]:
    for name in (primary, fallback):
        if not name:
            continue
        try:
            tool = comp.AddTool(name)
        except Exception:
            tool = None
        if tool:
            return tool
    return None


def connect_tools(dest: object, input_name: str, src: object) -> bool:
    try:
        dest.ConnectInput(input_name, src)
        return True
    except Exception:
        pass
    try:
        setattr(dest, input_name, src)
        return True
    except Exception:
        return False


def set_tool_input(tool: object, key: str, value: object) -> bool:
    try:
        tool.SetInput(key, value)
        return True
    except Exception:
        pass
    try:
        setattr(tool, key, value)
        return True
    except Exception:
        pass
    try:
        tool[key] = value
        return True
    except Exception:
        return False


def get_or_add_fusion_comp(clip_item: object) -> Optional[object]:
    comp = None
    try:
        count = clip_item.GetFusionCompCount()
    except Exception:
        count = 0
    if count < 1:
        try:
            comp = clip_item.AddFusionComp()
        except Exception:
            comp = None
    if not comp:
        try:
            comp = clip_item.GetFusionCompByIndex(1)
        except Exception:
            comp = None
    return comp


def get_track_items(timeline: object, track_index: int) -> List[object]:
    try:
        items = timeline.GetItemListInTrack("video", track_index)
    except Exception:
        return []
    return items or []


def get_first_video_item(timeline: object, track_index: int = 1) -> Optional[object]:
    items = get_track_items(timeline, track_index)
    return items[0] if items else None


def compute_overlay_center(
    resolution: Optional[Tuple[int, int]],
    png_size: Optional[Tuple[int, int]],
) -> Tuple[float, float]:
    safe_zone = max(0.5, min(1.0, SAFE_ZONE_FRACTION))
    margin = (1.0 - safe_zone) / 2.0
    safe_right = 1.0 - margin
    safe_bottom = 1.0 - margin

    center_x = safe_right
    center_y = safe_bottom
    if resolution and png_size:
        width, height = resolution
        png_w, png_h = png_size
        if width > 0 and height > 0:
            center_x = safe_right - (png_w / (2.0 * width))
            center_y = safe_bottom - (png_h / (2.0 * height))

    center_x = max(0.0, min(1.0, center_x))
    center_y = max(0.0, min(1.0, center_y))
    return center_x, center_y


def compute_png_scale(
    project_resolution: Optional[Tuple[int, int]],
    clip_resolution: Optional[Tuple[int, int]],
) -> float:
    if not project_resolution or not clip_resolution:
        return 1.0
    proj_w, proj_h = project_resolution
    clip_w, clip_h = clip_resolution
    if proj_w <= 0 or proj_h <= 0 or clip_w <= 0 or clip_h <= 0:
        return 1.0
    scale_w = clip_w / proj_w
    scale_h = clip_h / proj_h
    if abs(scale_w - scale_h) > 0.01:
        return min(scale_w, scale_h)
    return scale_w


def get_tool_name(tool: object) -> Optional[str]:
    try:
        attrs = tool.GetAttrs()
    except Exception:
        attrs = {}
    if not isinstance(attrs, dict):
        return None
    return attrs.get("TOOLS_Name") or attrs.get("TOOLB_Name") or attrs.get("Name")


def get_or_add_media_in2(comp: object) -> Optional[object]:
    media_in2 = get_tool_by_name(comp, ("MediaIn2",))
    if media_in2:
        return media_in2
    media_in2 = add_tool(comp, "MediaIn")
    if not media_in2:
        return None
    name = get_tool_name(media_in2)
    if name and name.lower() in {"mediain1", "mediain"}:
        return None
    return media_in2


def set_media_in_clip(
    media_in: object,
    media_pool_item: object,
    png_path: Path,
) -> bool:
    media_id = None
    if media_pool_item:
        for key in ("GetMediaId", "GetMediaID", "GetClipID"):
            try:
                getter = getattr(media_pool_item, key)
            except AttributeError:
                continue
            try:
                media_id = getter()
            except Exception:
                media_id = None
            if media_id:
                break

    candidates = [
        ("Clip", media_pool_item),
        ("MediaPoolItem", media_pool_item),
        ("MediaID", media_id),
        ("MediaId", media_id),
        ("ID", media_id),
        ("FileName", str(png_path)),
        ("Filename", str(png_path)),
        ("Path", str(png_path)),
    ]
    for key, value in candidates:
        if value and set_tool_input(media_in, key, value):
            return True
    return False


def apply_png_fusion_overlay(
    clip_item: object,
    png_item: object,
    png_path: Path,
    project_resolution: Optional[Tuple[int, int]],
    clip_resolution: Optional[Tuple[int, int]],
) -> bool:
    comp = get_or_add_fusion_comp(clip_item)
    if not comp:
        return False

    media_in = get_tool(comp, ("MediaIn1", "MediaIn"), "MediaIn")
    media_out = get_tool(comp, ("MediaOut1", "MediaOut"), "MediaOut")
    if not media_in or not media_out:
        return False

    media_in2 = get_or_add_media_in2(comp)
    if not media_in2:
        return False
    if not set_media_in_clip(media_in2, png_item, png_path):
        return False

    transform = get_tool(comp, ("Transform1", "Transform2"), "Transform")
    if not transform:
        transform = add_tool(comp, "Transform")
    if not transform:
        return False

    merge = get_tool(comp, ("Merge1", "Merge"), "Merge")
    if not merge:
        merge = add_tool(comp, "Merge")
    if not merge:
        return False

    connect_tools(transform, "Input", media_in2)
    connect_tools(merge, "Background", media_in)
    connect_tools(merge, "Foreground", transform)
    connect_tools(media_out, "Input", merge)

    resolution = project_resolution or clip_resolution
    png_size = read_png_size(png_path)
    center_x, center_y = compute_overlay_center(resolution, png_size)
    scale = compute_png_scale(project_resolution, clip_resolution)
    set_tool_input(transform, "Center", [center_x, center_y])
    set_tool_input(transform, "Size", scale)
    return True


def get_project_resolution(project: object) -> Optional[Tuple[int, int]]:
    try:
        width = project.GetSetting("timelineResolutionWidth")
        height = project.GetSetting("timelineResolutionHeight")
    except Exception:
        return None
    if not width or not height:
        return None
    try:
        return int(width), int(height)
    except ValueError:
        return None


def parse_resolution(value: str) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    match = re.search(r"(\d{3,5})\s*[xX]\s*(\d{3,5})", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def get_clip_resolution(clip: object) -> Optional[Tuple[int, int]]:
    try:
        props = clip.GetClipProperty()
    except Exception:
        props = {}

    return (
        parse_resolution(props.get("Resolution", ""))
        or parse_resolution(props.get("Format", ""))
        or parse_resolution(props.get("Video Format", ""))
    )


def set_timeline_resolution(timeline: object, resolution: Optional[Tuple[int, int]]) -> None:
    if not resolution:
        return
    width, height = resolution
    try:
        timeline.SetSetting("timelineResolutionWidth", str(width))
        timeline.SetSetting("timelineResolutionHeight", str(height))
    except Exception:
        return


def render_timeline(
    project: object,
    target_dir: Path,
    output_name: str,
    preset: Optional[str],
) -> bool:
    if preset:
        try:
            project.LoadRenderPreset(preset)
        except Exception:
            print(f"[WARN] Не удалось загрузить пресет: {preset}. Используем текущий.")

    try:
        project.SetRenderSettings(
            {
                "SelectAllFrames": True,
                "TargetDir": str(target_dir),
                "CustomName": output_name,
                "UseCurrentTimelineSettings": True,
            }
        )
    except Exception:
        return False

    try:
        job_id = project.AddRenderJob()
    except Exception:
        return False

    try:
        project.StartRendering()
    except Exception:
        return False

    while True:
        try:
            if not project.IsRenderingInProgress():
                break
        except Exception:
            break
        time.sleep(1.0)

    try:
        project.DeleteRenderJob(job_id)
    except Exception:
        pass
    return True


def main() -> None:
    print("=== DaVinci: add source PNG overlay ===")

    video_folder = Path(input_nonempty("Путь к папке с видео")).expanduser().resolve()
    if not video_folder.is_dir():
        die(f"Папка не найдена: {video_folder}")

    png_folder = Path(input_nonempty("Путь к папке с PNG источниками")).expanduser().resolve()
    if not png_folder.is_dir():
        die(f"Папка не найдена: {png_folder}")

    suffix = input_nonempty("Суффикс для рендера", "_channelAdd")
    preset_name = input("Имя render preset (Enter — текущий): ").strip() or None

    dvr_script = load_resolve_script()
    if not dvr_script:
        die("DaVinci Resolve scripting API не найден.")

    resolve = dvr_script.scriptapp("Resolve")
    if not resolve:
        die("Не удалось подключиться к DaVinci Resolve. Запустите Resolve.")

    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject() if project_manager else None
    if not project:
        die("Не открыт проект в Resolve.")

    media_pool = project.GetMediaPool()
    media_storage = resolve.GetMediaStorage()
    png_pool_cache: Dict[Path, object] = {}

    project_resolution = get_project_resolution(project)
    if not project_resolution:
        print("[WARN] Не удалось получить разрешение проекта. Будет использовано разрешение клипа.")

    files = find_video_files(video_folder)
    if not files:
        die("В папке нет видеофайлов.")

    png_files = find_png_files(png_folder)
    if not png_files:
        die("В папке нет PNG файлов.")

    png_map, duplicates = build_file_map(png_files)
    if duplicates:
        print("[WARN] Найдены дубликаты PNG по имени. Будет использован первый:")
        for key, paths in sorted(duplicates.items()):
            names = ", ".join(path.name for path in paths)
            print(f"  {key}: {names}")

    processed = 0
    skipped = 0
    missing = 0
    failed = 0

    for path in files:
        key = normalize_name(path.name)
        png_path = png_map.get(key)
        if not png_path:
            missing += 1
            continue

        output_name = f"{path.stem}{suffix}"
        output_path = path.with_name(output_name + path.suffix)
        if output_path.exists():
            print(f"[SKIP] Уже существует: {output_path.name}")
            skipped += 1
            continue

        clips = media_storage.AddItemListToMediaPool([str(path)])
        if not clips:
            print(f"[ERR] Не удалось импортировать: {path.name}")
            failed += 1
            continue

        timeline_name = f"{path.stem}{suffix}"
        timeline = media_pool.CreateTimelineFromClips(timeline_name, clips)
        if not timeline:
            print(f"[ERR] Не удалось создать timeline: {path.name}")
            failed += 1
            continue

        clip_resolution = get_clip_resolution(clips[0])
        resolution = project_resolution or clip_resolution
        if project_resolution:
            set_timeline_resolution(timeline, project_resolution)
        if resolution:
            print(f"[INFO] Разрешение: {resolution[0]}x{resolution[1]}")

        try:
            project.SetCurrentTimeline(timeline)
        except Exception:
            pass

        base_clip = get_first_video_item(timeline, 1)
        if not base_clip:
            print(f"[ERR] Не найден клип на V1: {path.name}")
            failed += 1
            try:
                project.DeleteTimeline(timeline)
            except Exception:
                pass
            continue

        png_item = png_pool_cache.get(png_path)
        if not png_item:
            png_items = media_storage.AddItemListToMediaPool([str(png_path)])
            if not png_items:
                print(f"[ERR] Не удалось импортировать PNG: {png_path.name}")
                failed += 1
                try:
                    project.DeleteTimeline(timeline)
                except Exception:
                    pass
                continue
            png_item = png_items[0]
            png_pool_cache[png_path] = png_item

        if not apply_png_fusion_overlay(
            base_clip, png_item, png_path, project_resolution, clip_resolution
        ):
            print(f"[ERR] Не удалось добавить PNG через Fusion: {png_path.name}")
            failed += 1
            try:
                project.DeleteTimeline(timeline)
            except Exception:
                pass
            continue

        ok = render_timeline(project, video_folder, output_name, preset_name)
        if ok:
            print(f"[OK] {path.name} → {output_name}")
            processed += 1
        else:
            print(f"[ERR] Рендер не удался: {path.name}")
            failed += 1

        try:
            project.DeleteTimeline(timeline)
        except Exception:
            pass

    print("\n=== Итог ===")
    print(f"Готово:     {processed}")
    print(f"Пропущено:  {skipped}")
    print(f"Без PNG:    {missing}")
    print(f"Ошибки:     {failed}")


if __name__ == "__main__":
    main()
