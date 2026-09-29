#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OSJD railway station database updater.

22 countries are processed.

EXCLUDED:
IR — Iran
CN — China
CZ — Czech Republic
KR — Republic of Korea
RO — Romania
LA — Laos

The database is saved only after all target countries
have been successfully parsed and validated.

Parser order:

1. PyMuPDF text
2. PyMuPDF words
3. PyMuPDF blocks
4. pdftotext
5. OCR with Tesseract

OCR is especially important for scanned OSJD PDFs.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "stations.json"

OSJD_PAGE = "https://osjd.org/ru/8974/page/106077?id=2227"

REQUEST_TIMEOUT = 90

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
}


# ============================================================
# COUNTRIES
# ============================================================

EXCLUDED_COUNTRIES = {
    "IR",
    "CN",
    "CZ",
    "KR",
    "RO",
    "LA",
}


COUNTRIES = {
    "AZ": "Азербайджан",
    "AF": "Афганистан",
    "BY": "Беларусь",
    "BG": "Болгария",
    "HU": "Венгрия",
    "VN": "Вьетнам",
    "GE": "Грузия",
    "KZ": "Казахстан",
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
    "EE": "Эстония",
}


COUNTRY_ALIASES = {
    "AZ": [
        "азербайджан",
        "азербайджанских железных дорог",
        "azerbaijan",
    ],
    "AF": [
        "афганистан",
        "железной дороги исламской республики афганистан",
        "afghanistan",
    ],
    "BY": [
        "беларус",
        "белорусской железной дороги",
        "belarus",
    ],
    "BG": [
        "болгар",
        "болгарских государственных железных дорог",
        "bulgaria",
    ],
    "HU": [
        "венгр",
        "венгерских государственных железных дорог",
        "hungary",
    ],
    "VN": [
        "вьетнам",
        "вьетнамской железной дороги",
        "vietnam",
    ],
    "GE": [
        "груз",
        "грузинской железной дороги",
        "georgia",
    ],
    "KZ": [
        "казахстан",
        "железных дорог казахстан",
        "kazakhstan",
    ],
    "KP": [
        "кндр",
        "корейской народно-демократической республики",
        "dprk",
    ],
    "KG": [
        "кыргыз",
        "кыргызской железной дороги",
        "kyrgyzstan",
    ],
    "LV": [
        "латв",
        "латвийской железной дороги",
        "latvia",
    ],
    "LT": [
        "литв",
        "литовских железных дорог",
        "lithuania",
    ],
    "MD": [
        "молдов",
        "железной дороги молдовы",
        "moldova",
    ],
    "MN": [
        "монгол",
        "улан-баторской железной дороги",
        "mongolia",
    ],
    "PL": [
        "поль",
        "польских государственных железных дорог",
        "poland",
    ],
    "RU": [
        "россий",
        "российских железных дорог",
        "russia",
    ],
    "SK": [
        "словац",
        "словацкой республики",
        "slovakia",
    ],
    "TJ": [
        "таджик",
        "таджикской железной дороги",
        "tajikistan",
    ],
    "TM": [
        "туркмен",
        "туркмендемиреллары",
        "turkmenistan",
    ],
    "UZ": [
        "узбек",
        "узбекистан",
        "узбекских железных дорог",
        "uzbekistan",
    ],
    "UA": [
        "украин",
        "украинской железной дороги",
        "ukraine",
    ],
    "EE": [
        "эстон",
        "эстонской железной дороги",
        "estonia",
    ],
}


# ============================================================
# HELPERS
# ============================================================

def normalize_space(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)

    text = text.replace("\xa0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_code(value: Any) -> str | None:
    if value is None:
        return None

    text = normalize_space(value)

    match = re.search(
        r"(?<!\d)(\d{6})(?!\d)",
        text,
    )

    if match:
        return match.group(1)

    digits = re.sub(r"\D", "", text)

    if len(digits) == 6:
        return digits

    return None


def clean_name(value: Any) -> str:
    text = normalize_space(value)

    text = re.sub(
        r"^[|;,:.\-–—]+",
        "",
        text,
    )

    text = re.sub(
        r"[|;,:.\-–—]+$",
        "",
        text,
    )

    return normalize_space(text)


def valid_name(value: Any) -> bool:
    text = clean_name(value)

    if len(text) < 2:
        return False

    if len(text) > 180:
        return False

    if not re.search(
        r"[A-Za-zА-Яа-яЁё]",
        text,
    ):
        return False

    lower = text.lower()

    bad = [
        "наименование станции",
        "код станции",
        "код погранич",
        "перечень грузовых станций",
        "коммерческие операции",
        "страница",
        "содержание",
        "station code",
        "station name",
    ]

    if any(
        item in lower
        for item in bad
    ):
        return False

    return True


def is_cyrillic_name(value: str) -> bool:
    return bool(
        re.search(
            r"[А-Яа-яЁё]",
            value or "",
        )
    )


def is_latin_name(value: str) -> bool:
    return bool(
        re.search(
            r"[A-Za-z]",
            value or "",
        )
    )


# ============================================================
# URL
# ============================================================

def normalize_osjd_pdf_url(
    url: str,
) -> str:

    if not url:
        return ""

    value = unquote(
        str(url).strip()
    )

    value = value.split("#", 1)[0]

    match = re.search(
        r"[?&]file=([^&#]+)",
        value,
        flags=re.IGNORECASE,
    )

    if match:

        file_part = unquote(
            match.group(1)
        )

        if file_part.startswith(
            (
                "http://",
                "https://",
            )
        ):
            value = file_part

        elif file_part.startswith("/"):
            value = urljoin(
                "https://osjd.org",
                file_part,
            )

        else:
            value = urljoin(
                "https://osjd.org/",
                file_part,
            )

    if value.startswith("/"):
        value = urljoin(
            "https://osjd.org",
            value,
        )

    return value


# ============================================================
# HTTP
# ============================================================

def download_pdf(
    url: str,
) -> bytes:

    url = normalize_osjd_pdf_url(
        url
    )

    print()
    print("-" * 70)
    print("DOWNLOAD PDF")
    print(url)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )

    print(
        "HTTP STATUS:",
        response.status_code,
    )

    print(
        "FINAL URL:",
        response.url,
    )

    content_type = (
        response.headers
        .get(
            "content-type",
            "",
        )
        .lower()
    )

    print(
        "CONTENT TYPE:",
        content_type,
    )

    print(
        "SIZE:",
        len(response.content),
    )

    response.raise_for_status()

    if (
        response.content.startswith(
            b"%PDF"
        )
        or "pdf" in content_type
    ):

        print(
            "✓ PDF RECEIVED"
        )

        return response.content

    raise RuntimeError(
        "URL did not return PDF: "
        + url
    )


# ============================================================
# DISCOVERY
# ============================================================

def discover_osjd_links() -> dict[str, str]:

    print()
    print("=" * 70)
    print("DISCOVERING OSJD PDF LINKS")
    print("=" * 70)

    response = requests.get(
        OSJD_PAGE,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    result = {}

    for link in soup.find_all("a"):

        href = link.get("href")

        if not href:
            continue

        text = normalize_space(
            link.get_text(
                " ",
                strip=True,
            )
        )

        full_url = urljoin(
            "https://osjd.org",
            href,
        )

        combined = (
            text
            + " "
            + href
            + " "
            + full_url
        ).lower()

        if (
            "api/media/resources"
            not in combined
            and "file=" not in combined
            and ".pdf" not in combined
        ):
            continue

        for code, aliases in (
            COUNTRY_ALIASES.items()
        ):

            if code in result:
                continue

            if any(
                alias in combined
                for alias in aliases
            ):

                result[code] = (
                    normalize_osjd_pdf_url(
                        full_url
                    )
                )

                print(
                    f"FOUND {code}: "
                    f"{COUNTRIES[code]}"
                )

                print(
                    result[code]
                )

                break

    return result


def get_pdf_urls() -> dict[str, str]:

    discovered = (
        discover_osjd_links()
    )

    result = {}

    for code in COUNTRIES:

        if code in discovered:

            result[code] = (
                normalize_osjd_pdf_url(
                    discovered[code]
                )
            )

    return result


# ============================================================
# PDF EXTRACTION
# ============================================================

def extract_pdf_pages(
    pdf_bytes: bytes,
) -> list[dict[str, Any]]:

    document = pymupdf.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    pages = []

    for page_number, page in enumerate(
        document,
        start=1,
    ):

        try:
            text = page.get_text(
                "text"
            )
        except Exception:
            text = ""

        try:
            words = page.get_text(
                "words"
            )
        except Exception:
            words = []

        try:
            blocks = page.get_text(
                "blocks"
            )
        except Exception:
            blocks = []

        pages.append(
            {
                "number": page_number,
                "text": text,
                "words": words,
                "blocks": blocks,
            }
        )

    document.close()

    return pages


def count_codes(
    pages: list[dict[str, Any]],
) -> int:

    total = 0

    for page in pages:

        total += len(
            re.findall(
                r"(?<!\d)\d{6}(?!\d)",
                page.get(
                    "text",
                    "",
                ),
            )
        )

    return total


# ============================================================
# TEXT PARSER
# ============================================================

def remove_code_noise(
    text: str,
) -> str:

    text = normalize_space(
        text
    )

    text = re.sub(
        r"(?<!\d)\d{6}(?!\d)",
        " ",
        text,
    )

    text = re.sub(
        r"(?<!\d)\d{4}(?!\d)",
        " ",
        text,
    )

    text = re.sub(
        r"\b\d+(?:[.,/]\d+)+\b",
        " ",
        text,
    )

    return normalize_space(
        text
    )


def parse_text(
    text: str,
    country_code: str,
) -> list[dict[str, Any]]:

    records = []

    lines = [
        normalize_space(line)
        for line in (
            text or ""
        ).splitlines()
    ]

    lines = [
        line
        for line in lines
        if line
    ]

    for index, line in enumerate(
        lines
    ):

        matches = list(
            re.finditer(
                r"(?<!\d)(\d{6})(?!\d)",
                line,
            )
        )

        if not matches:
            continue

        for match in matches:

            code = match.group(1)

            before = (
                remove_code_noise(
                    line[
                        :match.start()
                    ]
                )
            )

            after = (
                remove_code_noise(
                    line[
                        match.end():
                    ]
                )
            )

            russian = ""
            latin = ""

            if valid_name(before):
                russian = before

            if valid_name(after):
                if is_latin_name(after):
                    latin = after

            # Swap if columns are reversed.
            if (
                is_latin_name(russian)
                and is_cyrillic_name(after)
            ):

                russian = after
                latin = before

            # Look around neighbouring lines.
            if not russian or not latin:

                for offset in (
                    -2,
                    -1,
                    1,
                    2,
                ):

                    pos = (
                        index + offset
                    )

                    if (
                        pos < 0
                        or pos >= len(lines)
                    ):
                        continue

                    candidate = (
                        remove_code_noise(
                            lines[pos]
                        )
                    )

                    if not valid_name(
                        candidate
                    ):
                        continue

                    if (
                        not russian
                        and is_cyrillic_name(
                            candidate
                        )
                    ):
                        russian = candidate

                    if (
                        not latin
                        and is_latin_name(
                            candidate
                        )
                    ):
                        latin = candidate

            if not russian:
                continue

            if not latin:
                latin = russian

            record = make_record(
                country_code,
                code,
                russian,
                latin,
            )

            if record:
                records.append(
                    record
                )

    return deduplicate_records(
        records
    )


# ============================================================
# WORD PARSER
# ============================================================

def words_to_lines(
    words: list[tuple],
) -> list[str]:

    if not words:
        return []

    prepared = []

    for word in words:

        if len(word) < 5:
            continue

        x0, y0, x1, y1, text = (
            word[:5]
        )

        text = normalize_space(
            text
        )

        if not text:
            continue

        prepared.append(
            (
                float(x0),
                float(y0),
                text,
            )
        )

    prepared.sort(
        key=lambda item: (
            round(item[1], 1),
            item[0],
        )
    )

    groups = []

    for word in prepared:

        placed = False

        for group in reversed(
            groups[-8:]
        ):

            avg_y = (
                sum(
                    item[1]
                    for item in group
                )
                / len(group)
            )

            if abs(
                word[1] - avg_y
            ) <= 4:

                group.append(
                    word
                )

                placed = True
                break

        if not placed:
            groups.append(
                [word]
            )

    lines = []

    for group in groups:

        group.sort(
            key=lambda item: item[0]
        )

        lines.append(
            normalize_space(
                " ".join(
                    item[2]
                    for item in group
                )
            )
        )

    return lines


def parse_words(
    words: list[tuple],
    country_code: str,
) -> list[dict[str, Any]]:

    lines = words_to_lines(
        words
    )

    return parse_text(
        "\n".join(lines),
        country_code,
    )


# ============================================================
# BLOCK PARSER
# ============================================================

def parse_blocks(
    blocks: list[tuple],
    country_code: str,
) -> list[dict[str, Any]]:

    lines = []

    for block in blocks:

        if len(block) < 5:
            continue

        text = normalize_space(
            block[4]
        )

        if text:
            lines.append(
                text
            )

    return parse_text(
        "\n".join(lines),
        country_code,
    )


# ============================================================
# PDFTOTEXT
# ============================================================

def extract_pdftotext(
    pdf_bytes: bytes,
) -> str:

    executable = shutil.which(
        "pdftotext"
    )

    if not executable:

        print(
            "pdftotext is not installed."
        )

        return ""

    with tempfile.TemporaryDirectory() as tmp:

        pdf_path = (
            Path(tmp)
            / "source.pdf"
        )

        txt_path = (
            Path(tmp)
            / "source.txt"
        )

        pdf_path.write_bytes(
            pdf_bytes
        )

        command = [
            executable,
            "-layout",
            "-enc",
            "UTF-8",
            str(pdf_path),
            str(txt_path),
        ]

        try:

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180,
            )

            if (
                result.returncode != 0
                or not txt_path.exists()
            ):

                print(
                    "pdftotext failed."
                )

                return ""

            text = txt_path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            print(
                "pdftotext characters:",
                len(text),
            )

            return text

        except Exception as exc:

            print(
                "pdftotext ERROR:",
                repr(exc),
            )

            return ""


# ============================================================
# OCR
# ============================================================

def tesseract_available() -> bool:

    executable = shutil.which(
        "tesseract"
    )

    if executable:

        print(
            "Tesseract:",
            executable,
        )

        return True

    print(
        "Tesseract is NOT installed."
    )

    return False


def render_page_for_ocr(
    page: Any,
    dpi: int = 250,
):
    matrix = pymupdf.Matrix(
        dpi / 72,
        dpi / 72,
    )

    pixmap = page.get_pixmap(
        matrix=matrix,
        alpha=False,
    )

    return pixmap


def run_tesseract(
    image_path: Path,
) -> str:

    executable = shutil.which(
        "tesseract"
    )

    if not executable:
        return ""

    commands = [
        [
            executable,
            str(image_path),
            "stdout",
            "-l",
            "rus+eng",
            "--psm",
            "6",
        ],
        [
            executable,
            str(image_path),
            "stdout",
            "-l",
            "rus+eng",
            "--psm",
            "11",
        ],
    ]

    for command in commands:

        try:

            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180,
            )

            if result.returncode == 0:

                text = normalize_space(
                    result.stdout
                )

                if text:
                    return text

        except Exception as exc:

            print(
                "Tesseract ERROR:",
                repr(exc),
            )

    return ""


def extract_ocr_text(
    pdf_bytes: bytes,
) -> str:

    if not tesseract_available():
        return ""

    print()
    print("=" * 70)
    print("OCR FALLBACK")
    print("=" * 70)

    document = pymupdf.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    all_text = []

    with tempfile.TemporaryDirectory() as tmp:

        tmp_dir = Path(tmp)

        for page_number, page in enumerate(
            document,
            start=1,
        ):

            print(
                f"OCR page "
                f"{page_number}/"
                f"{len(document)}"
            )

            try:

                pixmap = (
                    render_page_for_ocr(
                        page,
                        dpi=250,
                    )
                )

                image_path = (
                    tmp_dir
                    / f"page_{page_number}.png"
                )

                pixmap.save(
                    str(image_path)
                )

                text = run_tesseract(
                    image_path
                )

                if text:

                    print(
                        "  OCR chars:",
                        len(text),
                    )

                    all_text.append(
                        text
                    )

                else:

                    print(
                        "  OCR returned "
                        "no text"
                    )

            except Exception as exc:

                print(
                    "  OCR page ERROR:",
                    repr(exc),
                )

    document.close()

    result = "\n".join(
        all_text
    )

    print()
    print(
        "TOTAL OCR CHARACTERS:",
        len(result),
    )

    return result


# ============================================================
# RECORD
# ============================================================

def make_record(
    country_code: str,
    code: str,
    russian_name: str,
    latin_name: str,
) -> dict[str, Any] | None:

    code = normalize_code(
        code
    )

    if not code:
        return None

    russian_name = clean_name(
        russian_name
    )

    latin_name = clean_name(
        latin_name
    )

    if not valid_name(
        russian_name
    ):
        return None

    if not valid_name(
        latin_name
    ):
        latin_name = russian_name

    return {
        "name": russian_name,
        "code": code,
        "country": COUNTRIES[
            country_code
        ],
        "country_code": country_code,
        "latin_name": latin_name,
    }


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    result = []

    seen = set()

    for record in records:

        country = record.get(
            "country_code"
        )

        code = normalize_code(
            record.get(
                "code"
            )
        )

        if not country or not code:
            continue

        key = (
            country,
            code,
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            record
        )

    return result


# ============================================================
# PARSE ONE PDF
# ============================================================

def parse_pdf(
    pdf_bytes: bytes,
    country_code: str,
) -> list[dict[str, Any]]:

    print()
    print("=" * 70)
    print(
        "PARSING:",
        country_code,
        COUNTRIES[country_code],
    )
    print("=" * 70)

    pages = extract_pdf_pages(
        pdf_bytes
    )

    print(
        "PDF pages:",
        len(pages),
    )

    text_codes = count_codes(
        pages
    )

    print(
        "6-digit codes in text:",
        text_codes,
    )

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    records = []

    for page in pages:

        page_records = parse_text(
            page["text"],
            country_code,
        )

        records.extend(
            page_records
        )

    records = deduplicate_records(
        records
    )

    print(
        "TEXT PARSER:",
        len(records),
    )

    # --------------------------------------------------------
    # WORDS
    # --------------------------------------------------------

    if len(records) < 3:

        word_records = []

        for page in pages:

            word_records.extend(
                parse_words(
                    page["words"],
                    country_code,
                )
            )

        word_records = (
            deduplicate_records(
                word_records
            )
        )

        print(
            "WORD PARSER:",
            len(word_records),
        )

        records.extend(
            word_records
        )

        records = deduplicate_records(
            records
        )

    # --------------------------------------------------------
    # BLOCKS
    # --------------------------------------------------------

    if len(records) < 3:

        block_records = []

        for page in pages:

            block_records.extend(
                parse_blocks(
                    page["blocks"],
                    country_code,
                )
            )

        block_records = (
            deduplicate_records(
                block_records
            )
        )

        print(
            "BLOCK PARSER:",
            len(block_records),
        )

        records.extend(
            block_records
        )

        records = deduplicate_records(
            records
        )

    # --------------------------------------------------------
    # PDFTOTEXT
    # --------------------------------------------------------

    if len(records) < 3:

        print()
        print(
            "Trying pdftotext..."
        )

        text = extract_pdftotext(
            pdf_bytes
        )

        if text:

            poppler_records = (
                parse_text(
                    text,
                    country_code,
                )
            )

            print(
                "POPPLER PARSER:",
                len(
                    poppler_records
                ),
            )

            records.extend(
                poppler_records
            )

            records = (
                deduplicate_records(
                    records
                )
            )

    # --------------------------------------------------------
    # OCR
    # --------------------------------------------------------

    if len(records) < 3:

        print()
        print(
            "Text extraction produced "
            "too few records."
        )

        print(
            "Trying OCR..."
        )

        ocr_text = (
            extract_ocr_text(
                pdf_bytes
            )
        )

        if ocr_text:

            ocr_records = parse_text(
                ocr_text,
                country_code,
            )

            print(
                "OCR PARSER:",
                len(ocr_records),
            )

            records.extend(
                ocr_records
            )

            records = (
                deduplicate_records(
                    records
                )
            )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    records = deduplicate_records(
        records
    )

    print()
    print(
        "FINAL PARSED RECORDS:",
        len(records),
    )

    if records:

        print()
        print(
            "FIRST RECORDS:"
        )

        for record in records[:10]:

            print(
                " ",
                record
            )

    return records


# ============================================================
# COUNTRY VALIDATION
# ============================================================

def validate_country_records(
    country_code: str,
    records: list[dict[str, Any]],
) -> None:

    if not records:

        raise RuntimeError(
            f"{country_code}: "
            "не найдено ни одной станции"
        )

    for record in records:

        if not re.fullmatch(
            r"\d{6}",
            str(
                record.get(
                    "code",
                    "",
                )
            ),
        ):

            raise RuntimeError(
                f"{country_code}: "
                "invalid station code"
            )

        if not valid_name(
            record.get(
                "name",
                "",
            )
        ):

            raise RuntimeError(
                f"{country_code}: "
                "invalid station name"
            )

    print(
        f"✓ {country_code}: "
        f"validation passed"
    )


# ============================================================
# EXISTING DATABASE
# ============================================================

def load_existing_database() -> list[
    dict[str, Any]
]:

    if not OUTPUT_FILE.exists():
        return []

    try:

        with OUTPUT_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        if isinstance(
            data,
            list,
        ):

            return data

    except Exception as exc:

        print(
            "WARNING reading stations.json:",
            repr(exc),
        )

    return []


# ============================================================
# MERGE
# ============================================================

def merge_records(
    new_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    existing = (
        load_existing_database()
    )

    new_countries = {
        record.get(
            "country_code"
        )
        for record in new_records
    }

    result = []

    for record in existing:

        country = record.get(
            "country_code"
        )

        if country in EXCLUDED_COUNTRIES:
            continue

        if country in new_countries:
            continue

        if country not in COUNTRIES:
            continue

        result.append(
            record
        )

    result.extend(
        new_records
    )

    return deduplicate_records(
        result
    )


# ============================================================
# GLOBAL VALIDATION
# ============================================================

def validate_all_countries(
    stations: list[dict[str, Any]],
) -> None:

    print()
    print("=" * 70)
    print("FINAL DATABASE VALIDATION")
    print("=" * 70)

    counters = Counter(
        station.get(
            "country_code",
            "",
        )
        for station in stations
    )

    missing = []

    for code, country in (
        COUNTRIES.items()
    ):

        count = counters.get(
            code,
            0,
        )

        if count:

            print(
                f"✓ {code:2} "
                f"{country:<25} "
                f"{count:6}"
            )

        else:

            print(
                f"✗ {code:2} "
                f"{country:<25} "
                f"{0:6}"
            )

            missing.append(
                code
            )

    if missing:

        raise RuntimeError(
            "Нет данных по странам: "
            + ", ".join(
                missing
            )
        )

    unexpected = sorted(
        set(counters)
        - set(COUNTRIES)
    )

    if unexpected:

        raise RuntimeError(
            "Неизвестные country_code: "
            + ", ".join(
                unexpected
            )
        )

    excluded = sorted(
        set(counters)
        & EXCLUDED_COUNTRIES
    )

    if excluded:

        raise RuntimeError(
            "В базе остались исключённые страны: "
            + ", ".join(
                excluded
            )
        )

    invalid_codes = [
        station
        for station in stations
        if not re.fullmatch(
            r"\d{6}",
            str(
                station.get(
                    "code",
                    "",
                )
            ),
        )
    ]

    print()
    print(
        "Total stations:",
        len(stations),
    )

    print(
        "Invalid codes:",
        len(invalid_codes),
    )

    if invalid_codes:

        raise RuntimeError(
            "Обнаружены некорректные коды."
        )

    duplicate_keys = []

    seen = set()

    for station in stations:

        key = (
            station.get(
                "country_code"
            ),
            station.get(
                "code"
            ),
        )

        if key in seen:

            duplicate_keys.append(
                key
            )

        seen.add(
            key
        )

    print(
        "Duplicate records:",
        len(duplicate_keys),
    )

    if duplicate_keys:

        raise RuntimeError(
            "Обнаружены дубликаты."
        )

    print()
    print(
        "✓ FINAL VALIDATION PASSED"
    )


# ============================================================
# SAVE
# ============================================================

def save_database(
    stations: list[dict[str, Any]],
) -> None:

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = (
        OUTPUT_FILE.with_suffix(
            ".json.tmp"
        )
    )

    with temp_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            stations,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")

    temp_file.replace(
        OUTPUT_FILE
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print()
    print("=" * 70)
    print("OSJD RAILWAY STATION DATABASE UPDATE")
    print("=" * 70)

    print()
    print(
        "Target countries:",
        len(COUNTRIES),
    )

    print(
        "Excluded:",
        ", ".join(
            sorted(
                EXCLUDED_COUNTRIES
            )
        ),
    )

    print(
        "Output:",
        OUTPUT_FILE,
    )

    # --------------------------------------------------------
    # SOURCES
    # --------------------------------------------------------

    pdf_urls = get_pdf_urls()

    print()
    print("=" * 70)
    print("PDF SOURCES")
    print("=" * 70)

    for code, country in (
        COUNTRIES.items()
    ):

        url = pdf_urls.get(
            code
        )

        if url:

            print(
                f"✓ {code} "
                f"{country}"
            )

            print(
                f"  {url}"
            )

        else:

            print(
                f"✗ {code} "
                f"{country}: NO SOURCE"
            )

    missing_sources = [
        code
        for code in COUNTRIES
        if not pdf_urls.get(
            code
        )
    ]

    if missing_sources:

        raise RuntimeError(
            "Не найдены PDF: "
            + ", ".join(
                missing_sources
            )
        )

    # --------------------------------------------------------
    # ALL COUNTRIES
    # --------------------------------------------------------

    all_records = []

    statistics = {}

    for country_code, country_name in (
        COUNTRIES.items()
    ):

        print()
        print("=" * 70)
        print(
            f"COUNTRY: "
            f"{country_code} — "
            f"{country_name}"
        )
        print("=" * 70)

        try:

            pdf_bytes = download_pdf(
                pdf_urls[
                    country_code
                ]
            )

            records = parse_pdf(
                pdf_bytes,
                country_code,
            )

            records = (
                deduplicate_records(
                    records
                )
            )

            validate_country_records(
                country_code,
                records,
            )

            statistics[
                country_code
            ] = len(records)

            all_records.extend(
                records
            )

            print()
            print(
                f"✓ SUCCESS "
                f"{country_code}: "
                f"{len(records)} stations"
            )

        except Exception as exc:

            print()
            print("=" * 70)
            print(
                f"✗ ERROR {country_code}"
            )
            print("=" * 70)

            print(
                repr(exc)
            )

            raise RuntimeError(
                f"Ошибка обработки "
                f"{country_code} "
                f"{country_name}: "
                f"{exc}"
            ) from exc

        time.sleep(
            0.5
        )

    # --------------------------------------------------------
    # COUNTRY COVERAGE
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("COUNTRY COVERAGE")
    print("=" * 70)

    for code, country in (
        COUNTRIES.items()
    ):

        count = statistics.get(
            code,
            0,
        )

        print(
            f"{'✓' if count else '✗'} "
            f"{code:2} "
            f"{country:<25} "
            f"{count:6}"
        )

    missing = [
        code
        for code in COUNTRIES
        if not statistics.get(
            code,
            0,
        )
    ]

    if missing:

        raise RuntimeError(
            "Нет данных по странам: "
            + ", ".join(
                missing
            )
        )

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    merged = merge_records(
        all_records
    )

    print()
    print("=" * 70)
    print("MERGED DATABASE")
    print("=" * 70)

    print(
        "New records:",
        len(all_records),
    )

    print(
        "Final records:",
        len(merged),
    )

    # --------------------------------------------------------
    # VALIDATE
    # --------------------------------------------------------

    validate_all_countries(
        merged
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SAVING DATABASE")
    print("=" * 70)

    save_database(
        merged
    )

    print()
    print("=" * 70)
    print("SUCCESS")
    print("=" * 70)

    print(
        "stations.json updated."
    )

    print(
        "Total records:",
        len(merged),
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "Interrupted by user."
        )

        sys.exit(130)

    except Exception as exc:

        print()
        print("=" * 70)
        print("FATAL ERROR")
        print("=" * 70)

        print(
            str(exc)
        )

        print()
        print(
            "stations.json НЕ изменён."
        )

        sys.exit(1)
