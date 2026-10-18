
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Строгая проверка базы железнодорожных станций ОСЖД."""

import json
import re
import sys
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
FILE = BASE_DIR / "data" / "stations.json"

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

EXCLUDED = {"IR", "CN", "CZ", "KR", "RO", "LA"}
ACTIVE = {k: v for k, v in COUNTRIES.items() if k not in EXCLUDED}

REQUIRED = {
    "name", "code", "country", "country_code", "latin_name"
}

BAD_FRAGMENTS = (
    "наименование станции",
    "код станции",
    "код погранич",
    "коммерческие операции",
    "производимые коммерческие",
    "перечень грузовых станций",
    "название станции",
    "содержание",
    "страница",
)


def clean(value):
    if not isinstance(value, str):
        return ""
    value = value.replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", value).strip()


def valid_name(value):
    value = clean(value)

    if not 2 <= len(value) <= 150:
        return False

    if not re.search(r"[A-Za-zА-Яа-яЁё]", value):
        return False

    if any(fragment in value.casefold() for fragment in BAD_FRAGMENTS):
        return False

    # Выявляем последовательности вроде 3,8н,10н.
    if re.fullmatch(
        r"\d+(?:[.,]\d+)*(?:[А-Яа-яЁё]{1,3})?"
        r"(?:,\d+(?:[.,]\d+)*(?:[А-Яа-яЁё]{1,3})?)+",
        value,
    ):
        return False

    if re.fullmatch(r"[\d\s.,;:/()\-]+", value):
        return False

    return True


def fail(errors, limit=1000):
    for error in errors[:limit]:
        print("ERROR:", error)

    if len(errors) > limit:
        print(f"... и ещё {len(errors) - limit} ошибок.")

    return 1


def main():
    print("=" * 70)
    print("OSJD STATIONS DATABASE VALIDATION")
    print("=" * 70)
    print("Файл:", FILE)

    if not FILE.is_file():
        print("ERROR: файл stations.json не найден.")
        return 1

    try:
        with FILE.open("r", encoding="utf-8") as f:
            stations = json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print("ERROR: невозможно прочитать JSON:", exc)
        return 1

    if not isinstance(stations, list) or not stations:
        print("ERROR: корень JSON должен быть непустым списком.")
        return 1

    print("Всего записей:", len(stations))

    # 1. Структура
    errors = []

    for i, station in enumerate(stations, 1):
        if not isinstance(station, dict):
            errors.append(f"Запись #{i}: не JSON-объект.")
            continue

        missing = REQUIRED - station.keys()
        if missing:
            errors.append(
                f"Запись #{i}: отсутствуют поля "
                + ", ".join(sorted(missing))
            )

    if errors:
        return fail(errors)

    # 2. Поля, коды и страны
    errors = []
    counts = Counter()
    seen = {}
    bad_name_count = 0

    for i, station in enumerate(stations, 1):
        code = station["code"]
        country_code = clean(station["country_code"])
        country = clean(station["country"])
        name = clean(station["name"])
        latin_name = clean(station["latin_name"])

        counts[country_code] += 1

        if country_code not in COUNTRIES:
            errors.append(
                f"Запись #{i}: неизвестная страна {country_code!r}."
            )
        elif country_code in EXCLUDED:
            errors.append(
                f"Запись #{i}: исключённая страна {country_code}."
            )
        elif country != COUNTRIES[country_code]:
            errors.append(
                f"Запись #{i}: страна {country!r} не соответствует "
                f"{country_code}; ожидалось {COUNTRIES[country_code]!r}."
            )

        if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code.strip()):
            errors.append(
                f"Запись #{i}: код должен быть строкой из 6 цифр: {code!r}."
            )

        if not valid_name(name):
            bad_name_count += 1
            errors.append(
                f"Запись #{i}: подозрительное название станции {name!r}."
            )

        if not valid_name(latin_name):
            errors.append(
                f"Запись #{i}: некорректный latin_name {latin_name!r}."
            )

        for field in ("operations", "border_code"):
            if field in station and station[field] is not None:
                if not isinstance(station[field], str):
                    errors.append(
                        f"Запись #{i}: {field} должен быть строкой или null."
                    )

        # Дубли проверяем по стране и коду.
        if isinstance(code, str) and re.fullmatch(r"\d{6}", code.strip()):
            key = (country_code, code.strip())
            if key in seen:
                errors.append(
                    f"Дубль {country_code}/{code.strip()}: "
                    f"записи #{seen[key]} и #{i}."
                )
            else:
                seen[key] = i

    # 3. Все 22 рабочие страны должны присутствовать.
    missing_countries = [
        f"{code} ({country})"
        for code, country in ACTIVE.items()
        if counts[code] == 0
    ]

    if missing_countries:
        errors.append(
            "Нет станций для рабочих стран: "
            + ", ".join(missing_countries)
        )

    # 4. Отчёт по странам
    print()
    print("СТАНЦИИ ПО СТРАНАМ:")

    for code, country in ACTIVE.items():
        print(f"{code} — {country}: {counts[code]}")

    print()
    print("Рабочих стран:", len(ACTIVE))
    print("Исключённых стран:", len(EXCLUDED))
    print("Записей с подозрительными названиями:", bad_name_count)
    print("Ошибок проверки:", len(errors))

    if errors:
        print()
        print("VALIDATION FAILED")
        return fail(errors)

    print()
    print("=" * 70)
    print("VALIDATION SUCCESS")
    print("Все проверки пройдены. База не изменялась.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
