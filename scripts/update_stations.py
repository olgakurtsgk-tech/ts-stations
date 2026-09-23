```python
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import fitz
import requests
from bs4 import BeautifulSoup


# ============================================================
# НАСТРОЙКИ
# ============================================================

OSJD_PAGE = "https://osjd.org/ru/8974/page/106077?id=2227"

OUTPUT = Path("data/stations.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/140.0 Safari/537.36"
    )
}

MIN_STATIONS = 10


# ============================================================
# ПОЛУЧЕНИЕ СТРАНИЦЫ ОСЖД
# ============================================================

def get_osjd_page():

    print("Получаем страницу ОСЖД...")

    response = requests.get(
        OSJD_PAGE,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    print(
        f"Страница получена: "
        f"{len(response.text)} символов"
    )

    return response.text


# ============================================================
# ПОИСК PDF-ДОКУМЕНТОВ
# ============================================================

def find_documents(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    documents = []

    seen = set()

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link["href"]

        title = " ".join(
            link.stripped_strings
        )

        if "file=" not in href:
            continue

        if "api/media/resources" not in href:
            continue

        full_url = urljoin(
            "https://osjd.org",
            href
        )

        parsed = urlparse(
            full_url
        )

        params = parse_qs(
            parsed.query
        )

        file_values = params.get(
            "file"
        )

        if not file_values:
            continue

        pdf_url = unquote(
            file_values[0]
        )

        if pdf_url.startswith("/"):
            pdf_url = urljoin(
                "https://osjd.org",
                pdf_url
            )

        pdf_url = pdf_url.split("?")[0]

        if pdf_url in seen:
            continue

        seen.add(pdf_url)

        documents.append(
            {
                "name": title,
                "url": pdf_url
            }
        )

    print(
        f"Найдено PDF-документов: "
        f"{len(documents)}"
    )

    return documents


# ============================================================
# ПОИСК РОССИЙСКОГО PDF
# ============================================================

def find_russian_document(documents):

    keywords = [
        "российских железных дорог",
        "российских ж. д.",
        "российских железных",
    ]

    for document in documents:

        name = document["name"].lower()

        for keyword in keywords:

            if keyword in name:

                print("")
                print(
                    "Найден российский документ:"
                )

                print(
                    document["name"]
                )

                print(
                    document["url"]
                )

                return document

    return None


# ============================================================
# СКАЧИВАНИЕ PDF
# ============================================================

def download_pdf(url):

    print("")
    print("Скачиваем PDF...")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=180
    )

    response.raise_for_status()

    content = response.content

    print(
        f"Получено: "
        f"{len(content) / 1024 / 1024:.2f} MB"
    )

    if not content.startswith(
        b"%PDF"
    ):

        print("")
        print(
            "ОШИБКА: полученный файл "
            "не является PDF."
        )

        raise RuntimeError(
            "OSJD вернул не PDF"
        )

    return content


# ============================================================
# ИЗВЛЕЧЕНИЕ ТЕКСТА ИЗ PDF
# ============================================================

def extract_pdf_pages(pdf_bytes):

    print("")
    print("Открываем PDF...")

    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    print(
        f"Страниц в PDF: "
        f"{len(document)}"
    )

    pages = []

    for page_number, page in enumerate(
        document,
        start=1
    ):

        text = page.get_text(
            "text"
        )

        pages.append(
            {
                "number": page_number,
                "text": text
            }
        )

    document.close()

    return pages


# ============================================================
# СЛУЖЕБНЫЕ ФУНКЦИИ
# ============================================================

def normalize_spaces(text):

    return " ".join(
        text.strip().split()
    )


def is_code(text):

    return bool(
        re.fullmatch(
            r"\d{6}",
            text.strip()
        )
    )


def looks_like_station_name(text):

    text = normalize_spaces(
        text
    )

    if not text:
        return False

    if len(text) < 2:
        return False

    lower = text.lower()

    bad_phrases = [
        "памятка осжд",
        "регламент",
        "перечень грузовых станций",
        "грузовых станций железных дорог",
        "по состоянию на",
        "наименование железной дороги",
        "код станции",
        "станция",
    ]

    for phrase in bad_phrases:

        if phrase in lower:
            return False

    return True


# ============================================================
# ПОПЫТКА №1
#
# Ищем строки:
#
# 123456 Название станции
#
# ============================================================

def parse_same_line(text):

    stations = []

    lines = text.splitlines()

    for line in lines:

        line = normalize_spaces(
            line
        )

        if not line:
            continue

        match = re.match(
            r"^(\d{6})\s+(.+)$",
            line
        )

        if not match:
            continue

        code = match.group(1)

        name = normalize_spaces(
            match.group(2)
        )

        if not looks_like_station_name(
            name
        ):
            continue

        stations.append(
            {
                "code": code,
                "name": name
            }
        )

    return stations


# ============================================================
# ПОПЫТКА №2
#
# PDF может хранить код и название
# отдельными текстовыми строками:
#
# 657606
# Самара-Сортировочная
#
# Поэтому ищем код, а затем ближайшую
# подходящую строку.
# ============================================================

def parse_separate_lines(text):

    stations = []

    raw_lines = text.splitlines()

    lines = []

    for line in raw_lines:

        line = normalize_spaces(
            line
        )

        if line:

            lines.append(line)

    for i, line in enumerate(lines):

        if not is_code(line):
            continue

        code = line

        candidates = []

        for j in range(
            i + 1,
            min(
                i + 6,
                len(lines)
            )
        ):

            candidate = lines[j]

            if is_code(candidate):
                break

            if looks_like_station_name(
                candidate
            ):

                candidates.append(
                    candidate
                )

        if not candidates:
            continue

        name = candidates[0]

        stations.append(
            {
                "code": code,
                "name": name
            }
        )

    return stations


# ============================================================
# ПОПЫТКА №3
#
# Используем координаты PDF.
#
# Это важно для таблиц, где визуально
# код и название находятся рядом,
# но обычный get_text("text")
# разбивает их по строкам.
# ============================================================

def parse_pdf_blocks(page):

    stations = []

    blocks = page.get_text(
        "blocks"
    )

    rows = []

    for block in blocks:

        if len(block) < 5:
            continue

        x0 = block[0]
        y0 = block[1]
        x1 = block[2]
        y1 = block[3]
        text = block[4]

        text = normalize_spaces(
            text
        )

        if not text:
            continue

        rows.append(
            {
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "text": text
            }
        )

    for row in rows:

        code_match = re.search(
            r"\b(\d{6})\b",
            row["text"]
        )

        if not code_match:
            continue

        code = code_match.group(1)

        remaining = (
            row["text"]
            .replace(
                code,
                "",
                1
            )
            .strip()
        )

        remaining = normalize_spaces(
            remaining
        )

        if looks_like_station_name(
            remaining
        ):

            stations.append(
                {
                    "code": code,
                    "name": remaining
                }
            )

            continue

        # Ищем ближайший блок
        # справа от кода.

        candidates = []

        for other in rows:

            if other is row:
                continue

            vertical_distance = abs(
                other["y0"] -
                row["y0"]
            )

            horizontal_distance = (
                other["x0"] -
                row["x1"]
            )

            if vertical_distance > 12:
                continue

            if horizontal_distance < -5:
                continue

            if horizontal_distance > 500:
                continue

            if not looks_like_station_name(
                other["text"]
            ):
                continue

            candidates.append(
                (
                    horizontal_distance,
                    vertical_distance,
                    other["text"]
                )
            )

        if candidates:

            candidates.sort(
                key=lambda item: (
                    item[1],
                    item[0]
                )
            )

            name = candidates[0][2]

            stations.append(
                {
                    "code": code,
                    "name": name
                }
            )

    return stations


# ============================================================
# ОБЩИЙ ПАРСЕР РОССИЙСКОГО PDF
# ============================================================

def parse_russian_pdf(pages):

    print("")
    print("Разбираем PDF...")

    all_stations = []

    # --------------------------------------------------------
    # Попытка 1 и 2
    # --------------------------------------------------------

    for page in pages:

        text = page["text"]

        found = parse_same_line(
            text
        )

        if not found:

            found = parse_separate_lines(
                text
            )

        for station in found:

            station["_page"] = page["number"]

            all_stations.append(
                station
            )

    # --------------------------------------------------------
    # Попытка 3 — координаты PDF
    # --------------------------------------------------------

    if len(all_stations) < MIN_STATIONS:

        print("")
        print(
            "Обычный разбор дал мало "
            "станций."
        )

        print(
            "Пробуем разобрать PDF "
            "по координатам таблицы..."
        )

        document_bytes = None

        # Нам здесь нужен исходный PDF,
        # поэтому координатный разбор
        # выполняется отдельно в main().
        #
        # Этот блок оставлен для совместимости.
        #
        # Реальный координатный разбор
        # выполняется функцией
        # parse_pdf_with_coordinates().

    return all_stations


# ============================================================
# КООРДИНАТНЫЙ ПАРСЕР ВСЕГО PDF
# ============================================================

def parse_pdf_with_coordinates(pdf_bytes):

    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    stations = []

    for page_number, page in enumerate(
        document,
        start=1
    ):

        found = parse_pdf_blocks(
            page
        )

        for station in found:

            station["_page"] = (
                page_number
            )

            stations.append(
                station
            )

    document.close()

    return stations


# ============================================================
# УДАЛЕНИЕ ДУБЛИКАТОВ
# ============================================================

def unique_stations(stations):

    result = {}

    for station in stations:

        code = station.get(
            "code",
            ""
        )

        if not is_code(code):
            continue

        name = normalize_spaces(
            station.get(
                "name",
                ""
            )
        )

        if not name:
            continue

        # Если код уже найден,
        # оставляем первый вариант.

        if code not in result:

            result[code] = {
                "name": name,
                "name_lat": "",
                "code": code,
                "country": "Россия",
                "country_code": "RU",
                "railway": "",
                "operations": [],
                "border_code": ""
            }

    return list(
        result.values()
    )


# ============================================================
# ДИАГНОСТИКА
# ============================================================

def print_sample(stations):

    print("")
    print("=" * 60)
    print("ПЕРВЫЕ НАЙДЕННЫЕ СТАНЦИИ")
    print("=" * 60)

    for station in stations[:30]:

        print(
            f'{station["code"]} — '
            f'{station["name"]}'
        )

    print("=" * 60)


# ============================================================
# СОХРАНЕНИЕ
# ============================================================

def save_json(stations):

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            stations,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("")
    print(
        f"JSON сохранён: {OUTPUT}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 60)
    print("ОБНОВЛЕНИЕ ЖД-СТАНЦИЙ ОСЖД")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. Страница ОСЖД
    # --------------------------------------------------------

    html = get_osjd_page()

    # --------------------------------------------------------
    # 2. Документы
    # --------------------------------------------------------

    documents = find_documents(
        html
    )

    if not documents:

        raise RuntimeError(
            "Не найдено ни одного PDF ОСЖД."
        )

    # --------------------------------------------------------
    # 3. Россия
    # --------------------------------------------------------

    russian = find_russian_document(
        documents
    )

    if not russian:

        raise RuntimeError(
            "Российский PDF ОСЖД "
            "не найден."
        )

    # --------------------------------------------------------
    # 4. Скачать PDF
    # --------------------------------------------------------

    pdf_bytes = download_pdf(
        russian["url"]
    )

    # --------------------------------------------------------
    # 5. Извлечь текст
    # --------------------------------------------------------

    pages = extract_pdf_pages(
        pdf_bytes
    )

    # --------------------------------------------------------
    # 6. Печатаем небольшой фрагмент
    #    для диагностики
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("ПЕРВЫЙ ФРАГМЕНТ PDF")
    print("=" * 60)

    preview_lines = []

    for page in pages[:2]:

        for line in page["text"].splitlines():

            line = normalize_spaces(
                line
            )

            if line:

                preview_lines.append(
                    line
                )

    for line in preview_lines[:80]:

        print(line)

    print("=" * 60)

    # --------------------------------------------------------
    # 7. Первый парсер
    # --------------------------------------------------------

    stations = parse_russian_pdf(
        pages
    )

    print("")
    print(
        f"После текстового разбора: "
        f"{len(stations)}"
    )

    # --------------------------------------------------------
    # 8. Если мало — координатный разбор
    # --------------------------------------------------------

    if len(stations) < MIN_STATIONS:

        print("")
        print(
            "Запускаем координатный "
            "разбор PDF..."
        )

        coordinate_stations = (
            parse_pdf_with_coordinates(
                pdf_bytes
            )
        )

        print(
            "Найдено координатным "
            "методом: "
            f"{len(coordinate_stations)}"
        )

        stations.extend(
            coordinate_stations
        )

    # --------------------------------------------------------
    # 9. Уникальные станции
    # --------------------------------------------------------

    stations = unique_stations(
        stations
    )

    print("")
    print(
        f"Уникальных станций: "
        f"{len(stations)}"
    )

    # --------------------------------------------------------
    # 10. КРИТИЧЕСКАЯ ПРОВЕРКА
    # --------------------------------------------------------

    if len(stations) < MIN_STATIONS:

        print("")
        print("=" * 60)
        print("ОШИБКА")
        print("=" * 60)

        print(
            "Парсер нашёл слишком мало "
            "станций."
        )

        print(
            f"Найдено: {len(stations)}"
        )

        print(
            f"Минимум: {MIN_STATIONS}"
        )

        print("")
        print(
            "Файл stations.json НЕ будет "
            "перезаписан."
        )

        print("=" * 60)

        sys.exit(1)

    # --------------------------------------------------------
    # 11. Показать результат
    # --------------------------------------------------------

    print_sample(
        stations
    )

    # --------------------------------------------------------
    # 12. Сохранить
    # --------------------------------------------------------

    save_json(
        stations
    )

    print("")
    print("=" * 60)
    print("ГОТОВО")
    print("=" * 60)

    print(
        f"Станций записано: "
        f"{len(stations)}"
    )


if __name__ == "__main__":

    main()
```
