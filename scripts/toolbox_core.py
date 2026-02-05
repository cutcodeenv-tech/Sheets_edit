from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional
import sys


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
PYTHON = sys.executable or "python3"


@dataclass
class ScriptField:
    key: str
    label: str
    field_type: str = "text"  # text, file, dir, int, float, bool, choice
    default: str = ""
    required: bool = False
    dialog_type: Optional[str] = None  # "file" | "dir"
    help_text: str = ""
    options: Optional[List[str]] = None


@dataclass
class ScriptConfig:
    key: str
    title: str
    description: str
    script_path: Path
    fields: List[ScriptField]
    args_builder: Callable[[Dict[str, str]], List[str]] = field(
        default=lambda values: []
    )
    stdin_builder: Callable[[Dict[str, str]], Optional[str]] = field(
        default=lambda values: None
    )


def newline_payload(responses: List[str]) -> str:
    return "\n".join(responses) + "\n"


def placeholders_stdin(values: Dict[str, str]) -> str:
    sheet = values.get("sheet_link", "").strip()
    need_xml = values.get("need_xml", "1") == "1"

    responses = [sheet, "y" if need_xml else "n"]

    if need_xml:
        column = (values.get("search_column") or "A").strip().upper() or "A"
        fps = values.get("fps", "25").strip() or "25"
        threshold = values.get("threshold", "70").strip() or "70"
        transcript = values.get("transcript_path", "").strip()
        if not transcript:
            raise ValueError("Укажите путь к JSON-расшифровке для XML.")
        responses.extend([column, fps, threshold, transcript])

    return newline_payload(responses)


def broll_stdin(values: Dict[str, str]) -> str:
    sheet = values.get("sheet_link", "").strip()
    src_col = (values.get("source_column") or "A").strip().upper() or "A"
    dst_col = (values.get("target_column") or "D").strip().upper() or "D"
    start_row = values.get("start_row", "2").strip() or "2"
    ideas_count = values.get("ideas_count", "7").strip() or "7"
    temperature = values.get("temperature", "0.9").strip() or "0.9"
    overwrite = "y" if values.get("overwrite", "1") == "1" else "n"
    dash_if_empty = "y" if values.get("dash_if_empty", "1") == "1" else "n"
    batch_size = values.get("batch_size", "1").strip() or "1"

    responses = [
        sheet,
        src_col,
        dst_col,
        start_row,
        ideas_count,
        temperature,
        overwrite,
        dash_if_empty,
        batch_size,
    ]
    return newline_payload(responses)


def link_router_stdin(values: Dict[str, str]) -> str:
    sheet = values.get("sheet_link", "").strip()

    responses = [sheet]
    return newline_payload(responses)


def title_enricher_stdin(values: Dict[str, str]) -> str:
    sheet = values.get("sheet_link", "").strip()

    batch_size = values.get("batch_size", "150").strip() or "150"
    max_runtime = values.get("max_runtime", "330").strip() or "330"
    sleep_seconds = values.get("sleep_seconds", "0.12").strip() or "0.12"
    force_refresh = "y" if values.get("force_refresh", "0") == "1" else "n"
    log_to_sheet = "y" if values.get("log_to_sheet", "1") == "1" else "n"
    log_sheet_name = values.get("log_sheet_name", "Log").strip() or "Log"
    use_cache = "y" if values.get("use_cache", "1") == "1" else "n"
    cache_sheet_name = values.get("cache_sheet_name", "Cache_Titles").strip() or "Cache_Titles"
    url_header = values.get("url_header", "URL").strip() or "URL"
    write_column = values.get("write_column", "D").strip() or "D"
    write_header = values.get("write_header", "Result_D").strip() or "Result_D"

    responses = [
        sheet,
        batch_size,
        max_runtime,
        sleep_seconds,
        force_refresh,
        log_to_sheet,
        log_sheet_name,
        use_cache,
        cache_sheet_name,
        url_header,
        write_column,
        write_header,
    ]
    return newline_payload(responses)


def download_img_stdin(values: Dict[str, str]) -> str:
    sheet = values.get("sheet_link", "").strip()
    out_dir = values.get("output_dir", "").strip()
    responses = [sheet, out_dir]
    return newline_payload(responses)


def motionarray_stdin(values: Dict[str, str]) -> str:
    sheet = values.get("sheet_link", "").strip()
    browser = (values.get("browser") or "comet").strip().lower() or "comet"
    first_click = values.get("download_point", "1568,702").strip() or "1568,702"
    second_click = values.get("hd_point", "1504,800").strip() or "1504,800"
    delay_before = values.get("delay_before_clicks", "5.0").strip() or "5.0"
    delay_between = values.get("delay_between_clicks", "5.0").strip() or "5.0"
    wait_dialog = values.get("delay_before_dialog", "5.0").strip() or "5.0"
    delay_between_paste = values.get("delay_between_paste", "5.0").strip() or "5.0"
    delay_after_enter = values.get("delay_after_enter", "5.0").strip() or "5.0"
    download_label = values.get("download_label", "Download").strip() or "Download"
    hd_label = values.get("hd_label", "HD").strip() or "HD"
    download_terms = values.get("download_terms", download_label).strip() or download_label
    hd_terms = values.get("hd_terms", "HD,Original").strip() or "HD,Original"
    fallback = "y" if values.get("use_fallback", "1") == "1" else "n"


    responses = [
        sheet,
        browser,
        first_click,
        second_click,
        delay_before,
        delay_between,
        wait_dialog,
        delay_between_paste,
        delay_after_enter,
        download_label,
        hd_label,
        download_terms,
        hd_terms,
        fallback,
    ]
    return newline_payload(responses)


def rename_stdin(values: Dict[str, str]) -> str:
    folder = values.get("folder", "").strip()
    sheet = values.get("sheet_link", "").strip()
    threshold = values.get("match_threshold", "").strip()

    responses = [sheet, folder, threshold]
    return newline_payload(responses)


def still_links_args(values: Dict[str, str]) -> List[str]:
    input_path = values.get("input_path", "").strip()
    if not input_path:
        raise ValueError("Выберите файл со списком ссылок.")

    out_dir = values.get("output_dir", "").strip() or str(
        Path.home() / "Downloads" / "download_all" / "os_ya" / "5_stiils_links"
    )
    width = values.get("width", "1600").strip() or "1600"
    height = values.get("height", "1000").strip() or "1000"
    wait_until = values.get("wait_until", "networkidle").strip() or "networkidle"
    delay = values.get("delay", "250").strip() or "250"
    concurrency = values.get("concurrency", "4").strip() or "4"
    timeout = values.get("timeout", "45000").strip() or "45000"

    return [
        "--input",
        input_path,
        "--outdir",
        out_dir,
        "--width",
        width,
        "--height",
        height,
        "--wait-until",
        wait_until,
        "--delay",
        delay,
        "--concurrency",
        concurrency,
        "--timeout",
        timeout,
    ]


SCRIPTS: List[ScriptConfig] = [
    ScriptConfig(
        key="placeholders",
        title="1.1 XML Placeholders",
        description="Плейсхолдеры JPG + (опционально) XML для Premiere.",
        script_path=BASE_DIR / "1.1_xml_placeholders.py",
        fields=[
            ScriptField("sheet_link", "Ссылка/ID Google Sheets:", required=False),
            ScriptField(
                "need_xml",
                "Собрать XML под Premiere",
                field_type="bool",
                default="1",
            ),
            ScriptField(
                "search_column",
                "Колонка с текстом (A/B/C):",
                default="A",
                help_text="Используется для XML.",
            ),
            ScriptField(
                "fps",
                "FPS секвенции:",
                default="25",
                help_text="Для XML.",
            ),
            ScriptField(
                "threshold",
                "Порог совпадения (0-100):",
                default="70",
                help_text="Для XML сопоставления текста.",
            ),
            ScriptField(
                "transcript_path",
                "JSON расшифровка:",
                field_type="file",
                help_text="Нужен только если строим XML.",
            ),
        ],
        stdin_builder=placeholders_stdin,
    ),
    ScriptConfig(
        key="broll",
        title="1.2 B-Roll Ideas",
        description="Генерация идей перекрытий через DeepSeek и запись в таблицу.",
        script_path=BASE_DIR / "1.2_B-Roll.py",
        fields=[
            ScriptField("sheet_link", "Ссылка/ID Google Sheets:", required=False),
            ScriptField("source_column", "Столбец с текстом:", default="A"),
            ScriptField("target_column", "Столбец для идей:", default="D"),
            ScriptField("start_row", "Стартовая строка:", default="2"),
            ScriptField("ideas_count", "Идей на строку:", default="7"),
            ScriptField("temperature", "Температура (0.0–1.2):", default="0.9"),
            ScriptField(
                "overwrite",
                "Перезаписывать существующие значения",
                field_type="bool",
                default="1",
            ),
            ScriptField(
                "dash_if_empty",
                "Если идей нет — ставить «—»",
                field_type="bool",
                default="1",
            ),
            ScriptField("batch_size", "Размер блока записи:", default="1"),
        ],
        stdin_builder=broll_stdin,
    ),
    ScriptConfig(
        key="link_router",
        title="1.3 Link Router",
        description="Разбирает ссылки с листа и раскладывает по 4 вкладкам (YT/IG, Images, Footages, Other).",
        script_path=BASE_DIR / "1.3_link_router.py",
        fields=[
            ScriptField("sheet_link", "Ссылка/ID Google Sheets:", required=False),
        ],
        stdin_builder=link_router_stdin,
    ),
    ScriptConfig(
        key="title_enricher",
        title="1.4 Title Enricher",
        description="Парсит заголовки страниц и пишет их в столбец D выбранного листа с кешом и логом.",
        script_path=BASE_DIR / "1.4_title_enricher.py",
        fields=[
            ScriptField("sheet_link", "Ссылка/ID Google Sheets:", required=False),
            ScriptField("batch_size", "Размер партии:", field_type="int", default="150"),
            ScriptField(
                "max_runtime",
                "Макс. время работы (сек):",
                field_type="int",
                default="330",
            ),
            ScriptField(
                "sleep_seconds",
                "Пауза между запросами (сек):",
                default="0.12",
            ),
            ScriptField(
                "force_refresh",
                "Перезаписывать уже заполненные значения",
                field_type="bool",
                default="0",
            ),
            ScriptField(
                "log_to_sheet",
                "Вести лог в отдельном листе",
                field_type="bool",
                default="1",
            ),
            ScriptField("log_sheet_name", "Имя лог-листа:", default="Log"),
            ScriptField(
                "use_cache",
                "Использовать кеш в листе",
                field_type="bool",
                default="1",
            ),
            ScriptField("cache_sheet_name", "Имя листа для кеша:", default="Cache_Titles"),
            ScriptField("url_header", "Заголовок колонки URL:", default="URL"),
            ScriptField("write_column", "Столбец для записи:", default="D"),
            ScriptField("write_header", "Заголовок результата:", default="Result_D"),
        ],
        stdin_builder=title_enricher_stdin,
    ),
    ScriptConfig(
        key="download_img",
        title="2. Download Images",
        description="Скачивает картинки по ссылкам из Google Sheets.",
        script_path=BASE_DIR / "2_download_img.py",
        fields=[
            ScriptField("sheet_link", "Ссылка/ID Google Sheets:", required=False),
            ScriptField(
                "output_dir",
                "Папка для сохранения:",
                field_type="dir",
                default=str(
                    Path.home() / "Downloads" / "download_all" / "01_pulltube"
                ),
                required=False,
            ),
        ],
        stdin_builder=download_img_stdin,
    ),
    ScriptConfig(
        key="motionarray",
        title="3.2 MotionArray Save",
        description="Автоклики через cliclick + обновление статусов в таблице.",
        script_path=BASE_DIR / "3.2_motionarray_save.py",
        fields=[
            ScriptField("sheet_link", "Ссылка/ID Google Sheets:", required=False),
            ScriptField("browser", "Браузер (comet/safari):", default="comet"),
            ScriptField(
                "download_point",
                "Координаты кнопки Download (x,y):",
                default="1568,702",
            ),
            ScriptField(
                "hd_point",
                "Координаты кнопки HD (x,y):",
                default="1504,800",
            ),
            ScriptField(
                "delay_before_clicks",
                "Задержка после открытия (сек):",
                default="5.0",
            ),
            ScriptField(
                "delay_between_clicks",
                "Пауза между Download и HD (сек):",
                default="5.0",
            ),
            ScriptField(
                "delay_before_dialog",
                "Ожидание диалога сохранения (сек):",
                default="5.0",
            ),
            ScriptField(
                "delay_between_paste",
                "Пауза между вставкой имени и Enter (сек):",
                default="5.0",
            ),
            ScriptField(
                "delay_after_enter",
                "Пауза после Enter (сек):",
                default="5.0",
            ),
            ScriptField(
                "download_label",
                "Название кнопки Download для логов:",
                default="Download",
            ),
            ScriptField("hd_label", "Название кнопки HD для логов:", default="HD"),
            ScriptField(
                "download_terms",
                "Варианты текста/атрибутов Download:",
                default="Download",
                help_text="Через запятую; используется при поиске кнопки.",
            ),
            ScriptField(
                "hd_terms",
                "Варианты текста/атрибутов HD:",
                default="HD,Original",
            ),
            ScriptField(
                "use_fallback",
                "Использовать координаты, если DOM не нашёл кнопки",
                field_type="bool",
                default="1",
            ),
        ],
        stdin_builder=motionarray_stdin,
    ),
    ScriptConfig(
        key="rename",
        title="4. Rename Files",
        description="Переименовывает скачанные файлы по таблице 1_PullTube.",
        script_path=BASE_DIR / "4_Change_name.py",
        fields=[
            ScriptField(
                "folder",
                "Папка с файлами:",
                field_type="dir",
                required=False,
            ),
            ScriptField("sheet_link", "Ссылка/ID Google Sheets:", required=False),
            ScriptField(
                "match_threshold",
                "Порог совпадения (0-100, Enter = по умолчанию):",
                help_text="Оставьте пустым, чтобы использовать встроенное значение.",
            ),
        ],
        stdin_builder=rename_stdin,
    ),
    ScriptConfig(
        key="still_links",
        title="5. Still Links",
        description="Playwright: делает скриншоты сайтов по списку ссылок.",
        script_path=BASE_DIR / "5_Still_links.py",
        fields=[
            ScriptField(
                "input_path",
                "Текстовый файл со ссылками:",
                field_type="file",
                required=True,
            ),
            ScriptField(
                "output_dir",
                "Папка для скриншотов:",
                field_type="dir",
                default=str(
                    Path.home() / "Downloads" / "download_all" / "os_ya" / "5_stiils_links"
                ),
            ),
            ScriptField("width", "Ширина вьюпорта:", field_type="int", default="1600"),
            ScriptField(
                "height",
                "Высота вьюпорта:",
                field_type="int",
                default="1000",
            ),
            ScriptField(
                "wait_until",
                "Ожидание загрузки:",
                field_type="choice",
                default="networkidle",
                options=["load", "domcontentloaded", "networkidle", "commit"],
            ),
            ScriptField("delay", "Задержка перед скрином (мс):", field_type="int", default="250"),
            ScriptField("concurrency", "Параллельных вкладок:", field_type="int", default="4"),
            ScriptField("timeout", "Таймаут загрузки (мс):", field_type="int", default="45000"),
        ],
        args_builder=still_links_args,
    ),
]


__all__ = [
    "ScriptField",
    "ScriptConfig",
    "SCRIPTS",
    "BASE_DIR",
    "PROJECT_ROOT",
    "PYTHON",
    "newline_payload",
]
