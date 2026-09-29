#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""
OSJD railway freight stations parser.

Получает PDF-перечни грузовых станций ОСЖД,
извлекает станции несколькими способами и обновляет
data/stations.json только после успешной проверки
всех 25 стран.

Исключены из проекта:
KR — Республика Корея
RO — Румыния
LA — Лаос
"""

from **future** import annotations

import json
import os
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

import fitz
import requests
from bs4 import BeautifulSoup

# ============================================================

# CONFIG

# ============================================================

BASE_DIR = Path(**file**).resolve().parent.parent
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

```
value = value.replace("\xa0", " ")
value = value.replace("\u200b", "")
value = re.sub(r"\s+", " ", value)

return value.strip()
```

def normalize_code(value: str) -> str | None:
"""
Извлекает ровно 6 цифр.

```
Исправляет варианты:
123 456
123-456
123.456
"""

if not value:
    return None

value = str(value).strip()

if re.fullmatch(r"\d{6}", value):
    return value

digits = re.sub(r"\D", "", value)

if len(digits) == 6:
    return digits

return None
```

def is_noise_name(value: str) -> bool:
if not value:
return True

```
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
```

def clean_station_name(value: str) -> str:
value = normalize_space(value)

```
value = re.sub(r"^[|;:,]+", "", value)
value = re.sub(r"[|;:,]+$", "", value)

value = normalize_space(value)

return value
```

def looks_like_operations(value: str) -> bool:
if not value:
return False

```
text = normalize_space(value)

if re.fullmatch(
    r"[\d,\s./()«»\"'А-Яа-яA-Za-z№#*КкНн\-]+",
    text,
):
    digits = re.findall(r"\d+", text)

    if digits:
        return True

return False
```

def valid_name(value: str) -> bool:
value = clean_station_name(value)

```
if is_noise_name(value):
    return False

if len(value) > 150:
    return False

if not re.search(r"[A-Za-zА-Яа-яЁё]", value):
    return False

return True
```

def score_name(value: str) -> int:
value = clean_station_name(value)

```
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
```

# ============================================================

# OSJD URL NORMALIZATION

# ============================================================

def normalize_osjd_pdf_url(url: str) -> str:
"""
Преобразует URL просмотрщика ОСЖД
в прямой URL media resource.
"""

```
if not url:
    return ""

url = unquote(str(url).strip())
url = url.split("#", 1)[0]

match = re.search(
    r"(?:[?&])file=([^#]+)",
    url,
    flags=re.IGNORECASE,
)

if match:
    file_part = unquote(match.group(1))

    if file_part.startswith(("http://", "https://")):
        url = file_part

    elif file_part.startswith("/"):
        url = urljoin(
            "https://osjd.org",
            file_part,
        )

    else:
        url = urljoin(
            "https://osjd.org/",
            file_part,
        )

    url = url.split("#", 1)[0]

if url.startswith("/"):
    url = urljoin(
        "https://osjd.org",
        url,
    )

return url
```

def find_direct_pdf_url_in_html(html: str) -> str | None:
"""
Ищет прямой media resource внутри HTML-обёртки.
"""

```
html = unquote(html or "")

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

    if match:
        value = (
            match.group(1)
            if match.lastindex
            else match.group(0)
        )

        return normalize_osjd_pdf_url(value)

return None
```

# ============================================================

# HTTP

# ============================================================

def download_pdf(url: str) -> bytes:
"""
Загружает PDF ОСЖД.

```
Если URL отдаёт HTML-обёртку,
пытается найти внутри неё прямой PDF.
"""

url = normalize_osjd_pdf_url(url)

print()
print("-" * 70)
print("DOWNLOAD")
print(url)

response = requests.get(
    url,
    headers=HEADERS,
    timeout=REQUEST_TIMEOUT,
    allow_redirects=True,
)

print("HTTP STATUS:", response.status_code)
print("FINAL URL:", response.url)
print(
    "CONTENT TYPE:",
    response.headers.get("content-type"),
)
print("SIZE:", len(response.content))

response.raise_for_status()

content_type = response.headers.get(
    "content-type",
    "",
).lower()

if (
    "pdf" in content_type
    or response.content.startswith(b"%PDF")
):
    print("✓ PDF RECEIVED")
    return response.content

direct_url = find_direct_pdf_url_in_html(
    response.text
)

if direct_url and direct_url != url:
    print("RECOVERED DIRECT PDF URL:")
    print(direct_url)

    pdf_response = requests.get(
        direct_url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )

    print(
        "PDF HTTP STATUS:",
        pdf_response.status_code,
    )

    print(
        "PDF CONTENT TYPE:",
        pdf_response.headers.get(
            "content-type"
        ),
    )

    print(
        "PDF SIZE:",
        len(pdf_response.content),
    )

    pdf_response.raise_for_status()

    pdf_content_type = pdf_response.headers.get(
        "content-type",
        "",
    ).lower()

    if (
        "pdf" in pdf_content_type
        or pdf_response.content.startswith(b"%PDF")
    ):
        print(
            "✓ PDF RECEIVED AFTER HTML RECOVERY"
        )

        return pdf_response.content

raise RuntimeError(
    f"URL did not return PDF: {url}"
)
```

# ============================================================

# OSJD PAGE DISCOVERY

# ============================================================

def discover_osjd_links() -> dict[str, str]:
"""
Загружает страницу ОСЖД и пытается определить
PDF для каждой из 25 стран.
"""

```
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

print(
    "HTTP STATUS:",
    response.status_code,
)

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
        link.get_text(
            " ",
            strip=True,
        )
    )

    combined = (
        f"{text} {href}"
    ).lower()

    if (
        "api/media/resources" not in combined
        and ".pdf" not in combined
    ):
        continue

    if href.startswith("/"):
        href = (
            "https://osjd.org"
            + href
        )

    for country_code, aliases in (
        COUNTRY_ALIASES.items()
    ):
        if country_code in result:
            continue

        if any(
            alias in combined
            for alias in aliases
        ):
            result[country_code] = (
                normalize_osjd_pdf_url(
                    href
                )
            )

            print(
                f"FOUND {country_code}: "
                f"{text[:100]}"
            )

            print(
                f"       {href}"
            )

            break

print()
print(
    "DISCOVERED PDF LINKS:",
    len(result),
)

return result
```

def get_pdf_urls(
country_code: str | None = None,
) -> dict[str, str] | str | None:
"""
Возвращает все PDF URL.

```
Если передан country_code,
возвращает URL только этой страны.

ВАЖНО:
функция принимает аргумент country_code,
поэтому старый TypeError из предыдущей версии
здесь устранён.
"""

discovered = discover_osjd_links()

result = dict(discovered)

# Fallback only for known problematic countries.
for code, url in FALLBACK_PDFS.items():

    if not result.get(code):
        normalized = (
            normalize_osjd_pdf_url(url)
        )

        print(
            f"FALLBACK {code}: "
            f"{normalized}"
        )

        result[code] = normalized

    else:
        result[code] = (
            normalize_osjd_pdf_url(
                result[code]
            )
        )

for code in list(result):
    result[code] = (
        normalize_osjd_pdf_url(
            result[code]
        )
    )

# Keep only countries used by this project.
result = {
    code: url
    for code, url in result.items()
    if code in COUNTRIES
    and url
}

if country_code is not None:
    return result.get(country_code)

return result
```

# ============================================================

# POPPLER / PDFTOTEXT FALLBACK

# ============================================================

def extract_pdftotext_pages(
pdf_bytes: bytes,
) -> list[str]:
"""
Использует Poppler pdftotext,
если PyMuPDF не смог извлечь текст.
"""

```
executable = shutil.which(
    "pdftotext"
)

if not executable:
    print(
        "pdftotext is not installed; "
        "Poppler fallback unavailable."
    )

    return []

with tempfile.TemporaryDirectory() as tmp_dir:

    pdf_path = (
        Path(tmp_dir)
        / "source.pdf"
    )

    txt_path = (
        Path(tmp_dir)
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

    success = False

    for command in commands:

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )

            if (
                result.returncode == 0
                and txt_path.exists()
            ):
                success = True
                break

        except Exception as exc:
            print(
                "pdftotext ERROR:",
                repr(exc),
            )

    if not success:
        print(
            "pdftotext failed to extract text."
        )

        return []

    text = txt_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

print(
    "pdftotext extracted characters:",
    len(text),
)

return re.split(
    r"\f",
    text,
)
```

def parse_pdftotext_line(
line: str,
country_code: str,
) -> dict[str, Any] | None:

```
line = (
    line
    .replace("\xa0", " ")
    .strip()
)

if not line:
    return None

lower = line.lower()

if (
    "наименование" in lower
    and "код" in lower
):
    return None

match6 = re.search(
    r"(?<!\d)(\d{6})(?!\d)",
    line,
)

if match6:

    code = match6.group(1)

    left = line[
        :match6.start()
    ].strip(" |;:")

    right = line[
        match6.end():
    ].strip(" |;:")

else:

    # Iran document uses 4-digit station code.
    # Railway code is 96.
    match4 = re.search(
        r"(?<!\d)(\d{4})(?!\d)",
        line,
    )

    if not match4:
        return None

    if country_code != "IR":
        return None

    code4 = match4.group(1)

    code = (
        "96"
        + code4
    )

    left = line[
        :match4.start()
    ].strip(" |;:")

    right = line[
        match4.end():
    ].strip(" |;:")

columns = [
    normalize_space(x)
    for x in re.split(
        r"\s{2,}|\t+",
        line,
    )
    if normalize_space(x)
]

russian = left
latin = right

if columns:

    code_index = None

    for i, col in enumerate(columns):

        if (
            code in col
            or (
                country_code == "IR"
                and code[2:] in col
            )
        ):
            code_index = i
            break

    if code_index is not None:

        if code_index > 0:
            russian = columns[
                code_index - 1
            ]

        if (
            code_index + 1
            < len(columns)
        ):
            latin = columns[
                code_index + 1
            ]

russian = clean_station_name(
    russian
)

latin = clean_station_name(
    latin
)

if not valid_name(russian):
    return None

if not valid_name(latin):
    latin = russian

return make_record(
    country_code=country_code,
    code=code,
    russian_name=russian,
    latin_name=latin,
)
```

def parse_pdftotext_pages(
pages: list[str],
country_code: str,
) -> list[dict[str, Any]]:

```
records = []

for page in pages:

    for line in page.splitlines():

        record = parse_pdftotext_line(
            line,
            country_code,
        )

        if record:
            records.append(record)

return deduplicate_records(
    records
)
```

# ============================================================

# PDF EXTRACTION

# ============================================================

def extract_text_methods(
pdf_bytes: bytes,
) -> dict[str, list[Any]]:

```
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
            f"WARNING text page "
            f"{page_number}: {exc}"
        )

        methods["text"].append("")

    try:
        methods["blocks"].append(
            page.get_text("blocks")
        )

    except Exception as exc:
        print(
            f"WARNING blocks page "
            f"{page_number}: {exc}"
        )

        methods["blocks"].append([])

    try:
        methods["words"].append(
            page.get_text("words")
        )

    except Exception as exc:
        print(
            f"WARNING words page "
            f"{page_number}: {exc}"
        )

        methods["words"].append([])

    try:
        methods["dict"].append(
            page.get_text("dict")
        )

    except Exception as exc:
        print(
            f"WARNING dict page "
            f"{page_number}: {exc}"
        )

        methods["dict"].append({})

document.close()

return methods
```

def count_codes(value: Any) -> int:

```
if value is None:
    return 0

if isinstance(value, str):

    return len(
        re.findall(
            r"(?<!\d)\d{6}(?!\d)",
            value,
        )
    )

if isinstance(
    value,
    (list, tuple),
):

    return sum(
        count_codes(item)
        for item in value
    )

if isinstance(value, dict):

    return sum(
        count_codes(item)
        for item in value.values()
    )

return 0
```

def diagnostic_pdf(
pdf_bytes: bytes,
country_code: str,
) -> None:

```
document = fitz.open(
    stream=pdf_bytes,
    filetype="pdf",
)

print()
print("=" * 70)
print(
    f"PDF DIAGNOSTIC: "
    f"{country_code}"
)
print("=" * 70)

print(
    "Pages:",
    len(document),
)

for page_index, page in enumerate(
    document,
    start=1,
):

    text = page.get_text(
        "text"
    )

    blocks = page.get_text(
        "blocks"
    )

    words = page.get_text(
        "words"
    )

    dictionary = page.get_text(
        "dict"
    )

    text_codes = count_codes(
        text
    )

    block_codes = count_codes(
        blocks
    )

    word_codes = count_codes(
        words
    )

    dict_codes = count_codes(
        dictionary
    )

    if max(
        text_codes,
        block_codes,
        word_codes,
        dict_codes,
    ) > 0:

        print(
            f"Page {page_index}: "
            f"text={text_codes}, "
            f"blocks={block_codes}, "
            f"words={word_codes}, "
            f"dict={dict_codes}"
        )

document.close()
```

# ============================================================

# WORDS -> LINES

# ============================================================

def words_to_lines(
words: list[tuple],
) -> list[dict[str, Any]]:

```
if not words:
    return []

groups: list[dict[str, Any]] = []

sorted_words = sorted(
    words,
    key=lambda item: (
        round(float(item[1]), 1),
        float(item[0]),
    ),
)

for word in sorted_words:

    x0, y0, x1, y1, text = word[:5]

    text = normalize_space(
        str(text)
    )

    if not text:
        continue

    placed = False

    for group in groups[-8:]:

        avg_y = group["avg_y"]

        if (
            abs(
                float(y0)
                - avg_y
            )
            <= 3.5
        ):

            group["words"].append(
                word
            )

            group["avg_y"] = (
                sum(
                    float(w[1])
                    for w in group["words"]
                )
                / len(
                    group["words"]
                )
            )

            placed = True
            break

    if not placed:

        groups.append(
            {
                "avg_y": float(y0),
                "words": [word],
            }
        )

lines = []

for group in groups:

    row = sorted(
        group["words"],
        key=lambda item: float(
            item[0]
        ),
    )

    full_text = normalize_space(
        " ".join(
            str(item[4])
            for item in row
        )
    )

    lines.append(
        {
            "words": row,
            "text": full_text,
        }
    )

return lines
```

# ============================================================

# CODE CANDIDATES

# ============================================================

def code_candidates_from_words(
words: list[tuple],
) -> list[dict[str, Any]]:

```
candidates = []

lines = words_to_lines(
    words
)

for line in lines:

    row = line["words"]

    for index, word in enumerate(row):

        raw = str(word[4])

        code = normalize_code(
            raw
        )

        if code:

            candidates.append(
                {
                    "code": code,
                    "line": line,
                    "index": index,
                    "source": "words",
                }
            )

            continue

        if index + 1 < len(row):

            combined = (
                raw
                + str(
                    row[index + 1][4]
                )
            )

            code = normalize_code(
                combined
            )

            if code:

                candidates.append(
                    {
                        "code": code,
                        "line": line,
                        "index": index,
                        "source": "words-split",
                    }
                )

return candidates
```

def code_candidates_from_blocks(
blocks: list[tuple],
) -> list[dict[str, Any]]:

```
candidates = []

for block in blocks:

    if len(block) < 5:
        continue

    x0, y0, x1, y1, text = block[:5]

    text = normalize_space(
        str(text)
    )

    matches = list(
        re.finditer(
            r"(?<!\d)\d{6}(?!\d)",
            text,
        )
    )

    for match in matches:

        candidates.append(
            {
                "code": match.group(0),
                "text": text,
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "source": "blocks",
            }
        )

return candidates
```

def code_candidates_from_text(
text: str,
) -> list[str]:

```
return re.findall(
    r"(?<!\d)\d{6}(?!\d)",
    text,
)
```

# ============================================================

# NAME EXTRACTION FROM WORD LINE

# ============================================================

def split_line_around_code(
candidate: dict[str, Any],
) -> tuple[str, str, str]:

```
line = candidate["line"]

words = line["words"]

index = candidate["index"]

code = candidate["code"]

left_words = []

for item in words[:index]:
    left_words.append(
        str(item[4])
    )

right_words = []

skip = (
    2
    if candidate["source"]
    == "words-split"
    else 1
)

for item in words[
    index + skip:
]:
    right_words.append(
        str(item[4])
    )

left = clean_station_name(
    " ".join(left_words)
)

right = clean_station_name(
    " ".join(right_words)
)

return left, code, right
```

def extract_latin_name(
right: str,
) -> str:

```
right = normalize_space(
    right
)

if not right:
    return ""

match = re.search(
    r"\b\d+(?:\s*[,./]\s*\d+)+\b",
    right,
)

if match:
    right = right[
        :match.start()
    ]

right = re.split(
    r"\b\d{4}\b",
    right,
    maxsplit=1,
)[0]

return clean_station_name(
    right
)
```

# ============================================================

# RECORD CREATION

# ============================================================

def make_record(
country_code: str,
code: str,
russian_name: str,
latin_name: str,
operations: str = "",
border_code: str = "",
) -> dict[str, Any] | None:

```
russian_name = clean_station_name(
    russian_name
)

latin_name = clean_station_name(
    latin_name
)

code = (
    normalize_code(code)
    or ""
)

if not code:
    return None

if not valid_name(
    russian_name
):
    return None

if not valid_name(
    latin_name
):
    return None

if country_code not in COUNTRIES:
    return None

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

if border_code:

    border_code = str(
        border_code
    ).strip()

    if re.fullmatch(
        r"\d{4}",
        border_code,
    ):
        record[
            "border_code"
        ] = border_code

return record
```

# ============================================================

# ADVANCED LINE PARSER

# ============================================================

def parse_words_page(
words: list[tuple],
country_code: str,
) -> list[dict[str, Any]]:

```
records = []

candidates = (
    code_candidates_from_words(
        words
    )
)

for candidate in candidates:

    left, code, right = (
        split_line_around_code(
            candidate
        )
    )

    if not left or not right:
        continue

    russian = left

    latin = extract_latin_name(
        right
    )

    if not valid_name(
        russian
    ):
        continue

    if not valid_name(
        latin
    ):
        continue

    operations = ""
    border_code = ""

    border_matches = re.findall(
        r"(?<!\d)\d{4}(?!\d)",
        right,
    )

    if border_matches:
        border_code = (
            border_matches[-1]
        )

    op_match = re.search(
        r"(\d+(?:\s*[,./]\s*\d+)*"
        r"(?:\s*[А-ЯA-Za-zКкНн«»\"']+)?)",
        right,
    )

    if op_match:

        possible_ops = (
            normalize_space(
                op_match.group(1)
            )
        )

        if looks_like_operations(
            possible_ops
        ):
            operations = (
                possible_ops
            )

    record = make_record(
        country_code=country_code,
        code=code,
        russian_name=russian,
        latin_name=latin,
        operations=operations,
    )

    if record:

        if border_code:
            record[
                "border_code"
            ] = border_code

        records.append(
            record
        )

return records
```

# ============================================================

# BLOCK-BASED PARSER

# ============================================================

def parse_blocks_page(
blocks: list[tuple],
country_code: str,
) -> list[dict[str, Any]]:

```
records = []

code_blocks = []

for block in blocks:

    if len(block) < 5:
        continue

    x0, y0, x1, y1, text = block[:5]

    text = normalize_space(
        str(text)
    )

    matches = list(
        re.finditer(
            r"(?<!\d)\d{6}(?!\d)",
            text,
        )
    )

    for match in matches:

        code_blocks.append(
            {
                "code": match.group(0),
                "text": text,
                "x0": float(x0),
                "y0": float(y0),
                "x1": float(x1),
                "y1": float(y1),
            }
        )

for code_item in code_blocks:

    code = code_item["code"]

    same_line = []

    for block in blocks:

        if len(block) < 5:
            continue

        x0, y0, x1, y1, text = block[:5]

        if (
            abs(
                float(y0)
                - code_item["y0"]
            )
            <= 8
        ):

            same_line.append(
                {
                    "x0": float(x0),
                    "x1": float(x1),
                    "text": normalize_space(
                        str(text)
                    ),
                }
            )

    same_line.sort(
        key=lambda item: item["x0"]
    )

    before = []
    after = []

    for block in same_line:

        if (
            block["x1"]
            <= code_item["x0"]
        ):
            before.append(
                block["text"]
            )

        elif (
            block["x0"]
            >= code_item["x1"]
        ):
            after.append(
                block["text"]
            )

    russian_candidates = [
        clean_station_name(text)
        for text in before
    ]

    latin_candidates = [
        clean_station_name(text)
        for text in after
    ]

    russian_candidates = [
        x
        for x in russian_candidates
        if valid_name(x)
    ]

    latin_candidates = [
        x
        for x in latin_candidates
        if valid_name(x)
    ]

    if not russian_candidates:
        continue

    if not latin_candidates:
        continue

    russian = max(
        russian_candidates,
        key=score_name,
    )

    latin = max(
        latin_candidates,
        key=score_name,
    )

    record = make_record(
        country_code=country_code,
        code=code,
        russian_name=russian,
        latin_name=latin,
    )

    if record:
        records.append(
            record
        )

return records
```

# ============================================================

# DICT PARSER

# ============================================================

def collect_dict_text(
dictionary: dict[str, Any],
) -> str:

```
parts = []

blocks = dictionary.get(
    "blocks",
    [],
)

for block in blocks:

    if block.get("type") != 0:
        continue

    for line in block.get(
        "lines",
        [],
    ):

        for span in line.get(
            "spans",
            [],
        ):

            text = span.get(
                "text",
                "",
            )

            if text:
                parts.append(
                    text
                )

return normalize_space(
    " ".join(parts)
)
```

def parse_dict_page(
dictionary: dict[str, Any],
country_code: str,
) -> list[dict[str, Any]]:

```
records = []

text = collect_dict_text(
    dictionary
)

if not text:
    return records

matches = list(
    re.finditer(
        r"(?<!\d)(\d{6})(?!\d)",
        text,
    )
)

for match in matches:

    code = match.group(1)

    before = text[
        max(
            0,
            match.start() - 180,
        ):
        match.start()
    ]

    after = text[
        match.end():
        match.end() + 180
    ]

    before = normalize_space(
        before
    )

    after = normalize_space(
        after
    )

    left_parts = before.split()

    if len(left_parts) > 12:
        left_parts = (
            left_parts[-12:]
        )

    right_parts = after.split()

    if len(right_parts) > 15:
        right_parts = (
            right_parts[:15]
        )

    russian = normalize_space(
        " ".join(left_parts)
    )

    latin = normalize_space(
        " ".join(right_parts)
    )

    russian = clean_station_name(
        russian
    )

    latin = clean_station_name(
        latin
    )

    if not valid_name(
        russian
    ):
        continue

    latin_words = []

    for word in latin.split():

        if re.fullmatch(
            r"[\d,./()]+",
            word,
        ):
            break

        latin_words.append(
            word
        )

        if len(latin_words) >= 8:
            break

    latin = normalize_space(
        " ".join(latin_words)
    )

    if not valid_name(
        latin
    ):
        continue

    record = make_record(
        country_code=country_code,
        code=code,
        russian_name=russian,
        latin_name=latin,
    )

    if record:
        records.append(
            record
        )

return records
```

# ============================================================

# DEDUPLICATION

# ============================================================

def deduplicate_records(
records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

```
result = []

seen = set()

for record in records:

    country_code = record.get(
        "country_code",
        "",
    )

    code = str(
        record.get(
            "code",
            "",
        )
    )

    key = (
        country_code,
        code,
    )

    if key in seen:
        continue

    seen.add(key)

    result.append(
        record
    )

return result
```

# ============================================================

# PARSE ONE PDF

# ============================================================

def parse_pdf(
pdf_bytes: bytes,
country_code: str,
) -> list[dict[str, Any]]:

```
print()
print("=" * 70)
print(
    f"PARSING COUNTRY: "
    f"{country_code} "
    f"{COUNTRIES[country_code]}"
)
print("=" * 70)

diagnostic_pdf(
    pdf_bytes,
    country_code,
)

methods = extract_text_methods(
    pdf_bytes
)

method_counts = {}

for method_name, pages in (
    methods.items()
):
    method_counts[
        method_name
    ] = count_codes(pages)

print()
print(
    "EXTRACTION METHOD CODE COUNTS"
)

for method_name, count in (
    method_counts.items()
):
    print(
        f"  {method_name:8}: "
        f"{count}"
    )

candidates = []

# --------------------------------------------------------
# 1. WORDS
# --------------------------------------------------------

for page_words in methods[
    "words"
]:

    if not page_words:
        continue

    records = parse_words_page(
        page_words,
        country_code,
    )

    candidates.extend(
        records
    )

candidates = deduplicate_records(
    candidates
)

print(
    "WORD PARSER RECORDS:",
    len(candidates),
)

# --------------------------------------------------------
# 2. BLOCKS
# --------------------------------------------------------

if len(candidates) < 3:

    block_candidates = []

    for page_blocks in methods[
        "blocks"
    ]:

        if not page_blocks:
            continue

        records = parse_blocks_page(
            page_blocks,
            country_code,
        )

        block_candidates.extend(
            records
        )

    block_candidates = (
        deduplicate_records(
            block_candidates
        )
    )

    print(
        "BLOCK PARSER RECORDS:",
        len(block_candidates),
    )

    candidates.extend(
        block_candidates
    )

    candidates = (
        deduplicate_records(
            candidates
        )
    )

# --------------------------------------------------------
# 3. DICT
# --------------------------------------------------------

if len(candidates) < 3:

    dict_candidates = []

    for page_dict in methods[
        "dict"
    ]:

        if not page_dict:
            continue

        records = parse_dict_page(
            page_dict,
            country_code,
        )

        dict_candidates.extend(
            records
        )

    dict_candidates = (
        deduplicate_records(
            dict_candidates
        )
    )

    print(
        "DICT PARSER RECORDS:",
        len(dict_candidates),
    )

    candidates.extend(
        dict_candidates
    )

    candidates = (
        deduplicate_records(
            candidates
        )
    )

# --------------------------------------------------------
# 4. TEXT FALLBACK
# --------------------------------------------------------

if len(candidates) < 3:

    text_codes = []

    for page_text in methods[
        "text"
    ]:

        text_codes.extend(
            code_candidates_from_text(
                page_text
            )
        )

    text_codes = list(
        dict.fromkeys(
            text_codes
        )
    )

    print(
        "TEXT CODES:",
        len(text_codes),
    )

# --------------------------------------------------------
# 5. POPPLER FALLBACK
# --------------------------------------------------------

if len(candidates) < 3:

    print()
    print(
        "PyMuPDF found too few "
        "station records."
    )

    print(
        "TRYING POPPLER "
        "pdftotext FALLBACK..."
    )

    poppler_pages = (
        extract_pdftotext_pages(
            pdf_bytes
        )
    )

    print(
        "pdftotext pages:",
        len(poppler_pages),
    )

    if poppler_pages:

        poppler_candidates = (
            parse_pdftotext_pages(
                poppler_pages,
                country_code,
            )
        )

        print(
            "POPPLER PARSER RECORDS:",
            len(poppler_candidates),
        )

        candidates.extend(
            poppler_candidates
        )

        candidates = (
            deduplicate_records(
                candidates
            )
        )

# --------------------------------------------------------
# FINAL
# --------------------------------------------------------

candidates = deduplicate_records(
    candidates
)

print()
print(
    f"FINAL PARSED RECORDS: "
    f"{len(candidates)}"
)

if candidates:

    print()
    print(
        "FIRST RECORDS:"
    )

    for record in candidates[:10]:

        print(
            "  ",
            record,
        )

return candidates
```

# ============================================================

# VALIDATE COUNTRY RECORDS

# ============================================================

def validate_country_records(
country_code: str,
records: list[dict[str, Any]],
) -> None:

```
if not records:

    raise RuntimeError(
        f"{country_code}: "
        "no station records parsed"
    )

invalid_codes = []

for record in records:

    code = str(
        record.get(
            "code",
            "",
        )
    )

    if not re.fullmatch(
        r"\d{6}",
        code,
    ):
        invalid_codes.append(
            record
        )

if invalid_codes:

    raise RuntimeError(
        f"{country_code}: "
        f"{len(invalid_codes)} "
        "invalid station codes"
    )

missing_names = []

for record in records:

    if not valid_name(
        record.get(
            "name",
            "",
        )
    ):
        missing_names.append(
            record
        )

    if not valid_name(
        record.get(
            "latin_name",
            "",
        )
    ):
        missing_names.append(
            record
        )

if missing_names:

    raise RuntimeError(
        f"{country_code}: "
        f"records with invalid names: "
        f"{len(missing_names)}"
    )
```

# ============================================================

# LOAD OLD DATABASE

# ============================================================

def load_existing_database() -> list[dict[str, Any]]:

```
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

    if not isinstance(
        data,
        list,
    ):
        return []

    return data

except Exception as exc:

    print(
        "WARNING: cannot read "
        "existing stations.json:",
        exc,
    )

    return []
```

# ============================================================

# MERGE

# ============================================================

def merge_records(
new_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
"""
Новые записи заменяют старые
для соответствующих стран.

```
Страны, которые не входят в текущий запуск,
сохраняются.

В текущем проекте используются 25 стран.
"""

existing = (
    load_existing_database()
)

new_country_codes = {
    record[
        "country_code"
    ]
    for record in new_records
}

result = []

for record in existing:

    country_code = record.get(
        "country_code"
    )

    if (
        country_code
        in new_country_codes
    ):
        continue

    # Do not keep explicitly excluded countries.
    if country_code in {
        "KR",
        "RO",
        "LA",
    }:
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
```

# ============================================================

# GLOBAL VALIDATION

# ============================================================

def validate_all_countries(
stations: list[dict[str, Any]],
) -> None:

```
print()
print("=" * 70)
print("STATISTICS BY COUNTRY")
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
            f"{count:6}"
        )

        missing.append(
            code
        )

print()
print("=" * 70)
print(
    "CHECKING 25 COUNTRIES"
)
print("=" * 70)

found = sum(
    1
    for code in COUNTRIES
    if counters.get(
        code,
        0,
    ) > 0
)

print(
    "Countries in database:",
    len(counters),
)

print(
    "Countries with data:",
    found,
)

print(
    "Countries without data:",
    len(missing),
)

if missing:

    print()
    print(
        "MISSING:"
    )

    for code in missing:

        print(
            f"  {code} — "
            f"{COUNTRIES[code]}"
        )

    raise RuntimeError(
        "КРИТИЧЕСКАЯ ОШИБКА: "
        f"отсутствует {len(missing)} "
        "стран. "
        "stations.json НЕ изменён."
    )

# --------------------------------------------------------
# EXCLUDED COUNTRIES
# --------------------------------------------------------

excluded_present = (
    sorted(
        set(counters)
        & {
            "KR",
            "RO",
            "LA",
        }
    )
)

if excluded_present:

    raise RuntimeError(
        "В базе обнаружены "
        "исключённые страны: "
        + ", ".join(
            excluded_present
        )
    )

# --------------------------------------------------------
# UNKNOWN COUNTRIES
# --------------------------------------------------------

unexpected = sorted(
    set(counters)
    - set(COUNTRIES)
)

if unexpected:

    raise RuntimeError(
        "Обнаружены неизвестные "
        "country_code: "
        + ", ".join(
            unexpected
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
print("=" * 70)
print("FINAL VALIDATION")
print("=" * 70)

print(
    "Total stations:",
    len(stations),
)

print(
    "Invalid codes:",
    len(invalid_codes),
)

if invalid_codes:

    for station in invalid_codes[:20]:
        print(
            station
        )

    raise RuntimeError(
        "Обнаружены некорректные "
        "6-значные коды."
    )

# --------------------------------------------------------
# NAMES
# --------------------------------------------------------

missing_ru = [
    station
    for station in stations
    if not valid_name(
        station.get(
            "name",
            "",
        )
    )
]

missing_latin = [
    station
    for station in stations
    if not valid_name(
        station.get(
            "latin_name",
            "",
        )
    )
]

print(
    "Without Russian name:",
    len(missing_ru),
)

print(
    "Without Latin name:",
    len(missing_latin),
)

if missing_ru:

    raise RuntimeError(
        "Есть станции без "
        "русского названия."
    )

if missing_latin:

    raise RuntimeError(
        "Есть станции без "
        "латинского названия."
    )

# --------------------------------------------------------
# DUPLICATES
# --------------------------------------------------------

duplicate_groups = {}

for station in stations:

    key = (
        station.get(
            "country_code"
        ),
        station.get(
            "code"
        ),
    )

    duplicate_groups.setdefault(
        key,
        [],
    ).append(
        station
    )

duplicates = {
    key: value
    for key, value
    in duplicate_groups.items()
    if len(value) > 1
}

print(
    "Duplicate country/code groups:",
    len(duplicates),
)

if duplicates:

    print()
    print(
        "WARNING: DUPLICATES"
    )

    for key, values in list(
        duplicates.items()
    )[:20]:

        print(
            f"  {key[0]} / "
            f"{key[1]}"
        )

        for value in values:

            print(
                f"    - "
                f"{value.get('name')} | "
                f"{value.get('latin_name')}"
            )

print()
print(
    "✓ FINAL VALIDATION PASSED"
)
```

# ============================================================

# SAVE

# ============================================================

def save_database(
stations: list[dict[str, Any]],
) -> None:

```
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
```

# ============================================================

# FOUR-COUNTRY PDF DIAGNOSTIC

# ============================================================

def run_four_country_diagnostic() -> None:

```
targets = {
    "IR": "Иран",
    "CN": "Китай",
    "CZ": "Чехия",
    "EE": "Эстония",
}

print()
print("=" * 70)
print(
    "OSJD FOUR-COUNTRY PDF DIAGNOSTIC"
)
print("=" * 70)

sources = get_pdf_urls()

for code, name in (
    targets.items()
):

    print()
    print("-" * 70)

    print(
        f"COUNTRY: {name}"
    )

    print(
        f"CODE: {code}"
    )

    url = sources.get(
        code
    )

    print(
        "PDF URL:"
    )

    print(
        url
        or "SOURCE NOT FOUND"
    )

    if not url:
        continue

    try:

        pdf_bytes = download_pdf(
            url
        )

        print(
            "PDF OK:",
            len(pdf_bytes),
            "bytes",
        )

        methods = (
            extract_text_methods(
                pdf_bytes
            )
        )

        text_count = count_codes(
            methods["text"]
        )

        word_count = count_codes(
            methods["words"]
        )

        block_count = count_codes(
            methods["blocks"]
        )

        dict_count = count_codes(
            methods["dict"]
        )

        print(
            "PyMuPDF text codes:",
            text_count,
        )

        print(
            "PyMuPDF word codes:",
            word_count,
        )

        print(
            "PyMuPDF block codes:",
            block_count,
        )

        print(
            "PyMuPDF dict codes:",
            dict_count,
        )

        if max(
            text_count,
            word_count,
            block_count,
            dict_count,
        ) == 0:

            pages = (
                extract_pdftotext_pages(
                    pdf_bytes
                )
            )

            print(
                "pdftotext pages:",
                len(pages),
            )

            records = (
                parse_pdftotext_pages(
                    pages,
                    code,
                )
            )

            print(
                "pdftotext records:",
                len(records),
            )

            for record in records[:10]:

                print(
                    "  ",
                    record,
                )

    except Exception as exc:

        print(
            "DIAGNOSTIC ERROR:",
            repr(exc),
        )
```

# ============================================================

# MAIN

# ============================================================

def main() -> None:

```
if (
    os.environ.get(
        "OSJD_FOUR_COUNTRY_DIAGNOSTIC"
    )
    == "1"
):

    run_four_country_diagnostic()
    return

print("=" * 70)
print(
    "OSJD RAILWAY STATION "
    "DATABASE UPDATE"
)
print("=" * 70)

print()
print(
    "Target countries:",
    len(COUNTRIES),
)

print(
    "Expected countries: 25"
)

print(
    "Excluded countries: "
    "KR, RO, LA"
)

print(
    "Output:",
    OUTPUT_FILE,
)

# --------------------------------------------------------
# GET PDF URLS
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
            f"{country}: "
            f"{url}"
        )

    else:

        print(
            f"✗ {code} "
            f"{country}: "
            "NO SOURCE"
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
# DOWNLOAD + PARSE
# --------------------------------------------------------

all_new_records = []

country_statistics = {}

for country_code, country_name in (
    COUNTRIES.items()
):

    url = pdf_urls[
        country_code
    ]

    print()
    print("=" * 70)

    print(
        f"COUNTRY "
        f"{country_code} — "
        f"{country_name}"
    )

    print("=" * 70)

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

        country_statistics[
            country_code
        ] = len(records)

        all_new_records.extend(
            records
        )

        print()
        print(
            f"✓ {country_code}: "
            f"{len(records)} records"
        )

    except Exception as exc:

        print()
        print(
            f"✗ ERROR "
            f"{country_code}:"
        )

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
print(
    "COUNTRY COVERAGE"
)
print("=" * 70)

for code, country in (
    COUNTRIES.items()
):

    count = (
        country_statistics.get(
            code,
            0,
        )
    )

    if count:

        print(
            f"✓ {code} "
            f"{country:<25} "
            f"{count}"
        )

    else:

        print(
            f"✗ {code} "
            f"{country:<25} "
            "0"
        )

missing = [
    code
    for code in COUNTRIES
    if not country_statistics.get(
        code,
        0,
    )
]

if missing:

    raise RuntimeError(
        "Не получены данные для: "
        + ", ".join(missing)
        + ". "
        "stations.json НЕ изменён."
    )

# --------------------------------------------------------
# MERGE
# --------------------------------------------------------

merged = merge_records(
    all_new_records
)

print()
print("=" * 70)
print(
    "MERGED DATABASE"
)
print("=" * 70)

print(
    "New parsed records:",
    len(all_new_records),
)

print(
    "Final records:",
    len(merged),
)

# --------------------------------------------------------
# GLOBAL VALIDATION
# --------------------------------------------------------

validate_all_countries(
    merged
)

# --------------------------------------------------------
# SAVE ONLY NOW
# --------------------------------------------------------

print()
print("=" * 70)
print(
    "SAVING DATABASE"
)
print("=" * 70)

save_database(
    merged
)

print()
print("=" * 70)
print(
    "SUCCESS"
)
print("=" * 70)

print(
    "stations.json updated:",
    len(merged),
    "records",
)
```

# ============================================================

# ENTRY POINT

# ============================================================

if **name** == "**main**":

```
try:

    main()

except KeyboardInterrupt:

    print(
        "\nInterrupted by user."
    )

    sys.exit(130)

except Exception as exc:

    print()
    print("=" * 70)
    print(
        "FATAL ERROR"
    )
    print("=" * 70)

    print(
        str(exc)
    )

    print()
    print(
        "stations.json НЕ изменён."
    )

    sys.exit(1)
