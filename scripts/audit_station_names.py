
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Безопасный аудит названий железнодорожных станций.
Не изменяет data/stations.json.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "stations.json"
REPORT_FILE = BASE_DIR / "station_name_audit.txt"

HEADER_WORDS = (
    "наименование станции",
    "код станции",
    "код погранич",
    "коммерческие операции",
    "производимые коммерческие",
    "перечень грузовых станций",
    "название станции",
    "страница",
    "содержание",
)

TRAILING_WORDS = (
    "на", "в", "из", "для", "по", "с", "и", "к", "от"
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

    folded = name.casefold()

    if any(word in folded for word in HEADER_WORDS):
        return "похоже на заголовок таблицы"

    # Числа с буквенными индексами и перечни операций.
    if re.fullmatch(
        r"\d+(?:[.,]\d+)*(?:[А-Яа-яЁёA-Za-z]{1,3})?"
        r"(?:\s*[,;/]\s*\d+(?:[.,]\d+)*"
        r"(?:[А-Яа-яЁёA-Za-z]{1,3})?)+",
        name,
    ):
        return "похоже на коды грузовых операций"

    if re.fullmatch(r"[\d\s.,;:/()\-]+", name):
        return "только цифры и знаки"

    if name.endswith(("...", "…", "-", "—")):
        return "возможное обрезание строки"

    last_word = folded.rsplit(" ", 1)[-1].strip(".,;:()")
    if last_word in TRAILING_WORDS:
        return "возможно, обрезано в конце"

    if re.search(r"\b(?:экспорт|импорт)\s+на$", folded):
        return "возможно, обрезано после указания направления"

    return ""


def main():
    if not DATA_FILE.is_file():
        raise SystemExit(f"Не найден файл базы: {DATA_FILE}")

    with DATA_FILE.open(encoding="utf-8") as file:
        stations = json.load(file)

    if not isinstance(stations, list):
        raise SystemExit("Ошибка: корень stations.json должен быть списком.")

    issues = []
    by_code = defaultdict(list)
    by_name = defaultdict(list)
    country_counts = Counter()
    country_issues = Counter()

    for index, item in enumerate(stations, 1):
        if not isinstance(item, dict):
            issues.append(
                f"ОШИБКА СТРУКТУРЫ | запись #{index} | "
                "запись не является объектом"
            )
            continue

        code = clean(item.get("code"))
        country = clean(item.get("country_code")) or "НЕ УКАЗАНА"
        name = clean(item.get("name"))
        latin = clean(item.get("latin_name"))

        country_counts[country] += 1

        if not code:
            issues.append(
                f"ПУСТОЙ КОД | запись #{index} | "
                f"{country} | name={name!r}"
            )
            country_issues[country] += 1
        elif not re.fullmatch(r"\d{6}", code):
            issues.append(
                f"ПОДОЗРИТЕЛЬНЫЙ КОД | запись #{index} | "
                f"{country}/{code} | name={name!r}"
            )
            country_issues[country] += 1

        reason = suspicious_name(name)
        if reason:
            issues.append(
                f"ПОДОЗРИТЕЛЬНОЕ НАЗВАНИЕ | запись #{index} | "
                f"{country}/{code} | {reason} | name={name!r}"
            )
            country_issues[country] += 1

        latin_reason = suspicious_name(latin)
        if latin_reason:
            issues.append(
                f"ПОДОЗРИТЕЛЬНЫЙ LATIN | запись #{index} | "
                f"{country}/{code} | {latin_reason} | "
                f"latin_name={latin!r}"
            )
            country_issues[country] += 1

        if code:
            by_code[(country, code)].append((index, name, latin))

        if name:
            by_name[(country, name.casefold())].append(
                (index, code, latin)
            )

    for (country, code), records in sorted(by_code.items()):
        if len(records) > 1:
            details = "; ".join(
                f"#{idx} name={name!r} latin={latin!r}"
                for idx, name, latin in records
            )
            issues.append(
                f"ПОВТОР КОДА | {country}/{code} | {details}"
            )
            country_issues[country] += 1

    for (country, name), records in sorted(by_name.items()):
        codes = sorted({code for _, code, _ in records if code})
        if len(codes) > 1:
            details = "; ".join(
                f"#{idx} code={code!r} latin={latin!r}"
                for idx, code, latin in records
            )
            issues.append(
                f"ОДИНАКОВОЕ НАЗВАНИЕ С РАЗНЫМИ КОДАМИ | "
                f"{country} | {name!r} | {details}"
            )
            country_issues[country] += 1

    report = [
        "АУДИТ НАЗВАНИЙ ЖЕЛЕЗНОДОРОЖНЫХ СТАНЦИЙ",
        f"Файл базы: {DATA_FILE}",
        f"Всего записей: {len(stations)}",
        f"Найдено предупреждений: {len(issues)}",
        "",
        "КОЛИЧЕСТВО ЗАПИСЕЙ ПО СТРАНАМ",
    ]

    for country, count in sorted(country_counts.items()):
        report.append(
            f"{country}: записей={count}, "
            f"предупреждений={country_issues[country]}"
        )

    report.extend([
        "",
        "ДЕТАЛИ ПРОВЕРКИ",
        "Предупреждения требуют сверки с исходным PDF ОСЖД.",
        "Этот аудит не подтверждает ошибку и не исправляет базу.",
        "",
    ])

    report.extend(issues or ["Подозрительных случаев не найдено."])

    REPORT_FILE.write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )

    print("\n".join(report[:8]))
    print(f"\nОтчёт сохранён: {REPORT_FILE}")
    print("База stations.json не изменялась.")


if __name__ == "__main__":
    main()
