from __future__ import annotations

# Simple config describing the wizard steps, input fields, and prompt patterns.
# Patterns are regexes matched against script stdout to decide when to send input.

STEPS = [
    {
        "id": "0_structure",
        "title": "Создание структуры проекта",
        "script": "scripts/0_structure.py",
        "description": "Создает структуру папок проекта.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "1_parse_links",
        "title": "Парсинг ссылок из Google таблицы",
        "script": "scripts/1_parse_links.py",
        "description": "Тянет ссылки из Google Sheets и сохраняет CSV.",
        "fields": [
            {
                "key": "spreadsheet_url",
                "label": "Ссылка на Google таблицу",
                "type": "url",
                "placeholder": "https://docs.google.com/spreadsheets/d/...",
                "help": "Таблица должна быть расшарена на сервисный email.",
                "required": True,
                "persist": True,
            },
            {
                "key": "worksheet_title",
                "label": "Название листа (если потребуется)",
                "type": "text",
                "placeholder": "Лист1",
                "help": "Заполните, если скрипт не сможет выбрать лист автоматически.",
                "required": False,
                "persist": True,
            },
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите ссылку на Google таблицу",
                "field": "spreadsheet_url",
                "required": True,
            },
            {
                "pattern": r"Введите название листа из списка выше",
                "field": "worksheet_title",
                "required": True,
            },
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "1_1_title_enricher",
        "title": "Обогащение названий каналов",
        "script": "scripts/1.1_title_enricher.py",
        "description": "Определяет названия каналов YouTube и сохраняет CSV.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
            {
                "key": "sleep_seconds",
                "label": "Пауза между запросами (сек)",
                "type": "number",
                "placeholder": "0.250",
                "help": "Оставьте пустым, чтобы использовать значение по умолчанию.",
                "required": False,
                "persist": True,
                "step": "0.001",
                "min": "0",
            },
            {
                "key": "force_refresh",
                "label": "Перезаписывать уже обработанные ссылки",
                "type": "checkbox",
                "help": "Отметьте, если нужно перепарсить уже обработанные ссылки.",
                "required": False,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
            {
                "pattern": r"Пауза между запросами, сек",
                "field": "sleep_seconds",
                "required": False,
            },
            {
                "pattern": r"Перезаписывать уже обработанные ссылки\? \(y/n\) \[n\]",
                "field": "force_refresh",
                "required": False,
            },
        ],
    },
    {
        "id": "1_2_author",
        "title": "Генерация авторских плашек",
        "script": "scripts/1.2_author.py",
        "description": "Создает PNG с источником на основе каналов.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "1_2_xml_placeholders",
        "title": "XML-плейсхолдеры",
        "script": "scripts/1.2_xml_placeholders.py",
        "description": "Создает изображения плейсхолдеров для XML.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "2_download_img",
        "title": "Скачивание изображений",
        "script": "scripts/2_download_img.py",
        "description": "Скачивает изображения по ссылкам.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "2_1_smart_cropping",
        "title": "Smart-cropping",
        "script": "scripts/2.1_smart_cropping.py",
        "description": "Кадрирует изображения под нужный формат.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "3_2_pulltube",
        "title": "Pulltube (YouTube видео)",
        "script": "scripts/3.2_pulltube.py",
        "description": "Скачивает YouTube видео по ссылкам.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "3_3_motionarray",
        "title": "MotionArray (видео)",
        "script": "scripts/3.3_motionarray.py",
        "description": "Скачивает видео с MotionArray.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "3_4_pullvids_download",
        "title": "PullVids (другие видео)",
        "script": "scripts/3.4_pullvids_download.py",
        "description": "Скачивает видео с прочих источников.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "4_pulltube_rename",
        "title": "Переименование Pulltube файлов",
        "script": "scripts/4_pulltube_rename.py",
        "description": "Переименовывает скачанные YouTube видео.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "4_1_motionarray_rename",
        "title": "Переименование MotionArray файлов",
        "script": "scripts/4.1_motionarray_rename.py",
        "description": "Переименовывает скачанные файлы MotionArray.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "5_photo_placeholders",
        "title": "Фото-плейсхолдеры",
        "script": "scripts/5_photo_placeholders.py",
        "description": "Создает плейсхолдеры для фотографий.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "6_voiceover",
        "title": "Расшифровка озвучки",
        "script": "scripts/6_voiceover.py",
        "description": "Запускает Whisper и генерирует транскрипт.",
        "fields": [
            {
                "key": "overwrite_voiceover",
                "label": "Перезаписывать существующие файлы",
                "type": "checkbox",
                "help": "Если включено, перезапишет текущую расшифровку/YAML.",
                "required": False,
                "persist": True,
            },
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Перезаписать существующие файлы\? \(y/n\)",
                "field": "overwrite_voiceover",
                "required": False,
            },
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
    {
        "id": "7_screenshot_other_links",
        "title": "Скриншоты других ссылок",
        "script": "scripts/7_screenshot_other_links.py",
        "description": "Делает скриншоты из other_links.csv.",
        "fields": [
            {
                "key": "project_name",
                "label": "Название проекта",
                "type": "text",
                "placeholder": "osnovateli_doc_polonsky",
                "help": "Формат: osnovateli_doc_{name}",
                "required": True,
                "persist": True,
            },
        ],
        "prompts": [
            {
                "pattern": r"Введите название проекта",
                "field": "project_name",
                "required": True,
            },
        ],
    },
]
