import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import pymupdf
import requests
from bs4 import BeautifulSoup


# ============================================================
# НАСТРОЙКИ
# ============================================================

OSJD_PAGE = "https://osjd.org/ru/8974/page/106077?id=2227"

OUTPUT = Path("data/stations.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
    )
}


# ============================================================
# СТРАНЫ ОСЖД
# ============================================================

COUNTRIES = {
    "Азербайджан": "AZ",
    "Афганистан": "AF",
    "Беларусь": "BY",
    "Болгария": "BG",
    "Венгрия": "HU",
    "Вьетнам": "VN",
    "Грузия": "GE",
    "Иран": "IR",
    "Казахстан": "KZ",
    "Китай": "CN",
    "КНДР": "KP",
    "Кыргызстан": "KG",
    "Республика Корея": "KR",
    "Лаос": "LA",
    "Латвия": "LV",
    "Литва": "LT",
    "Молдова": "MD",
    "Монголия": "MN",
    "Польша": "PL",
    "Россия": "RU",
    "Румыния": "RO",
    "Словакия": "SK",
    "Таджикистан": "TJ",
    "Туркменистан": "TM",
    "Узбекистан": "UZ",
    "Украина": "UA",
    "Чехия": "CZ",
    "Эстония": "EE",
}


# ============================================================
# СЛУЖЕБНЫЕ ФУНКЦИИ
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def get_pdf_url(href):
    """
    Превращает ссылку ОСЖД/viewer в прямую ссылку на PDF.
    """

    href = urljoin(OSJD_PAGE, href)

    parsed = urlparse(href)
    query = parse_qs(parsed.query)

    if "file" in query:
        file_url = unquote(query["file"][0])

        if file_url.startswith("http"):
            return file_url

        return urljoin("https://osjd.org", file_url)

    return href


def identify_country(text):
    """
    Определяем страну по названию документа.
    """

    text = clean_text(text).lower()

    patterns = [
        ("Азербайджан", ["азербайджан"]),
        ("Афганистан", ["афганистан"]),
        ("Беларусь", ["белорус"]),
        ("Болгария", ["болгар"]),
        ("Венгрия", ["венгер"]),
        ("Вьетнам", ["вьетнам"]),
        ("Грузия", ["грузин"]),
        ("Иран", ["иран"]),
        ("Казахстан", ["казахстан"]),
        ("Китай", ["китай"]),
        ("КНДР", ["кндр", "корейской народной"]),
        ("Кыргызстан", ["кыргыз"]),
        ("Республика Корея", ["республики корея"]),
        ("Лаос", ["лаос"]),
        ("Латвия", ["латв"]),
        ("Литва", ["литов"]),
        ("Молдова", ["молдов"]),
        ("Монголия", ["улан-батор", "монгол"]),
        ("Польша", ["польск"]),
        ("Россия", ["российск", "ржд"]),
        ("Румыния", ["румын"]),
        ("Словакия", ["словац"]),
        ("Таджикистан", ["таджик"]),
        ("Туркменистан", ["туркмен"]),
        ("Узбекистан", ["узбек"]),
        ("Украина", ["украин"]),
        ("Чехия", ["чеш"]),
        ("Эстония", ["эстон"]),
    ]

    for country, words in patterns:
        for word in words:
            if word in text:
                return country, COUNTRIES[country]

    return None, None


def download_pdf(url):
    print(f"  Download: {url}")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=180
    )

    response.raise_for_status()

    content_type = response.headers.get("content-type", "")

    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(
            f"Ссылка не вернула PDF. "
            f"Content-Type: {content_type}"
        )

    return response.content


# ============================================================
# ОПРЕДЕЛЕНИЕ СТРОКИ СТАНЦИИ
# ============================================================

def parse_station_line(line):
    """
    Разбирает строку примерно такого вида:

    АБАКАН 888004 ABAKAN 1,2,3,4,5,8,8Н,9,10

    или:

    АБАГУР-ЛЕСНОЙ 864300 ABAGUR-LESNOI 3
    """

    line = clean_text(line)

    if not line:
        return None

    # --------------------------------------------------------
    # Ищем шестизначный код станции
    # --------------------------------------------------------

    code_match = re.search(
        r"(?<!\d)(\d{6})(?!\d)",
        line
    )

    if not code_match:
        return None

    code = code_match.group(1)

    before = clean_text(
        line[:code_match.start()]
    )

    after = clean_text(
        line[code_match.end():]
    )

    # Название станции не может быть слишком коротким
    if len(before) < 2:
        return None

    # --------------------------------------------------------
    # Исключаем служебные строки
    # --------------------------------------------------------

    low = line.lower()

    bad_words = [
        "код станции",
        "наименование станции",
        "пограничного перехода",
        "коммерческие операции",
        "производимые операции",
        "таблица расстояний",
        "раздел 1",
        "раздел 2",
        "раздел 3",
        "раздел 4",
        "содержание",
        "железнодорожный код страны",
        "код железнодорожного предприятия",
    ]

    if any(word in low for word in bad_words):
        return None

    # --------------------------------------------------------
    # После кода должно идти латинское название
    # --------------------------------------------------------

    latin_match = re.search(
        r"[A-Za-z][A-Za-z0-9À-ÿÄÖÜäöüßА-Яа-я0-9().,'’'\/\-\s]*",
        after
    )

    if not latin_match:
        return None

    name_lat = clean_text(
        latin_match.group(0)
    )

    # Если в латинское название случайно попали цифры операций,
    # отделяем их.
    operation_match = re.search(
        r"\s+(?=\d+(?:[Нн])?(?:\s*,|\s*$))",
        name_lat
    )

    if operation_match:
        name_lat = name_lat[
            :operation_match.start()
        ].strip()

    if not name_lat:
        return None

    # --------------------------------------------------------
    # Операции
    # --------------------------------------------------------

    tail = after[latin_match.end():]

    operations = []

    operation_pattern = re.compile(
        r"(?<![A-Za-zА-Яа-я0-9])"
        r"(10Н|11Н|12Н|8Н|9Н|10|11|12|1|2|3|4|5|6|7|8|9|К)"
        r"(?![A-Za-zА-Яа-я0-9])",
        re.IGNORECASE
    )

    for match in operation_pattern.findall(tail):
        operation = match.upper()

        if operation not in operations:
            operations.append(operation)

    # --------------------------------------------------------
    # Иногда операции идут прямо после латинского названия
    # --------------------------------------------------------

    attached_operations = re.findall(
        r"(10Н|11Н|12Н|8Н|9Н|10|11|12|1|2|3|4|5|6|7|8|9|К)",
        tail.upper()
    )

    for operation in attached_operations:
        if operation not in operations:
            operations.append(operation)

    # --------------------------------------------------------
    # Код пограничного перехода
    # --------------------------------------------------------

    border_code = ""

    border_match = re.search(
        r"(?<!\d)(\d{4})(?!\d)",
        tail
    )

    if border_match:
        border_code = border_match.group(1)

    # --------------------------------------------------------
    # Результат
    # --------------------------------------------------------

    return {
        "name": before,
        "name_lat": name_lat,
        "code": code,
        "operations": operations,
        "border_code": border_code,
    }


# ============================================================
# РАЗБОР PDF
# ============================================================

def parse_pdf(pdf_bytes, country, country_code, railway):
    stations = []

    document = pymupdf.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    print(
        f"  PDF pages: {len(document)}"
    )

    # --------------------------------------------------------
    # Сначала определяем страницу, где реально начинается
    # таблица станций.
    #
    # Ищем строку:
    # "Наименование станции на русском языке"
    # --------------------------------------------------------

    start_page = None
    end_page = len(document)

    for page_index in range(len(document)):

        page = document[page_index]

        text = page.get_text("text")

        if (
            "Наименование станции на русском языке"
            in text
            and "Код" in text
            and "Наименование станции на латыни"
            in text
        ):
            start_page = page_index
            break

    # --------------------------------------------------------
    # Если специальный заголовок не найден,
    # начинаем поиск с 1-й страницы.
    # --------------------------------------------------------

    if start_page is None:
        start_page = 0

    print(
        f"  Station table starts at page: "
        f"{start_page + 1}"
    )

    # --------------------------------------------------------
    # Ищем конец раздела.
    # --------------------------------------------------------

    for page_index in range(start_page, len(document)):

        page = document[page_index]

        text = page.get_text("text")

        if (
            "Раздел 4." in text
            or "Пограничные переходы" in text
        ):
            end_page = page_index
            break

    print(
        f"  Station table ends before page: "
        f"{end_page + 1}"
    )

    # --------------------------------------------------------
    # Обрабатываем страницы таблицы
    # --------------------------------------------------------

    for page_index in range(
        start_page,
        end_page
    ):

        page = document[page_index]

        text = page.get_text("text")

        lines = text.splitlines()

        for line in lines:

            parsed = parse_station_line(line)

            if not parsed:
                continue

            parsed["country"] = country
            parsed["country_code"] = country_code
            parsed["railway"] = railway

            stations.append(parsed)

    return stations


# ============================================================
# УДАЛЕНИЕ ДУБЛИКАТОВ
# ============================================================

def deduplicate(stations):

    result = {}

    for station in stations:

        key = (
            station.get("country_code", ""),
            station.get("code", ""),
            station.get("name", "").upper()
        )

        if key not in result:
            result[key] = station

    return list(result.values())


# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================================

def main():

    print("========================================")
    print(" OSJD RAILWAY STATION DATABASE")
    print("========================================")

    print()
    print("Получаем страницу ОСЖД...")

    response = requests.get(
        OSJD_PAGE,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # --------------------------------------------------------
    # Ищем PDF
    # --------------------------------------------------------

    pdf_links = []

    for link in soup.find_all("a"):

        text = clean_text(
            link.get_text(" ", strip=True)
        )

        href = link.get("href")

        if not href:
            continue

        if "Перечень грузовых станций" not in text:
            continue

        country, country_code = identify_country(text)

        if not country:
            print(
                f"  Не удалось определить страну: {text}"
            )
            continue

        pdf_url = get_pdf_url(href)

        pdf_links.append({
            "country": country,
            "country_code": country_code,
            "title": text,
            "url": pdf_url,
        })

    print()
    print(
        f"Найдено перечней ОСЖД: "
        f"{len(pdf_links)}"
    )

    if len(pdf_links) < 20:

        raise RuntimeError(
            "ОСЖД вернула слишком мало перечней. "
            f"Найдено: {len(pdf_links)}"
        )

    # --------------------------------------------------------
    # Разбираем документы
    # --------------------------------------------------------

    all_stations = []

    successful_countries = []
    failed_countries = []

    for item in pdf_links:

        print()
        print("----------------------------------------")
        print(item["country"])
        print("----------------------------------------")

        try:

            pdf = download_pdf(
                item["url"]
            )

            stations = parse_pdf(
                pdf_bytes=pdf,
                country=item["country"],
                country_code=item["country_code"],
                railway=item["title"]
            )

            print(
                f"  Найдено станций: "
                f"{len(stations)}"
            )

            if stations:

                successful_countries.append(
                    item["country"]
                )

                all_stations.extend(
                    stations
                )

            else:

                failed_countries.append(
                    item["country"]
                )

        except Exception as error:

            print(
                f"  ERROR: {error}"
            )

            failed_countries.append(
                item["country"]
            )

        # Небольшая пауза
        time.sleep(0.5)

    # --------------------------------------------------------
    # Удаляем дубли
    # --------------------------------------------------------

    print()
    print("----------------------------------------")
    print("Удаляем дубликаты...")
    print("----------------------------------------")

    before_count = len(all_stations)

    all_stations = deduplicate(
        all_stations
    )

    after_count = len(all_stations)

    print(
        f"До удаления дублей: {before_count}"
    )

    print(
        f"После удаления дублей: {after_count}"
    )

    # --------------------------------------------------------
    # Проверка
    # --------------------------------------------------------

    if len(all_stations) < 1000:

        print()
        print("========================================")
        print("ОШИБКА")
        print("========================================")

        print(
            f"Получено станций: "
            f"{len(all_stations)}"
        )

        print(
            "Файл stations.json НЕ будет изменён."
        )

        print()
        print(
            "Успешные страны:"
        )

        for country in successful_countries:
            print(
                f"  ✓ {country}"
            )

        print()
        print(
            "Страны без найденных станций:"
        )

        for country in failed_countries:
            print(
                f"  ✗ {country}"
            )

        raise RuntimeError(
            f"Слишком мало станций: "
            f"{len(all_stations)}"
        )

    # --------------------------------------------------------
    # Сортировка
    # --------------------------------------------------------

    all_stations.sort(
        key=lambda item: (
            item.get("country", ""),
            item.get("name", "").upper(),
            item.get("code", "")
        )
    )

    # --------------------------------------------------------
    # Сохраняем JSON
    # --------------------------------------------------------

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with OUTPUT.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            all_stations,
            file,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # Итог
    # --------------------------------------------------------

    print()
    print("========================================")
    print("ГОТОВО")
    print("========================================")

    print(
        f"Всего станций: "
        f"{len(all_stations)}"
    )

    print(
        f"Файл: {OUTPUT}"
    )

    print()
    print("Успешные страны:")

    for country in successful_countries:
        print(
            f"  ✓ {country}"
        )

    if failed_countries:

        print()
        print("Без найденных станций:")

        for country in failed_countries:
            print(
                f"  ! {country}"
            )

    # --------------------------------------------------------
    # Первые 10 записей
    # --------------------------------------------------------

    print()
    print("----------------------------------------")
    print("ПЕРВЫЕ 10 ЗАПИСЕЙ")
    print("----------------------------------------")

    for number, station in enumerate(
        all_stations[:10],
        start=1
    ):

        print(
            f"{number}. "
            f"{station['name']} | "
            f"{station['code']} | "
            f"{station['name_lat']} | "
            f"{station['country']}"
        )


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    main()
