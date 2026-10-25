#!/usr/bin/env python3

"""
OSJD railway freight stations parser.

Получает актуальные PDF-перечни грузовых станций ОСЖД,
извлекает станции несколькими способами и обновляет
data/stations.json только после успешной проверки всех
активных стран.

Основная страница ОСЖД:
https://osjd.org/ru/8974/page/106077?id=2227
"""

import io
import json
import math
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
# COUNTRIES
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

EXCLUDED_COUNTRIES = {"IR", "CN", "CZ", "KR", "RO", "LA"}
ACTIVE_COUNTRIES = {
    code: name for code, name in COUNTRIES.items()
    if code not in EXCLUDED_COUNTRIES
}


# ============================================================
# FALLBACK PDF URLS
#
# Эти URL уже диагностированы на сайте ОСЖД.
# Используются, если автоматический поиск не нашёл
# ссылку для страны.
# ============================================================

FALLBACK_PDFS = {
    "GE": "https://osjd.org/api/media/resources/2814?action=download",
    "IR": "https://osjd.org/api/media/resources/9608?action=download",
    "CN": "https://osjd.org/api/media/resources/1537?action=download",
    "KR": "https://osjd.org/api/media/resources/1637529?action=download",
    "RO": "https://osjd.org/api/media/resources/2813?action=download",
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
    # ВАЖНО: убрано слишком общее слово "груз",
    # из-за которого ловилась "Памятка ОСЖД О 405".
    "GE": [
        "грузовых станций грузинской железной дороги",
        "перечень грузовых станций грузинской",
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
    "KR": [
        "республики кореи",
        "республика корея",
        "железных дорог республики кореи",
    ],
    "LA": [
        "лаос",
        "лаосской национальной железной дороги",
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
    "RO": [
        "румын",
        "румынских ж",
        "чфр",
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
        "государственном языке",
    ]

    if any(fragment in lower for fragment in bad_fragments):
        return True

    if re.fullmatch(r"[\d\s.,;:/()\-]+", text):
        return True

    return False


def clean_station_name(value: str) -> str:
    value = normalize_space(value)

    value = re.sub(r"^[|;:,]+", "", value)
    value = re.sub(r"[|;:,]+$", "", value)

    value = normalize_space(value)

    return value


def looks_like_operations(value: str) -> bool:
    if not value:
        return False
    text = normalize_space(value)
    # Ловит: "8н,10н", "1;3(ТП)", "1; 4;9 (ТП)", "(ТП)", "ТП" и т.п.
    pattern = (
        r"(?i)"
        r"(?:\(?\s*[A-Za-zА-Яа-яЁё]{1,3}\s*\)?)?"
        r"(?:\d+\s*[A-Za-zА-Яа-яЁё]?\s*[,;/.]?\s*)*"
        r"(?:\(?\s*[A-Za-zА-Яа-яЁё]{1,3}\s*\)?)?"
    )
    return bool(re.fullmatch(pattern, text))


def valid_name(value: str) -> bool:
    value = clean_station_name(value)

    if is_noise_name(value):
        return False

    if len(value) > 150:
        return False

    if looks_like_operations(value):
        return False

    if not re.search(r"[A-Za-zА-Яа-яЁё]", value):
        return False

    return True


def strict_station_name(value: str, script: str) -> bool:
    """
    Проверка поля названия до создания записи.
    Отклоняет служебные операции, шестизначные коды и смешанные
    фрагменты таблицы, которые могли попасть в поле названия.
    """
    value = clean_station_name(value)
    if not valid_name(value):
        return False
    if re.search(r"(?<!\d)\d{6}(?!\d)", value):
        return False
    if re.search(
        r"(?<!\S)\d+\s*[А-ЯA-Za-z]?"
        r"(?:\s*[,;./]\s*\d+\s*[А-ЯA-Za-z]?)*(?=\s|$)",
        value,
    ):
        return False
    if script == "ru" and not re.search(r"[А-Яа-яЁё]", value):
        return False
    if script == "latin" and not re.search(r"[A-Za-z]", value):
        return False
    if len(value.split()) > 8:
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
    Находит ссылки ОСЖД и преобразует ссылки просмотра
    документов в прямые ссылки на скачивание PDF.
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

    soup = BeautifulSoup(response.text, "html.parser")
    result: dict[str, str] = {}

    for link in soup.find_all("a"):
        href = link.get("href")
        if not href:
            continue

        text = normalize_space(link.get_text(" ", strip=True))
        combined = f"{text} {href}".lower()

        if "api/media/resources" not in combined and ".pdf" not in combined:
            continue

        if href.startswith("/"):
            href = "https://osjd.org" + href

        resource_match = re.search(r"/api/media/resources/(\d+)", href)
        if resource_match:
            resource_id = resource_match.group(1)
            pdf_url = (
                "https://osjd.org/api/media/resources/"
                f"{resource_id}?action=download"
            )
        else:
            pdf_url = href.split("#", 1)[0]

        for country_code, aliases in COUNTRY_ALIASES.items():
            if country_code in result:
                continue

            if any(alias in combined for alias in aliases):
                result[country_code] = pdf_url
                print(f"FOUND {country_code}: {text[:100]}")
                print(f"       {pdf_url}")
                break

    return result


def get_pdf_urls() -> dict[str, str]:
    """
    Объединяет найденные на странице ОСЖД ссылки
    с заранее проверенными резервными PDF-ссылками.
    Ссылки, обнаруженные на странице, имеют приоритет.
    """
    discovered = discover_osjd_links()
    urls = dict(FALLBACK_PDFS)
    urls.update(discovered)
    return urls


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

    for page_number, page in enumerate(document, start=1):
        try:
            methods["text"].append(page.get_text("text"))
        except Exception as exc:
            print(f"WARNING text page {page_number}: {exc}")
            methods["text"].append("")

        try:
            methods["blocks"].append(page.get_text("blocks"))
        except Exception as exc:
            print(f"WARNING blocks page {page_number}: {exc}")
            methods["blocks"].append([])

        try:
            methods["words"].append(page.get_text("words"))
        except Exception as exc:
            print(f"WARNING words page {page_number}: {exc}")
            methods["words"].append([])

        try:
            methods["dict"].append(page.get_text("dict"))
        except Exception as exc:
            print(f"WARNING dict page {page_number}: {exc}")
            methods["dict"].append({})

    document.close()

    return methods


def count_codes(value: Any) -> int:
    """
    Подсчёт 6-значных кодов в произвольном объекте.
    """

    if value is None:
        return 0

    if isinstance(value, str):
        return len(
            re.findall(
                r"(?<!\d)\d{6}(?!\d)",
                value,
            )
        )

    if isinstance(value, (list, tuple)):
        return sum(count_codes(item) for item in value)

    if isinstance(value, dict):
        return sum(count_codes(item) for item in value.values())

    return 0


def diagnostic_pdf(
    pdf_bytes: bytes,
    country_code: str,
) -> None:
    """
    Короткая диагностика PDF перед разбором.
    """

    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    print()
    print("=" * 70)
    print(f"PDF DIAGNOSTIC: {country_code}")
    print("=" * 70)

    print("Pages:", len(document))

    for page_index, page in enumerate(document, start=1):
        text = page.get_text("text")
        blocks = page.get_text("blocks")
        words = page.get_text("words")
        dictionary = page.get_text("dict")

        text_codes = count_codes(text)
        block_codes = count_codes(blocks)
        word_codes = count_codes(words)
        dict_codes = count_codes(dictionary)

        if max(text_codes, block_codes, word_codes, dict_codes) > 0:
            print(
                f"Page {page_index}: "
                f"text={text_codes}, "
                f"blocks={block_codes}, "
                f"words={word_codes}, "
                f"dict={dict_codes}"
            )

    document.close()


# ============================================================
# WORDS -> LINES
# ============================================================

def words_to_lines(
    words: list[tuple],
) -> list[dict[str, Any]]:
    """
    Собирает PDF words в визуальные строки.

    Формат PyMuPDF word:
    x0, y0, x1, y1, text, block_no, line_no, word_no
    """

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

        text = normalize_space(str(text))

        if not text:
            continue

        placed = False

        # Расширенное окно и увеличенный вертикальный допуск
        # помогают собрать строки таблиц, у которых ячейки
        # смещены по y-координате (как в PDF Азербайджана).
        for group in groups[-30:]:
            avg_y = group["avg_y"]

            if abs(float(y0) - avg_y) <= 5.0:
                group["words"].append(word)
                group["avg_y"] = (
                    sum(float(w[1]) for w in group["words"])
                    / len(group["words"])
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
            key=lambda item: float(item[0]),
        )

        full_text = normalize_space(
            " ".join(str(item[4]) for item in row)
        )

        lines.append(
            {
                "words": row,
                "text": full_text,
            }
        )

    return lines


# ============================================================
# CODE CANDIDATES
# ============================================================

def code_candidates_from_words(
    words: list[tuple],
) -> list[dict[str, Any]]:
    candidates = []

    lines = words_to_lines(words)

    for line in lines:
        row = line["words"]

        for index, word in enumerate(row):
            raw = str(word[4])

            code = normalize_code(raw)

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
                combined = raw + str(row[index + 1][4])

                code = normalize_code(combined)

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


def code_candidates_from_blocks(
    blocks: list[tuple],
) -> list[dict[str, Any]]:
    candidates = []

    for block in blocks:
        if len(block) < 5:
            continue

        x0, y0, x1, y1, text = block[:5]

        text = normalize_space(str(text))

        matches = list(
            re.finditer(r"(?<!\d)\d{6}(?!\d)", text)
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


def code_candidates_from_text(
    text: str,
) -> list[str]:
    return re.findall(r"(?<!\d)\d{6}(?!\d)", text)


# ============================================================
# NAME EXTRACTION FROM WORD LINE
# ============================================================

def split_line_around_code(
    candidate: dict[str, Any],
) -> tuple[str, str, str]:
    """
    Возвращает:

    left  = всё до кода
    code  = код
    right = всё после кода
    """

    line = candidate["line"]
    words = line["words"]
    index = candidate["index"]
    code = candidate["code"]

    left_words = [str(item[4]) for item in words[:index]]

    right_words = []

    skip = 2 if candidate["source"] == "words-split" else 1

    for item in words[index + skip:]:
        right_words.append(str(item[4]))

    left = clean_station_name(" ".join(left_words))
    right = clean_station_name(" ".join(right_words))

    return left, code, right


def extract_latin_name(right: str) -> str:
    """
    Выделяет латинское название из правой части строки.
    Коды операций, четырёхзначный пограничный код и одиночные
    маркеры вроде «ТП»/«(ТП)» не должны попадать в название.
    """
    right = normalize_space(right)
    if not right:
        return ""

    # 1. Пограничный код и всё, что после него.
    right = re.split(r"(?<!\d)\d{4}(?!\d)", right, maxsplit=1)[0]
    right = normalize_space(right)

    # 2. Коды операций в любом месте строки
    #    (не только в конце, как было раньше).
    right = re.split(
        r"(?<!\S)\d+\s*[A-Za-zА-Яа-яЁё]?"
        r"(?:\s*[,;./]\s*\d+\s*[A-Za-zА-Яа-яЁё]?)*",
        right,
        maxsplit=1,
    )[0]
    right = normalize_space(right)

    # 3. Одиночные маркеры операций вроде «ТП» / «(ТП)».
    right = re.sub(
        r"\s*\(?\s*(?:ТП|TП|TP)\s*\)?\s*$",
        "",
        right,
        flags=re.IGNORECASE,
    )

    return clean_station_name(right)


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

    russian_name = clean_station_name(russian_name)
    latin_name = clean_station_name(latin_name)
    code = normalize_code(code) or ""

    if not code:
        return None

    if not valid_name(russian_name):
        return None

    if not valid_name(latin_name):
        return None

    country = COUNTRIES[country_code]

    record = {
        "name": russian_name,
        "code": code,
        "country": country,
        "country_code": country_code,
        "latin_name": latin_name,
    }

    if operations:
        record["operations"] = normalize_space(operations)

    if border_code:
        border_code = normalize_code(border_code)
        if border_code:
            record["border_code"] = border_code

    return record


# ============================================================
# ADVANCED LINE PARSER
# ============================================================

def parse_words_page(
    words: list[tuple],
    country_code: str,
) -> list[dict[str, Any]]:
    """
    Строгий разбор строк PyMuPDF.

    Запись принимается только когда код, русское название и латинское
    название находятся в одной визуальной строке. Сомнительные строки
    отбрасываются.
    """
    records: list[dict[str, Any]] = []
    candidates = code_candidates_from_words(words)

    for candidate in candidates:
        left, code, right = split_line_around_code(candidate)
        if not left or not right:
            continue

        russian = clean_station_name(left)
        latin = extract_latin_name(right)

        if not strict_station_name(russian, "ru"):
            continue
        if not strict_station_name(latin, "latin"):
            continue

        border_matches = re.findall(r"(?<!\d)\d{4}(?!\d)", right)
        border_code = border_matches[0] if border_matches else ""

        operations = ""
        op_match = re.search(
            r"(?<!\S)(\d+\s*[А-ЯA-Za-z]?"
            r"(?:\s*[,;./]\s*\d+\s*[А-ЯA-Za-z]?)*)"
            r"(?=\s|$)",
            right,
        )
        if op_match and looks_like_operations(op_match.group(1)):
            operations = normalize_space(op_match.group(1))

        record = make_record(
            country_code=country_code,
            code=code,
            russian_name=russian,
            latin_name=latin,
            operations=operations,
            border_code=border_code,
        )
        if record:
            records.append(record)

    return records


# ============================================================
# BLOCK-BASED PARSER
# ============================================================

def parse_blocks_page(
    blocks: list[tuple],
    country_code: str,
) -> list[dict[str, Any]]:
    """
    Консервативный резервный разбор блоков.
    """
    records: list[dict[str, Any]] = []
    code_items = []

    for block in blocks:
        if len(block) < 5:
            continue
        x0, y0, x1, y1, text = block[:5]
        text = normalize_space(str(text))
        for match in re.finditer(r"(?<!\d)\d{6}(?!\d)", text):
            code_items.append({
                "code": match.group(0),
                "x0": float(x0),
                "y0": float(y0),
                "x1": float(x1),
                "y1": float(y1),
                "text": text,
            })

    for code_item in code_items:
        same_line = []
        for block in blocks:
            if len(block) < 5:
                continue
            x0, y0, x1, y1, text = block[:5]
            if abs(float(y0) - code_item["y0"]) <= 2.5:
                same_line.append({
                    "x0": float(x0),
                    "x1": float(x1),
                    "text": normalize_space(str(text)),
                })

        left_blocks = [
            item for item in same_line
            if item["x1"] <= code_item["x0"]
            and strict_station_name(clean_station_name(item["text"]), "ru")
        ]
        right_blocks = [
            item for item in same_line
            if item["x0"] >= code_item["x1"]
            and strict_station_name(
                extract_latin_name(item["text"]), "latin"
            )
        ]

        if not left_blocks or not right_blocks:
            continue

        left_blocks.sort(key=lambda item: code_item["x0"] - item["x1"])
        right_blocks.sort(key=lambda item: item["x0"] - code_item["x1"])
        russian = clean_station_name(left_blocks[0]["text"])
        latin = extract_latin_name(right_blocks[0]["text"])

        if len(left_blocks) > 1:
            d1 = code_item["x0"] - left_blocks[0]["x1"]
            d2 = code_item["x0"] - left_blocks[1]["x1"]
            if abs(d2 - d1) < 2.0:
                continue
        if len(right_blocks) > 1:
            d1 = right_blocks[0]["x0"] - code_item["x1"]
            d2 = right_blocks[1]["x0"] - code_item["x1"]
            if abs(d2 - d1) < 2.0:
                continue

        record = make_record(
            country_code=country_code,
            code=code_item["code"],
            russian_name=russian,
            latin_name=latin,
        )
        if record:
            records.append(record)

    return records


# ============================================================
# DICT PARSER
# ============================================================

def collect_dict_text(
    dictionary: dict[str, Any],
) -> str:

    parts = []

    blocks = dictionary.get("blocks", [])

    for block in blocks:
        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if text:
                    parts.append(text)

    return normalize_space(" ".join(parts))


def parse_dict_page(
    dictionary: dict[str, Any],
    country_code: str,
) -> list[dict[str, Any]]:

    records = []

    text = collect_dict_text(dictionary)

    if not text:
        return records

    matches = list(
        re.finditer(r"(?<!\d)(\d{6})(?!\d)", text)
    )

    for match in matches:
        code = match.group(1)

        before = text[max(0, match.start() - 180):match.start()]
        after = text[match.end():match.end() + 180]

        before = normalize_space(before)
        after = normalize_space(after)

        left_parts = before.split()

        if len(left_parts) > 12:
            left_parts = left_parts[-12:]

        right_parts = after.split()

        if len(right_parts) > 15:
            right_parts = right_parts[:15]

        russian = normalize_space(" ".join(left_parts))
        latin = normalize_space(" ".join(right_parts))

        russian = clean_station_name(russian)
        latin = extract_latin_name(latin)

        if not valid_name(russian):
            continue

        latin_words = []

        for word in latin.split():
            if re.fullmatch(r"[\d,./()]+", word):
                break
            latin_words.append(word)
            if len(latin_words) >= 8:
                break

        latin = normalize_space(" ".join(latin_words))

        if not valid_name(latin):
            continue

        record = make_record(
            country_code=country_code,
            code=code,
            russian_name=russian,
            latin_name=latin,
        )

        if record:
            records.append(record)

    return records


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    result = []
    seen = set()

    for record in records:
        country_code = record.get("country_code", "")
        code = str(record.get("code", ""))
        key = (country_code, code)

        if key in seen:
            continue

        seen.add(key)
        result.append(record)

    return result


def normalize_name_for_match(value: str) -> str:
    """Нормализация названия только для сравнения результатов парсеров."""
    value = clean_station_name(value).casefold()
    value = re.sub(r"[^a-zа-яё0-9]+", "", value)
    return value


# ============================================================
# PARSE ONE PDF
# ============================================================

def parse_pdf(
    pdf_bytes: bytes,
    country_code: str,
) -> list[dict[str, Any]]:

    print()
    print("=" * 70)
    print(f"PARSING COUNTRY: {country_code} {COUNTRIES[country_code]}")
    print("=" * 70)

    diagnostic_pdf(pdf_bytes, country_code)

    methods = extract_text_methods(pdf_bytes)

    method_counts = {}
    for method_name, pages in methods.items():
        method_counts[method_name] = count_codes(pages)

    print()
    print("EXTRACTION METHOD CODE COUNTS")
    for method_name, count in method_counts.items():
        print(f"  {method_name:8}: {count}")

    # 1. WORDS
    word_candidates = []

    for page_words in methods["words"]:
        if not page_words:
            continue
        word_candidates.extend(
            parse_words_page(page_words, country_code)
        )

    word_candidates = deduplicate_records(word_candidates)
    print("WORD PARSER RECORDS:", len(word_candidates))

    # 2. BLOCKS
    block_candidates = []

    for page_blocks in methods["blocks"]:
        if not page_blocks:
            continue
        block_candidates.extend(
            parse_blocks_page(page_blocks, country_code)
        )

    block_candidates = deduplicate_records(block_candidates)
    print("BLOCK PARSER RECORDS:", len(block_candidates))

    # 3. DICT — теперь используется как источник данных,
    # а не только для диагностики.
    dict_candidates = []

    for page_dict in methods["dict"]:
        if not page_dict:
            continue
        dict_candidates.extend(
            parse_dict_page(page_dict, country_code)
        )

    dict_candidates = deduplicate_records(dict_candidates)
    print("DICT PARSER RECORDS:", len(dict_candidates))

    # 4. Объединение по приоритету: words > blocks > dict.
    # Код, уже принятый более надёжным источником,
    # из менее надёжного не дублируется.
    candidates: list[dict[str, Any]] = []
    seen_codes: set[str] = set()

    for source_name, source_records in (
        ("words", word_candidates),
        ("blocks", block_candidates),
        ("dict", dict_candidates),
    ):
        added = 0
        for record in source_records:
            code = str(record.get("code", ""))
            if not code or code in seen_codes:
                continue
            if not strict_station_name(record.get("name", ""), "ru"):
                continue
            if not strict_station_name(record.get("latin_name", ""), "latin"):
                continue
            candidates.append(record)
            seen_codes.add(code)
            added += 1
        print(f"ACCEPTED FROM {source_name.upper()}: {added}")

    candidates = deduplicate_records(candidates)
    candidates.sort(key=lambda record: str(record.get("code", "")))

    text_codes = []

    for page_text in methods["text"]:
        text_codes.extend(code_candidates_from_text(page_text))

    text_codes = list(dict.fromkeys(text_codes))

    print("TEXT UNIQUE CODES:", len(text_codes))

    print()
    print("FINAL PARSED RECORDS:", len(candidates))

    if candidates:
        print()
        print("FIRST RECORDS:")
        for record in candidates[:10]:
            print("  ", record)

    return candidates


# ============================================================
# VALIDATE COUNTRY RECORDS
# ============================================================

def validate_country_records(
    country_code: str,
    records: list[dict[str, Any]],
) -> None:

    if not records:
        raise RuntimeError(
            f"{country_code}: no station records parsed"
        )

    invalid_codes = []

    for record in records:
        code = str(record.get("code", ""))
        if not re.fullmatch(r"\d{6}", code):
            invalid_codes.append(record)

    if invalid_codes:
        raise RuntimeError(
            f"{country_code}: {len(invalid_codes)} invalid station codes"
        )

    missing_names = []

    for record in records:
        if not valid_name(record.get("name", "")):
            missing_names.append(record)
        if not valid_name(record.get("latin_name", "")):
            missing_names.append(record)

    if missing_names:
        raise RuntimeError(
            f"{country_code}: records with invalid names: "
            f"{len(missing_names)}"
        )


# ============================================================
# LOAD OLD DATABASE
# ============================================================

def load_existing_database() -> list[dict[str, Any]]:
    if not OUTPUT_FILE.exists():
        return []

    try:
        with OUTPUT_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            return []

        return data

    except Exception as exc:
        print("WARNING: cannot read existing stations.json:", exc)
        return []


# ============================================================
# MERGE
# ============================================================

def merge_records(
    new_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    existing = load_existing_database()

    new_country_codes = {
        record["country_code"]
        for record in new_records
    }

    result = []

    for record in existing:
        country_code = record.get("country_code")

        if country_code not in ACTIVE_COUNTRIES:
            continue

        if country_code in new_country_codes:
            continue

        result.append(record)

    result.extend(new_records)

    return deduplicate_records(result)


# ============================================================
# GLOBAL VALIDATION
# ============================================================

def validate_all_countries(
    stations: list[dict[str, Any]],
) -> None:

    print()
    print("=" * 70)
    print("STATISTICS BY COUNTRY")
    print("=" * 70)

    counters = Counter(
        station.get("country_code", "")
        for station in stations
    )

    missing = []

    for code, country in ACTIVE_COUNTRIES.items():

        count = counters.get(code, 0)

        if count:
            print(f"✓ {code:2} {country:<25} {count:6}")
        else:
            print(f"✗ {code:2} {country:<25} {count:6}")
            missing.append(code)

    print()
    print("=" * 70)
    print("CHECKING ACTIVE COUNTRIES")
    print("=" * 70)

    found = sum(
        1 for code in ACTIVE_COUNTRIES
        if counters.get(code, 0) > 0
    )

    print(f"Countries in database: {len(counters)}")
    print(f"Countries with data:   {found}")
    print(f"Countries without data: {len(missing)}")

    if missing:
        print()
        print("MISSING:")
        for code in missing:
            print(f"  {code} — {COUNTRIES[code]}")
        raise RuntimeError(
            "КРИТИЧЕСКАЯ ОШИБКА: "
            f"отсутствует {len(missing)} стран. "
            "stations.json НЕ изменён."
        )

    unexpected = sorted(set(counters) - set(ACTIVE_COUNTRIES))

    if unexpected:
        raise RuntimeError(
            "Обнаружены неизвестные country_code: "
            + ", ".join(unexpected)
        )

    invalid_codes = []

    for station in stations:
        code = str(station.get("code", ""))
        if not re.fullmatch(r"\d{6}", code):
            invalid_codes.append(station)

    print()
    print("=" * 70)
    print("FINAL VALIDATION")
    print("=" * 70)

    print(f"Total stations: {len(stations)}")
    print(f"Invalid codes: {len(invalid_codes)}")

    if invalid_codes:
        for station in invalid_codes[:20]:
            print(station)
        raise RuntimeError("Обнаружены некорректные 6-значные коды.")

    missing_ru = [
        station for station in stations
        if not valid_name(station.get("name", ""))
    ]
    missing_latin = [
        station for station in stations
        if not valid_name(station.get("latin_name", ""))
    ]

    print(f"Without Russian name: {len(missing_ru)}")
    print(f"Without Latin name:   {len(missing_latin)}")

    if missing_ru:
        raise RuntimeError("Есть станции без русского названия.")
    if missing_latin:
        raise RuntimeError("Есть станции без латинского названия.")

    duplicate_groups = {}

    for station in stations:
        key = (station.get("country_code"), station.get("code"))
        duplicate_groups.setdefault(key, []).append(station)

    duplicates = {
        key: value for key, value in duplicate_groups.items()
        if len(value) > 1
    }

    print(f"Duplicate country/code groups: {len(duplicates)}")

    if duplicates:
        print()
        print("WARNING: DUPLICATES")
        for key, values in list(duplicates.items())[:20]:
            print(f"  {key[0]} / {key[1]}")
            for value in values:
                print(
                    f"    - {value.get('name')} | "
                    f"{value.get('latin_name')}"
                )

    print()
    print("✓ FINAL VALIDATION PASSED")


# ============================================================
# SAVE
# ============================================================

def save_database(
    stations: list[dict[str, Any]],
) -> None:

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    temp_file = OUTPUT_FILE.with_suffix(".json.tmp")

    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(
            stations,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")

    temp_file.replace(OUTPUT_FILE)


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=" * 70)
    print("OSJD RAILWAY STATION DATABASE UPDATE")
    print("=" * 70)

    print()
    print("Target active countries:", len(ACTIVE_COUNTRIES))
    print("Output:", OUTPUT_FILE)

    pdf_urls = get_pdf_urls()

    print()
    print("=" * 70)
    print("PDF SOURCES")
    print("=" * 70)

    for code, country in ACTIVE_COUNTRIES.items():
        url = pdf_urls.get(code)
        if url:
            print(f"✓ {code} {country}: {url}")
        else:
            print(f"✗ {code} {country}: NO SOURCE")

    missing_sources = [
        code for code in ACTIVE_COUNTRIES
        if code not in pdf_urls
    ]

    if missing_sources:
        raise RuntimeError(
            "Не найдены PDF для стран: " + ", ".join(missing_sources)
        )

    existing_records = load_existing_database()

    all_new_records: list[dict[str, Any]] = []
    country_statistics: dict[str, int] = {}

    for country_code, country_name in ACTIVE_COUNTRIES.items():

        url = pdf_urls[country_code]

        print()
        print("=" * 70)
        print(f"COUNTRY {country_code} — {country_name}")
        print("=" * 70)

        try:
            pdf_bytes = download_pdf(url)

            records = parse_pdf(pdf_bytes, country_code)
            records = deduplicate_records(records)
            validate_country_records(country_code, records)

            existing_country_records = [
                item for item in existing_records
                if item.get("country_code") == country_code
            ]
            existing_count = len(existing_country_records)

            if existing_count:
                minimum_expected = max(
                    1,
                    math.ceil(existing_count * 0.65),
                )
                if len(records) < minimum_expected:
                    print()
                    print(
                        f"⚠ {country_code}: parsed only {len(records)} "
                        f"records; existing database has {existing_count}. "
                        f"Minimum safe threshold is {minimum_expected}. "
                        f"Keeping existing records for this country."
                    )
                    country_statistics[country_code] = existing_count
                    # Не добавляем в all_new_records — старые записи
                    # сохранятся автоматически в merge_records().
                    continue

            country_statistics[country_code] = len(records)
            all_new_records.extend(records)

            print()
            print(f"✓ {country_code}: {len(records)} records")

        except Exception as exc:
            print()
            print(f"✗ ERROR {country_code}:")
            print(repr(exc))
            raise RuntimeError(
                f"Ошибка обработки {country_code} {country_name}: {exc}"
            ) from exc

        time.sleep(0.5)

    print()
    print("=" * 70)
    print("COUNTRY COVERAGE")
    print("=" * 70)

    for code, country in ACTIVE_COUNTRIES.items():
        count = country_statistics.get(code, 0)
        if count:
            print(f"✓ {code} {country:<25} {count}")
        else:
            print(f"✗ {code} {country:<25} 0")

    missing = [
        code for code in ACTIVE_COUNTRIES
        if not country_statistics.get(code, 0)
    ]

    if missing:
        raise RuntimeError(
            "Не получены данные для: "
            + ", ".join(missing)
            + ". stations.json НЕ изменён."
        )

    merged = merge_records(all_new_records)

    print()
    print("=" * 70)
    print("MERGED DATABASE")
    print("=" * 70)

    print("New parsed records:", len(all_new_records))
    print("Final records:", len(merged))

    validate_all_countries(merged)

    print()
    print("=" * 70)
    print("SAVING DATABASE")
    print("=" * 70)

    save_database(merged)

    print()
    print("=" * 70)
    print("SUCCESS")
    print("=" * 70)

    print(f"stations.json updated: {len(merged)} records")


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)

    except Exception as exc:
        print()
        print("=" * 70)
        print("FATAL ERROR")
        print("=" * 70)
        print(str(exc))
        print()
        print("stations.json НЕ изменён.")
        sys.exit(1)
