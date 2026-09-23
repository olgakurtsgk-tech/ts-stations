import json
import re
import requests
import fitz
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote


OSJD_PAGE = "https://osjd.org/ru/8974/page/106077?id=2227"

OUTPUT = Path("data/stations.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TS-Stations/1.0)"
}


def get_osjd_page():
    print("Получаем страницу ОСЖД...")

    response = requests.get(
        OSJD_PAGE,
        headers=HEADERS,
        timeout=60
    )

    response.raise_for_status()

    return response.text


def find_pdf_links(html):
    print("Ищем документы ОСЖД...")

    soup = BeautifulSoup(html, "html.parser")

    documents = []
    seen = set()

    for link in soup.find_all("a", href=True):

        href = link["href"]
        title = " ".join(link.stripped_strings)

        # Нас интересуют ссылки на документы
        if "file=" not in href:
            continue

        if "api/media/resources" not in href:
            continue

        # Превращаем относительную ссылку в абсолютную
        full_url = urljoin(
            "https://osjd.org",
            href
        )

        # Получаем настоящий адрес PDF
        parsed = urlparse(full_url)
        params = parse_qs(parsed.query)

        file_values = params.get("file")

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

        # Убираем ?action=download и подобные параметры
        pdf_url = pdf_url.split("?")[0]

        if pdf_url in seen:
            continue

        seen.add(pdf_url)

        documents.append({
            "name": title,
            "url": pdf_url
        })

    print(
        f"Найдено документов: {len(documents)}"
    )

    for document in documents:
        print(
            f"  {document['name']} -> "
            f"{document['url']}"
        )

    return documents


def download_pdf(url):

    print(
        f"Скачиваем PDF: {url}"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=120
    )

    response.raise_for_status()

    content_type = response.headers.get(
        "content-type",
        ""
    ).lower()

    print(
        f"Content-Type: {content_type}"
    )

    if "pdf" not in content_type:

        # Иногда сервер ОСЖД не сообщает правильный Content-Type.
        # Проверяем сигнатуру PDF.
        if not response.content.startswith(
            b"%PDF"
        ):
            raise ValueError(
                "Получен не PDF-файл"
            )

    return response.content


def extract_text(pdf_bytes):

    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    pages = []

    for page in document:

        text = page.get_text(
            "text"
        )

        pages.append(text)

    document.close()

    return "\n".join(pages)


def find_station_records(text):

    records = []

    lines = text.splitlines()

    for index, line in enumerate(lines):

        line = " ".join(
            line.strip().split()
        )

        if not line:
            continue

        # Ищем шестизначный код станции
        match = re.search(
            r"(?<!\d)(\d{6})(?!\d)",
            line
        )

        if not match:
            continue

        code = match.group(1)

        # Берём несколько соседних строк.
        # Это поможет нам позже разобрать таблицу.
        context = []

        start = max(
            0,
            index - 2
        )

        end = min(
            len(lines),
            index + 3
        )

        for i in range(
            start,
            end
        ):

            value = " ".join(
                lines[i].strip().split()
            )

            if value:
                context.append(value)

        records.append({
            "code": code,
            "raw": " | ".join(context)
        })

    return records


def detect_country(document_name):

    countries = {
        "Азербайджан": "AZ",
        "Афганистан": "AF",
        "Белорус": "BY",
        "Болгар": "BG",
        "Венгр": "HU",
        "Вьетнам": "VN",
        "Груз": "GE",
        "Иран": "IR",
        "Казахстан": "KZ",
        "Китай": "CN",
        "КНДР": "KP",
        "Кыргыз": "KG",
        "Коре": "KR",
        "Лаос": "LA",
        "Латв": "LV",
        "Литв": "LT",
        "Молдов": "MD",
        "Монгол": "MN",
        "Поль": "PL",
        "Росс": "RU",
        "Румын": "RO",
        "Слова": "SK",
        "Таджик": "TJ",
        "Туркмен": "TM",
        "Узбек": "UZ",
        "Украин": "UA",
        "Чеш": "CZ",
        "Эстон": "EE"
    }

    for name, code in countries.items():

        if name.lower() in document_name.lower():

            return code

    return ""


def clean_country_name(document_name):

    name = document_name.strip()

    name = re.sub(
        r"^Перечень грузовых станций\s*",
        "",
        name,
        flags=re.IGNORECASE
    )

    name = re.sub(
        r"\s*\(\d+kb\)\s*$",
        "",
        name,
        flags=re.IGNORECASE
    )

    return name.strip()


def main():

    html = get_osjd_page()

    documents = find_pdf_links(
        html
    )

    if not documents:

        raise RuntimeError(
            "ОСЖД: документы не найдены"
        )

    stations = []

    for number, document in enumerate(
        documents,
        start=1
    ):

        print(
            f"\n[{number}/{len(documents)}] "
            f"{document['name']}"
        )

        try:

            pdf = download_pdf(
                document["url"]
            )

            text = extract_text(
                pdf
            )

            records = find_station_records(
                text
            )

            country = clean_country_name(
                document["name"]
            )

            country_code = detect_country(
                document["name"]
            )

            print(
                f"Найдено кодов станций: "
                f"{len(records)}"
            )

            for record in records:

                stations.append({

                    "name": "",

                    "name_lat": "",

                    "code": record["code"],

                    "country": country,

                    "country_code": country_code,

                    "railway": "",

                    "operations": [],

                    "border_code": "",

                    "_source": document["url"],

                    "_raw": record["raw"]
                })

        except Exception as error:

            print(
                f"ОШИБКА: {error}"
            )

    # Убираем дубли по коду + стране
    unique = {}

    for station in stations:

        key = (
            station["country_code"],
            station["code"]
        )

        if key not in unique:
            unique[key] = station

    stations = list(
        unique.values()
    )

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

    print(
        "\n=============================="
    )

    print(
        f"ГОТОВО. Всего записей: "
        f"{len(stations)}"
    )

    print(
        "=============================="
    )


if __name__ == "__main__":
    main()
