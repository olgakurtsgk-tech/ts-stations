#!/usr/bin/env python3

from __future__ import annotations

"""
OSJD railway freight stations parser.

Получает актуальные PDF-перечни грузовых станций ОСЖД,
извлекает станции несколькими способами и обновляет
data/stations.json только после успешной проверки всех
25 стран.

Основная страница ОСЖД:
https://osjd.org/ru/8974/page/106077?id=2227
"""

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "stations.json"

OSJD_PAGE = "https://osjd.org/ru/8974/page/106077?id=2227"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/153.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 60


# ============================================================
# 25 COUNTRIES
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
    "LV": "Латвия",
    "LT": "Литва",
    "MD": "Молдова",
    "MN": "Монголия",
    "PL": "Польша",
    "RU": "Россия",
    "SK": "Словакия",
    "TJ": "Таджикистан",
    "TM": "Туркменистан",
    "UZ": "Узбекистан",
    "UA": "Украина",
    "CZ": "Чехия",
    "EE": "Эстония",
}


# ============================================================
# FALLBACK PDF URLS
#
# Эти URL уже диагностированы на сайте ОСЖД.
# ============================================================

FALLBACK_PDFS = {
    "IR": "https://osjd.org/api/media/resources/9608?action=download",
    "CN": "https://osjd.org/api/media/resources/1537?action=download",
    "CZ": "https://osjd.org/api/media/resources/3904?action=download",
    "EE": "https://osjd.org/api/media/resources/1671839?action=download",
}


# ============================================================
# NAME MATCHING
# ============================================================

COUNTRY_ALIASES = {
    "AZ": [
        "азербайджан",
        "азербайджанских железных дорог",
    ],
    "AF": [
        "афганистан",
        "железной дороги исламской республики афганистан",
    ],
    "BY": [
        "беларус",
        "белорусской железной дороги",
    ],
    "BG": [
        "болгар",
        "болгарских государственных железных дорог",
    ],
    "HU": [
        "венгр",
        "венгерских государственных железных дорог",
    ],
    "VN": [
        "вьетнам",
        "вьетнамской железной дороги",
    ],
    "GE": [
        "груз",
        "грузинской железной дороги",
    ],
    "IR": [
        "иран",
        "железной дороги исламской республики иран",
    ],
    "KZ": [
        "казахстан",
        "железных дорог казахстан",
    ],
    "CN": [
        "китай",
        "китайских железных дорог",
    ],
    "KP": [
        "кндр",
        "корейской народно-демократической республики",
    ],
    "KG": [
        "кыргыз",
        "кыргызской железной дороги",
    ],
    "LV": [
        "латв",
        "латвийской железной дороги",
    ],
    "LT": [
        "литв",
        "литовских железных дорог",
    ],
    "MD": [
        "молдов",
        "железной дороги молдовы",
    ],
    "MN": [
        "монгол",
        "улан-баторской железной дороги",
    ],
    "PL": [
        "поль",
        "польских государственных железных дорог",
    ],
    "RU": [
        "россий",
        "российских железных дорог",
    ],
    "SK": [
        "словац",
        "словацкой республики",
    ],
    "TJ": [
        "таджик",
        "таджикской железной дороги",
    ],
    "TM": [
        "туркмен",
        "туркмендемиреллары",
    ],
    "UZ": [
        "узбек",
        "узбекистан",
        "узбекских железных дорог",
    ],
    "UA": [
        "украин",
        "украинской железной дороги",
    ],
    "CZ": [
        "чеш",
        "чешских железных дорог",
    ],
    "EE": [
        "эстон",
        "эстонской железной дороги",
    ],
}


# ============================================================
# HELPERS
# ============================================================

def normalize_space(value: str) -> str:
    if not value:
        return ""

    value = value.replace("\xa0", " ")
    value = value.replace("\u200b", "")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_code(value: str) -> str | None:
    """
    Извлекает ровно 6 цифр.

    Дополнительно пытается исправить:
    123 456
    123-456
    123.456
    """
    if not value:
        return None

    value = value.strip()

    if re.fullmatch(r"\d{6}", value):
        return value

    digits = re.sub(r"\D", "", value)

    if len(digits) == 6:
        return digits

    return None


def is_noise_name(value: str) -> bool:
    if not value:
        return True

    text = normalize_space(value)

    if len(text) < 2:
        return True

    lower = text.lower()

    bad_fragments = [
        "наименование станции",
        "код станции",
        "код погранич",
        "производимые коммерческие",
        "операции",
        "страница",
        "содержание",
        "раздел ",
        "перечень грузовых станций",
        "железной дороги",
        "железных дорог",
        "код ",
        "наименование",
    ]

    if any(fragment in lower for fragment in bad_fragments):
        return True

    if re.fullmatch(r"[\d\s.,;:/()\-]+", text):
        return True

    return False


def clean_station_name(value: str) -> str:
    value = normalize_space(value)

    # Убираем служебные разделители.
    value = re.sub(r"^[|;:,]+", "", value)
    value = re.sub(r"[|;:,]+$", "", value)

    value = normalize_space(value)

    return value


def looks_like_operations(value: str) -> bool:
    if not value:
        return False

    text = normalize_space(value)

    # Коммерческие операции обычно состоят из цифр,
    # запятых, буквенных обозначений и служебных символов.
    if re.fullmatch(
        r"[\d,\s./()«»\"'А-Яа-яA-Za-z№#*КкНн\-]+",
        text,
    ):
        digits = re.findall(r"\d+", text)

        if digits:
            return True

    return False


def valid_name(value: str) -> bool:
    value = clean_station_name(value)

    if is_noise_name(value):
        return False

    if len(value) > 150:
        return False

    # Должна быть хотя бы одна буква.
    if not re.search(r"[A-Za-zА-Яа-яЁё]", value):
        return False

    return True


def score_name(value: str) -> int:
    """
    Оценка кандидата на название станции.
    """
    value = clean_station_name(value)

    if not valid_name(value):
        return -100

    score = 0

    if 2 <= len(value) <= 80:
        score += 10

    if re.search(r"[А-Яа-яЁё]", value):
        score += 5

    if re.search(r"[A-Za-z]", value):
        score += 3

    if "(" in value or ")" in value:
        score += 1

    return score


# ============================================================
# HTTP
# ============================================================

def download_pdf(url: str) -> bytes:
    print()
    print("-" * 70)
    print("DOWNLOAD")
    print(url)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )

    print("HTTP STATUS:", response.status_code)
    print("CONTENT TYPE:", response.headers.get("content-type"))
    print("SIZE:", len(response.content))

    response.raise_for_status()

    content_type = (
        response.headers.get("content-type", "")
        .lower()
    )

    if (
        "pdf" not in content_type
        and not response.content.startswith(b"%PDF")
    ):
        raise RuntimeError(
            f"URL did not return PDF: {url}"
        )

    return response.content


# ============================================================
# OSJD PAGE DISCOVERY
# ============================================================

def discover_osjd_links() -> dict[str, str]:
    """
    Загружает текущую страницу ОСЖД и пытается определить
    PDF для каждой страны.
    """

    print()
    print("=" * 70)
    print("DISCOVERING OSJD PDF LINKS")
    print("=" * 70)
    print(OSJD_PAGE)

    response = requests.get(
        OSJD_PAGE,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )

    print("HTTP STATUS:", response.status_code)

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    result: dict[str, str] = {}

    for link in soup.find_all("a"):
        href = link.get("href")

        if not href:
            continue

        text = normalize_space(
            link.get_text(" ", strip=True)
        )

        combined = f"{text} {href}".lower()

        # Нужны именно ссылки на PDF / media resources.
        if (
            "api/media/resources" not in combined
            and ".pdf" not in combined
        ):
            continue

        if href.startswith("/"):
            href = "https://osjd.org" + href

        for country_code, aliases in COUNTRY_ALIASES.items():
            if country_code in result:
                continue

            if any(
                alias in combined
                for alias in aliases
            ):
                result[country_code] = href

                print(
                    f"FOUND {country_code}: "
                    f"{text[:100]}"
                )

                print(
                    f"       {href}"
                )

                break

    return result


def get_pdf_urls() -> dict[str, str]:
    discovered = discover_osjd_links()

    result = dict(discovered)

    # Для проблемных стран fallback обязателен.
    for code, url in FALLBACK_PDFS.items():
        if code not in result:
            print(
                f"FALLBACK {code}: {url}"
            )
            result[code] = url

    return result


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_text_methods(
    pdf_bytes: bytes,
) -> dict[str, list[Any]]:
    """
    Возвращает результаты четырёх способов PyMuPDF.
    """

    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    methods: dict[str, list[Any]] = {
        "text": [],
        "blocks": [],
        "words": [],
        "dict": [],
    }

    for page_number, page in enumerate(
        document,
        start=1,
    ):
        try:
            methods["text"].append(
                page.get_text("text")
            )
        except Exception as exc:
            print(
                f"WARNING text page {page_number}: {exc}"
            )
            methods["text"].append("")

        try:
            methods["blocks"].append(
                page.get_text("blocks")
            )
        except Exception as exc:
            print(
                f"WARNING blocks page {page_number}: {exc}"
            )
            methods["blocks"].append([])

        try:
            methods["words"].append(
                page.get_text("words")
            )
        except Exception as exc:
            print(
                f"WARNING words page {page_number}: {exc}"
            )
            methods["words"].append([])

        try:
            methods["dict"].append(
                page.get_text("dict")
            )
        except Exception as exc:
            print(
                f"WARNING dict page {page_number}: {exc}"
            )
            methods["dict"].append({})

    document.close()

    return methods

