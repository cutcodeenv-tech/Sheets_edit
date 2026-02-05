#!/usr/bin/env python3
"""
Скрипт для скачивания YouTube видео через pull-vids (docker)
Читает список ссылок из локального CSV (кэш таблицы) и скачивает их в директорию проекта
"""

import os
import subprocess
import sys
import time
import re
import pty
from pathlib import Path
from typing import List, Optional

from sheet_cache import csv_path_for_sheet, prompt_project_context, read_csv_rows


def extract_video_id(url):
    """
    Извлекает ID видео из YouTube URL
    
    Args:
        url: YouTube URL
    
    Returns:
        ID видео или None
    """
    # Паттерны для различных форматов YouTube URL
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11}).*',  # Стандартный формат
        r'(?:embed/)([0-9A-Za-z_-]{11})',  # Embed формат
        r'(?:watch\?v=)([0-9A-Za-z_-]{11})',  # Watch формат
        r'youtu\.be/([0-9A-Za-z_-]{11})',  # Короткий формат
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def check_video_exists(video_dir, video_id):
    """
    Проверяет существование видео файла с данным ID
    
    Args:
        video_dir: Директория с видео
        video_id: ID видео для поиска
    
    Returns:
        True если файл существует, False иначе
    """
    if not video_id:
        return False
    
    video_extensions = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.wmv', '.m4v'}
    video_path = Path(video_dir)

    if not video_path.exists():
        return False

    for p in video_path.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() in video_extensions and video_id in p.name:
            return True
    
    return False


def get_existing_videos_count(video_dir):
    """
    Подсчитывает количество видео файлов в директории
    
    Args:
        video_dir: Директория с видео
    
    Returns:
        Количество видео файлов
    """
    if not os.path.exists(video_dir):
        return 0
    
    video_extensions = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.wmv', '.m4v'}
    video_path = Path(video_dir)
    if not video_path.exists():
        return 0
    return sum(1 for p in video_path.iterdir() if p.is_file() and p.suffix.lower() in video_extensions)


def input_nonempty(prompt, default=None):
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("❌ Значение не может быть пустым!")


def _extract_urls_from_text(text: str) -> List[str]:
    if not text:
        return []
    if re.match(r"^https?://", text.strip(), flags=re.I):
        return [text.strip()]
    pattern = re.compile(r"\bhttps?://[^\s<>\"')\]]+", flags=re.I)
    urls: List[str] = []
    for match in pattern.finditer(text):
        candidate = match.group(0).rstrip("),].")
        urls.append(candidate)
    return urls


def _detect_url_column(values: List[List[str]]) -> Optional[int]:
    if not values:
        return None
    max_cols = max((len(r) for r in values), default=0)
    if max_cols == 0:
        return None

    counts = [0] * max_cols
    for row in values:
        for c in range(max_cols):
            cell = row[c].strip() if c < len(row) else ""
            if _extract_urls_from_text(cell):
                counts[c] += 1

    best_idx = max(range(max_cols), key=lambda i: counts[i])
    return best_idx if counts[best_idx] > 0 else None


def read_links_from_sheet(values: List[List[str]]) -> List[str]:
    url_col = _detect_url_column(values)
    if url_col is None:
        return []

    header_tokens = {"url", "link", "ссылка", "youtube", "yt"}
    links: List[str] = []
    seen = set()

    for row_idx, row in enumerate(values, start=1):
        cell = row[url_col].strip() if url_col < len(row) else ""
        if row_idx == 1 and cell.lower() in header_tokens:
            continue
        for url in _extract_urls_from_text(cell):
            if url not in seen:
                seen.add(url)
                links.append(url)
    return links


def check_docker():
    """Проверяет наличие docker и docker-compose"""
    try:
        subprocess.run(['docker', '--version'], capture_output=True, check=True)
        print("✓ Docker найден")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Docker не найден! Установите Docker Desktop")
        return False
    
    try:
        subprocess.run(['docker', 'compose', 'version'], capture_output=True, check=True)
        print("✓ Docker Compose найден")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Docker Compose не найден!")
        return False


def _is_netscape_cookies_file(file_path: str) -> bool:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline().strip()
        return first_line.startswith("# Netscape HTTP Cookie File")
    except Exception:
        return False


def _create_empty_netscape_cookies(file_path: str) -> None:
    # Минимальный заголовок в нужном формате. Файл всё равно надо заполнить реальными cookies.
    content = (
        "# Netscape HTTP Cookie File\n"
        "# This file was generated by the script. Replace with real cookies.\n"
        "#\n"
    )
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


def check_cookies_file(base_dir):
    """Проверяет наличие cookies.txt для YouTube аутентификации. Если отсутствует/неверный формат — создаёт валидный шаблон."""
    cookies_file = os.path.join(base_dir, 'cookies.txt')

    if os.path.exists(cookies_file):
        if _is_netscape_cookies_file(cookies_file):
            print(f"✓ Найден файл cookies.txt для аутентификации YouTube")
            return cookies_file
        else:
            # Бэкап неверного файла и создаём корректный шаблон
            backup_path = cookies_file + ".bak"
            try:
                os.replace(cookies_file, backup_path)
                print(f"⚠️  cookies.txt был не в Netscape формате. Сохранён бэкап: {backup_path}")
            except Exception as e:
                print(f"⚠️  Не удалось сохранить бэкап cookies.txt: {e}")
            try:
                _create_empty_netscape_cookies(cookies_file)
                print(f"✓ Создан пустой cookies.txt в Netscape формате")
            except Exception as e:
                print(f"❌ Не удалось создать cookies.txt: {e}")
                return None
            return cookies_file

    # Если файла нет — создаём
    try:
        _create_empty_netscape_cookies(cookies_file)
        print(f"⚠️  cookies.txt не найден. Создан пустой файл в Netscape формате: {cookies_file}")
        print("   Замените его на реальные cookies, иначе скачивание может не работать.")
        return cookies_file
    except Exception as e:
        print(f"❌ Не удалось создать cookies.txt: {e}")
        return None


def check_ffmpeg():
    """Проверяет наличие ffmpeg в системе"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("⚠️  ffmpeg не найден! Конвертация видео будет недоступна")
        print("   Установите ffmpeg: brew install ffmpeg")
        return False


def prompt_convert_choice() -> bool:
    print("Нужна конвертация в MP4?")
    print("1. Да")
    print("2. Нет")
    while True:
        choice = input("Выбор: ").strip()
        if choice == "1":
            return True
        if choice == "2":
            return False
        print("Введите 1 или 2.")


def list_video_files(directory):
    """Возвращает список видеофайлов в директории (рекурсивно)."""
    video_extensions = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.wmv', '.m4v'}
    video_files = []
    base_path = Path(directory)
    if not base_path.exists():
        return []

    for p in base_path.rglob('*'):
        if not p.is_file():
            continue
        if p.suffix.lower() not in video_extensions:
            continue
        if p.name.endswith(('.part', '.tmp', '.temp')):
            continue
        video_files.append(str(p))

    return video_files


def find_latest_video(directory, before_time=None):
    """
    Находит последний добавленный видео файл в директории
    
    Args:
        directory: Директория для поиска
        before_time: Искать файлы, созданные после этого времени
    
    Returns:
        Путь к найденному файлу или None
    """
    video_files = list_video_files(directory)
    if not video_files:
        return None

    # Фильтруем файлы по времени если указано (и если фильтр не отсекает всё)
    if before_time:
        recent_files = [f for f in video_files if os.path.getmtime(f) > before_time]
        if recent_files:
            video_files = recent_files
    
    if not video_files:
        return None
    
    # Возвращаем самый новый файл
    latest_file = max(video_files, key=os.path.getmtime)
    return latest_file


def convert_to_mp4(input_file, output_dir):
    """
    Конвертирует видео файл в mp4 через ffmpeg
    
    Args:
        input_file: Путь к исходному файлу
        output_dir: Директория для сохранения результата
    
    Returns:
        True если конвертация успешна, False иначе
    """
    if not os.path.exists(input_file):
        print(f"  ❌ Файл не найден: {input_file}")
        return False
    
    # Если файл уже mp4, ничего не делаем
    if input_file.lower().endswith('.mp4'):
        print(f"  ℹ️  Файл уже в формате MP4, конвертация не требуется")
        return True
    
    # Генерируем имя выходного файла
    input_filename = os.path.basename(input_file)
    output_filename = os.path.splitext(input_filename)[0] + '.mp4'
    output_file = os.path.join(output_dir, output_filename)
    
    # Если выходной файл уже существует, добавляем суффикс
    counter = 1
    while os.path.exists(output_file):
        output_filename = f"{os.path.splitext(input_filename)[0]}_{counter}.mp4"
        output_file = os.path.join(output_dir, output_filename)
        counter += 1
    
    print(f"  🔄 Конвертация в MP4: {os.path.basename(input_file)} -> {os.path.basename(output_file)}")
    
    try:
        # Команда ffmpeg с оптимальными параметрами
        cmd = [
            'ffmpeg',
            '-i', input_file,
            '-c:v', 'libx264',  # Видеокодек H.264
            '-preset', 'medium',  # Баланс скорости и качества
            '-crf', '23',  # Качество (18-28, меньше = лучше)
            '-c:a', 'aac',  # Аудиокодек AAC
            '-b:a', '192k',  # Битрейт аудио
            '-movflags', '+faststart',  # Оптимизация для потоковой передачи
            '-y',  # Перезаписывать выходной файл
            output_file
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Проверяем, что файл создан
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            print(f"  ✓ Конвертация завершена: {os.path.basename(output_file)}")
            
            # Удаляем оригинальный файл
            try:
                os.remove(input_file)
                print(f"  🗑️  Удален оригинальный файл: {os.path.basename(input_file)}")
            except Exception as e:
                print(f"  ⚠️  Не удалось удалить оригинал: {e}")
            
            return True
        else:
            print(f"  ❌ Выходной файл не создан или пуст")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Ошибка при конвертации: {e}")
        if e.stderr:
            print(f"  Детали ошибки: {e.stderr[-500:]}")  # Последние 500 символов
        return False
    except Exception as e:
        print(f"  ❌ Неожиданная ошибка при конвертации: {e}")
        return False


def run_command_with_pty(cmd, cwd=None):
    """Запускает команду в псевдо-TTY, чтобы прогресс-бар был единым и цветным."""
    try:
        pid, fd = pty.fork()
        if pid == 0:
            if cwd:
                os.chdir(cwd)
            os.execvp(cmd[0], cmd)
        else:
            while True:
                try:
                    data = os.read(fd, 1024)
                except OSError:
                    break
                if not data:
                    break
                os.write(sys.stdout.fileno(), data)
            _, status = os.waitpid(pid, 0)
            return os.waitstatus_to_exitcode(status)
    except Exception:
        result = subprocess.run(cmd, cwd=cwd)
        return result.returncode


def wait_for_stable_file(file_path, stable_seconds=2, timeout=60):
    """Ждёт, пока файл перестанет расти в размере."""
    start = time.time()
    last_size = -1
    stable_for = 0.0
    step = 0.5

    while time.time() - start < timeout:
        if not os.path.exists(file_path):
            time.sleep(step)
            continue
        size = os.path.getsize(file_path)
        if size > 0 and size == last_size:
            stable_for += step
            if stable_for >= stable_seconds:
                return True
        else:
            stable_for = 0.0
            last_size = size
        time.sleep(step)
    return False


def find_new_video_from_snapshot(directory, before_files):
    """Ищет новый видеофайл после скачивания, сравнивая снимок до/после."""
    current_files = set(list_video_files(directory))
    new_files = list(current_files - set(before_files))
    if new_files:
        return max(new_files, key=os.path.getmtime)
    return None


def download_video(url, output_dir, cookies_file=None, pull_vids_dir=None, convert_to_mp4_flag=False):
    """
    Скачивает видео через pull-vids docker-compose и конвертирует в mp4
    
    Args:
        url: URL видео для скачивания
        output_dir: Директория для сохранения видео
        cookies_file: Путь к файлу cookies (опционально)
        pull_vids_dir: Директория с pull-vids (где docker-compose.yml)
        convert_to_mp4_flag: Конвертировать в mp4 после скачивания
    
    Returns:
        True если успешно, False иначе
    """
    # Создаем выходную директорию
    os.makedirs(output_dir, exist_ok=True)
    
    # Снимок файлов перед скачиванием (ищем новый файл после)
    before_download_files = list_video_files(output_dir)
    
    # Команда docker-compose
    cmd = [
        'docker', 'compose', 'run', '--rm',
        '-v', f'{output_dir}:/downloads',
    ]
    
    # Добавляем volume с cookies если файл существует
    if cookies_file and os.path.exists(cookies_file):
        cmd.extend(['-v', f'{cookies_file}:/cookies.txt'])
        cmd.extend(['pull-vids', '--cookies', '/cookies.txt', '-o', '/downloads', url])
    else:
        cmd.extend(['pull-vids', '-o', '/downloads', url])
    
    # Запускаем в директории pull-vids
    try:
        print(f"  📥 Скачивание видео...")
        result_code = run_command_with_pty(cmd, cwd=pull_vids_dir)
        if result_code != 0:
            return False
        
        print(f"  ✓ Видео скачано")
        
        # Если нужна конвертация, ищем скачанный файл и конвертируем
        if convert_to_mp4_flag:
            # Даем время на завершение записи файла
            time.sleep(1)
            
            # Ищем новый файл
            downloaded_file = find_new_video_from_snapshot(output_dir, before_download_files)
            if not downloaded_file:
                # Фоллбек: берём самый новый файл без фильтра по времени
                downloaded_file = find_latest_video(output_dir)
            
            if downloaded_file:
                print(f"  📁 Найден файл: {os.path.basename(downloaded_file)}")

                if not wait_for_stable_file(downloaded_file, stable_seconds=2, timeout=60):
                    print("  ⚠️  Файл ещё записывается или нестабилен, пробую конвертировать...")

                # Конвертируем в mp4
                if convert_to_mp4(downloaded_file, output_dir):
                    return True
                else:
                    print(f"  ⚠️  Конвертация не удалась, но файл скачан")
                    return True  # Всё равно считаем успехом, файл же скачан
            else:
                print(f"  ⚠️  Не удалось найти скачанный файл для конвертации")
                try:
                    recent = sorted(
                        (os.path.join(dp, f) for dp, _, files in os.walk(output_dir) for f in files),
                        key=lambda p: os.path.getmtime(p),
                        reverse=True
                    )[:5]
                    if recent:
                        print("  ⚠️  Последние файлы в output_dir:")
                        for p in recent:
                            print(f"     - {os.path.basename(p)}")
                except Exception:
                    pass
                return True  # Файл скачан, просто не нашли его
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Ошибка при скачивании: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Неожиданная ошибка: {e}")
        return False


def main():
    """Основная функция скрипта"""
    print("=== СКРИПТ СКАЧИВАНИЯ ВИДЕО ЧЕРЕЗ PULL-VIDS ===")
    
    # Базовые пути
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base_dir = repo_dir
    project_root = os.path.dirname(repo_dir)
    download_base_dir = '/Volumes/01_Extreme SSD/[001] Projects/00_YT_Downloader'

    env_pull_vids = os.getenv("PULL_VIDS_DIR", "").strip()
    pull_vids_candidates = [
        env_pull_vids,
        os.path.join(project_root, 'scripts', 'pull-vids'),
        os.path.join(repo_dir, 'scripts', 'pull-vids'),
        os.path.join(repo_dir, 'scripts_Gleb', 'pull-vids'),
        os.path.join(os.getcwd(), 'scripts', 'pull-vids'),
    ]
    pull_vids_candidates = [p for p in pull_vids_candidates if p]
    pull_vids_dir = next((p for p in pull_vids_candidates if os.path.exists(p)), None)
    
    # Проверяем наличие pull-vids
    if not pull_vids_dir:
        print("❌ Директория pull-vids не найдена.")
        for p in pull_vids_candidates:
            print(f"   Проверено: {p}")
        return
    
    docker_compose_file = os.path.join(pull_vids_dir, 'docker-compose.yml')
    if not os.path.exists(docker_compose_file):
        print(f"❌ Файл docker-compose.yml не найден в {pull_vids_dir}")
        return
    
    print(f"✓ Найдена директория pull-vids: {pull_vids_dir}")
    
    # Проверяем Docker
    if not check_docker():
        return
    
    # Проверяем ffmpeg
    has_ffmpeg = check_ffmpeg()
    want_convert = prompt_convert_choice()
    convert_enabled = want_convert and has_ffmpeg
    if want_convert and not has_ffmpeg:
        print("⚠️  Конвертация отключена: ffmpeg не найден.")
    elif convert_enabled:
        print("✓ Конвертация в MP4 будет выполнена")
    
    # Проверяем cookies
    cookies_file = check_cookies_file(base_dir)
    
    # Читаем ссылки из локального CSV (кэш таблицы)
    try:
        project = prompt_project_context("Проект (Enter = последняя): ")
    except Exception as exc:
        print(f"❌ Ошибка: {exc}")
        return

    worksheet_name = "1_Youtube"
    csv_path = csv_path_for_sheet(project, worksheet_name)
    values = read_csv_rows(csv_path)
    if not values:
        print(f"❌ Не найден локальный CSV для листа '{worksheet_name}'.")
        print("   Сначала создайте кэш таблицы (скачайте её один раз).")
        return

    links = read_links_from_sheet(values)
    if not links:
        print("❌ В таблице не найдено ссылок!")
        return

    print(f"✓ Найдено ссылок в таблице: {len(links)}")
    
    # Директория для сохранения видео
    safe_sheet_title = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", project.title).strip() or "untitled_sheet"
    video_dir = os.path.join(download_base_dir, safe_sheet_title, "02_video")
    os.makedirs(video_dir, exist_ok=True)
    print(f"📁 Директория для видео: {video_dir}")
    
    # Проверяем уже скачанные видео
    existing_count = get_existing_videos_count(video_dir)
    if existing_count > 0:
        print(f"📦 Уже скачано видео: {existing_count}")
    
    # Фильтруем ссылки, пропуская уже скачанные
    links_to_download = []
    links_skipped = []
    
    for url in links:
        video_id = extract_video_id(url)
        if video_id and check_video_exists(video_dir, video_id):
            links_skipped.append(url)
        else:
            links_to_download.append(url)
    
    if links_skipped:
        print(f"⏭️  Пропущено (уже скачаны): {len(links_skipped)}")
    
    if not links_to_download:
        print("\n✅ Все видео уже скачаны! Нечего обрабатывать.")
        return
    
    print(f"📊 Будет скачано новых роликов: {len(links_to_download)}")
    
    # Скачиваем видео
    print(f"\n=== СКАЧИВАНИЕ ВИДЕО ===")
    successful = 0
    failed = 0
    converted = 0
    error_rows = []
    
    for idx, url in enumerate(links_to_download, 1):
        print(f"\n[{idx}/{len(links_to_download)}] Обработка: {url}")
        
        if download_video(url, video_dir, cookies_file, pull_vids_dir, convert_to_mp4_flag=convert_enabled):
            print(f"  ✅ Успешно обработано")
            successful += 1
            if convert_enabled:
                converted += 1
        else:
            print(f"  ❌ Не удалось скачать")
            failed += 1
            error_rows.append(url)
    
    # Итоги
    print(f"\n=== РЕЗУЛЬТАТЫ ===")
    print(f"Всего ссылок в списке: {len(links)}")
    if links_skipped:
        print(f"Пропущено (уже скачаны): {len(links_skipped)}")
    print(f"Успешно скачано новых: {successful}")
    if convert_enabled and converted > 0:
        print(f"Сконвертировано в MP4: {converted}")
    if failed > 0:
        print(f"Ошибок: {failed}")
    print(f"Обработано: {len(links_to_download)}")
    print(f"\n📁 Все видео сохранены в: {video_dir}")

    if error_rows:
        error_path = os.path.join(video_dir, "download_errors.txt")
        with open(error_path, "w", encoding="utf-8") as f:
            for idx, url in enumerate(error_rows, 1):
                f.write(f"[{idx}] {url}\n")
    
    # Финальная статистика
    total_videos = get_existing_videos_count(video_dir)
    print(f"📦 Всего видео в директории: {total_videos}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] Операция отменена пользователем.")
        sys.exit(1)
