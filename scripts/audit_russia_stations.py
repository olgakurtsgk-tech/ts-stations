
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Безопасная проверка российских станций. Базу не изменяет."""

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "stations.json"
REPORT = ROOT / "russia_station_audit_report.json"

CODE_RE = re.compile(r"^\d{6}$")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
OPERATIONS_RE = re.compile(r"^\s*\d+\s*[Нн]?(?:\s*[,;]\s*|\s+)\d.*$")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def norm(value):
    return re.sub(
        r"\s+", " ",
        str(value or "").replace("\xa0", " ")
    ).strip()


def main():
    if not SOURCE.is_file():
        raise SystemExit(f"ERROR: Не найден файл {SOURCE}")

    before_hash = sha256(SOURCE)

    with SOURCE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise SystemExit(
            "ERROR: stations.json должен содержать список записей"
        )

    russia = [
        row for row in data
        if isinstance(row, dict)
        and (
            norm(row.get("country_code")).upper() == "RU"
            or norm(row.get("country")).casefold() == "россия"
        )
    ]

    flagged = []
    code_counts = Counter()

    missing = 0
    invalid_codes = 0
    suspicious_names = 0
    suspicious_latin = 0

    for index, row in enumerate(russia, start=1):
        name = norm(row.get("name"))
        code = norm(row.get("code"))
        latin = norm(row.get("latin_name"))
        reasons = []

        if not name or not code or not latin:
            missing += 1
            reasons.append("missing_required_field")

        if not CODE_RE.fullmatch(code):
            invalid_codes += 1
            reasons.append("code_not_six_digits")

        if code:
            code_counts[code] += 1

        if name and (
            OPERATIONS_RE.fullmatch(name)
            or (
                not CYRILLIC_RE.search(name)
                and not LATIN_RE.search(name)
            )
        ):
            suspicious_names += 1
            reasons.append("suspicious_station_name")

        if latin and OPERATIONS_RE.fullmatch(latin):
            suspicious_latin += 1
            reasons.append("suspicious_latin_name")

        if reasons:
            flagged.append({
                "russia_row_number": index,
                "name": name,
                "code": code,
                "latin_name": latin,
                "reasons": reasons,
            })

    after_hash = sha256(SOURCE)

    duplicates = sorted(
        code for code, count in code_counts.items()
        if count > 1
    )

    report = {
        "report_type": "read_only_russia_station_audit",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": "data/stations.json",
        "database_records_total": len(data),
        "russia_records": len(russia),
        "database_sha256_before": before_hash,
        "database_sha256_after": after_hash,
        "database_unchanged": before_hash == after_hash,
        "summary": {
            "russia_rows_with_any_flag": len(flagged),
            "missing_required_fields_count": missing,
            "invalid_station_code_count": invalid_codes,
            "duplicate_station_codes_count": len(duplicates),
            "suspicious_station_names_count": suspicious_names,
            "suspicious_latin_names_count": suspicious_latin,
            "unique_russia_codes": len(code_counts),
        },
        "duplicate_codes_sample": duplicates[:100],
        "flagged_rows_sample": flagged[:300],
        "note": "Проверка только для чтения. База не изменяется."
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    print("=" * 55)
    print("ПРОВЕРКА ЖД-СТАНЦИЙ РОССИИ")
    print("РЕЖИМ: ТОЛЬКО ЧТЕНИЕ")
    print("=" * 55)
    print(f"Всего записей в базе: {len(data)}")
    print(f"Записей России: {len(russia)}")
    print(f"Записей с замечаниями: {len(flagged)}")
    print(f"Нет обязательных полей: {missing}")
    print(f"Некорректных кодов: {invalid_codes}")
    print(f"Дублирующихся кодов: {len(duplicates)}")
    print(f"Подозрительных названий: {suspicious_names}")
    print(f"Подозрительных латинских названий: {suspicious_latin}")
    print(f"Уникальных кодов России: {len(code_counts)}")
    print(f"База не изменилась: {before_hash == after_hash}")
    print(f"Отчёт создан: {REPORT}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

