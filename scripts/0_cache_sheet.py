#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Однократное создание локального кэша CSV из Google Sheets.
После этого все скрипты работают только с 01_data и не обращаются в интернет.
"""

from sheet_cache import prompt_remote_cache


def main() -> None:
    print("=== Создание локального кэша CSV ===")
    project = prompt_remote_cache()
    print(f"✓ Кэш создан: {project.root_dir}")
    print(f"✓ CSV: {project.data_dir}")


if __name__ == "__main__":
    main()
