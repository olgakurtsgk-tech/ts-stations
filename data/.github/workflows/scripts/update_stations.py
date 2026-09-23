import json
import re
import requests
import fitz
from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urljoin


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


def find_pdf_links(html):
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):

        href = a["href"]
        text = " ".join(a.stripped_strings)

        if "/api/media/resources/" in href:

            if href.startswith("/"):
                href = urljoin(
                    "https://osjd.org",
                    href
                )

            links.append({
                "name": text,
                "url": href
            })

    # убираем дубли
    result = []
    seen = set()

    for item in links:

        if item["url"] not in seen:

            seen.add(item["url"])
            result.append(item)

    return result


def download_pdf(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=120
    )

    response.raise_for_status()

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


def detect_station_lines(text):

    records = []

    for line in text.splitlines():

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

        records.append({
            "raw": line,
            "code": code
        })

    return records


def main():

    print("Получаем страницу ОСЖД...")

    html = get_page()

    links = find_pdf_links(html)

    print(
        f"Найдено документов: {len(links)}"
    )

    stations = []

    for number, item in enumerate(
        links,
        start=1
    ):

        print()
        print(
            f"[{number}/{len(links)}] "
            f"{item['name']}"
        )

        try:

            pdf = download_pdf(
                item["url"]
            )

            text = extract_text(pdf)

            lines = detect_station_lines(
                text
            )

            print(
                f"Найдено строк с кодами: "
                f"{len(lines)}"
            )

            for row in lines:

                stations.append({

                    "name": "",

                    "name_lat": "",

                    "code": row["code"],

                    "country": item["name"],

                    "country_code": "",

                    "railway": "",

                    "operations": [],

                    "border_code": "",

                    "_source": item["url"],

                    "_raw": row["raw"]

                })

        except Exception as error:

            print(
                f"ОШИБКА: {error}"
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

    print()
    print(
        f"Готово. Записей: "
        f"{len(stations)}"
    )

    print(
        f"Файл: {OUTPUT}"
    )


if __name__ == "__main__":

    main()
