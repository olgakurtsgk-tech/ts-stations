#!/usr/bin/env python3
"""Безопасная диагностика парсера ОСЖД. Не изменяет data/stations.json."""

import argparse
import hashlib
import json
import re
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# scripts/ is already on sys.path when this file is run from the repository.
import update_stations as updater


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_text_codes(methods: dict[str, list[Any]]) -> list[str]:
    found: set[str] = set()
    for page_text in methods.get("text", []):
        if isinstance(page_text, str):
            found.update(re.findall(r"(?<!\d)\d{6}(?!\d)", page_text))
    return sorted(found)


def inspect_records(records: list[dict[str, Any]], country_code: str) -> dict[str, Any]:
    seen: set[str] = set()
    duplicate_codes: list[str] = []
    invalid_codes: list[dict[str, Any]] = []
    invalid_names: list[dict[str, Any]] = []
    suspicious: list[dict[str, Any]] = []

    for record in records:
        code = str(record.get("code", ""))
        if not re.fullmatch(r"\d{6}", code):
            invalid_codes.append(record)
        if code in seen:
            duplicate_codes.append(code)
        seen.add(code)

        ru = str(record.get("name", ""))
        latin = str(record.get("latin_name", ""))
        if not updater.strict_station_name(ru, "ru") or not updater.strict_station_name(latin, "latin"):
            invalid_names.append(record)

        # Surface rows that look like an operation-code fragment or header leakage.
        if updater.looks_like_operations(ru) or updater.looks_like_operations(latin):
            suspicious.append(record)

    return {
        "records": len(records),
        "unique_station_codes": len(seen),
        "duplicate_codes": sorted(set(duplicate_codes)),
        "invalid_codes_count": len(invalid_codes),
        "invalid_codes_sample": invalid_codes[:10],
        "invalid_names_count": len(invalid_names),
        "invalid_names_sample": invalid_names[:15],
        "suspicious_operation_names_count": len(suspicious),
        "suspicious_operation_names_sample": suspicious[:15],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the OSJD parser without writing stations.json.")
    parser.add_argument(
        "--report",
        default="/tmp/stations-dry-run-report.json",
        help="Where to write the diagnostic JSON report (default: /tmp/stations-dry-run-report.json)",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    output_file = Path(updater.OUTPUT_FILE)
    before_hash = sha256_file(output_file)
    existing_records = updater.load_existing_database()
    existing_counts = Counter(
        str(item.get("country_code", ""))
        for item in existing_records
    )

    report: dict[str, Any] = {
        "run_type": "dry-run-no-database-write",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_page": updater.OSJD_PAGE,
        "database_path": str(output_file),
        "database_sha256_before": before_hash,
        "database_sha256_after": None,
        "database_unchanged": None,
        "existing_database_records": len(existing_records),
        "existing_counts_by_country": {
            code: existing_counts.get(code, 0)
            for code in updater.ACTIVE_COUNTRIES
        },
        "countries": {},
        "summary": {},
        "fatal_errors": [],
    }

    print("=" * 72)
    print("OSJD PARSER DRY RUN — stations.json WILL NOT BE WRITTEN")
    print("=" * 72)
    print("Current database:", output_file)
    print("Current database SHA-256:", before_hash)
    print("Active countries:", len(updater.ACTIVE_COUNTRIES))

    try:
        pdf_urls = updater.get_pdf_urls()
        report["discovered_pdf_sources"] = {
            code: pdf_urls.get(code)
            for code in updater.ACTIVE_COUNTRIES
        }
    except Exception as exc:
        message = f"Could not discover OSJD PDF links: {type(exc).__name__}: {exc}"
        report["fatal_errors"].append(message)
        print("FATAL:", message)
        pdf_urls = {}

    all_records: list[dict[str, Any]] = []
    countries_ok = 0
    countries_failed = 0

    for country_code, country_name in updater.ACTIVE_COUNTRIES.items():
        item: dict[str, Any] = {
            "country_name": country_name,
            "source_url": pdf_urls.get(country_code),
            "existing_records": existing_counts.get(country_code, 0),
            "status": "NOT_RUN",
            "errors": [],
        }
        report["countries"][country_code] = item

        print()
        print("-" * 72)
        print(f"{country_code} — {country_name}")

        url = pdf_urls.get(country_code)
        if not url:
            item["status"] = "FAIL"
            item["errors"].append("No PDF source was discovered for this active country.")
            countries_failed += 1
            print("FAIL: no PDF source")
            continue

        try:
            pdf_bytes = updater.download_pdf(url)
            methods = updater.extract_text_methods(pdf_bytes)
            text_codes = unique_text_codes(methods)
            item["pdf_bytes"] = len(pdf_bytes)
            item["pdf_pages"] = len(methods.get("text", []))
            item["unique_codes_in_extracted_text"] = len(text_codes)
            item["text_codes_sample"] = text_codes[:20]

            records = updater.parse_pdf(pdf_bytes, country_code)
            records = updater.deduplicate_records(records)
            item.update(inspect_records(records, country_code))
            item["parsed_vs_existing_ratio"] = (
                round(len(records) / item["existing_records"], 3)
                if item["existing_records"]
                else None
            )
            minimum_expected = max(1, int(item["existing_records"] * 0.65 + 0.999999)) if item["existing_records"] else 1
            item["minimum_expected_65_percent"] = minimum_expected
            item["below_65_percent_of_existing"] = (
                len(records) < minimum_expected if item["existing_records"] else False
            )

            if not records:
                item["errors"].append("No station records parsed.")
            if item["invalid_codes_count"]:
                item["errors"].append("Invalid station codes detected.")
            if item["invalid_names_count"]:
                item["errors"].append("Names failed strict validation.")
            if item["suspicious_operation_names_count"]:
                item["errors"].append("Operation-code-like names detected.")
            if item["below_65_percent_of_existing"]:
                item["errors"].append(
                    f"Parsed {len(records)} records, below the safety threshold {minimum_expected} "
                    f"based on {item['existing_records']} existing records."
                )

            if item["errors"]:
                item["status"] = "REVIEW"
                countries_failed += 1
            else:
                item["status"] = "PASS"
                countries_ok += 1

            all_records.extend(records)
            print(
                f"DRY RUN RESULT: {item['status']} | "
                f"parsed={len(records)} | "
                f"text unique codes={len(text_codes)} | "
                f"existing={item['existing_records']}"
            )
            if item["errors"]:
                for error in item["errors"]:
                    print("REVIEW:", error)

        except Exception as exc:
            item["status"] = "FAIL"
            item["errors"].append(f"{type(exc).__name__}: {exc}")
            item["traceback"] = traceback.format_exc(limit=8)
            countries_failed += 1
            print("FAIL:", type(exc).__name__, exc)

    report["summary"] = {
        "active_countries_total": len(updater.ACTIVE_COUNTRIES),
        "countries_passed": countries_ok,
        "countries_need_review_or_failed": countries_failed,
        "total_parsed_records": len(all_records),
        "total_unique_country_code_pairs": len({
            (str(record.get("country_code", "")), str(record.get("code", "")))
            for record in all_records
        }),
        "status": "PASS" if countries_failed == 0 and not report["fatal_errors"] else "REVIEW_REQUIRED",
    }

    # Hard safety check: this script never calls save_database(); verify the input file stayed identical.
    after_hash = sha256_file(output_file)
    report["database_sha256_after"] = after_hash
    report["database_unchanged"] = before_hash == after_hash
    if before_hash != after_hash:
        report["fatal_errors"].append("SAFETY FAILURE: stations.json hash changed during dry run.")
        report["summary"]["status"] = "SAFETY_FAILURE"

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print("DRY RUN SUMMARY")
    print("=" * 72)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("stations.json unchanged:", report["database_unchanged"])
    print("Report:", report_path)

    return 0 if report["summary"]["status"] == "PASS" and report["database_unchanged"] else 1


if __name__ == "__main__":
    sys.exit(main())
