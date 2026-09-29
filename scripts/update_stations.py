#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OSJD railway station database updater.

Обрабатываются 22 страны.

ИСКЛЮЧЕНЫ:
IR — Иран
CN — Китай
CZ — Чехия
KR — Республика Корея
RO — Румыния
LA — Лаос

Главный принцип:
stations.json изменяется только после успешного получения
и проверки данных по всем 22 странам.
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
# TARGET COUNTRIES
# ============================================================

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


# ============================================================
# COUNTRY ALIASES
# ============================================================

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
# KNOWN OSJD PDF RESOURCES
# ============================================================

KNOWN_RESOURCES = {
    "IR": 9608,
    "CN": 1537,
    "KR": 1637529,
    "RO": 2813,
    "CZ": 3904,
    "EE": 1671839,
}


# ============================================================
# TEXT HELPERS
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

    text = normalize_space(text)

    return text


def contains_letters(value: str) -> bool:
    return bool(
        re.search(
            r"[A-Za-zА-Яа-яЁё]",
            value,
        )
    )


def is_noise_name(value: str) -> bool:
    text = clean_name(value)

    if not text:
        return True

    if len(text) < 2:
        return True

    lower = text.lower()

    noise_fragments = [
        "наименование станции",
        "код станции",
        "код погранич",
        "производимые коммерческие",
        "коммерческие операции",
        "коммерческими операциями",
        "операции",
        "страница",
        "содержание",
        "перечень грузовых станций",
        "перечень станций",
        "железной дороги",
        "железных дорог",
        "железная дорога",
        "код ",
        "наименование",
        "station name",
        "station code",
        "commercial operations",
        "railway station",
        "railway",
    ]

    if any(
        fragment in lower
        for fragment in noise_fragments
    ):
        return True

    if re.fullmatch(
        r"[\d\s.,;:/()\-–—]+",
        text,
    ):
        return True

    if len(text) > 180:
        return True

    return False


def valid_name(value: Any) -> bool:
    text = clean_name(value)

    if is_noise_name(text):
        return False

    if not contains_letters(text):
        return False

    if len(text) > 180:
        return False

    return True


def latin_score(value: str) -> int:
    text = clean_name(value)

    if not text:
        return -100

    score = 0

    if re.search(
        r"[A-Za-z]",
        text,
    ):
        score += 20

    if re.search(
        r"[А-Яа-яЁё]",
        text,
    ):
        score += 5

    if 2 <= len(text) <= 100:
        score += 10

    if any(
        word in text.lower()
        for word in [
            "railway",
            "station",
            "stantsiya",
        ]
    ):
        score -= 10

    return score


# ============================================================
# URL HELPERS
# ============================================================

def normalize_osjd_pdf_url(url: str) -> str:
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


def resource_url(resource_id: int) -> str:
    return (
        "https://osjd.org/api/media/resources/"
        f"{resource_id}?action=download"
    )


def extract_resource_id(
    value: str,
) -> str | None:

    match = re.search(
        r"/api/media/resources/(\d+)",
        value or "",
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1)

    return None


# ============================================================
# HTTP DOWNLOAD
# ============================================================

def request_url(
    url: str,
) -> requests.Response:

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response


def download_pdf(
    url: str,
) -> bytes:

    url = normalize_osjd_pdf_url(url)

    print()
    print("-" * 70)
    print("DOWNLOAD PDF")
    print(url)

    response = request_url(url)

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

    if (
        response.content.startswith(
            b"%PDF"
        )
        or "pdf" in content_type
    ):
        print("✓ PDF RECEIVED")

        return response.content

    # --------------------------------------------------------
    # TRY TO FIND PDF URL INSIDE HTML
    # --------------------------------------------------------

    html = response.text

    patterns = [
        r"https?://osjd\.org/api/media/resources/\d+(?:\?[^\"'<>\s]*)?",
        r"/api/media/resources/\d+(?:\?[^\"'<>\s]*)?",
        r"[?&]file=(/api/media/resources/\d+(?:\?[^\"'<>\s]*)?)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        direct = (
            match.group(1)
            if match.lastindex
            else match.group(0)
        )

        direct = normalize_osjd_pdf_url(
            direct
        )

        if not direct:
            continue

        if direct == url:
            continue

        print(
            "RECOVERED PDF URL:"
        )

        print(direct)

        pdf_response = request_url(
            direct
        )

        pdf_type = (
            pdf_response
            .headers
            .get(
                "content-type",
                "",
            )
            .lower()
        )

        print(
            "RECOVERED STATUS:",
            pdf_response.status_code,
        )

        print(
            "RECOVERED TYPE:",
            pdf_type,
        )

        print(
            "RECOVERED SIZE:",
            len(pdf_response.content),
        )

        if (
            pdf_response.content.startswith(
                b"%PDF"
            )
            or "pdf" in pdf_type
        ):
            print(
                "✓ PDF RECEIVED AFTER RECOVERY"
            )

            return pdf_response.content

    raise RuntimeError(
        "OSJD URL did not return a PDF: "
        + url
    )


# ============================================================
# DISCOVER OSJD PDF LINKS
# ============================================================

def discover_osjd_links() -> dict[str, str]:

    print()
    print("=" * 70)
    print("DISCOVERING OSJD PDF LINKS")
    print("=" * 70)

    print(
        "OSJD PAGE:",
        OSJD_PAGE,
    )

    response = request_url(
        OSJD_PAGE
    )

    print(
        "HTTP STATUS:",
        response.status_code,
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    result: dict[str, str] = {}

    # --------------------------------------------------------
    # NORMAL LINKS
    # --------------------------------------------------------

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

        full_href = urljoin(
            "https://osjd.org",
            href,
        )

        combined = (
            f"{text} {href} {full_href}"
        ).lower()

        if (
            "api/media/resources"
            not in combined
            and ".pdf"
            not in combined
            and "file=" not in combined
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

                normalized = (
                    normalize_osjd_pdf_url(
                        full_href
                    )
                )

                if normalized:

                    result[code] = normalized

                    print(
                        f"FOUND {code}: "
                        f"{COUNTRIES[code]}"
                    )

                    print(
                        f"  {normalized}"
                    )

                    break

    # --------------------------------------------------------
    # SEARCH RAW HTML FOR RESOURCE IDS
    # --------------------------------------------------------

    raw_html = unquote(
        response.text
    )

    resource_matches = re.findall(
        r"(?:/api/media/resources/|resources/)(\d+)",
        raw_html,
        flags=re.IGNORECASE,
    )

    resource_matches = list(
        dict.fromkeys(
            resource_matches
        )
    )

    print()
    print(
        "RESOURCE IDS FOUND IN HTML:",
        len(resource_matches),
    )

    return result


# ============================================================
# GET PDF URLS
# ============================================================

def get_pdf_urls() -> dict[str, str]:

    discovered = (
        discover_osjd_links()
    )

    result: dict[str, str] = {}

    for code in COUNTRIES:

        if code in discovered:

            result[code] = (
                normalize_osjd_pdf_url(
                    discovered[code]
                )
            )

    # --------------------------------------------------------
    # KNOWN RESOURCE FALLBACK
    # --------------------------------------------------------

    for code, resource_id in (
        KNOWN_RESOURCES.items()
    ):

        if code not in COUNTRIES:
            continue

        if code in result:
            continue

        result[code] = resource_url(
            resource_id
        )

        print()
        print(
            f"FALLBACK {code}: "
            f"resource {resource_id}"
        )

        print(
            result[code]
        )

    return result


# ============================================================
# PDF TEXT EXTRACTION
# ============================================================

def extract_pages(
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

        page_text = ""

        try:
            page_text = page.get_text(
                "text"
            )
        except Exception:
            page_text = ""

        blocks = []

        try:
            blocks = page.get_text(
                "blocks"
            )
        except Exception:
            blocks = []

        words = []

        try:
            words = page.get_text(
                "words"
            )
        except Exception:
            words = []

        dictionary = {}

        try:
            dictionary = page.get_text(
                "dict"
            )
        except Exception:
            dictionary = {}

        pages.append(
            {
                "number": page_number,
                "text": page_text,
                "blocks": blocks,
                "words": words,
                "dict": dictionary,
            }
        )

    document.close()

    return pages


# ============================================================
# CODE EXTRACTION
# ============================================================

CODE_RE = re.compile(
    r"(?<!\d)\d{6}(?!\d)"
)


def find_codes(
    text: str,
) -> list[str]:

    return [
        match.group(1)
        for match in re.finditer(
            r"(?<!\d)(\d{6})(?!\d)",
            text or "",
        )
    ]


# ============================================================
# WORD LINES
# ============================================================

def words_to_lines(
    words: list[tuple],
) -> list[dict[str, Any]]:

    if not words:
        return []

    prepared = []

    for word in words:

        if len(word) < 5:
            continue

        x0, y0, x1, y1, text = word[:5]

        text = normalize_space(
            text
        )

        if not text:
            continue

        prepared.append(
            (
                float(x0),
                float(y0),
                float(x1),
                float(y1),
                text,
            )
        )

    prepared.sort(
        key=lambda item: (
            round(item[1], 1),
            item[0],
        )
    )

    groups: list[list[tuple]] = []

    for word in prepared:

        placed = False

        for group in reversed(
            groups[-10:]
        ):

            avg_y = sum(
                item[1]
                for item in group
            ) / len(group)

            if abs(
                word[1] - avg_y
            ) <= 4.0:

                group.append(word)
                placed = True
                break

        if not placed:
            groups.append(
                [word]
            )

    result = []

    for group in groups:

        group.sort(
            key=lambda item: item[0]
        )

        text = normalize_space(
            " ".join(
                item[4]
                for item in group
            )
        )

        result.append(
            {
                "words": group,
                "text": text,
            }
        )

    return result


# ============================================================
# NAME CANDIDATES
# ============================================================

def remove_table_noise(
    text: str,
) -> str:

    text = normalize_space(text)

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

    text = normalize_space(text)

    return text


def candidate_name_from_text(
    text: str,
) -> str:

    text = remove_table_noise(
        text
    )

    text = clean_name(text)

    if not valid_name(text):
        return ""

    # Не берём слишком длинные куски.
    words = text.split()

    if len(words) > 10:
        words = words[-10:]

        text = normalize_space(
            " ".join(words)
        )

    return text


# ============================================================
# PARSER: WORDS
# ============================================================

def parse_words(
    words: list[tuple],
    country_code: str,
) -> list[dict[str, Any]]:

    records = []

    lines = words_to_lines(
        words
    )

    for line_index, line in enumerate(
        lines
    ):

        row = line["words"]

        full_text = line["text"]

        codes = find_codes(
            full_text
        )

        if not codes:
            continue

        # ----------------------------------------------------
        # FIRST TRY: SAME LINE
        # ----------------------------------------------------

        for code in codes:

            code_pos = full_text.find(
                code
            )

            left = full_text[
                :code_pos
            ]

            right = full_text[
                code_pos + len(code):
            ]

            left_name = (
                candidate_name_from_text(
                    left
                )
            )

            right_name = (
                candidate_name_from_text(
                    right
                )
            )

            russian = ""
            latin = ""

            if left_name:
                russian = left_name

            if right_name:

                if re.search(
                    r"[A-Za-z]",
                    right_name,
                ):
                    latin = right_name

            # ------------------------------------------------
            # IF LEFT IS LATIN AND RIGHT IS RUSSIAN,
            # SWAP THEM
            # ------------------------------------------------

            if (
                russian
                and re.search(
                    r"[A-Za-z]",
                    russian,
                )
                and re.search(
                    r"[А-Яа-яЁё]",
                    right_name,
                )
            ):

                russian = right_name
                latin = left_name

            # ------------------------------------------------
            # LOOK AROUND NEIGHBOURING LINES
            # ------------------------------------------------

            if (
                not russian
                or not latin
            ):

                nearby = []

                start = max(
                    0,
                    line_index - 2,
                )

                end = min(
                    len(lines),
                    line_index + 3,
                )

                for idx in range(
                    start,
                    end,
                ):

                    if idx == line_index:
                        continue

                    nearby.append(
                        lines[idx]["text"]
                    )

                for neighbour in nearby:

                    neighbour_clean = (
                        candidate_name_from_text(
                            neighbour
                        )
                    )

                    if not neighbour_clean:
                        continue

                    if (
                        not russian
                        and re.search(
                            r"[А-Яа-яЁё]",
                            neighbour_clean,
                        )
                    ):
                        russian = neighbour_clean

                    if (
                        not latin
                        and re.search(
                            r"[A-Za-z]",
                            neighbour_clean,
                        )
                    ):
                        latin = neighbour_clean

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
# PARSER: RAW TEXT
# ============================================================

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

            before = line[
                :match.start()
            ]

            after = line[
                match.end():
            ]

            before_name = (
                candidate_name_from_text(
                    before
                )
            )

            after_name = (
                candidate_name_from_text(
                    after
                )
            )

            russian = ""
            latin = ""

            if before_name:
                russian = before_name

            if after_name:
                if re.search(
                    r"[A-Za-z]",
                    after_name,
                ):
                    latin = after_name

            if (
                russian
                and re.search(
                    r"[A-Za-z]",
                    russian,
                )
                and re.search(
                    r"[А-Яа-яЁё]",
                    after_name,
                )
            ):

                russian = after_name
                latin = before_name

            # ------------------------------------------------
            # NEIGHBOURING LINES
            # ------------------------------------------------

            nearby = []

            for offset in (
                -2,
                -1,
                1,
                2,
            ):

                pos = index + offset

                if (
                    pos < 0
                    or pos >= len(lines)
                ):
                    continue

                nearby.append(
                    lines[pos]
                )

            for neighbour in nearby:

                candidate = (
                    candidate_name_from_text(
                        neighbour
                    )
                )

                if not candidate:
                    continue

                if (
                    not russian
                    and re.search(
                        r"[А-Яа-яЁё]",
                        candidate,
                    )
                ):
                    russian = candidate

                if (
                    not latin
                    and re.search(
                        r"[A-Za-z]",
                        candidate,
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
# PARSER: BLOCKS
# ============================================================

def parse_blocks(
    blocks: list[tuple],
    country_code: str,
) -> list[dict[str, Any]]:

    text_parts = []

    for block in blocks:

        if len(block) < 5:
            continue

        text = normalize_space(
            block[4]
        )

        if text:
            text_parts.append(
                text
            )

    combined = "\n".join(
        text_parts
    )

    return parse_text(
        combined,
        country_code,
    )


# ============================================================
# POPPLER FALLBACK
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

        commands = [
            [
                executable,
                "-layout",
                "-enc",
                "UTF-8",
                str(pdf_path),
                str(txt_path),
            ],
            [
                executable,
                "-enc",
                "UTF-8",
                str(pdf_path),
                str(txt_path),
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

                if (
                    result.returncode == 0
                    and txt_path.exists()
                ):

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
# RECORD CREATION
# ============================================================

def make_record(
    country_code: str,
    code: str,
    russian_name: str,
    latin_name: str,
    operations: str = "",
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

    # --------------------------------------------------------
    # Latin name is allowed to fall back to Russian name.
    # This prevents loss of valid station records when the
    # OSJD PDF contains only one station-name column.
    # --------------------------------------------------------

    if not valid_name(
        latin_name
    ):
        latin_name = russian_name

    record = {
        "name": russian_name,
        "code": code,
        "country": COUNTRIES[
            country_code
        ],
        "country_code": country_code,
        "latin_name": latin_name,
    }

    if operations:
        record["operations"] = (
            normalize_space(
                operations
            )
        )

    return record


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    result = []

    seen = set()

    for record in records:

        code = normalize_code(
            record.get(
                "code"
            )
        )

        country = record.get(
            "country_code"
        )

        if not code or not country:
            continue

        key = (
            country,
            code,
        )

        if key in seen:
            continue

        seen.add(key)

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

    pages = extract_pages(
        pdf_bytes
    )

    print(
        "PDF pages:",
        len(pages),
    )

    total_codes = 0

    for page in pages:

        total_codes += len(
            find_codes(
                page["text"]
            )
        )

    print(
        "6-digit codes in text:",
        total_codes,
    )

    # --------------------------------------------------------
    # WORDS PARSER
    # --------------------------------------------------------

    records = []

    for page in pages:

        page_records = parse_words(
            page["words"],
            country_code,
        )

        records.extend(
            page_records
        )

    records = deduplicate_records(
        records
    )

    print(
        "WORD PARSER:",
        len(records),
    )

    # --------------------------------------------------------
    # RAW TEXT PARSER
    # --------------------------------------------------------

    if len(records) < 3:

        text_records = []

        for page in pages:

            page_records = parse_text(
                page["text"],
                country_code,
            )

            text_records.extend(
                page_records
            )

        text_records = (
            deduplicate_records(
                text_records
            )
        )

        print(
            "TEXT PARSER:",
            len(text_records),
        )

        records.extend(
            text_records
        )

        records = deduplicate_records(
            records
        )

    # --------------------------------------------------------
    # BLOCK PARSER
    # --------------------------------------------------------

    if len(records) < 3:

        block_records = []

        for page in pages:

            page_records = parse_blocks(
                page["blocks"],
                country_code,
            )

            block_records.extend(
                page_records
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
    # POPPLER
    # --------------------------------------------------------

    if len(records) < 3:

        print()
        print(
            "PyMuPDF parsers found too few "
            "records."
        )

        print(
            "Trying pdftotext fallback..."
        )

        poppler_text = (
            extract_pdftotext(
                pdf_bytes
            )
        )

        if poppler_text:

            poppler_records = (
                parse_text(
                    poppler_text,
                    country_code,
                )
            )

            print(
                "POPPLER PARSER:",
                len(poppler_records),
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
                record,
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

    invalid = []

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
            invalid.append(
                record
            )

    if invalid:

        raise RuntimeError(
            f"{country_code}: "
            f"{len(invalid)} invalid codes"
        )

    for record in records:

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
        f"country validation passed"
    )


# ============================================================
# LOAD EXISTING DATABASE
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
            "WARNING: cannot read existing "
            "stations.json:",
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

        # Remove explicitly excluded countries.
        if country in EXCLUDED_COUNTRIES:
            continue

        # Replace countries freshly parsed.
        if country in new_countries:
            continue

        # Remove unknown countries.
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

    # --------------------------------------------------------
    # COUNTRY COVERAGE
    # --------------------------------------------------------

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
                f"{count:6}"
            )

            missing.append(
                code
            )

    if missing:

        raise RuntimeError(
            "КРИТИЧЕСКАЯ ОШИБКА: "
            "нет данных по странам: "
            + ", ".join(
                missing
            )
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
            "Обнаружены неизвестные "
            "country_code: "
            + ", ".join(
                unknown
            )
        )

    # --------------------------------------------------------
    # EXCLUDED COUNTRIES
    # --------------------------------------------------------

    excluded = sorted(
        set(counters)
        & EXCLUDED_COUNTRIES
    )

    if excluded:

        raise RuntimeError(
            "В базе остались исключённые "
            "страны: "
            + ", ".join(
                excluded
            )
        )

    # --------------------------------------------------------
    # CODE VALIDATION
    # --------------------------------------------------------

    invalid_codes = []

    for station in stations:

        code = str(
            station.get(
                "code",
                "",
            )
        )

        if not re.fullmatch(
            r"\d{6}",
            code,
        ):
            invalid_codes.append(
                station
            )

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

        for station in invalid_codes[:10]:
            print(
                station
            )

        raise RuntimeError(
            "Обнаружены некорректные "
            "коды станций."
        )

    # --------------------------------------------------------
    # NAMES
    # --------------------------------------------------------

    missing_names = []

    for station in stations:

        if not valid_name(
            station.get(
                "name",
                "",
            )
        ):
            missing_names.append(
                station
            )

    print(
        "Stations without names:",
        len(missing_names),
    )

    if missing_names:

        raise RuntimeError(
            "Есть станции без "
            "корректного названия."
        )

    # --------------------------------------------------------
    # DUPLICATES
    # --------------------------------------------------------

    keys = [
        (
            station.get(
                "country_code"
            ),
            station.get(
                "code"
            ),
        )
        for station in stations
    ]

    duplicate_count = (
        len(keys)
        - len(set(keys))
    )

    print(
        "Duplicate records:",
        duplicate_count,
    )

    if duplicate_count:
        raise RuntimeError(
            "Обнаружены дубликаты "
            "country_code + code."
        )

    print()
    print(
        "✓ FINAL VALIDATION PASSED"
    )


# ============================================================
# SAVE DATABASE
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
    # PDF SOURCES
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
                f"{country}:"
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
            "Не найдены PDF для стран: "
            + ", ".join(
                missing_sources
            )
        )

    # --------------------------------------------------------
    # DOWNLOAD AND PARSE ALL COUNTRIES
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

        url = pdf_urls[
            country_code
        ]

        try:

            pdf_bytes = download_pdf(
                url
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
                f"✗ ERROR "
                f"{country_code}"
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
    # CHECK COUNTRY STATISTICS
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

    missing = [
        code
        for code in COUNTRIES
        if statistics.get(
            code,
            0,
        ) == 0
    ]

    if missing:

        raise RuntimeError(
            "Не получены данные по странам: "
            + ", ".join(
                missing
            )
        )

    # --------------------------------------------------------
    # MERGE WITH EXISTING DATABASE
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
    # FINAL VALIDATION
    # --------------------------------------------------------

    validate_all_countries(
        merged
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SAVING")
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

        print()
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
