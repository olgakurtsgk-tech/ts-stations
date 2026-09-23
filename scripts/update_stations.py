import json
import re
import requests
import fitz
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote


OSJD_PAGE = "https://osjd.org/ru/8974/page/106077?id=2227"

OUTPUT = Path("data/stations.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TS-Stations/1.0)"
}


def get_page():
    response = requests.get(
        OSJD_PAGE,
        headers=HEADERS,
        timeout=60
    )
    response.raise_for_status()
    return response.text


def find_documents(html):

    soup = BeautifulSoup(html, "html.parser")

    documents = []
    seen = set()

    for link in soup.find_all("a", href=True):

        href = link["href"]
        title = " ".join(link.stripped_strings)

        if "file=" not in href:
            continue

        if "api/media/resources" not in href:
            continue

        full_url = urljoin(
            "https://osjd.org",
            href
        )

        parsed = urlparse(full_url)
        params = parse_qs(parsed.query)

        file_values = params.get("file")

        if not file_values:
            continue

        pdf_url = unquote(file_values[0])

        if pdf_url.startswith("/"):
            pdf_url = urljoin(
                "https://osjd.org",
                pdf_url
            )

        pdf_url = pdf_url.split("?")[0]

        if pdf_url in seen:
            continue

        seen.add(pdf_url)

        documents.append({
            "name": title,
            "url": pdf_url
        })

    return documents


def download_pdf(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=120
    )

    response.raise_for_status()

    if not response.content.startswith(b"%PDF"):
        raise ValueError(
            "Полученный файл не является PDF"
        )

    return response.content


def extract_pages(pdf_bytes):

    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    pages = []

    for page in document:

        pages.append(
            page.get_text("text")
        )

    document.close()

    return pages


def is_station_code(value):

    return bool(
        re.fullmatch(
            r"\d{6}",
            value.strip()
        )
    )


def parse_station_line(line):

    line = " ".join(
        line.strip().split()
    )

    if not line:
        return None

    # Ищем шестизначный код,
    # который находится в начале строки.
    match = re.match(
        r"^(\d{6})\s+(.+)$",
        line
    )

    if not match:
        return None

    code = match.group(1)
    rest = match.group(2).strip()

    # Исключаем очевидные служебные строки
    bad_words = [
        "памятка",
        "регламент",
        "перечень грузовых станций",
        "железных дорог осжд"
    ]

    lower = rest.lower()

    for word in bad_words:

        if word in lower:
            return None

    # Если после кода есть нормальный текст,
    # считаем его названием станции.
    if len(rest) < 2:
        return None

    return {
        "code": code,
        "name": rest
    }


def parse_russian_pdf(pages):

    stations = []

    for page_number, page_text in enumerate(
        pages,
        start=1
    ):

        lines = page_text.splitlines()

        for line in lines:

            station = parse_station_line(line)

            if station:

                station["country"] = "Россия"
                station["country_code"] = "RU"
                station["railway"] = ""
                station["name_lat"] = ""
                station["operations"] = []
                station["border_code"] = ""
                station["_page"] = page_number

                stations.append(
                    station
                )

    return stations


def find_russian_document(documents):

    for document in documents:

        name = document["name"].lower()

        if "российских железных дорог" in name:
            return document

    return None


def main():

    print("Получаем страницу ОСЖД...")

    html = get_page()

    print("Ищем документы...")

    documents = find_documents(html)

    print(
        f"Найдено документов: {len(documents)}"
    )

    russian = find_russian_document(
        documents
    )

    if not russian:

        raise RuntimeError(
            "Российский перечень ОСЖД не найден"
        )

    print("")
    print("Найден российский перечень:")
    print(russian["name"])
    print(russian["url"])

    print("")
    print("Скачиваем PDF...")

    pdf = download_pdf(
        russian["url"]
    )

    print(
        f"Размер PDF: "
        f"{len(pdf) / 1024 / 1024:.2f} MB"
    )

    print("")
    print("Читаем PDF...")

    pages = extract_pages(
        pdf
    )

    print(
        f"Количество страниц: {len(pages)}"
    )

    print("")
    print("Разбираем станции...")

    stations = parse_russian_pdf(
        pages
    )

    # Убираем дубли
    unique = {}

    for station in stations:

        key = station["code"]

        if key not in unique:

            unique[key] = station

    stations = list(
        unique.values()
    )

    print("")
    print(
        f"Найдено станций: {len(stations)}"
    )

    print("")
    print("Первые 20:")

    for station in stations[:20]:

        print(
            station["code"],
            "—",
            station["name"]
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

    print("")
    print(
        f"JSON сохранён: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
