
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VALIDATE OSJD RAILWAY STATION DATABASE

Проверяет data/stations.json после работы update_stations.py.

Проверки:
1. Файл существует, доступен для чтения и содержит корректный JSON.
2. Корень JSON — непустой список.
3. Все записи являются объектами с обязательными полями.
4. Код станции состоит ровно из 6 цифр.
5. Страна соответствует country_code.
6. Исключённые страны отсутствуют.
7. Каждая из 22 рабочих стран представлена в базе.
8. Нет дублей по паре country_code + code.
9. Названия станций не пустые и не похожи на технический мусор.
10. latin_name не пустой.
11. Дополнительные поля operations и border_code имеют
    допустимый тип, если присутствуют.

Файл ничего не изменяет в stations.json.

При успехе: exit code 0.
При ошибке: exit code 1.
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
INPUT_FILE = BASE_DIR / "data" / "stations.json"


# ============================================================
# OSJD COUNTRIES
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


EXCLUDED_COUNTRIES = {
    "IR", "CN", "CZ", "KR", "RO", "LA",
}


ACTIVE_COUNTRIES = {
    code: name
    for code, name in COUNTRIES.items()
    if code not in EXCLUDED_COUNTRIES
}


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
    """Нормализует пробелы и управляющие пробельные символы."""
    if value is None:
        return ""

    value = str(value)
    value = value.replace("\xa0", " ")
    value = value.replace("\u200b", "")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def is_valid_station_code(value: Any) -> bool:
    """
    Код хранится в строковом виде, чтобы не терять ведущие нули.
    Допустимы ровно 6 цифр.
    """
    return (
        isinstance(value, str)
        and bool(re.fullmatch(r"\d{6}", value.strip()))
    )


def looks_like_technical_name(value: str) -> bool:
    """Выявляет некоторые характерные ошибки извлечения из PDF."""
    lower = value.casefold()

    bad_fragments = (
        "наименование станции",
        "код станции",
        "код погранич",
        "производимые коммерческие",
        "коммерческие операции",
        "перечень грузовых станций",
        "название станции",
        "наименование",
        "страница",
        "содержание",
        "таблица",
        "примечание",
    )

    if any(fragment in lower for fragment in bad_fragments):
        return True

    # Примеры мусора: 3,8н,10н; 12,14,16.
    # Не блокируем обычные названия, содержащие цифры,
    # например "1 Мая" или "5-й километр".
    if re.fullmatch(
        r"\d+(?:[.,]\d+)*(?:[А-Яа-яЁё]{1,3})?"
        r"(?:,\d+(?:[.,]\d+)*(?:[А-Яа-яЁё]{1,3})?)+",
        value,
    ):
        return True

    # Длинная последовательность цифр и знаков без букв.
    if re.fullmatch(r"[\d\s.,;:/()\-]+", value):
        return True

    return False


def is_valid_station_name(value: Any) -> bool:
    """Проверяет основное название станции."""
    if not isinstance(value, str):
        return False

    value = normalize_space(value)

    if not value or len(value) < 2 or len(value) > 150:
        return False

    if not re.search(r"[A-Za-zА-Яа-яЁё]", value):
        return False

    if looks_like_technical_name(value):
        return False

    return True


def is_valid_latin_name(value: Any) -> bool:
    """
    Проверяет наличие пригодного отображаемого названия.
    Латиница не обязательна: парсер может использовать fallback.
    """
    if not isinstance(value, str):
        return False

    value = normalize_space(value)

    if not value or len(value) < 2 or len(value) > 150:
        return False

    if not re.search(r"[A-Za-zА-Яа-яЁё]", value):
        return False

    if looks_like_technical_name(value):
        return False

    return True


def show_errors(errors: list[str], limit: int = 50) -> None:
    """Выводит ограниченное число ошибок, сохраняя общее количество."""
    for error in errors[:limit]:
        print(f"ERROR: {error}")

    if len(errors) > limit:
        print(f"... и ещё {len(errors) - limit} ошибок.")


# ============================================================
# LOAD DATABASE
# ============================================================

def load_database() -> list[Any]:
    print("\n" + "=" * 70)
    print("LOADING STATIONS DATABASE")
    print("=" * 70)
    print(f"File: {INPUT_FILE}")

    if not INPUT_FILE.exists():
        raise RuntimeError(f"Файл не найден: {INPUT_FILE}")

    if not INPUT_FILE.is_file():
        raise RuntimeError(f"Это не файл: {INPUT_FILE}")

    try:
        raw_text = INPUT_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(
            f"Не удалось прочитать stations.json: {exc}"
        ) from exc

    if not raw_text.strip():
        raise RuntimeError("stations.json пуст.")

    print(f"File size: {len(raw_text)} bytes")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Некорректный JSON: "
            f"строка {exc.lineno}, колонка {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, list):
        raise RuntimeError("Корень JSON должен быть списком.")

    if not data:
        raise RuntimeError("В базе нет записей.")

    print(f"Records loaded: {len(data)}")

    return data


# ============================================================
# STRUCTURE VALIDATION
# ============================================================

def validate_structure(stations: list[Any]) -> None:
    print("\n" + "=" * 70)
    print("STRUCTURE VALIDATION")
    print("=" * 70)

    errors = []

    for index, station in enumerate(stations, start=1):
        if not isinstance(station, dict):
            errors.append(
                f"Запись #{index}: ожидался объект JSON."
            )
            continue

        missing = REQUIRED_FIELDS - set(station.keys())

        if missing:
            errors.append(
                f"Запись #{index}: отсутствуют поля: "
                + ", ".join(sorted(missing))
            )

    print(f"Records checked: {len(stations)}")
    print(f"Structure errors: {len(errors)}")

    if errors:
        show_errors(errors)
        raise RuntimeError("Ошибка структуры базы.")

    print("✓ Structure validation passed")


# ============================================================
# FIELD VALIDATION
# ============================================================

def validate_fields(stations: list[Any]) -> None:
    print("\n" + "=" * 70)
    print("FIELD VALIDATION")
    print("=" * 70)

    errors = []

    for index, station in enumerate(stations, start=1):
        country_code = normalize_space(
            station.get("country_code")
        )
        country = normalize_space(station.get("country"))
        name = normalize_space(station.get("name"))
        code = station.get("code")
        latin_name = station.get("latin_name")

        # Country code
        if country_code not in COUNTRIES:
            errors.append(
                f"Запись #{index}: неизвестный country_code="
                f"{country_code!r}"
            )
        elif country_code in EXCLUDED_COUNTRIES:
            errors.append(
                f"Запись #{index}: исключённая страна {country_code}"
            )

        # Country name
        if country_code in COUNTRIES:
            expected = COUNTRIES[country_code]
            if country != expected:
                errors.append(
                    f"Запись #{index}: country={country!r}; "
                    f"для {country_code} ожидалось {expected!r}"
                )

        # Station code
        if not is_valid_station_code(code):
            errors.append(
                f"Запись #{index}: код должен быть строкой "
                f"из 6 цифр, получено {code!r}"
            )

        # Station name
        if not is_valid_station_name(name):
            errors.append(
                f"Запись #{index}: подозрительное или пустое "
                f"название станции {name!r}"
            )

        # Latin/display name
        if not is_valid_latin_name(latin_name):
            errors.append(
                f"Запись #{index}: некорректный latin_name "
                f"{latin_name!r}"
            )

        # Optional fields
        for field in ("operations", "border_code"):
            if field in station and station[field] is not None:
                if not isinstance(station[field], str):
                    errors.append(
                        f"Запись #{index}: поле {field} "
                        "должно быть строкой или null."
                    )

    print(f"Field errors: {len(errors)}")

    if errors:
        show_errors(errors)
        raise RuntimeError("Обнаружены ошибки в полях станций.")

    print("✓ Field validation passed")


# ============================================================
# COUNTRY VALIDATION
# ============================================================

def validate_countries(stations: list[Any]) -> Counter:
    print("\n" + "=" * 70)
    print("COUNTRY VALIDATION")
    print("=" * 70)

    counters = Counter(
        normalize_space(station["country_code"])
        for station in stations
    )

    for code, country in ACTIVE_COUNTRIES.items():
        count = counters.get(code, 0)
        mark = "✓" if count > 0 else "✗"
        print(f"{mark} {code:2} {country:<25} {count:6} stations")

    missing = [
        code for code in ACTIVE_COUNTRIES
        if counters.get(code, 0) == 0
    ]

    unknown = sorted(set(counters) - set(COUNTRIES))
    excluded_found = sorted(set(counters) & EXCLUDED_COUNTRIES)

    errors = []

    if missing:
        errors.append(
            "Нет станций для рабочих стран: " + ", ".join(missing)
        )

    if unknown:
        errors.append(
            "Неизвестные страны: " + ", ".join(unknown)
        )

    if excluded_found:
        errors.append(
            "Обнаружены исключённые страны: "
            + ", ".join(excluded_found)
        )

    print(f"\nActive countries expected: {len(ACTIVE_COUNTRIES)}")
    print(f"Excluded countries: {len(EXCLUDED_COUNTRIES)}")

    if errors:
        show_errors(errors)
        raise RuntimeError("Проверка состава стран не пройдена.")

    print("✓ Country validation passed")

    return counters


# ============================================================
# DUPLICATE VALIDATION
# ============================================================

def validate_duplicates(stations: list[Any]) -> None:
    print("\n" + "=" * 70)
    print("DUPLICATE VALIDATION")
    print("=" * 70)

    seen = {}
    duplicates = []

    for index, station in enumerate(stations, start=1):
        country_code = normalize_space(station["country_code"])
        code = normalize_space(station["code"])
        key = (country_code, code)

        if key in seen:
            duplicates.append(
                f"Запись #{index}: {country_code}/{code}, "
                f"первое появление в записи #{seen[key]}; "
                f"name={station['name']!r}"
            )
        else:
            seen[key] = index

    print(f"Duplicate records: {len(duplicates)}")

    if duplicates:
        show_errors(duplicates)
        raise RuntimeError("Обнаружены дубли по country_code + code.")

    print("✓ Duplicate validation passed")


# ============================================================
# STATISTICS
# ============================================================

def print_code_statistics(stations: list[Any]) -> None:
    codes = [station["code"] for station in stations]
    valid = sum(1 for code in codes if is_valid_station_code(code))

    print("\n" + "=" * 70)
    print("CODE STATISTICS")
    print("=" * 70)
    print(f"Total codes: {len(codes)}")
    print(f"Valid 6-digit codes: {valid}")
    print(f"Invalid codes: {len(codes) - valid}")


def print_name_statistics(stations: list[Any]) -> None:
    names = Counter(
        normalize_space(station["name"]).casefold()
        for station in stations
    )

    repeated = sorted(
        ((name, count) for name, count in names.items() if count > 1),
        key=lambda item: (-item[1], item[0]),
    )

    print("\n" + "=" * 70)
    print("NAME STATISTICS")
    print("=" * 70)
    print(f"Unique station names: {len(names)}")
    print(f"Repeated names: {len(repeated)}")

    if repeated:
        print("Top repeated names:")
        for name, count in repeated[:20]:
            print(f"  {count:4} x {name}")


def print_final_report(
    stations: list[Any],
    counters: Counter,
) -> None:
    print("\n" + "=" * 70)
    print("FINAL VALIDATION REPORT")
    print("=" * 70)

    print(f"Total stations: {len(stations)}")
    print(f"Countries represented: {sum(c > 0 for c in counters.values())}")
    print(f"Expected active countries: {len(ACTIVE_COUNTRIES)}")
    print(f"Excluded countries: {', '.join(sorted(EXCLUDED_COUNTRIES))}")

    print("\nStations by country:")

    for code, country in ACTIVE_COUNTRIES.items():
        print(f"  {code:2} {country:<25} {counters.get(code, 0):6}")


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    print("\n" + "=" * 70)
    print("OSJD STATIONS DATABASE VALIDATOR")
    print("=" * 70)
    print(f"Repository: {BASE_DIR}")
    print(f"Input: {INPUT_FILE}")
    print(f"Active countries: {len(ACTIVE_COUNTRIES)}")
    print(f"Excluded: {', '.join(sorted(EXCLUDED_COUNTRIES))}")

    try:
        stations = load_database()
        validate_structure(stations)
        validate_fields(stations)
        counters = validate_countries(stations)
        validate_duplicates(stations)

        print_code_statistics(stations)
        print_name_statistics(stations)
        print_final_report(stations, counters)

        print("\n" + "=" * 70)
        print("VALIDATION SUCCESS")
        print("=" * 70)
        print("stations.json прошёл все проверки.")
        print("Файл базы не изменялся.")

        return 0

    except Exception as exc:
        print("\n" + "=" * 70)
        print("VALIDATION FAILED")
        print("=" * 70)
        print(f"ERROR: {exc}")

        return 1


if __name__ == "__main__":
    sys.exit(main())
