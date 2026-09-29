#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VALIDATE OSJD RAILWAY STATION DATABASE

Проверяет data/stations.json после работы update_stations.py.

Проверяется:

1. Файл stations.json существует.
2. JSON корректный.
3. Корень JSON является списком.
4. База не пустая.
5. Все записи являются объектами.
6. Есть обязательные поля:
   - name
   - code
   - country
   - country_code
   - latin_name
7. Код станции состоит ровно из 6 цифр.
8. country_code является допустимым.
9. country соответствует country_code.
10. В базе нет исключённых стран:
    IR - Иран
    CN - Китай
    CZ - Чехия
    KR - Республика Корея
    RO - Румыния
    LA - Лаос
11. Для каждой рабочей страны есть хотя бы одна станция.
12. Нет дублей по паре:
    country_code + code
13. Названия станций не пустые.
14. Названия не выглядят как технический мусор.
15. latin_name не пустой.
16. Дополнительное поле operations, если присутствует,
    должно быть строкой.
17. Дополнительное поле border_code, если присутствует,
    должно быть строкой.

При успешной проверке:
    exit code = 0

При ошибке:
    exit code = 1
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
INPUT_FILE = DATA_DIR / "stations.json"


# ============================================================
# ALL OSJD COUNTRIES
# ============================================================

COUNTRIES = {
    "AZ": "Азербайджан",
    "AF": "Афганистан",
    "BY": "Беларусь",
    "BG": "Болгария",
    "HU": "Венгрия",
    "VN": "Вьетнам",
    "GE": "Грузия",
    "IR": "Иран",
    "KZ": "Казахстан",
    "CN": "Китай",
    "KP": "КНДР",
    "KG": "Кыргызстан",
    "KR": "Республика Корея",
    "LA": "Лаос",
    "LV": "Латвия",
    "LT": "Литва",
    "MD": "Молдова",
    "MN": "Монголия",
    "PL": "Польша",
    "RU": "Россия",
    "RO": "Румыния",
    "SK": "Словакия",
    "TJ": "Таджикистан",
    "TM": "Туркменистан",
    "UZ": "Узбекистан",
    "UA": "Украина",
    "CZ": "Чехия",
    "EE": "Эстония",
}


# ============================================================
# EXCLUDED COUNTRIES
# ============================================================

EXCLUDED_COUNTRIES = {
    "IR",
    "CN",
    "CZ",
    "KR",
    "RO",
    "LA",
}


# ============================================================
# ACTIVE COUNTRIES
# ============================================================

ACTIVE_COUNTRIES = {
    code: country
    for code, country in COUNTRIES.items()
    if code not in EXCLUDED_COUNTRIES
}


# ============================================================
# REQUIRED FIELDS
# ============================================================

REQUIRED_FIELDS = {
    "name",
    "code",
    "country",
    "country_code",
    "latin_name",
}


# ============================================================
# HELPERS
# ============================================================

def normalize_space(value: Any) -> str:
    """
    Приводит строку к нормальному виду:
    убирает NBSP, лишние пробелы и переводы строк.
    """

    if value is None:
        return ""

    value = str(value)

    value = value.replace("\xa0", " ")
    value = value.replace("\u200b", "")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def is_valid_station_code(value: Any) -> bool:
    """
    Код станции должен состоять ровно из 6 цифр.
    """

    if value is None:
        return False

    value = str(value).strip()

    return bool(
        re.fullmatch(
            r"\d{6}",
            value,
        )
    )


def is_valid_station_name(value: Any) -> bool:
    """
    Проверка названия станции.
    """

    value = normalize_space(value)

    if not value:
        return False

    if len(value) < 2:
        return False

    if len(value) > 150:
        return False

    # В названии должна присутствовать хотя бы одна буква.
    if not re.search(
        r"[A-Za-zА-Яа-яЁё]",
        value,
    ):
        return False

    # Очевидный технический мусор.
    bad_fragments = [
        "наименование станции",
        "код станции",
        "код погранич",
        "производимые коммерческие",
        "коммерческие операции",
        "операции",
        "страница",
        "содержание",
        "перечень грузовых станций",
        "наименование",
        "название станции",
    ]

    lower = value.lower()

    for fragment in bad_fragments:
        if fragment in lower:
            return False

    # Только цифры и знаки пунктуации — не название.
    if re.fullmatch(
        r"[\d\s.,;:/()\-]+",
        value,
    ):
        return False

    return True


def is_valid_latin_name(value: Any) -> bool:
    """
    Проверяет latin_name.

    На практике текущий parser может использовать
    русское название как fallback, поэтому здесь
    не требуем исключительно латиницу.
    """

    value = normalize_space(value)

    if not value:
        return False

    if len(value) < 2:
        return False

    if len(value) > 150:
        return False

    if not re.search(
        r"[A-Za-zА-Яа-яЁё]",
        value,
    ):
        return False

    return True


# ============================================================
# LOAD JSON
# ============================================================

def load_database() -> list[Any]:
    """
    Загружает stations.json.
    """

    print()
    print("=" * 70)
    print("LOADING STATIONS DATABASE")
    print("=" * 70)

    print()
    print("File:")
    print(INPUT_FILE)

    if not INPUT_FILE.exists():
        raise RuntimeError(
            f"Файл не найден: {INPUT_FILE}"
        )

    if not INPUT_FILE.is_file():
        raise RuntimeError(
            f"Путь существует, но это не файл: {INPUT_FILE}"
        )

    try:
        raw_text = INPUT_FILE.read_text(
            encoding="utf-8"
        )
    except Exception as exc:
        raise RuntimeError(
            f"Не удалось прочитать stations.json: {exc}"
        ) from exc

    if not raw_text.strip():
        raise RuntimeError(
            "stations.json пустой."
        )

    print(
        "File size:",
        len(raw_text),
        "bytes",
    )

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "stations.json содержит некорректный JSON.\n"
            f"Строка: {exc.lineno}\n"
            f"Колонка: {exc.colno}\n"
            f"Ошибка: {exc.msg}"
        ) from exc

    if not isinstance(data, list):
        raise RuntimeError(
            "Корень stations.json должен быть JSON-массивом."
        )

    if not data:
        raise RuntimeError(
            "stations.json содержит 0 записей."
        )

    print(
        "Records loaded:",
        len(data),
    )

    return data


# ============================================================
# STRUCTURE VALIDATION
# ============================================================

def validate_structure(
    stations: list[Any],
) -> None:
    """
    Проверяет общую структуру записей.
    """

    print()
    print("=" * 70)
    print("STRUCTURE VALIDATION")
    print("=" * 70)

    errors = []

    for index, station in enumerate(
        stations,
        start=1,
    ):
        if not isinstance(station, dict):
            errors.append(
                f"Запись #{index}: "
                "должна быть объектом JSON."
            )
            continue

        missing = sorted(
            REQUIRED_FIELDS
            - set(station.keys())
        )

        if missing:
            errors.append(
                f"Запись #{index}: "
                f"отсутствуют поля: "
                f"{', '.join(missing)}"
            )

    print(
        "Records checked:",
        len(stations),
    )

    print(
        "Structure errors:",
        len(errors),
    )

    if errors:
        print()

        for error in errors[:30]:
            print(
                "ERROR:",
                error,
            )

        if len(errors) > 30:
            print(
                f"... и ещё {len(errors) - 30} ошибок."
            )

        raise RuntimeError(
            "Ошибка структуры базы."
        )

    print(
        "✓ Structure validation passed"
    )


# ============================================================
# FIELD VALIDATION
# ============================================================

def validate_fields(
    stations: list[Any],
) -> None:
    """
    Проверяет поля каждой станции.
    """

    print()
    print("=" * 70)
    print("FIELD VALIDATION")
    print("=" * 70)

    errors = []

    for index, station in enumerate(
        stations,
        start=1,
    ):
        country_code = normalize_space(
            station.get(
                "country_code",
                "",
            )
        )

        country = normalize_space(
            station.get(
                "country",
                "",
            )
        )

        name = normalize_space(
            station.get(
                "name",
                "",
            )
        )

        code = normalize_space(
            station.get(
                "code",
                "",
            )
        )

        latin_name = normalize_space(
            station.get(
                "latin_name",
                "",
            )
        )

        # ----------------------------------------------------
        # COUNTRY CODE
        # ----------------------------------------------------

        if country_code not in COUNTRIES:
            errors.append(
                f"Запись #{index}: "
                f"неизвестный country_code="
                f"{country_code!r}"
            )

        # ----------------------------------------------------
        # EXCLUDED COUNTRY
        # ----------------------------------------------------

        if country_code in EXCLUDED_COUNTRIES:
            errors.append(
                f"Запись #{index}: "
                f"используется исключённая страна "
                f"{country_code}"
            )

        # ----------------------------------------------------
        # COUNTRY NAME
        # ----------------------------------------------------

        if country_code in COUNTRIES:

            expected_country = COUNTRIES[
                country_code
            ]

            if country != expected_country:
                errors.append(
                    f"Запись #{index}: "
                    f"country={country!r}, "
                    f"ожидалось "
                    f"{expected_country!r} "
                    f"для {country_code}"
                )

        # ----------------------------------------------------
        # STATION CODE
        # ----------------------------------------------------

        if not is_valid_station_code(code):
            errors.append(
                f"Запись #{index}: "
                f"некорректный код станции "
                f"{code!r}"
            )

        # ----------------------------------------------------
        # RUSSIAN / MAIN NAME
        # ----------------------------------------------------

        if not is_valid_station_name(name):
            errors.append(
                f"Запись #{index}: "
                f"некорректное название станции "
                f"{name!r}"
            )

        # ----------------------------------------------------
        # LATIN NAME
        # ----------------------------------------------------

        if not is_valid_latin_name(
            latin_name
        ):
            errors.append(
                f"Запись #{index}: "
                f"некорректное latin_name "
                f"{latin_name!r}"
            )

        # ----------------------------------------------------
        # OPTIONAL FIELDS
        # ----------------------------------------------------

        if (
            "operations" in station
            and station["operations"] is not None
            and not isinstance(
                station["operations"],
                str,
            )
        ):
            errors.append(
                f"Запись #{index}: "
                "поле operations должно быть строкой."
            )

        if (
            "border_code" in station
            and station["border_code"] is not None
            and not isinstance(
                station["border_code"],
                str,
            )
        ):
            errors.append(
                f"Запись #{index}: "
                "поле border_code должно быть строкой."
            )

    print(
        "Field errors:",
        len(errors),
    )

    if errors:
        print()

        for error in errors[:50]:
            print(
                "ERROR:",
                error,
            )

        if len(errors) > 50:
            print(
                f"... и ещё {len(errors) - 50} ошибок."
            )

        raise RuntimeError(
            "Обнаружены ошибки в полях станций."
        )

    print(
        "✓ Field validation passed"
    )


# ============================================================
# COUNTRY VALIDATION
# ============================================================

def validate_countries(
    stations: list[Any],
) -> Counter:
    """
    Проверяет состав стран и количество станций
    по каждой стране.
    """

    print()
    print("=" * 70)
    print("COUNTRY VALIDATION")
    print("=" * 70)

    counters = Counter(
        normalize_space(
            station.get(
                "country_code",
                "",
            )
        )
        for station in stations
    )

    print()

    for code, country in ACTIVE_COUNTRIES.items():

        count = counters.get(
            code,
            0,
        )

        if count > 0:
            print(
                f"✓ {code:2} "
                f"{country:<25} "
                f"{count:6} stations"
            )
        else:
            print(
                f"✗ {code:2} "
                f"{country:<25} "
                f"{0:6} stations"
            )

    print()

    missing = [
        code
        for code in ACTIVE_COUNTRIES
        if counters.get(
            code,
            0,
        ) == 0
    ]

    if missing:
        raise RuntimeError(
            "В базе отсутствуют рабочие страны: "
            + ", ".join(missing)
        )

    # --------------------------------------------------------
    # UNKNOWN COUNTRIES
    # --------------------------------------------------------

    unknown = sorted(
        set(counters)
        - set(COUNTRIES)
    )

    if unknown:
        raise RuntimeError(
            "В базе обнаружены неизвестные "
            "country_code: "
            + ", ".join(unknown)
        )

    # --------------------------------------------------------
    # EXCLUDED COUNTRIES
    # --------------------------------------------------------

    excluded_found = sorted(
        set(counters)
        & EXCLUDED_COUNTRIES
    )

    if excluded_found:
        raise RuntimeError(
            "В базе обнаружены исключённые страны: "
            + ", ".join(excluded_found)
        )

    print(
        "Active countries:",
        len(ACTIVE_COUNTRIES),
    )

    print(
        "Excluded countries:",
        len(EXCLUDED_COUNTRIES),
    )

    print(
        "✓ Country validation passed"
    )

    return counters


# ============================================================
# DUPLICATE VALIDATION
# ============================================================

def validate_duplicates(
    stations: list[Any],
) -> None:
    """
    Проверяет дубли станций.

    Уникальный ключ:
        country_code + code
    """

    print()
    print("=" * 70)
    print("DUPLICATE VALIDATION")
    print("=" * 70)

    seen = set()
    duplicates = []

    for index, station in enumerate(
        stations,
        start=1,
    ):
        country_code = normalize_space(
            station.get(
                "country_code",
                "",
            )
        )

        code = normalize_space(
            station.get(
                "code",
                "",
            )
        )

        key = (
            country_code,
            code,
        )

        if key in seen:
            duplicates.append(
                {
                    "index": index,
                    "country_code": country_code,
                    "code": code,
                    "name": station.get(
                        "name",
                        "",
                    ),
                }
            )

        seen.add(key)

    print(
        "Duplicate records:",
        len(duplicates),
    )

    if duplicates:

        print()

        for duplicate in duplicates[:50]:
            print(
                "DUPLICATE:",
                duplicate["country_code"],
                duplicate["code"],
                "-",
                duplicate["name"],
                f"(record #{duplicate['index']})",
            )

        if len(duplicates) > 50:
            print(
                f"... и ещё "
                f"{len(duplicates) - 50} дублей."
            )

        raise RuntimeError(
            "Обнаружены дубли станций."
        )

    print(
        "✓ Duplicate validation passed"
    )


# ============================================================
# NAME DUPLICATE INFORMATION
# ============================================================

def print_name_statistics(
    stations: list[Any],
) -> None:
    """
    Информационная статистика по названиям.

    Одинаковые названия станций НЕ считаются ошибкой,
    поскольку в разных странах и даже внутри одной
    железнодорожной системы они могут встречаться.
    """

    print()
    print("=" * 70)
    print("NAME STATISTICS")
    print("=" * 70)

    names = Counter(
        normalize_space(
            station.get(
                "name",
                "",
            )
        ).lower()
        for station in stations
    )

    repeated = [
        (
            name,
            count,
        )
        for name, count in names.items()
        if count > 1
    ]

    repeated.sort(
        key=lambda item: (
            -item[1],
            item[0],
        )
    )

    print(
        "Unique station names:",
        len(names),
    )

    print(
        "Repeated names:",
        len(repeated),
    )

    if repeated:
        print()
        print(
            "Top repeated names:"
        )

        for name, count in repeated[:20]:
            print(
                f"  {count:4} × {name}"
            )


# ============================================================
# CODE STATISTICS
# ============================================================

def print_code_statistics(
    stations: list[Any],
) -> None:
    """
    Показывает статистику кодов.
    """

    print()
    print("=" * 70)
    print("CODE STATISTICS")
    print("=" * 70)

    codes = [
        normalize_space(
            station.get(
                "code",
                "",
            )
        )
        for station in stations
    ]

    six_digit = sum(
        1
        for code in codes
        if re.fullmatch(
            r"\d{6}",
            code,
        )
    )

    print(
        "Total codes:",
        len(codes),
    )

    print(
        "6-digit valid codes:",
        six_digit,
    )

    print(
        "Invalid codes:",
        len(codes) - six_digit,
    )


# ============================================================
# FINAL REPORT
# ============================================================

def print_final_report(
    stations: list[Any],
    counters: Counter,
) -> None:
    """
    Финальный красивый отчёт.
    """

    print()
    print("=" * 70)
    print("FINAL VALIDATION REPORT")
    print("=" * 70)

    print()

    print(
        "Total stations:",
        len(stations),
    )

    print(
        "Countries in database:",
        len(counters),
    )

    print(
        "Expected active countries:",
        len(ACTIVE_COUNTRIES),
    )

    print(
        "Excluded countries:",
        ", ".join(
            sorted(
                EXCLUDED_COUNTRIES
            )
        ),
    )

    print()

    print(
        "Stations by country:"
    )

    for code, country in ACTIVE_COUNTRIES.items():

        count = counters.get(
            code,
            0,
        )

        print(
            f"  {code:2} "
            f"{country:<25} "
            f"{count:6}"
        )


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    print()
    print("=" * 70)
    print("OSJD STATIONS DATABASE VALIDATOR")
    print("=" * 70)

    print()
    print(
        "Repository:",
        BASE_DIR,
    )

    print(
        "Input:",
        INPUT_FILE,
    )

    print()
    print(
        "Active countries:",
        len(ACTIVE_COUNTRIES),
    )

    print(
        "Excluded:",
        ", ".join(
            sorted(
                EXCLUDED_COUNTRIES
            )
        ),
    )

    try:

        # ----------------------------------------------------
        # LOAD
        # ----------------------------------------------------

        stations = load_database()

        # ----------------------------------------------------
        # STRUCTURE
        # ----------------------------------------------------

        validate_structure(
            stations
        )

        # ----------------------------------------------------
        # FIELDS
        # ----------------------------------------------------

        validate_fields(
            stations
        )

        # ----------------------------------------------------
        # COUNTRIES
        # ----------------------------------------------------

        counters = validate_countries(
            stations
        )

        # ----------------------------------------------------
        # DUPLICATES
        # ----------------------------------------------------

        validate_duplicates(
            stations
        )

        # ----------------------------------------------------
        # STATISTICS
        # ----------------------------------------------------

        print_code_statistics(
            stations
        )

        print_name_statistics(
            stations
        )

        # ----------------------------------------------------
        # FINAL REPORT
        # ----------------------------------------------------

        print_final_report(
            stations,
            counters,
        )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("✓✓✓ VALIDATION SUCCESS ✓✓✓")
        print("=" * 70)

        print()
        print(
            "stations.json прошёл все проверки."
        )

        print(
            "База готова для использования."
        )

        print()

        return 0

    except Exception as exc:

        print()
        print("=" * 70)
        print("✗✗✗ VALIDATION FAILED ✗✗✗")
        print("=" * 70)

        print()
        print(
            "ERROR:",
            str(exc),
        )

        print()

        return 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(
        main()
    )
