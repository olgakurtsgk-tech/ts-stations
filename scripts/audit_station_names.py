#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Безопасный аудит названий станций. Базу не изменяет."""

import json
import re
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "stations.json"
REPORT_FILE = BASE_DIR / "station_name_audit.txt"

BAD_FRAGMENTS = (
    "наименование станции",
    "код станции",
    "код погранич",
    "коммерческие операции",
    "производимые коммерческие",
    "перечень грузовых станций",
    "название станции",
    "страница",
    "(тп)",
)

def clean(value):
    if not isinstance(value, str):
        return ""
    value = value.replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", value).strip()

def suspicious_name(value):
    name = clean(value)
    if not name:
        return "пустое название"
    if len(name) < 2:
        return "слишком короткое название"
    if len(name) > 150:
        return "слишком длинное название"
    if not re.search(r"[A-Za-zА-Яа-яЁё]", name):
        return "нет букв"
    if any(x in name.casefold() for x in BAD_FRAGMENTS):
        return "похоже на заголовок или операции"
    if re.fullmatch(r"[\d\s.,;:/()\-]+", name):
        return "только цифры и знаки"
    if re.fullmatch(
        r"\d+(?:[.,]\d+)*(?:[А-Яа-яЁё]{1,3})?"
        r"(?:,\d+(?:[.,]\d+)*(?:[А-Яа-яЁё]{1,3})?)+",
        name,
    ):
        return "похоже на номера операций"
    if name.endswith((" на", " в", " из", " для", " по", " с")):
        return "возможно, обрезано в конце"
    return ""

def main():
    if not DATA_FILE.is_file():
        raise SystemExit(f"Не найден файл: {DATA_FILE}")

    with DATA_FILE.open(encoding="utf-8") as f:
        stations = json.load(f)

    if not isinstance(stations, list):
        raise SystemExit("Ошибка: корень JSON должен быть списком.")

    issues = []
    by_code = defaultdict(list)
    by_name = defaultdict(list)

    for index, item in enumerate(stations, 1):
        if not isinstance(item, dict):
            issues.append(f"Запись #{index}: не является объектом")
            continue

        code = clean(item.get("code"))
        country = clean(item.get("country_code"))
        name = clean(item.get("name"))
        latin = clean(item.get("latin_name"))

        reason = suspicious_name(name)
        if reason:
            issues.append(
                f"ПОДОЗРИТЕЛЬНОЕ НАЗВАНИЕ | запись #{index} | "
                f"{country}/{code} | {reason} | name={name!r}"
            )

        latin_reason = suspicious_name(latin)
        if latin_reason:
            issues.append(
                f"ПОДОЗРИТЕЛЬНЫЙ LATIN | запись #{index} | "
                f"{country}/{code} | {latin_reason} | latin_name={latin!r}"
            )

        if code:
            by_code[(country, code)].append((index, name, latin))

        if name:
            by_name[(country, name.casefold())].append(
                (index, code, latin)
            )

    for (country, code), records in sorted(by_code.items()):
        if len(records) > 1:
            details = "; ".join(
                f"#{i} name={n!r} latin={l!r}"
                for i, n, l in records
            )
            issues.append(
                f"ПОВТОР КОДА | {country}/{code} | {details}"
            )

    for (country, name), records in sorted(by_name.items()):
        codes = sorted({code for _, code, _ in records if code})
        if len(codes) > 1:
            details = "; ".join(
                f"#{i} code={code!r} latin={latin!r}"
                for i, code, latin in records
            )
            issues.append(
                f"ОДИНАКОВОЕ НАЗВАНИЕ С РАЗНЫМИ КОДАМИ | "
                f"{country} | {name!r} | {details}"
            )

    header = [
        "АУДИТ НАЗВАНИЙ ЖЕЛЕЗНОДОРОЖНЫХ СТАНЦИЙ",
        f"Файл: {DATA_FILE}",
        f"Всего записей: {len(stations)}",
        f"Найдено подозрительных случаев: {len(issues)}",
        "",
        "Важно: подозрительные случаи требуют ручной сверки с источником.",
        "Этот отчёт не подтверждает ошибку и не исправляет данные.",
        "",
    ]

    REPORT_FILE.write_text(
        "\n".join(header + (issues or ["Подозрительных случаев не найдено."]))
        + "\n",
        encoding="utf-8",
    )

    print("\n".join(header))
    print(f"Отчёт сохранён: {REPORT_FILE}")
    print("База stations.json не изменялась.")

if __name__ == "__main__":
    main()
