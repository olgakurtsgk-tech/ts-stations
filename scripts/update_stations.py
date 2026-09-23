import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote

import fitz
import requests
from bs4 import BeautifulSoup


OSJD_PAGE = "https://osjd.org/ru/8931/page/106077?id=2227"

OUTPUT = Path("data/stations.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# Страны, которые сейчас опубликованы ОСЖД
COUNTRIES = {
    "Азербайджан": ("AZ", "Азербайджанские железные дороги"),
    "Афганистан": ("AF", "Железная дорога Исламской Республики Афганистан"),
    "Беларусь": ("BY", "Белорусская железная дорога"),
    "Болгария": ("BG", "Болгарские государственные железные дороги"),
    "Венгрия": ("HU", "Венгерские государственные железные дороги"),
    "Вьетнам": ("VN", "Вьетнамская железная дорога"),
    "Грузия": ("GE", "Грузинская железная дорога"),
    "Иран": ("IR", "Железная дорога Исламской Республики Иран"),
    "Казахстан": ("KZ", "железных дорог Казахстана"),
    "Китай": ("CN", "Китайских железных дорог"),
    "КНДР": ("KP", "железных дорог КНДР"),
    "Кыргызстан": ("KG", "Кыргызской железной дороги"),
    "Республика Корея": ("KR", "железных дорог Республики Корея"),
    "Лаос": ("LA", "Лаосской национальной железной дороги"),
    "Латвия": ("LV", "Латвийской железной дороги"),
    "Литва": ("LT", "Литовских железных дорог"),
    "Молдова": ("MD", "железной дороги Молдовы"),
    "Монголия": ("MN", "Улан-Баторской железной дороги"),
    "Польша": ("PL", "Польских государственных железных дорог"),
    "Россия": ("RU", "Российских железных дорог"),
    "Румыния": ("RO", "Румынских ж. д."),
    "Словакия": ("SK", "железных дорог Словацкой Республики"),
    "Таджикистан": ("TJ", "Таджикской железной дороги"),
    "Туркменистан": ("TM", "Туркмендемиреллары"),
    "Узбекистан": ("UZ", "Узбекских железных дорог"),
    "Украина": ("UA", "Украинской железной дороги"),
    "Чехия": ("CZ", "Чешских железных дорог"),
    "Эстония": ("EE", "Эстонской железной дороги"),
}


def clean_text(value):
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def get_pdf_url(href):
    """
    ОСЖД сейчас открывает PDF через viewer:
    /ru/page/...?...file=/api/media/resources/XXXX?action=download

    Извлекаем настоящий URL PDF.
    """
    href = urljoin(OSJD_PAGE, href)

    parsed = urlparse(href)
    query = parse_qs(parsed.query)

    if "file" in query:
        file_path = unquote(query["file"][0])

        if file_path.startswith("http"):
            return file_path

        return urljoin("https://osjd.org", file_path)

    return href


def identify_country(link_text):
    text = clean_text(link_text).lower()

    for country, (code, marker) in COUNTRIES.items():
        if marker.lower() in text:
            return country, code

    # отдельные варианты названий
    aliases = {
        "азербайджанских": ("Азербайджан", "AZ"),
        "афганистан": ("Афганистан", "AF"),
        "белорусской": ("Беларусь", "BY"),
        "болгарских": ("Болгария", "BG"),
        "венгерских": ("Венгрия", "HU"),
        "вьетнамской": ("Вьетнам", "VN"),
        "грузинской": ("Грузия", "GE"),
        "иран": ("Иран", "IR"),
        "казахстана": ("Казахстан", "KZ"),
        "китайских": ("Китай", "CN"),
        "кндр": ("КНДР", "KP"),
        "кыргызской": ("Кыргызстан", "KG"),
        "кореи": ("Республика Корея", "KR"),
        "лаосской": ("Лаос", "LA"),
        "латвийской": ("Латвия", "LV"),
        "литовских": ("Литва", "LT"),
        "молдовы": ("Молдова", "MD"),
        "улан-баторской": ("Монголия", "MN"),
        "польских": ("Польша", "PL"),
        "российских": ("Россия", "RU"),
        "румынских": ("Румыния", "RO"),
        "словацкой": ("Словакия", "SK"),
        "таджикской": ("Таджикистан", "TJ"),
        "туркмен": ("Туркменистан", "TM"),
        "узбекских": ("Узбекистан", "UZ"),
        "украинской": ("Украина", "UA"),
        "чешских": ("Чехия", "CZ"),
        "эстонской": ("Эстония", "EE"),
    }

    for alias, result in aliases.items():
        if alias in text:
            return result

    return None, None


def download_pdf(url):
    print(f"  Download: {url}")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=120
    )

    response.raise_for_status()

    if not response.content.startswith(b"%PDF"):
        raise RuntimeError("Получен не PDF-файл")

    return response.content


def parse_station_line(line):
    """
    Основная задача:
    найти 6-значный код станции и разобрать строку вокруг него.

    Пример:
    АБАКАН 888004 ABAKAN 1,2,3,4,5,8,8Н,9,10
    """

    line = clean_text(line)

    # Убираем явный мусор страниц
    if not line:
        return None

    # Ищем шестизначный код станции
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", line)

    if not match:
        return None

    code = match.group(1)

    before = line[:match.start()].strip()
    after = line[match.end():].strip()

    # До кода должно быть название станции
    if len(before) < 2:
        return None

    # Отсекаем заголовки таблиц и служебные строки
    bad_words = [
        "наименование",
        "код станции",
        "производимые",
        "коммерческие операции",
        "код пограничного",
        "раздел",
        "таблица",
        "станций железных дорог",
    ]

    low = line.lower()

    if any(word in low for word in bad_words):
        return None

    name = before

    # Иногда PDF склеивает несколько строк.
    # Для латинского названия ищем начало латинского текста.
    latin_match = re.search(
        r"([A-Za-z][A-Za-z0-9 .,\-()'’/]+)",
        after
    )

    if not latin_match:
        return None

    name_lat = latin_match.group(1).strip()

    # Убираем хвост, который явно относится к операциям
    # и пограничному коду.
    tail = after[latin_match.end():].strip()

    # Более надёжно: операции ищем в хвосте.
    operations = []

    op_matches = re.findall(
        r"(?<![A-Za-zА-Яа-я])"
        r"(?:1|2|3|4|5|6|7|8|9|10|11|12)"
        r"(?:Н|н)?"
        r"(?![A-Za-zА-Яа-я])",
        tail
    )

    for op in op_matches:
        op = op.upper()
        if op not in operations:
            operations.append(op)

    # Иногда операции приклеены прямо к латинскому названию:
    # ABAKAN1,3,4
    attached = re.search(
        r"(?:^|[A-Za-z)])"
        r"((?:1|2|3|4|5|6|7|8|9|10|11|12)(?:Н|н)?"
        r"(?:,(?:1|2|3|4|5|6|7|8|9|10|11|12)(?:Н|н)?)+)",
        after
    )

    if attached:
        for op in attached.group(1).split(","):
            op = op.upper()
            if op not in operations:
                operations.append(op)

    # Код пограничного перехода — обычно 4 цифры.
    border_match = re.search(r"(?<!\d)(\d{4})(?!\d)", tail)

    border_code = border_match.group(1) if border_match else ""

    return {
        "name": name,
        "name_lat": name_lat,
        "code": code,
        "operations": operations,
        "border_code": border_code,
    }


def parse_pdf(pdf_bytes, country, country_code, railway):
    stations = []

    document = fitz.open(stream=pdf_bytes, filetype="pdf")

    in_station_section = False

    for page_number, page in enumerate(document):
        text = page.get_text("text")

        if "Раздел 3." in text or "Алфавитный перечень" in text:
            in_station_section = True

        if "Раздел 4." in text or "Пограничные переходы" in text:
            if in_station_section:
                break

        if not in_station_section:
            continue

        # Разбираем строки
        lines = text.splitlines()

        # PDF иногда склеивает две станции в одну строку.
        # Поэтому сначала пробуем обычные строки.
        for line in lines:
            parsed = parse_station_line(line)

            if parsed:
                parsed["country"] = country
                parsed["country_code"] = country_code
                parsed["railway"] = railway

                stations.append(parsed)

    return stations


def deduplicate(stations):
    result = {}

    for station in stations:
        key = (
            station["country_code"],
            station["code"],
            station["name"]
        )

        if key not in result:
            result[key] = station

    return list(result.values())


def main():
    print("========================================")
    print(" OSJD railway station database updater")
    print("========================================")

    print("\nПолучаем страницу ОСЖД...")

    response = requests.get(
        OSJD_PAGE,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    pdf_links = []

    for link in soup.find_all("a"):
        text = clean_text(link.get_text(" ", strip=True))
        href = link.get("href")

        if not href:
            continue

        if "Перечень грузовых станций" not in text:
            continue

        country, country_code = identify_country(text)

        if not country:
            continue

        pdf_url = get_pdf_url(href)

        pdf_links.append({
            "country": country,
            "country_code": country_code,
            "title": text,
            "url": pdf_url,
        })

    print(f"\nНайдено перечней ОСЖД: {len(pdf_links)}")

    if len(pdf_links) < 20:
        raise RuntimeError(
            f"ОСЖД должно быть около 28 перечней, "
            f"а найдено только {len(pdf_links)}"
        )

    all_stations = []

    for item in pdf_links:
        print("\n----------------------------------------")
        print(item["country"])
        print("----------------------------------------")

        try:
            pdf = download_pdf(item["url"])

            # Железную дорогу берём из названия документа.
            railway = item["title"]

            stations = parse_pdf(
                pdf,
                item["country"],
                item["country_code"],
                railway
            )

            print(f"  Найдено станций: {len(stations)}")

            all_stations.extend(stations)

        except Exception as exc:
            print(
                f"  ERROR: {item['country']}: {exc}"
            )

        time.sleep(1)

    all_stations = deduplicate(all_stations)

    # Проверка качества.
    # Главное — не позволить GitHub записать пустой/сломанный JSON.
    if len(all_stations) < 1000:
        raise RuntimeError(
            f"Слишком мало станций: {len(all_stations)}. "
            "JSON НЕ будет перезаписан."
        )

    all_stations.sort(
        key=lambda x: (
            x["country"],
            x["name"].upper(),
            x["code"]
        )
    )

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

    print("\n========================================")
    print("ГОТОВО")
    print("========================================")
    print(f"Всего станций: {len(all_stations)}")
    print(f"Файл: {OUTPUT}")

    # Небольшой контрольный вывод
    print("\nПримеры:")

    for station in all_stations[:10]:
        print(
            station["name"],
            "|",
            station["code"],
            "|",
            station["name_lat"],
            "|",
            station["country"]
        )


if __name__ == "__main__":
    main()
