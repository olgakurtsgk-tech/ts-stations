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

# Минимум записей, который считаем нормальным результатом.
# Российский список намного больше этого числа.
MIN_STATIONS = 100


# ============================================================
# ЗАГРУЗКА СТРАНИЦЫ ОСЖД
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

        values = params.get(
            "file"
        )

        if not values:
            continue

        pdf_url = unquote(
            values[0]
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
# ПОИСК РОССИЙСКОГО ДОКУМЕНТА
# ============================================================

def find_russian_document(documents):

    keywords = [
        "перечень грузовых станций российских железных дорог",
        "российских железных дорог"
    ]

    for document in documents:

        name = document["name"].lower()

        for keyword in keywords:

            if keyword in name:

                print("")
                print(
                    "Найден российский PDF:"
                )

                print(
                    document["name"]
                )

                print(
                    document["url"]
                )

                return document

    raise RuntimeError(
        "Российский перечень ОСЖД "
        "не найден на странице ОСЖД."
    )


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

    data = response.content

    print(
        f"Размер PDF: "
        f"{len(data) / 1024 / 1024:.2f} MB"
    )

    if not data.startswith(b"%PDF"):

        raise RuntimeError(
            "ОСЖД вернул файл, "
            "который не является PDF."
        )

    return data


# ============================================================
# НОРМАЛИЗАЦИЯ ТЕКСТА
# ============================================================

def clean_text(text):

    text = text.replace(
        "\xa0",
        " "
    )

    text = text.replace(
        "–",
        "-"
    )

    text = text.replace(
        "—",
        "-"
    )

    text = " ".join(
        text.split()
    )

    return text.strip()


# ============================================================
# ПРОВЕРКА КОДА СТАНЦИИ
# ============================================================

def is_station_code(text):

    text = text.strip()

    return bool(
        re.fullmatch(
            r"\d{6}",
            text
        )
    )


# ============================================================
# ПРОВЕРКА НАЗВАНИЯ СТАНЦИИ
# ============================================================

def looks_like_russian_name(text):

    text = clean_text(text)

    if len(text) < 2:
        return False

    # В названии должна быть кириллица.
    if not re.search(
        r"[А-ЯЁ]",
        text
    ):
        return False

    bad = [
        "раздел",
        "наименование поля",
        "содержание поля",
        "код станции",
        "производимые коммерческие операции",
        "код пограничного перехода",
        "перечень грузовых станций",
        "общие сведения",
        "алфавитный перечень"
    ]

    lower = text.lower()

    for word in bad:

        if word in lower:
            return False

    return True


# ============================================================
# ПРОВЕРКА ЛАТИНСКОГО НАЗВАНИЯ
# ============================================================

def looks_like_latin_name(text):

    text = clean_text(text)

    if not text:
        return False

    return bool(
        re.search(
            r"[A-Za-z]",
            text
        )
    )


# ============================================================
# ОПЕРАЦИИ
# ============================================================

VALID_OPERATIONS = {
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "8Н",
    "8H",
    "9",
    "10",
    "10Н",
    "10H",
    "11",
    "11Н",
    "11H",
    "12",
    "12Н",
    "12H",
    "К",
    "K"
}


def extract_operations(tokens):

    operations = []
    border_code = ""

    for token in tokens:

        token = clean_text(
            token
        )

        if not token:
            continue

        # Иногда PDF объединяет:
        # 1,2,3,5
        parts = re.split(
            r"[,;]+",
            token
        )

        for part in parts:

            part = part.strip()

            if not part:
                continue

            # Пограничный код обычно состоит
            # из 3–4 цифр.
            if re.fullmatch(
                r"\d{3,4}",
                part
            ):

                if not border_code:
                    border_code = part

                continue

            # Нормализуем латинскую H
            # в кириллическую Н.
            normalized = part.upper()

            if normalized.endswith("H"):

                normalized = (
                    normalized[:-1] +
                    "Н"
                )

            if normalized in VALID_OPERATIONS:

                if normalized not in operations:

                    operations.append(
                        normalized
                    )

    return operations, border_code


# ============================================================
# РАЗБОР ОДНОЙ СТРОКИ PDF
#
# Используем слова PDF вместе с координатами.
# Это значительно надёжнее обычного splitlines().
# ============================================================

def parse_page(page):

    words = page.get_text(
        "words"
    )

    if not words:
        return []

    # Формат слова PyMuPDF:
    #
    # x0, y0, x1, y1,
    # text,
    # block_no,
    # line_no,
    # word_no
    #

    grouped = {}

    for word in words:

        if len(word) < 8:
            continue

        x0 = word[0]
        y0 = word[1]
        text = clean_text(
            word[4]
        )

        block_no = word[5]
        line_no = word[6]

        if not text:
            continue

        key = (
            block_no,
            line_no
        )

        grouped.setdefault(
            key,
            []
        ).append(
            {
                "x": x0,
                "text": text
            }
        )

    stations = []

    for key, row in grouped.items():

        row.sort(
            key=lambda item: item["x"]
        )

        tokens = [
            item["text"]
            for item in row
        ]

        # Ищем 6-значный код.
        code_index = None

        for index, token in enumerate(
            tokens
        ):

            if is_station_code(
                token
            ):

                code_index = index
                break

        if code_index is None:
            continue

        code = tokens[
            code_index
        ]

        # ----------------------------------------------------
        # Название станции
        # ----------------------------------------------------

        name_tokens = tokens[
            :code_index
        ]

        name = clean_text(
            " ".join(
                name_tokens
            )
        )

        if not looks_like_russian_name(
            name
        ):
            continue

        # ----------------------------------------------------
        # Всё после кода
        # ----------------------------------------------------

        after_code = tokens[
            code_index + 1:
        ]

        if not after_code:
            continue

        # ----------------------------------------------------
        # Ищем начало латинского названия
        # ----------------------------------------------------

        latin_tokens = []
        tail_tokens = []

        latin_started = False

        for token in after_code:

            # Операции/погранкод начинаются
            # с цифры или одиночной K/К.
            is_numeric = bool(
                re.match(
                    r"^\d",
                    token
                )
            )

            is_operation_k = (
                token.upper()
                in {"K", "К"}
            )

            if (
                latin_started
                and (
                    is_numeric
                    or is_operation_k
                )
            ):

                tail_tokens.append(
                    token
                )

                continue

            if not latin_started:

                if (
                    re.search(
                        r"[A-Za-z]",
                        token
                    )
                    and not is_numeric
                ):

                    latin_started = True

                    latin_tokens.append(
                        token
                    )

                    continue

                # Если после кода сразу
                # цифра — странная строка.
                continue

            latin_tokens.append(
                token
            )

        latin = clean_text(
            " ".join(
                latin_tokens
            )
        )

        if not looks_like_latin_name(
            latin
        ):
            continue

        # ----------------------------------------------------
        # Операции и пограничный код
        # ----------------------------------------------------

        operations, border_code = (
            extract_operations(
                tail_tokens
            )
        )

        stations.append(
            {
                "name": name,
                "name_lat": latin,
                "code": code,
                "country": "Россия",
                "country_code": "RU",
                "railway": (
                    "Российские железные дороги"
                ),
                "operations": operations,
                "border_code": border_code
            }
        )

    return stations


# ============================================================
# РАЗБОР ВСЕГО PDF
# ============================================================

def parse_pdf(pdf_bytes):

    print("")
    print(
        "Разбираем PDF по структуре "
        "таблицы..."
    )

    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    stations = []

    for page_number, page in enumerate(
        document,
        start=1
    ):

        text = page.get_text(
            "text"
        )

        # ----------------------------------------------------
        # После Раздела 4 начинается
        # другая информация.
        # Нам она не нужна.
        # ----------------------------------------------------

        if (
            "Раздел 4." in text
            and page_number > 4
        ):

            print(
                f"Дошли до Раздела 4 "
                f"на странице {page_number}."
            )

            break

        # Станции начинаются с раздела 2.
        if page_number < 4:
            continue

        found = parse_page(
            page
        )

        if found:

            stations.extend(
                found
            )

            print(
                f"Страница {page_number}: "
                f"+{len(found)} станций"
            )

    document.close()

    return stations


# ============================================================
# УДАЛЕНИЕ ДУБЛИКАТОВ
# ============================================================

def remove_duplicates(stations):

    unique = {}

    for station in stations:

        code = station["code"]

        if code not in unique:

            unique[code] = station

        else:

            # Если первая запись была
            # без операций, а вторая
            # содержит их — объединяем.

            old = unique[code]

            if (
                not old["operations"]
                and station["operations"]
            ):

                old["operations"] = (
                    station["operations"]
                )

            if (
                not old["border_code"]
                and station["border_code"]
            ):

                old["border_code"] = (
                    station["border_code"]
                )

    return list(
        unique.values()
    )


# ============================================================
# ПРОВЕРКА ДАННЫХ
# ============================================================

def validate(stations):

    print("")
    print("=" * 60)
    print("ПРОВЕРКА РЕЗУЛЬТАТА")
    print("=" * 60)

    print(
        f"Всего станций: "
        f"{len(stations)}"
    )

    if len(stations) < MIN_STATIONS:

        raise RuntimeError(
            "Найдено слишком мало станций: "
            f"{len(stations)}. "
            "JSON не будет сохранён."
        )

    bad_codes = []

    for station in stations:

        if not is_station_code(
            station["code"]
        ):

            bad_codes.append(
                station["code"]
            )

    if bad_codes:

        raise RuntimeError(
            "Обнаружены неправильные "
            "коды станций."
        )

    names_missing = sum(
        1
        for station in stations
        if not station["name"]
    )

    latin_missing = sum(
        1
        for station in stations
        if not station["name_lat"]
    )

    print(
        f"Без русского названия: "
        f"{names_missing}"
    )

    print(
        f"Без латинского названия: "
        f"{latin_missing}"
    )

    if names_missing > 0:

        raise RuntimeError(
            "Есть станции без русского "
            "названия."
        )

    print(
        "Проверка пройдена."
    )


# ============================================================
# ПЕЧАТЬ ПРИМЕРОВ
# ============================================================

def print_examples(stations):

    print("")
    print("=" * 60)
    print("ПЕРВЫЕ 30 СТАНЦИЙ")
    print("=" * 60)

    for station in stations[:30]:

        print("")
        print(
            f'Название: '
            f'{station["name"]}'
        )

        print(
            f'Латиница: '
            f'{station["name_lat"]}'
        )

        print(
            f'Код: '
            f'{station["code"]}'
        )

        print(
            f'Операции: '
            f'{", ".join(station["operations"])}'
        )

        print(
            f'Погранкод: '
            f'{station["border_code"]}'
        )

    print("")
    print("=" * 60)


# ============================================================
# СОХРАНЕНИЕ JSON
# ============================================================

def save_json(stations):

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Сначала создаём JSON
    # во временный файл.
    #
    # Это дополнительная защита:
    # если запись оборвётся,
    # основной stations.json
    # не будет повреждён.

    temp_file = OUTPUT.with_suffix(
        ".tmp"
    )

    with open(
        temp_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            stations,
            file,
            ensure_ascii=False,
            indent=2
        )

    temp_file.replace(
        OUTPUT
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
    print(
        "ОБНОВЛЕНИЕ СПРАВОЧНИКА "
        "ЖД-СТАНЦИЙ ОСЖД"
    )
    print("=" * 60)

    # --------------------------------------------------------
    # 1. Получаем страницу ОСЖД
    # --------------------------------------------------------

    html = get_osjd_page()

    # --------------------------------------------------------
    # 2. Находим документы
    # --------------------------------------------------------

    documents = find_documents(
        html
    )

    if not documents:

        raise RuntimeError(
            "На странице ОСЖД "
            "не найдено документов."
        )

    # --------------------------------------------------------
    # 3. Российский PDF
    # --------------------------------------------------------

    russian = find_russian_document(
        documents
    )

    # --------------------------------------------------------
    # 4. Скачиваем
    # --------------------------------------------------------

    pdf = download_pdf(
        russian["url"]
    )

    # --------------------------------------------------------
    # 5. Разбираем
    # --------------------------------------------------------

    stations = parse_pdf(
        pdf
    )

    print("")
    print(
        f"Получено записей: "
        f"{len(stations)}"
    )

    # --------------------------------------------------------
    # 6. Убираем дубли
    # --------------------------------------------------------

    stations = remove_duplicates(
        stations
    )

    print(
        f"После удаления дублей: "
        f"{len(stations)}"
    )

    # --------------------------------------------------------
    # 7. Проверяем
    # --------------------------------------------------------

    validate(
        stations
    )

    # --------------------------------------------------------
    # 8. Показываем примеры
    # --------------------------------------------------------

    print_examples(
        stations
    )

    # --------------------------------------------------------
    # 9. Сохраняем
    # --------------------------------------------------------

    save_json(
        stations
    )

    print("")
    print("=" * 60)
    print("ГОТОВО!")
    print("=" * 60)


if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        print("")
        print("=" * 60)
        print("ОШИБКА")
        print("=" * 60)

        print(
            str(error)
        )

        print("=" * 60)

        sys.exit(1)
```
