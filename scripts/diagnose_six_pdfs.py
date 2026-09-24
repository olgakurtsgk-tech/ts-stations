import re
import sys

import pymupdf
import requests
from bs4 import BeautifulSoup


# ============================================================
# НАСТРОЙКИ
# ============================================================

TARGET_COUNTRIES = {
    "Иран": "IR",
    "Китай": "CN",
    "Чехия": "CZ",
    "Эстония": "EE",
}

MAX_SAMPLE_LINES = 80
MAX_CODE_LINES = 100
MAX_PAGES_TO_SHOW = 8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
}


# ============================================================
# ИМПОРТ ОСНОВНОГО ПАРСЕРА
# ============================================================

try:
    import update_stations
except ImportError:
    print()
    print("=" * 70)
    print("ОШИБКА")
    print("=" * 70)
    print()
    print(
        "Не удалось импортировать scripts/update_stations.py"
    )
    print()
    print(
        "Запускайте этот скрипт из корня репозитория:"
    )
    print()
    print(
        "python scripts/diagnose_six_pdfs.py"
    )
    print()
    sys.exit(1)


OSJD_PAGE = update_stations.OSJD_PAGE


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def identify_country(text):
    """
    Определяет одну из четырёх диагностируемых стран
    по тексту ссылки ОСЖД.
    """

    text_clean = clean_text(text).lower()

    country_aliases = {
        "Иран": [
            "иран",
            "iran",
        ],
        "Китай": [
            "китай",
            "china",
        ],
        "Чехия": [
            "чехия",
            "czech",
            "czechia",
            "чешск",
        ],
        "Эстония": [
            "эстония",
            "estonia",
        ],
    }

    for country, aliases in country_aliases.items():

        for alias in aliases:

            if alias.lower() in text_clean:

                return (
                    country,
                    TARGET_COUNTRIES[country],
                )

    return None, None


def get_pdf_url(href):
    """
    Совместимо с текущим update_stations.py.

    В актуальном основном парсере используется
    функция get_pdf_urls(), поэтому здесь
    не обращаемся к несуществующей get_pdf_url().
    """

    # --------------------------------------------------------
    # Сначала пробуем актуальную функцию get_pdf_urls()
    # --------------------------------------------------------

    if hasattr(update_stations, "get_pdf_urls"):

        try:

            result = update_stations.get_pdf_urls(
                href
            )

            if isinstance(result, str):

                if result:
                    return result

            if isinstance(result, (list, tuple)):

                for url in result:

                    if url:
                        return url

        except Exception as error:

            print(
                "get_pdf_urls ERROR:",
                repr(error)
            )

    # --------------------------------------------------------
    # Если функция вернула ничего,
    # пытаемся обработать ссылку самостоятельно.
    # --------------------------------------------------------

    if href.startswith("http://"):
        return href.replace(
            "http://",
            "https://",
            1
        )

    if href.startswith("https://"):
        return href

    if href.startswith("//"):
        return "https:" + href

    if href.startswith("/"):

        return (
            "https://osjd.org"
            + href
        )

    return href


def download_pdf(url):

    print()
    print("DOWNLOAD:")
    print(url)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=180
    )

    print(
        "HTTP STATUS:",
        response.status_code
    )

    print(
        "CONTENT TYPE:",
        response.headers.get(
            "content-type",
            ""
        )
    )

    print(
        "SIZE:",
        f"{len(response.content):,}",
        "bytes"
    )

    response.raise_for_status()

    if not response.content.startswith(
        b"%PDF"
    ):

        raise RuntimeError(
            "Полученный файл не является PDF"
        )

    return response.content


# ============================================================
# ПОИСК PDF НА СТРАНИЦЕ ОСЖД
# ============================================================

def find_country_pdfs():

    print()
    print("=" * 70)
    print("SEARCHING OSJD PDF SOURCES")
    print("=" * 70)

    print()
    print("OSJD PAGE:")
    print(OSJD_PAGE)

    print()

    response = requests.get(
        OSJD_PAGE,
        headers=HEADERS,
        timeout=120
    )

    print(
        "HTTP STATUS:",
        response.status_code
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    results = {}

    # --------------------------------------------------------
    # Ищем все ссылки
    # --------------------------------------------------------

    for link in soup.find_all("a"):

        text = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        href = link.get("href")

        if not href:
            continue

        # Основной текст ссылки ОСЖД
        if (
            "Перечень грузовых станций"
            not in text
        ):
            continue

        country, country_code = identify_country(
            text
        )

        if not country:
            continue

        if country not in TARGET_COUNTRIES:
            continue

        pdf_url = get_pdf_url(
            href
        )

        results[country] = {
            "country": country,
            "country_code": country_code,
            "title": text,
            "url": pdf_url,
        }

    return results


# ============================================================
# ДИАГНОСТИКА ОДНОГО PDF
# ============================================================

def diagnose_pdf(
    country,
    item
):

    print()
    print()
    print("=" * 70)
    print(
        f"COUNTRY: {country}"
    )
    print(
        f"CODE: {item['country_code']}"
    )
    print("=" * 70)

    print()
    print("DOCUMENT TITLE:")
    print(
        item["title"]
    )

    print()
    print("PDF URL:")
    print(
        item["url"]
    )

    # --------------------------------------------------------
    # Скачивание
    # --------------------------------------------------------

    try:

        pdf_bytes = download_pdf(
            item["url"]
        )

    except Exception as error:

        print()
        print("DOWNLOAD ERROR:")
        print(
            repr(error)
        )

        return

    # --------------------------------------------------------
    # Открытие PDF
    # --------------------------------------------------------

    try:

        document = pymupdf.open(
            stream=pdf_bytes,
            filetype="pdf"
        )

    except Exception as error:

        print()
        print("PDF OPEN ERROR:")
        print(
            repr(error)
        )

        return

    print()
    print("-" * 70)
    print("PDF INFORMATION")
    print("-" * 70)

    print(
        "Pages:",
        len(document)
    )

    print(
        "Metadata:",
        document.metadata
    )

    total_text_length = 0
    total_lines = 0
    total_six_digit_codes = 0

    pages_with_codes = []
    pages_with_station_headers = []

    all_code_matches = []

    # ========================================================
    # ПРОХОДИМ ПО СТРАНИЦАМ
    # ========================================================

    for page_index in range(
        len(document)
    ):

        page = document[
            page_index
        ]

        text = page.get_text(
            "text"
        )

        total_text_length += len(
            text
        )

        lines = text.splitlines()

        total_lines += len(
            lines
        )

        codes = re.findall(
            r"(?<!\d)\d{6}(?!\d)",
            text
        )

        if codes:

            total_six_digit_codes += len(
                codes
            )

            pages_with_codes.append(
                page_index + 1
            )

            all_code_matches.extend(
                codes
            )

        header_text = text.lower()

        if (
            "наименование станции"
            in header_text
            or "код станции"
            in header_text
            or "station code"
            in header_text
            or "station name"
            in header_text
        ):

            pages_with_station_headers.append(
                page_index + 1
            )

    # ========================================================
    # ОБЩАЯ СТАТИСТИКА
    # ========================================================

    print()
    print("-" * 70)
    print("TEXT EXTRACTION")
    print("-" * 70)

    print(
        "Total extracted text:",
        f"{total_text_length:,}",
        "characters"
    )

    print(
        "Total lines:",
        f"{total_lines:,}"
    )

    print(
        "6-digit codes:",
        f"{total_six_digit_codes:,}"
    )

    print()
    print(
        "Pages containing 6-digit codes:"
    )

    if pages_with_codes:

        print(
            ", ".join(
                str(x)
                for x in pages_with_codes[
                    :100
                ]
            )
        )

    else:

        print("NONE")

    print()
    print(
        "Pages containing station-table headers:"
    )

    if pages_with_station_headers:

        print(
            ", ".join(
                str(x)
                for x in pages_with_station_headers
            )
        )

    else:

        print("NONE")

    # ========================================================
    # УНИКАЛЬНЫЕ КОДЫ
    # ========================================================

    unique_codes = sorted(
        set(
            all_code_matches
        )
    )

    print()
    print("-" * 70)
    print("UNIQUE 6-DIGIT CODES")
    print("-" * 70)

    print(
        "Unique codes:",
        len(unique_codes)
    )

    if unique_codes:

        for code in unique_codes[
            :MAX_CODE_LINES
        ]:

            print(
                code
            )

        if (
            len(unique_codes)
            > MAX_CODE_LINES
        ):

            print(
                "... and",
                len(unique_codes)
                - MAX_CODE_LINES,
                "more"
            )

    else:

        print(
            "NO 6-DIGIT CODES FOUND"
        )

    # ========================================================
    # РАЗНЫЕ СПОСОБЫ ИЗВЛЕЧЕНИЯ
    # ========================================================

    print()
    print("-" * 70)
    print("PYMUPDF EXTRACTION METHODS")
    print("-" * 70)

    methods = [
        "text",
        "blocks",
        "words",
        "dict",
    ]

    for method in methods:

        print()
        print(
            f"METHOD: {method}"
        )

        total_items = 0
        total_chars = 0
        total_codes = 0

        for page_index in range(
            len(document)
        ):

            page = document[
                page_index
            ]

            try:

                data = page.get_text(
                    method
                )

                if isinstance(
                    data,
                    str
                ):

                    total_items += len(
                        data.splitlines()
                    )

                    total_chars += len(
                        data
                    )

                    total_codes += len(
                        re.findall(
                            r"(?<!\d)\d{6}(?!\d)",
                            data
                        )
                    )

                elif isinstance(
                    data,
                    list
                ):

                    total_items += len(
                        data
                    )

                    total_chars += len(
                        str(data)
                    )

                    total_codes += len(
                        re.findall(
                            r"(?<!\d)\d{6}(?!\d)",
                            str(data)
                        )
                    )

                elif isinstance(
                    data,
                    dict
                ):

                    total_items += len(
                        data
                    )

                    total_chars += len(
                        str(data)
                    )

                    total_codes += len(
                        re.findall(
                            r"(?<!\d)\d{6}(?!\d)",
                            str(data)
                        )
                    )

            except Exception as error:

                print(
                    "  ERROR:",
                    repr(error)
                )

        print(
            "  items:",
            total_items
        )

        print(
            "  characters:",
            total_chars
        )

        print(
            "  6-digit codes:",
            total_codes
        )

    # ========================================================
    # RAW TEXT
    # ========================================================

    print()
    print("-" * 70)
    print("RAW TEXT SAMPLE")
    print("-" * 70)

    pages_to_show = min(
        len(document),
        MAX_PAGES_TO_SHOW
    )

    for page_index in range(
        pages_to_show
    ):

        page = document[
            page_index
        ]

        text = page.get_text(
            "text"
        )

        print()
        print(
            f"### PAGE {page_index + 1}"
        )

        print()

        lines = text.splitlines()

        if not lines:

            print(
                "[NO TEXT EXTRACTED]"
            )

            continue

        for number, line in enumerate(
            lines[
                :MAX_SAMPLE_LINES
            ],
            start=1
        ):

            clean_line = line.strip()

            if not clean_line:
                continue

            print(
                f"{number:03d}: "
                f"{clean_line}"
            )

        if (
            len(lines)
            > MAX_SAMPLE_LINES
        ):

            print(
                f"... "
                f"{len(lines) - MAX_SAMPLE_LINES} "
                f"more lines"
            )

    # ========================================================
    # BLOCKS
    # ========================================================

    print()
    print("-" * 70)
    print("TEXT BLOCK SAMPLE")
    print("-" * 70)

    for page_index in range(
        min(
            len(document),
            3
        )
    ):

        page = document[
            page_index
        ]

        print()
        print(
            f"### PAGE {page_index + 1}"
        )

        try:

            blocks = page.get_text(
                "blocks"
            )

            print(
                "Blocks:",
                len(blocks)
            )

            for block_number, block in enumerate(
                blocks[:30],
                start=1
            ):

                print()
                print(
                    f"BLOCK {block_number}"
                )

                print(
                    repr(block)
                )

        except Exception as error:

            print(
                "BLOCK ERROR:",
                repr(error)
            )

    # ========================================================
    # WORDS
    # ========================================================

    print()
    print("-" * 70)
    print("WORD SAMPLE")
    print("-" * 70)

    for page_index in range(
        min(
            len(document),
            2
        )
    ):

        page = document[
            page_index
        ]

        print()
        print(
            f"### PAGE {page_index + 1}"
        )

        try:

            words = page.get_text(
                "words"
            )

            print(
                "Words:",
                len(words)
            )

            for word in words[:100]:

                print(
                    repr(word)
                )

        except Exception as error:

            print(
                "WORDS ERROR:",
                repr(error)
            )

    # ========================================================
    # ТАБЛИЦЫ
    # ========================================================

    print()
    print("-" * 70)
    print("TABLE DETECTION")
    print("-" * 70)

    for page_index in range(
        min(
            len(document),
            10
        )
    ):

        page = document[
            page_index
        ]

        try:

            finder = page.find_tables()

            tables = finder.tables

            if tables:

                print()
                print(
                    f"PAGE {page_index + 1}: "
                    f"{len(tables)} table(s)"
                )

                for table_number, table in enumerate(
                    tables,
                    start=1
                ):

                    print(
                        f"  Table {table_number}: "
                        f"{table.row_count} rows x "
                        f"{table.col_count} columns"
                    )

                    try:

                        extracted = table.extract()

                        for row in extracted[:10]:

                            print(
                                "   ",
                                repr(row)
                            )

                    except Exception as error:

                        print(
                            "    "
                            "TABLE EXTRACT ERROR:",
                            repr(error)
                        )

            else:

                print(
                    f"PAGE {page_index + 1}: "
                    "no tables detected"
                )

        except Exception as error:

            print(
                f"PAGE {page_index + 1}: "
                f"table detection error: "
                f"{error}"
            )

    # ========================================================
    # ИТОГ
    # ========================================================

    print()
    print("=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)

    print()
    print(
        "Country:",
        country
    )

    print(
        "Country code:",
        item["country_code"]
    )

    print(
        "PDF pages:",
        len(document)
    )

    print(
        "Extracted characters:",
        f"{total_text_length:,}"
    )

    print(
        "Extracted lines:",
        f"{total_lines:,}"
    )

    print(
        "6-digit codes:",
        f"{total_six_digit_codes:,}"
    )

    print(
        "Unique 6-digit codes:",
        len(unique_codes)
    )

    if not total_text_length:

        print()
        print(
            "!!! IMPORTANT !!!"
        )

        print(
            "PDF contains no extractable text."
        )

        print(
            "Likely scanned/image PDF."
        )

    elif not total_six_digit_codes:

        print()
        print(
            "!!! IMPORTANT !!!"
        )

        print(
            "Text exists, but no 6-digit station "
            "codes were detected."
        )

        print(
            "Likely unusual PDF structure, "
            "broken text encoding, "
            "or codes split across PDF objects."
        )

    else:

        print()
        print(
            "6-digit codes ARE PRESENT."
        )

        print(
            "The problem is probably station-row "
            "reconstruction rather than PDF access."
        )

    print()
    print("=" * 70)
    print(
        "END OF DIAGNOSTIC:",
        country
    )
    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("OSJD FOUR-COUNTRY PDF DIAGNOSTIC")
    print("=" * 70)

    print()
    print(
        "Target countries:"
    )

    for country, code in TARGET_COUNTRIES.items():

        print(
            f"  {code} | {country}"
        )

    sources = find_country_pdfs()

    print()
    print("=" * 70)
    print("FOUND SOURCES")
    print("=" * 70)

    if not sources:

        print()
        print(
            "NO TARGET PDF SOURCES FOUND."
        )

        raise SystemExit(1)

    for country in TARGET_COUNTRIES:

        code = TARGET_COUNTRIES[
            country
        ]

        if country in sources:

            item = sources[
                country
            ]

            print()
            print(
                f"✓ {code} | {country}"
            )

            print(
                item["url"]
            )

        else:

            print()
            print(
                f"✗ {code} | {country}"
            )

            print(
                "SOURCE NOT FOUND"
            )

    # ========================================================
    # ДИАГНОСТИРУЕМ КАЖДУЮ НАЙДЕННУЮ СТРАНУ
    # ========================================================

    for country in TARGET_COUNTRIES:

        if country not in sources:
            continue

        diagnose_pdf(
            country,
            sources[country]
        )

    print()
    print("=" * 70)
    print("ALL DIAGNOSTICS FINISHED")
    print("=" * 70)

    print()

    print(
        "This script DOES NOT modify stations.json."
    )

    print()


if __name__ == "__main__":
    main()
