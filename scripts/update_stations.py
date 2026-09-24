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
# РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ
# ============================================================

STATION_CODE_RE = re.compile(
    r"(?<!\d)(\d{6})(?!\d)"
)

OPERATION_RE = re.compile(
    r"(?<![A-Za-zА-Яа-я0-9])"
    r"(10Н|11Н|12Н|8Н|9Н|10|11|12|1|2|3|4|5|6|7|8|9|К)"
    r"(?![A-Za-zА-Яа-я0-9])",
    re.IGNORECASE
)

FOUR_DIGIT_RE = re.compile(
    r"(?<!\d)(\d{4})(?!\d)"
)


# ============================================================
# СЛУЖЕБНЫЕ ФУНКЦИИ
# ============================================================

def clean_text(text):
    """
    Нормализация текста PDF.
    """
    if not text:
        return ""

    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_station_name(text):
    """
    Нормализует название станции,
    но не меняет само написание.
    """
    text = clean_text(text)

    text = text.strip(" |;")

    return text


def has_letters(text):
    """
    Проверяет, содержит ли строка хотя бы одну букву.
    Работает и для кириллицы, и для латиницы,
    и для других алфавитов.
    """
    return any(char.isalpha() for char in text)


def is_station_code_line(line):
    """
    Проверяет, является ли вся строка шестизначным
    кодом станции.
    """
    line = clean_text(line)

    return bool(
        re.fullmatch(r"\d{6}", line)
    )


def is_service_line(line):
    """
    Отбрасывает заголовки и служебные строки PDF.
    """
    low = clean_text(line).lower()

    if not low:
        return True

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
        "раздел 5",
        "раздел 6",
        "содержание",
        "железнодорожный код страны",
        "код железнодорожного предприятия",
        "сокращенное наименование",
        "дата актуализации",
        "дата вступления",
        "контактные данные",
        "телефон",
        "эл.почта",
        "email",
        "перечень грузовых станций",
        "общие сведения",
        "прием и выдача",
        "станций",
        "наименование поля",
        "содержание поля",
    ]

    for word in bad_words:
        if word in low:
            return True

    return False


def get_pdf_url(href):
    """
    Превращает ссылку ОСЖД/viewer
    в прямую ссылку на PDF.
    """

    href = urljoin(OSJD_PAGE, href)

    parsed = urlparse(href)
    query = parse_qs(parsed.query)

    if "file" in query:
        file_url = unquote(query["file"][0])

        if file_url.startswith("http"):
            return file_url

        return urljoin(
            "https://osjd.org",
            file_url
        )

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
    """
    Скачивает PDF ОСЖД.
    """

    print(f"  Download: {url}")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=180
    )

    response.raise_for_status()

    content_type = response.headers.get(
        "content-type",
        ""
    )

    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(
            "Ссылка не вернула PDF. "
            f"Content-Type: {content_type}"
        )

    return response.content


# ============================================================
# ИЗВЛЕЧЕНИЕ ОПЕРАЦИЙ
# ============================================================

def extract_operations(text):
    """
    Извлекает коды коммерческих операций.

    Пример:
    1,2,3,5,8Н,10
    """

    operations = []

    for match in OPERATION_RE.findall(
        clean_text(text)
    ):
        operation = match.upper()

        if operation not in operations:
            operations.append(operation)

    return operations


# ============================================================
# INLINE-ПАРСЕР
# ============================================================

def parse_inline_station_line(line):
    """
    Разбирает строку, если PDF вдруг отдал
    всю станцию одной строкой:

    АБАКАН 888004 ABAKAN 1,2,3,4,5
    """

    line = clean_text(line)

    if not line:
        return None

    code_match = STATION_CODE_RE.search(line)

    if not code_match:
        return None

    code = code_match.group(1)

    before = clean_text(
        line[:code_match.start()]
    )

    after = clean_text(
        line[code_match.end():]
    )

    if len(before) < 2:
        return None

    if is_service_line(before):
        return None

    if not has_letters(before):
        return None

    # Ищем латинское название.
    # В большинстве PDF оно идёт сразу после кода.
    latin_match = re.search(
        r"[A-Za-zÀ-ÿÄÖÜäöüß]"
        r"[A-Za-zÀ-ÿÄÖÜäöüß0-9().,'’'\/\-\s]*",
        after
    )

    if not latin_match:
        return None

    name_lat = clean_text(
        latin_match.group(0)
    )

    # Убираем случайно попавшие операции.
    operation_match = re.search(
        r"\s+(?="
        r"(?:10Н|11Н|12Н|8Н|9Н|10|11|12|1|2|3|4|5|6|7|8|9|К)"
        r"(?:\s*[,;]\s*|\s*$)"
        r")",
        name_lat,
        re.IGNORECASE
    )

    if operation_match:
        name_lat = name_lat[
            :operation_match.start()
        ].strip()

    if not name_lat:
        return None

    tail = after[latin_match.end():]

    operations = extract_operations(tail)

    border_code = ""

    border_match = FOUR_DIGIT_RE.search(tail)

    if border_match:
        border_code = border_match.group(1)

    return {
        "name": normalize_station_name(before),
        "name_lat": clean_text(name_lat),
        "code": code,
        "operations": operations,
        "border_code": border_code,
    }


# ============================================================
# МНОГОСТРОЧНЫЙ ПАРСЕР
# ============================================================

def parse_multiline_stations(lines):
    """
    Главный новый парсер.

    Реальная структура PDF России:

        АБАГУР-ЛЕСНОЙ
        864300
        ABAGUR-LESNOI
        3

        АБАДЗЕХСКАЯ
        535004
        ABADZEHSKAIA
        1

    То есть одна станция занимает несколько строк.

    Алгоритм:

        название
        ↓
        шестизначный код
        ↓
        латинское название
        ↓
        операции
        ↓
        следующая станция
    """

    stations = []

    # --------------------------------------------------------
    # Нормализуем строки
    # --------------------------------------------------------

    clean_lines = []

    for line in lines:
        line = clean_text(line)

        if line:
            clean_lines.append(line)

    # --------------------------------------------------------
    # Ищем позиции кодов станций
    # --------------------------------------------------------

    code_positions = []

    for index, line in enumerate(clean_lines):

        if is_station_code_line(line):

            code_positions.append(index)

    # --------------------------------------------------------
    # Разбираем каждый код
    # --------------------------------------------------------

    for position_number, code_index in enumerate(
        code_positions
    ):

        code = clean_lines[code_index]

        # ----------------------------------------------------
        # Название станции находится перед кодом.
        # ----------------------------------------------------

        name_index = code_index - 1

        while (
            name_index >= 0
            and not clean_lines[name_index]
        ):
            name_index -= 1

        if name_index < 0:
            continue

        name = clean_lines[name_index]

        # ----------------------------------------------------
        # Проверяем название.
        # ----------------------------------------------------

        if is_service_line(name):
            continue

        if not has_letters(name):
            continue

        if len(name) < 2:
            continue

        # ----------------------------------------------------
        # Следующая строка после кода =
        # латинское название станции.
        # ----------------------------------------------------

        latin_index = code_index + 1

        if latin_index >= len(clean_lines):
            continue

        name_lat = clean_lines[latin_index]

        # Если сразу после кода снова код,
        # это не станция.
        if is_station_code_line(name_lat):
            continue

        if is_service_line(name_lat):
            continue

        if not has_letters(name_lat):
            continue

        # ----------------------------------------------------
        # Защита от ситуации, когда после кода
        # идёт не латинское название, а мусор.
        # ----------------------------------------------------

        if len(name_lat) < 2:
            continue

        # ----------------------------------------------------
        # Определяем границу текущей станции.
        # ----------------------------------------------------

        next_code_index = len(clean_lines)

        if position_number + 1 < len(code_positions):
            next_code_index = code_positions[
                position_number + 1
            ]

        tail_lines = clean_lines[
            latin_index + 1:next_code_index
        ]

        tail_text = " ".join(tail_lines)

        # ----------------------------------------------------
        # Операции
        # ----------------------------------------------------

        operations = extract_operations(
            tail_text
        )

        # ----------------------------------------------------
        # Код пограничного перехода.
        #
        # В некоторых документах это отдельное
        # четырёхзначное значение.
        # ----------------------------------------------------

        border_code = ""

        for tail_line in tail_lines:

            # Если строка содержит ровно 4 цифры,
            # рассматриваем её как возможный код перехода.
            if re.fullmatch(
                r"\d{4}",
                tail_line
            ):
                border_code = tail_line
                break

        # Если отдельной строки нет,
        # ищем четырёхзначный код в хвосте.
        if not border_code:

            border_match = FOUR_DIGIT_RE.search(
                tail_text
            )

            if border_match:
                border_code = (
                    border_match.group(1)
                )

        # ----------------------------------------------------
        # Создаём запись
        # ----------------------------------------------------

        station = {
            "name": normalize_station_name(name),
            "name_lat": clean_text(name_lat),
            "code": code,
            "operations": operations,
            "border_code": border_code,
        }

        # ----------------------------------------------------
        # Финальная защита
        # ----------------------------------------------------

        if not station["name"]:
            continue

        if not station["name_lat"]:
            continue

        if not re.fullmatch(
            r"\d{6}",
            station["code"]
        ):
            continue

        stations.append(station)

    return stations


# ============================================================
# ОПРЕДЕЛЕНИЕ НАЧАЛА ТАБЛИЦЫ
# ============================================================

def find_station_table_start(document):
    """
    Ищем страницу, где начинается таблица станций.

    Не полагаемся только на оглавление,
    потому что в нём тоже встречаются слова
    "Пограничные переходы".
    """

    header_patterns = [
        (
            "Наименование станции на русском языке",
            "Наименование станции на латыни"
        ),
        (
            "Наименование станции",
            "Код станции"
        ),
    ]

    # Сначала ищем настоящий заголовок таблицы.
    for page_index in range(len(document)):

        text = document[
            page_index
        ].get_text("text")

        text_clean = clean_text(text)

        for pattern1, pattern2 in header_patterns:

            if (
                pattern1 in text_clean
                and pattern2 in text_clean
            ):
                return page_index

    # --------------------------------------------------------
    # Запасной вариант:
    # ищем первую страницу, где есть
    # последовательность:
    #
    # название
    # 6 цифр
    # название
    # --------------------------------------------------------

    for page_index in range(len(document)):

        lines = document[
            page_index
        ].get_text("text").splitlines()

        lines = [
            clean_text(line)
            for line in lines
            if clean_text(line)
        ]

        for index, line in enumerate(lines):

            if not is_station_code_line(line):
                continue

            if index == 0:
                continue

            if index + 1 >= len(lines):
                continue

            before = lines[index - 1]
            after = lines[index + 1]

            if (
                has_letters(before)
                and has_letters(after)
                and not is_service_line(before)
                and not is_service_line(after)
            ):
                return page_index

    return 0


# ============================================================
# ОПРЕДЕЛЕНИЕ КОНЦА ТАБЛИЦЫ
# ============================================================

def find_station_table_end(
    document,
    start_page
):
    """
    Определяем конец таблицы.

    ВАЖНО:
    Не останавливаемся на первом упоминании
    "Пограничные переходы", потому что оно может
    находиться в оглавлении.

    Ищем раздел после того, как уже нашли станции.
    """

    found_stations_page = False

    for page_index in range(
        start_page,
        len(document)
    ):

        text = document[
            page_index
        ].get_text("text")

        text_clean = clean_text(text)

        # Проверяем, есть ли на странице
        # хотя бы одна потенциальная станция.
        lines = [
            clean_text(line)
            for line in text.splitlines()
            if clean_text(line)
        ]

        page_has_station = False

        for index, line in enumerate(lines):

            if not is_station_code_line(line):
                continue

            if index == 0:
                continue

            if index + 1 >= len(lines):
                continue

            before = lines[index - 1]
            after = lines[index + 1]

            if (
                has_letters(before)
                and has_letters(after)
                and not is_service_line(before)
                and not is_service_line(after)
            ):
                page_has_station = True
                break

        if page_has_station:
            found_stations_page = True
            continue

        # После того как реальные станции уже встретились,
        # можно считать следующий раздел концом таблицы.
        if found_stations_page:

            section4 = (
                "Раздел 4" in text_clean
                or "Пограничные переходы" in text_clean
            )

            if section4:
                return page_index

    return len(document)


# ============================================================
# РАЗБОР ОДНОГО PDF
# ============================================================

def parse_pdf(
    pdf_bytes,
    country,
    country_code,
    railway
):
    stations = []

    document = pymupdf.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    print(
        f"  PDF pages: {len(document)}"
    )

    # --------------------------------------------------------
    # Начало таблицы
    # --------------------------------------------------------

    start_page = find_station_table_start(
        document
    )

    print(
        f"  Station table starts at page: "
        f"{start_page + 1}"
    )

    # --------------------------------------------------------
    # Конец таблицы
    # --------------------------------------------------------

    end_page = find_station_table_end(
        document,
        start_page
    )

    print(
        f"  Station table ends before page: "
        f"{end_page + 1}"
    )

    # --------------------------------------------------------
    # Собираем строки всех страниц таблицы.
    # --------------------------------------------------------

    all_lines = []

    for page_index in range(
        start_page,
        end_page
    ):

        page = document[
            page_index
        ]

        text = page.get_text("text")

        lines = text.splitlines()

        all_lines.extend(lines)

    # --------------------------------------------------------
    # Основной многострочный парсер.
    # --------------------------------------------------------

    parsed_stations = parse_multiline_stations(
        all_lines
    )

    # --------------------------------------------------------
    # Если многострочный парсер ничего не нашёл,
    # пробуем старый inline-формат.
    # --------------------------------------------------------

    if not parsed_stations:

        print(
            "  Многострочный формат не найден. "
            "Пробуем inline-формат..."
        )

        for line in all_lines:

            parsed = parse_inline_station_line(
                line
            )

            if parsed:
                parsed_stations.append(
                    parsed
                )

    # --------------------------------------------------------
    # Добавляем информацию о стране.
    # --------------------------------------------------------

    for station in parsed_stations:

        station["country"] = country
        station["country_code"] = country_code
        station["railway"] = railway

    # --------------------------------------------------------
    # Убираем дубли внутри одного PDF.
    # --------------------------------------------------------

    parsed_stations = deduplicate(
        parsed_stations
    )

    # --------------------------------------------------------
    # Показываем первые найденные станции.
    # --------------------------------------------------------

    if parsed_stations:

        print(
            "  Первые найденные станции:"
        )

        for station in parsed_stations[:5]:

            print(
                "    "
                f"{station['name']} | "
                f"{station['code']} | "
                f"{station['name_lat']}"
            )

    return parsed_stations


# ============================================================
# УДАЛЕНИЕ ДУБЛИКАТОВ
# ============================================================

def deduplicate(stations):
    """
    Удаляет дубли по:

        страна
        код станции
        название
    """

    result = {}

    for station in stations:

        key = (
            station.get(
                "country_code",
                ""
            ),
            station.get(
                "code",
                ""
            ),
            clean_text(
                station.get(
                    "name",
                    ""
                )
            ).upper()
        )

        if key not in result:

            result[key] = station

    return list(
        result.values()
    )


# ============================================================
# ПРОВЕРКА ДАННЫХ
# ============================================================

def validate_station(station):
    """
    Проверяет одну запись станции.
    """

    required_fields = [
        "name",
        "name_lat",
        "code",
        "country",
        "country_code",
        "railway",
        "operations",
        "border_code",
    ]

    for field in required_fields:

        if field not in station:
            return False

    if not station["name"]:
        return False

    if not station["name_lat"]:
        return False

    if not re.fullmatch(
        r"\d{6}",
        str(station["code"])
    ):
        return False

    return True


def validate_database(stations):
    """
    Проверяет всю базу.
    """

    valid = []

    invalid = []

    for station in stations:

        if validate_station(station):

            valid.append(station)

        else:

            invalid.append(station)

    return valid, invalid


# ============================================================
# СТАТИСТИКА
# ============================================================

def print_country_statistics(
    stations
):
    """
    Показывает количество станций
    по каждой стране.
    """

    statistics = {}

    for station in stations:

        country = station.get(
            "country",
            "Неизвестно"
        )

        statistics[country] = (
            statistics.get(
                country,
                0
            )
            + 1
        )

    print()

    print(
        "СТАТИСТИКА ПО СТРАНАМ"
    )

    print(
        "----------------------------------------"
    )

    for country in sorted(
        statistics
    ):

        print(
            f"  {country}: "
            f"{statistics[country]}"
        )


# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        " OSJD RAILWAY STATION DATABASE"
    )

    print(
        "========================================"
    )

    print()

    print(
        "Получаем страницу ОСЖД..."
    )

    # --------------------------------------------------------
    # Загружаем страницу ОСЖД.
    # --------------------------------------------------------

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
    # Ищем PDF.
    # --------------------------------------------------------

    pdf_links = []

    seen_urls = set()

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

        if (
            "Перечень грузовых станций"
            not in text
        ):
            continue

        country, country_code = identify_country(
            text
        )

        if not country:

            print(
                "  Не удалось определить страну: "
                f"{text}"
            )

            continue

        pdf_url = get_pdf_url(
            href
        )

        if pdf_url in seen_urls:
            continue

        seen_urls.add(
            pdf_url
        )

        pdf_links.append(
            {
                "country": country,
                "country_code": country_code,
                "title": text,
                "url": pdf_url,
            }
        )

    print()

    print(
        f"Найдено перечней ОСЖД: "
        f"{len(pdf_links)}"
    )

    if len(pdf_links) < 20:

        raise RuntimeError(
            "ОСЖД вернула слишком мало "
            "перечней. "
            f"Найдено: {len(pdf_links)}"
        )

    # --------------------------------------------------------
    # Разбираем документы.
    # --------------------------------------------------------

    all_stations = []

    successful_countries = []

    failed_countries = []

    for item in pdf_links:

        print()

        print(
            "----------------------------------------"
        )

        print(
            item["country"]
        )

        print(
            "----------------------------------------"
        )

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

        time.sleep(0.5)

    # --------------------------------------------------------
    # Удаляем дубли.
    # --------------------------------------------------------

    print()

    print(
        "----------------------------------------"
    )

    print(
        "Удаляем дубликаты..."
    )

    print(
        "----------------------------------------"
    )

    before_count = len(
        all_stations
    )

    all_stations = deduplicate(
        all_stations
    )

    after_count = len(
        all_stations
    )

    print(
        f"До удаления дублей: "
        f"{before_count}"
    )

    print(
        f"После удаления дублей: "
        f"{after_count}"
    )

    # --------------------------------------------------------
    # Проверяем записи.
    # --------------------------------------------------------

    valid_stations, invalid_stations = (
        validate_database(
            all_stations
        )
    )

    print()

    print(
        "ПРОВЕРКА ЗАПИСЕЙ"
    )

    print(
        "----------------------------------------"
    )

    print(
        f"Корректных записей: "
        f"{len(valid_stations)}"
    )

    print(
        f"Некорректных записей: "
        f"{len(invalid_stations)}"
    )

    # --------------------------------------------------------
    # КРИТИЧЕСКАЯ ПРОВЕРКА
    #
    # Если получилось меньше 1000 станций,
    # старый JSON НЕ трогаем.
    # --------------------------------------------------------

    if len(valid_stations) < 1000:

        print()

        print(
            "========================================"
        )

        print(
            "ОШИБКА"
        )

        print(
            "========================================"
        )

        print(
            f"Получено станций: "
            f"{len(valid_stations)}"
        )

        print()

        print(
            "Файл stations.json "
            "НЕ будет изменён."
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

        print_country_statistics(
            valid_stations
        )

        raise RuntimeError(
            "Слишком мало станций: "
            f"{len(valid_stations)}"
        )

    # --------------------------------------------------------
    # Сортировка.
    # --------------------------------------------------------

    valid_stations.sort(
        key=lambda item: (
            item.get(
                "country",
                ""
            ),
            item.get(
                "name",
                ""
            ).upper(),
            item.get(
                "code",
                ""
            )
        )
    )

    # --------------------------------------------------------
    # Создаём директорию.
    # --------------------------------------------------------

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Сохраняем JSON.
    # --------------------------------------------------------

    with OUTPUT.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            valid_stations,
            file,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # Статистика.
    # --------------------------------------------------------

    print_country_statistics(
        valid_stations
    )

    # --------------------------------------------------------
    # Финальный результат.
    # --------------------------------------------------------

    print()

    print(
        "========================================"
    )

    print(
        "ГОТОВО"
    )

    print(
        "========================================"
    )

    print(
        f"Всего станций: "
        f"{len(valid_stations)}"
    )

    print(
        f"Файл: {OUTPUT}"
    )

    print()

    print(
        "Успешные страны:"
    )

    for country in successful_countries:

        print(
            f"  ✓ {country}"
        )

    if failed_countries:

        print()

        print(
            "Без найденных станций:"
        )

        for country in failed_countries:

            print(
                f"  ! {country}"
            )

    # --------------------------------------------------------
    # Первые 20 записей.
    # --------------------------------------------------------

    print()

    print(
        "----------------------------------------"
    )

    print(
        "ПЕРВЫЕ 20 ЗАПИСЕЙ"
    )

    print(
        "----------------------------------------"
    )

    for number, station in enumerate(
        valid_stations[:20],
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
