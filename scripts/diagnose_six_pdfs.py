#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OSJD SIX PDF DIAGNOSTIC

Диагностирует источники PDF для шести стран,
которые ранее не удалось нормально обработать.

Важно:
Этот файл НЕ импортирует OSJD_PAGE из update_stations.py.
Он полностью самостоятельный.

Проверяем:
IR - Иран
CN - Китай
KR - Республика Корея
RO - Румыния
CZ - Чехия
EE - Эстония
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests


# ============================================================
# SETTINGS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

TIMEOUT = 30

PDF_RESOURCES = {
    "IR": {
        "country": "Иран",
        "resource_id": "9608",
    },
    "CN": {
        "country": "Китай",
        "resource_id": "1537",
    },
    "KR": {
        "country": "Республика Корея",
        "resource_id": "1637529",
    },
    "RO": {
        "country": "Румыния",
        "resource_id": "2813",
    },
    "CZ": {
        "country": "Чехия",
        "resource_id": "3904",
    },
    "EE": {
        "country": "Эстония",
        "resource_id": "1671839",
    },
}


# ============================================================
# URL BUILDERS
# ============================================================

def build_api_url(resource_id: str) -> str:
    return (
        "https://osjd.org/api/media/resources/"
        f"{resource_id}?action=download"
    )


def build_page_url(resource_id: str) -> str:
    return (
        "https://osjd.org/ru/page/2101101"
        f"?file=/api/media/resources/"
        f"{resource_id}?action=download"
        "#zoom=page-height"
    )


# ============================================================
# DIAGNOSTIC
# ============================================================

def diagnose_country(
    code: str,
    country_data: dict,
) -> bool:

    country = country_data["country"]
    resource_id = country_data["resource_id"]

    api_url = build_api_url(resource_id)
    page_url = build_page_url(resource_id)

    print()
    print("-" * 70)
    print(f"{code} - {country}")
    print("-" * 70)

    print()
    print("Resource ID:")
    print(resource_id)

    print()
    print("API URL:")
    print(api_url)

    print()
    print("Page URL:")
    print(page_url)

    try:

        response = requests.get(
            api_url,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        print()
        print("HTTP status:")
        print(response.status_code)

        print()
        print("Final URL:")
        print(response.url)

        content_type = response.headers.get(
            "Content-Type",
            "",
        )

        print()
        print("Content-Type:")
        print(content_type)

        content_length = response.headers.get(
            "Content-Length",
            "",
        )

        print()
        print("Content-Length:")
        print(content_length)

        data = response.content

        print()
        print("Downloaded bytes:")
        print(len(data))

        if response.status_code != 200:
            print()
            print(
                "✗ HTTP ERROR"
            )
            return False

        if not data:
            print()
            print(
                "✗ EMPTY RESPONSE"
            )
            return False

        # ----------------------------------------------------
        # PDF SIGNATURE
        # ----------------------------------------------------

        if data[:4] == b"%PDF":

            print()
            print(
                "✓ PDF SIGNATURE DETECTED"
            )

            return True

        # ----------------------------------------------------
        # HTML RESPONSE
        # ----------------------------------------------------

        text_start = data[:500].decode(
            "utf-8",
            errors="replace",
        )

        print()
        print("First response bytes:")
        print(
            text_start[:500]
        )

        print()

        if "<html" in text_start.lower():

            print(
                "⚠ RESPONSE IS HTML, NOT PDF"
            )

        else:

            print(
                "⚠ RESPONSE IS NOT A PDF"
            )

        return False

    except requests.RequestException as exc:

        print()
        print(
            "✗ REQUEST ERROR:"
        )

        print(
            repr(exc)
        )

        return False

    except Exception as exc:

        print()
        print(
            "✗ UNEXPECTED ERROR:"
        )

        print(
            repr(exc)
        )

        return False


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    print()
    print("=" * 70)
    print("DIAGNOSING SIX MISSING OSJD PDFS")
    print("=" * 70)

    print()
    print(
        "Working directory:"
    )
    print(
        BASE_DIR
    )

    results = {}

    for code, country_data in PDF_RESOURCES.items():

        results[code] = diagnose_country(
            code,
            country_data,
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)

    print()

    for code, success in results.items():

        country = PDF_RESOURCES[
            code
        ]["country"]

        if success:

            print(
                f"✓ {code} "
                f"{country}"
            )

        else:

            print(
                f"✗ {code} "
                f"{country}"
            )

    successful = sum(
        1
        for value in results.values()
        if value
    )

    failed = len(results) - successful

    print()
    print(
        "Successful:",
        successful,
    )

    print(
        "Failed:",
        failed,
    )

    print()

    # --------------------------------------------------------
    # IMPORTANT:
    # Diagnostic itself should NOT fail GitHub Actions
    # merely because a PDF is unavailable.
    # --------------------------------------------------------

    print("=" * 70)
    print("DIAGNOSTIC COMPLETED")
    print("=" * 70)

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(
        main()
    )
