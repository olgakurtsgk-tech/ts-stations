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

REQUEST_TIMEOUT = 180


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
# АЛИАСЫ ДЛЯ ОПРЕДЕЛЕНИЯ СТРАН
# ============================================================

COUNTRY_PATTERNS = [
    ("Азербайджан", ["азербайджан"]),
    ("Афганистан", ["афганистан"]),
    ("Беларусь", ["белорус", "беларус"]),
    ("Болгария", ["болгар"]),
    ("Венгрия", ["венгер"]),
    ("Вьетнам", ["вьетнам"]),
    ("Грузия", ["грузин"]),
    ("Иран", ["иран"]),
    ("Казахстан", ["казахстан"]),
    ("Китай", ["китай"]),
    ("КНДР", [
        "кндр",
        "корейской народной",
        "демократической республики корея",
    ]),
    ("Кыргызстан", ["кыргыз"]),
    ("Республика Корея", [
        "республики корея",
        "южной корея",
        "south korea",
        "republic of korea",
    ]),
    ("Лаос", ["лаос"]),
    ("Латвия", ["латв"]),
    ("Литва", ["литов"]),
    ("Молдова", ["молдов"]),
    ("Монголия", ["улан-батор", "монгол"]),
    ("Польша", ["польск"]),
    ("Россия", ["российск", "ржд"]),
    ("Румыния", ["румын", "cfr marfa"]),
    ("Словакия", ["словац"]),
    ("Таджикистан", ["таджик"]),
    ("Туркменистан", ["туркмен"]),
    ("Узбекистан", ["узбек"]),
    ("Украина", ["украин"]),
    ("Чехия", ["чеш", "чех"]),
    ("Эстония", ["эстон"]),
]


# ============================================================
# REGEX
# ============================================================

STATION_CODE_RE = re.compile(
    r"(?<!\d)(\d{6})(?!\d)"
)

FOUR_DIGIT_RE = re.compile(
    r"(?<!\d)(\d{4})(?!\d)"
)

OPERATION_RE = re.compile(
    r"(?<![A-Za-zА-Яа-я0-9])"
    r"(10Н|11Н|12Н|8Н|9Н|10|11|12|1|2|3|4|5|6|7|8|9|К)"
    r"(?![A-Za-zА-Яа-я0-9])",
    re.IGNORECASE
)


# ============================================================
# ТЕКСТОВЫЕ ФУНКЦИИ
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = str(text)

    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")
    text = text.replace("\r", "\n")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)

    return text.strip()


def clean_line(text):
    text = clean_text(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" |;\t")


def has_letters(text):
    return any(char.isalpha() for char in text)


def is_station_code_line(line):
    line = clean_line(line)
    return bool(re.fullmatch(r"\d{6}", line))


def normalize_station_name(text):
    return clean_line(text)


# ============================================================
# СЛУЖЕБНЫЕ СТРОКИ
# ============================================================

def is_service_line(line):

    low = clean_line(line).lower()

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
        "наименование поля",
        "содержание поля",
        "страница",
        "page",
    ]

    for word in bad_words:
        if word in low:
            return True

    return False


# ============================================================
# ОПРЕДЕЛЕНИЕ СТРАНЫ
# ============================================================

def identify_country(text):

    text = clean_text(text).lower()

    for country, words in COUNTRY_PATTERNS:

        for word in words:

            if word in text:
                return country, COUNTRIES[country]

    return None, None


# ============================================================
# ПОЛУЧЕНИЕ PDF-ССЫЛОК С ОСЖД
# ============================================================

def get_pdf_url(href):

    href = urljoin(OSJD_PAGE, href)

    parsed = urlparse(href)

    query = parse_qs(
        parsed.query,
        keep_blank_values=True
    )

    if "file" in query:

        file_url = unquote(
            query["file"][0]
        )

        if file_url.startswith("http"):
            return file_url

        return urljoin(
            "https://osjd.org",
            file_url
        )

    return href


def discover_osjd_documents():

    print()
    print("=" * 70)
    print("ОПРЕДЕЛЯЕМ ДОКУМЕНТЫ ОСЖД")
    print("=" * 70)

    print()
    print("Источник:")
    print(OSJD_PAGE)

    response = requests.get(
        OSJD_PAGE,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    documents = []

    for link in soup.find_all("a", href=True):

        href = link.get("href", "").strip()

        if not href:
            continue

        text = clean_line(
            link.get_text(" ", strip=True)
        )

        href_lower = href.lower()
        text_lower = text.lower()

        # Ищем документы по признакам.
        is_document = (
            ".pdf" in href_lower
            or "api/media/resources" in href_lower
            or "перечень грузовых станций" in text_lower
        )

        if not is_document:
            continue

        # Памятку О 405 не берём.
        if "памятк" in text_lower:
            continue

        pdf_url = get_pdf_url(href)

        country, country_code = identify_country(
            text
        )

        documents.append({
            "country": country,
            "country_code": country_code,
            "text": text,
            "url": pdf_url,
        })

    # --------------------------------------------------------
    # Удаляем дубликаты
    # --------------------------------------------------------

    unique = {}

    for item in documents:

        key = item["url"]

        if key not in unique:
            unique[key] = item

    documents = list(
        unique.values()
    )

    # --------------------------------------------------------
    # Сортировка по стране
    # --------------------------------------------------------

    documents.sort(
        key=lambda x: (
            x["country_code"] or "ZZ",
            x["text"]
        )
    )

    print()
    print(
        f"Найдено документов: {len(documents)}"
    )

    print()

    for index, item in enumerate(
        documents,
        start=1
    ):

        print(
            f"[{index:02d}] "
            f"{item['country_code'] or '??'} "
            f"{item['country'] or 'НЕ ОПРЕДЕЛЕНА'}"
        )

        print(
            f"     {item['text']}"
        )

        print(
            f"     {item['url']}"
        )

    return documents


# ============================================================
# СКАЧИВАНИЕ PDF
# ============================================================

def download_pdf(url):

    print()
    print(
        f"  Download: {url}"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    content_type = response.headers.get(
        "content-type",
        ""
    )

    content = response.content

    # Иногда сервер ОСЖД может вернуть PDF
    # с неправильным Content-Type.
    if not content.startswith(b"%PDF"):

        raise RuntimeError(
            "Ссылка не вернула PDF. "
            f"Content-Type: {content_type}"
        )

    return content


# ============================================================
# ИЗВЛЕЧЕНИЕ ОПЕРАЦИЙ
# ============================================================

def extract_operations(text):

    operations = []

    for match in OPERATION_RE.findall(
        clean_text(text)
    ):

        operation = match.upper()

        if operation not in operations:
            operations.append(operation)

    return operations


# ============================================================
# ИЗВЛЕЧЕНИЕ КОДА ПОГРАНИЧНОГО ПЕРЕХОДА
# ============================================================

def extract_border_code(text):

    text = clean_text(text)

    matches = FOUR_DIGIT_RE.findall(
        text
    )

    if not matches:
        return ""

    # Берём последний найденный 4-значный код.
    # Это безопаснее для таблиц, где в начале
    # могут встречаться годы/номера разделов.
    return matches[-1]


# ============================================================
# ПРОВЕРКА LATIN
# ============================================================

def looks_like_latin_name(text):

    text = clean_line(text)

    if not text:
        return False

    if not has_letters(text):
        return False

    # Хотя бы одна латинская буква.
    return bool(
        re.search(
            r"[A-Za-zÀ-ÿÄÖÜäöüß]",
            text
        )
    )


# ============================================================
# ВАРИАНТ №1
# МНОГОСТРОЧНЫЙ ПАРСЕР
# ============================================================

def parse_multiline_stations(lines):

    stations = []

    clean_lines = []

    for line in lines:

        line = clean_line(line)

        if line:
            clean_lines.append(line)

    code_positions = []

    for index, line in enumerate(
        clean_lines
    ):

        if is_station_code_line(line):

            code_positions.append(index)

    for position_number, code_index in enumerate(
        code_positions
    ):

        code = clean_lines[code_index]

        # ----------------------------------------------------
        # Название непосредственно перед кодом.
        # ----------------------------------------------------

        name_index = code_index - 1

        if name_index < 0:
            continue

        name = clean_lines[name_index]

        if is_service_line(name):
            continue

        if not has_letters(name):
            continue

        if len(name) < 2:
            continue

        # ----------------------------------------------------
        # Следующая строка = латинское название.
        # ----------------------------------------------------

        latin_index = code_index + 1

        if latin_index >= len(
            clean_lines
        ):
            continue

        name_lat = clean_lines[
            latin_index
        ]

        if is_station_code_line(name_lat):
            continue

        if is_service_line(name_lat):
            continue

        if not looks_like_latin_name(
            name_lat
        ):
            continue

        # ----------------------------------------------------
        # Хвост станции до следующего кода.
        # ----------------------------------------------------

        next_code_index = len(
            clean_lines
        )

        if (
            position_number + 1
            < len(code_positions)
        ):

            next_code_index = code_positions[
                position_number + 1
            ]

        tail_lines = clean_lines[
            latin_index + 1:
            next_code_index
        ]

        tail_text = " ".join(
            tail_lines
        )

        operations = extract_operations(
            tail_text
        )

        border_code = ""

        for tail_line in tail_lines:

            if re.fullmatch(
                r"\d{4}",
                tail_line
            ):

                border_code = tail_line
                break

        if not border_code:
            border_code = extract_border_code(
                tail_text
            )

        station = {
            "name": normalize_station_name(
                name
            ),
            "name_lat": clean_line(
                name_lat
            ),
            "code": code,
            "operations": operations,
            "border_code": border_code,
        }

        if not station["name"]:
            continue

        if not station["name_lat"]:
            continue

        if not re.fullmatch(
            r"\d{6}",
            station["code"]
        ):
            continue

        stations.append(
            station
        )

    return stations


# ============================================================
# ВАРИАНТ №2
# ПАРСЕР ПО 6-ЗНАЧНЫМ КОДАМ
# ============================================================

def parse_by_code_blocks(lines):

    stations = []

    clean_lines = [
        clean_line(line)
        for line in lines
        if clean_line(line)
    ]

    for index, line in enumerate(
        clean_lines
    ):

        if not is_station_code_line(
            line
        ):
            continue

        code = line

        # Ищем название выше.
        name = ""

        for back in range(
            1,
            5
        ):

            pos = index - back

            if pos < 0:
                break

            candidate = clean_lines[pos]

            if is_station_code_line(
                candidate
            ):
                break

            if is_service_line(
                candidate
            ):
                continue

            if has_letters(candidate):

                name = candidate
                break

        if not name:
            continue

        # Ищем латиницу ниже.
        name_lat = ""

        for forward in range(
            1,
            6
        ):

            pos = index + forward

            if pos >= len(
                clean_lines
            ):
                break

            candidate = clean_lines[pos]

            if is_station_code_line(
                candidate
            ):
                break

            if is_service_line(
                candidate
            ):
                continue

            if looks_like_latin_name(
                candidate
            ):

                name_lat = candidate
                break

        if not name_lat:
            continue

        # Хвост.
        tail = []

        for pos in range(
            index + 1,
            min(
                index + 8,
                len(clean_lines)
            )
        ):

            candidate = clean_lines[pos]

            if is_station_code_line(
                candidate
            ):
                break

            tail.append(candidate)

        tail_text = " ".join(
            tail
        )

        station = {
            "name": normalize_station_name(
                name
            ),
            "name_lat": clean_line(
                name_lat
            ),
            "code": code,
            "operations": extract_operations(
                tail_text
            ),
            "border_code": extract_border_code(
                tail_text
            ),
        }

        if len(station["name"]) < 2:
            continue

        if len(station["name_lat"]) < 2:
            continue

        stations.append(
            station
        )

    return stations


# ============================================================
# ВАРИАНТ №3
# ПАРСЕР СТРОКАМИ С КОДОМ ВНУТРИ СТРОКИ
# ============================================================

def parse_inline_stations(lines):

    stations = []

    for line in lines:

        line = clean_line(line)

        if not line:
            continue

        match = STATION_CODE_RE.search(
            line
        )

        if not match:
            continue

        code = match.group(1)

        before = clean_line(
            line[
                :match.start()
            ]
        )

        after = clean_line(
            line[
                match.end():
            ]
        )

        if not before:
            continue

        if is_service_line(
            before
        ):
            continue

        if not has_letters(
            before
        ):
            continue

        # ----------------------------------------------------
        # Ищем латинское название.
        # ----------------------------------------------------

        latin_match = re.search(
            r"[A-Za-zÀ-ÿÄÖÜäöüß]"
            r"[A-Za-zÀ-ÿÄÖÜäöüß0-9().,'’'\/\-\s]*",
            after
        )

        if not latin_match:
            continue

        name_lat = clean_line(
            latin_match.group(0)
        )

        if not name_lat:
            continue

        tail = after[
            latin_match.end():
        ]

        station = {
            "name": normalize_station_name(
                before
            ),
            "name_lat": name_lat,
            "code": code,
            "operations": extract_operations(
                tail
            ),
            "border_code": extract_border_code(
                tail
            ),
        }

        stations.append(
            station
        )

    return stations


# ============================================================
# ВАРИАНТ №4
# ПАРСЕР ПО ТАБЛИЦАМ PDF
# ============================================================

def parse_pdf_tables(document):

    stations = []

    for page in document:

        try:

            tables = page.find_tables()

        except Exception:

            continue

        if not tables:
            continue

        for table in tables.tables:

            try:
                rows = table.extract()
            except Exception:
                continue

            if not rows:
                continue

            for row in rows:

                if not row:
                    continue

                cells = [
                    clean_line(cell or "")
                    for cell in row
                ]

                cells = [
                    cell
                    for cell in cells
                    if cell
                ]

                if not cells:
                    continue

                # ------------------------------------------------
                # Ищем 6-значный код среди ячеек.
                # ------------------------------------------------

                code = ""

                code_index = -1

                for i, cell in enumerate(
                    cells
                ):

                    if is_station_code_line(
                        cell
                    ):

                        code = cell
                        code_index = i
                        break

                    match = STATION_CODE_RE.fullmatch(
                        cell
                    )

                    if match:

                        code = match.group(1)
                        code_index = i
                        break

                if not code:
                    continue

                # ------------------------------------------------
                # Ищем русское название.
                # ------------------------------------------------

                name = ""

                for i, cell in enumerate(
                    cells
                ):

                    if i == code_index:
                        continue

                    if is_service_line(
                        cell
                    ):
                        continue

                    if not has_letters(
                        cell
                    ):
                        continue

                    # Предпочитаем кириллицу.
                    if re.search(
                        r"[А-Яа-яЁё]",
                        cell
                    ):

                        name = cell
                        break

                if not name:
                    continue

                # ------------------------------------------------
                # Ищем латинское название.
                # ------------------------------------------------

                name_lat = ""

                for i, cell in enumerate(
                    cells
                ):

                    if i == code_index:
                        continue

                    if cell == name:
                        continue

                    if is_service_line(
                        cell
                    ):
                        continue

                    if looks_like_latin_name(
                        cell
                    ):

                        name_lat = cell
                        break

                if not name_lat:
                    continue

                full_row = " ".join(
                    cells
                )

                stations.append({
                    "name": name,
                    "name_lat": name_lat,
                    "code": code,
                    "operations": extract_operations(
                        full_row
                    ),
                    "border_code": extract_border_code(
                        full_row
                    ),
                })

    return stations


# ============================================================
# ПОИСК СТАНЦИЙ В PDF
# ============================================================

def extract_pdf_text(document):

    pages = []

    for page_number, page in enumerate(
        document
    ):

        text = page.get_text(
            "text"
        )

        pages.append({
            "page": page_number + 1,
            "text": text,
            "lines": text.splitlines(),
        })

    return pages


# ============================================================
# ВАЛИДАЦИЯ
# ============================================================

def validate_stations(stations):

    valid = []

    seen = set()

    for station in stations:

        name = clean_line(
            station.get(
                "name",
                ""
            )
        )

        name_lat = clean_line(
            station.get(
                "name_lat",
                ""
            )
        )

        code = clean_line(
            station.get(
                "code",
                ""
            )
        )

        if not name:
            continue

        if not name_lat:
            continue

        if not re.fullmatch(
            r"\d{6}",
            code
        ):
            continue

        key = (
            code,
            name,
            name_lat
        )

        if key in seen:
            continue

        seen.add(key)

        valid.append({
            "name": name,
            "name_lat": name_lat,
            "code": code,
            "operations": station.get(
                "operations",
                []
            ),
            "border_code": station.get(
                "border_code",
                ""
            ),
        })

    return valid


# ============================================================
# ОЦЕНКА РЕЗУЛЬТАТА
# ============================================================

def score_result(stations):

    if not stations:
        return 0

    score = 0

    score += len(stations) * 10

    latin_count = sum(
        1
        for s in stations
        if looks_like_latin_name(
            s["name_lat"]
        )
    )

    score += latin_count * 5

    unique_codes = len(
        set(
            s["code"]
            for s in stations
        )
    )

    score += unique_codes * 3

    return score


# ============================================================
# РАЗБОР ОДНОГО PDF
# ============================================================

def parse_pdf_document(
    pdf_bytes,
    country,
    country_code
):

    print()
    print("=" * 70)
    print(
        f"РАЗБОР PDF: "
        f"{country} ({country_code})"
    )
    print("=" * 70)

    document = pymupdf.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    print(
        f"Страниц PDF: {len(document)}"
    )

    pages = extract_pdf_text(
        document
    )

    all_lines = []

    for page in pages:

        all_lines.extend(
            page["lines"]
        )

    print(
        f"Извлечено строк: "
        f"{len(all_lines)}"
    )

    # --------------------------------------------------------
    # Количество 6-значных кодов
    # --------------------------------------------------------

    raw_code_count = sum(
        1
        for line in all_lines
        if is_station_code_line(
            line
        )
    )

    print(
        f"6-значных строк-кодов: "
        f"{raw_code_count}"
    )

    # --------------------------------------------------------
    # Вариант 1
    # --------------------------------------------------------

    result1 = validate_stations(
        parse_multiline_stations(
            all_lines
        )
    )

    print(
        f"Метод 1 — multiline: "
        f"{len(result1)} записей"
    )

    # --------------------------------------------------------
    # Вариант 2
    # --------------------------------------------------------

    result2 = validate_stations(
        parse_by_code_blocks(
            all_lines
        )
    )

    print(
        f"Метод 2 — code blocks: "
        f"{len(result2)} записей"
    )

    # --------------------------------------------------------
    # Вариант 3
    # --------------------------------------------------------

    result3 = validate_stations(
        parse_inline_stations(
            all_lines
        )
    )

    print(
        f"Метод 3 — inline: "
        f"{len(result3)} записей"
    )

    # --------------------------------------------------------
    # Вариант 4 — таблицы
    # --------------------------------------------------------

    result4 = validate_stations(
        parse_pdf_tables(
            document
        )
    )

    print(
        f"Метод 4 — PDF tables: "
        f"{len(result4)} записей"
    )

    # --------------------------------------------------------
    # Выбираем лучший результат.
    # --------------------------------------------------------

    candidates = [
        (
            "multiline",
            result1
        ),
        (
            "code_blocks",
            result2
        ),
        (
            "inline",
            result3
        ),
        (
            "pdf_tables",
            result4
        ),
    ]

    candidates.sort(
        key=lambda item: score_result(
            item[1]
        ),
        reverse=True
    )

    best_method, best_result = candidates[0]

    print()
    print(
        f"ВЫБРАН МЕТОД: "
        f"{best_method}"
    )

    print(
        f"Результат: "
        f"{len(best_result)} записей"
    )

    # --------------------------------------------------------
    # Дополнительная проверка.
    # --------------------------------------------------------

    if raw_code_count > 0:

        ratio = (
            len(best_result)
            / raw_code_count
        )

        print(
            f"Доля распознанных кодов: "
            f"{ratio:.1%}"
        )

    else:

        ratio = 0

    # --------------------------------------------------------
    # Если результат подозрительно маленький,
    # выводим предупреждение.
    # --------------------------------------------------------

    if (
        raw_code_count >= 20
        and len(best_result)
        < raw_code_count * 0.20
    ):

        print()
        print(
            "⚠️ ВНИМАНИЕ: результат "
            "подозрительно маленький."
        )

    # --------------------------------------------------------
    # Добавляем страну к каждой записи.
    # --------------------------------------------------------

    for station in best_result:

        station["country"] = country
        station["country_code"] = country_code

        # railway будет заполнен ниже.
        station["railway"] = ""

    document.close()

    return best_result


# ============================================================
# ОПРЕДЕЛЕНИЕ ЖЕЛЕЗНОЙ ДОРОГИ
# ============================================================

def railway_name(country):

    mapping = {

        "AZ": "Азербайджанские железные дороги",

        "AF": "Железная дорога Исламской Республики Афганистан",

        "BY": "Белорусская железная дорога",

        "BG": "Болгарские государственные железные дороги",

        "HU": "Венгерские государственные железные дороги",

        "VN": "Вьетнамская железная дорога",

        "GE": "Грузинская железная дорога",

        "IR": "Железная дорога Исламской Республики Иран",

        "KZ": "Казахстанские железные дороги",

        "CN": "Китайские железные дороги",

        "KP": "Железные дороги КНДР",

        "KG": "Кыргызская железная дорога",

        "KR": "Железные дороги Республики Корея",

        "LA": "Лаосская национальная железная дорога",

        "LV": "Латвийская железная дорога",

        "LT": "Литовские железные дороги",

        "MD": "Железная дорога Молдовы",

        "MN": "Улан-Баторская железная дорога",

        "PL": "Польские государственные железные дороги",

        "RU": "Российские железные дороги",

        "RO": "Румынские железные дороги CFR Marfa",

        "SK": "Железные дороги Словацкой Республики",

        "TJ": "Таджикская железная дорога",

        "TM": "Туркменские железные дороги",

        "UZ": "Узбекские железные дороги",

        "UA": "Украинская железная дорога",

        "CZ": "Чешские железные дороги",

        "EE": "Эстонская железная дорога",
    }

    return mapping.get(
        country,
        ""
    )


# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================================

def main():

    print()
    print("=" * 70)
    print("OSJD STATION DATABASE UPDATE")
    print("=" * 70)

    # --------------------------------------------------------
    # Находим документы.
    # --------------------------------------------------------

    documents = discover_osjd_documents()

    if not documents:

        raise RuntimeError(
            "Не найдено ни одного "
            "документа ОСЖД."
        )

    # --------------------------------------------------------
    # Проверяем количество.
    # --------------------------------------------------------

    expected_count = len(
        COUNTRIES
    )

    print()
    print(
        f"Ожидается стран ОСЖД: "
        f"{expected_count}"
    )

    print(
        f"Найдено документов: "
        f"{len(documents)}"
    )

    if len(documents) < 20:

        raise RuntimeError(
            "Найдено слишком мало "
            "документов ОСЖД. "
            "Обновление остановлено."
        )

    # --------------------------------------------------------
    # Результаты.
    # --------------------------------------------------------

    all_stations = []

    country_stats = {}

    failed_countries = []

    processed_countries = set()

    # --------------------------------------------------------
    # Скачиваем и разбираем документы.
    # --------------------------------------------------------

    for index, document in enumerate(
        documents,
        start=1
    ):

        country = document[
            "country"
        ]

        country_code = document[
            "country_code"
        ]

        print()
        print(
            "=" * 70
        )

        print(
            f"ДОКУМЕНТ "
            f"{index}/{len(documents)}"
        )

        print(
            f"Страна: "
            f"{country or 'НЕ ОПРЕДЕЛЕНА'}"
        )

        print(
            f"Код: "
            f"{country_code or '??'}"
        )

        print(
            f"Название: "
            f"{document['text']}"
        )

        if not country_code:

            print(
                "⚠️ Не удалось определить "
                "страну. Пропускаем."
            )

            continue

        processed_countries.add(
            country_code
        )

        try:

            pdf_bytes = download_pdf(
                document["url"]
            )

            stations = parse_pdf_document(
                pdf_bytes,
                country,
                country_code
            )

            # ------------------------------------------------
            # Добавляем железную дорогу.
            # ------------------------------------------------

            railway = railway_name(
                country_code
            )

            for station in stations:

                station["railway"] = railway

            count = len(
                stations
            )

            country_stats[
                country_code
            ] = count

            if count == 0:

                failed_countries.append(
                    country_code
                )

                print(
                    "❌ Страна не дала "
                    "ни одной станции."
                )

            else:

                print(
                    f"✅ Получено станций: "
                    f"{count}"
                )

                all_stations.extend(
                    stations
                )

        except Exception as error:

            print()
            print(
                f"❌ ОШИБКА "
                f"{country_code}:"
            )

            print(
                repr(error)
            )

            failed_countries.append(
                country_code
            )

        time.sleep(0.5)

    # ========================================================
    # УДАЛЯЕМ ДУБЛИКАТЫ
    # ========================================================

    print()
    print("=" * 70)
    print("УДАЛЕНИЕ ДУБЛИКАТОВ")
    print("=" * 70)

    unique = {}

    for station in all_stations:

        key = (
            station["country_code"],
            station["code"],
            station["name"],
            station["name_lat"],
        )

        if key not in unique:

            unique[key] = station

    all_stations = list(
        unique.values()
    )

    print(
        f"После удаления дублей: "
        f"{len(all_stations)}"
    )

    # ========================================================
    # СОРТИРОВКА
    # ========================================================

    all_stations.sort(
        key=lambda station: (
            station.get(
                "country_code",
                ""
            ),
            station.get(
                "name",
                ""
            ).lower(),
        )
    )

    # ========================================================
    # СТАТИСТИКА ПО СТРАНАМ
    # ========================================================

    final_stats = {}

    for station in all_stations:

        code = station[
            "country_code"
        ]

        final_stats[
            code
        ] = (
            final_stats.get(
                code,
                0
            ) + 1
        )

    print()
    print("=" * 70)
    print("СТАТИСТИКА ПО СТРАНАМ")
    print("=" * 70)

    for country_name, code in COUNTRIES.items():

        count = final_stats.get(
            code,
            0
        )

        symbol = (
            "✓"
            if count > 0
            else "✗"
        )

        print(
            f"{symbol} "
            f"{code:2} "
            f"{country_name:25} "
            f"{count:6}"
        )

    # ========================================================
    # ПРОВЕРКА 28 СТРАН
    # ========================================================

    missing = []

    for country_name, code in COUNTRIES.items():

        if final_stats.get(
            code,
            0
        ) == 0:

            missing.append(
                (
                    code,
                    country_name
                )
            )

    print()
    print("=" * 70)
    print("ПРОВЕРКА 28 СТРАН")
    print("=" * 70)

    print(
        f"Стран в справочнике: "
        f"{len(COUNTRIES)}"
    )

    print(
        f"Стран с данными: "
        f"{len(COUNTRIES) - len(missing)}"
    )

    print(
        f"Стран без данных: "
        f"{len(missing)}"
    )

    if missing:

        print()
        print(
            "⚠️ ОТСУТСТВУЮТ:"
        )

        for code, name in missing:

            print(
                f"  {code} — {name}"
            )

    else:

        print()
        print(
            "🎉 ВСЕ 28 СТРАН ПРИСУТСТВУЮТ!"
        )

    # ========================================================
    # ОБЩАЯ ПРОВЕРКА
    # ========================================================

    print()
    print("=" * 70)
    print("ФИНАЛЬНАЯ ПРОВЕРКА")
    print("=" * 70)

    print(
        f"Всего станций: "
        f"{len(all_stations)}"
    )

    invalid_codes = [
        station
        for station in all_stations
        if not re.fullmatch(
            r"\d{6}",
            station["code"]
        )
    ]

    missing_names = [
        station
        for station in all_stations
        if not station["name"]
    ]

    missing_lat = [
        station
        for station in all_stations
        if not station["name_lat"]
    ]

    print(
        f"Некорректных кодов: "
        f"{len(invalid_codes)}"
    )

    print(
        f"Без русского названия: "
        f"{len(missing_names)}"
    )

    print(
        f"Без латинского названия: "
        f"{len(missing_lat)}"
    )

    # ========================================================
    # КРИТИЧЕСКАЯ ЗАЩИТА
    # ========================================================

    # Если база получилась слишком маленькой,
    # старый stations.json НЕ перезаписываем.

    MIN_TOTAL_STATIONS = 1000

    if len(all_stations) < MIN_TOTAL_STATIONS:

        raise RuntimeError(
            "КРИТИЧЕСКАЯ ОШИБКА: "
            f"получено только "
            f"{len(all_stations)} станций. "
            f"Минимум: "
            f"{MIN_TOTAL_STATIONS}. "
            "stations.json НЕ изменён."
        )

    # Если исчезло больше 3 стран,
    # тоже не перезаписываем базу.

    if len(missing) > 3:

        raise RuntimeError(
            "КРИТИЧЕСКАЯ ОШИБКА: "
            f"отсутствует "
            f"{len(missing)} стран. "
            "stations.json НЕ изменён."
        )

    # ========================================================
    # СОХРАНЕНИЕ
    # ========================================================

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

    print()
    print("=" * 70)
    print("DATABASE SAVED")
    print("=" * 70)

    print(
        f"Файл: {OUTPUT}"
    )

    print(
        f"Записей: "
        f"{len(all_stations)}"
    )

    print()
    print(
        "✅ UPDATE FINISHED"
    )


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":

    main()
