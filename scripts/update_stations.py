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
    print("Ищем официальные документы ОСЖД...")
    
    soup = BeautifulSoup(html, "html.parser")
    
    links = []
    seen = set()

    for link in soup.find_all("a", href=True):

        href = link["href"]

        text = " ".join(link.stripped_strings)

        if "/api/media/resources/" not in href:
            continue

        if href.startswith("/"):
            href = urljoin("https://osjd.org", href)

        if href in seen:
            continue

        seen.add(href)

        links.append({
            "name": text,
            "url": href
        })

    print(f"Найдено документов: {len(links)}")

    return links


def download_pdf(url):
    print(f"Скачиваем: {url}")

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

    text = []

    for page in document:
        text.append(page.get_text("text"))

    document.close()

    return "\n".join(text)


def find_station_codes(text):

    results = []

    for line in text.splitlines():

        line = " ".join(
            line.strip().split()
        )

        if not line:
            continue

        matches = re.findall(
            r"(?<!\d)\d{6}(?!\d)",
            line
        )

        for code in matches:

            results.append({
                "code": code,
                "raw": line
            })

    return results


def main():

    html = get_osjd_page()

    documents = find_pdf_links(html)

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

            text = extract_text(pdf)

            records = find_station_codes(text)

            print(
                f"Найдено строк с кодами: "
                f"{len(records)}"
            )

            for record in records:

                stations.append({
                    "name": "",
                    "name_lat": "",
                    "code": record["code"],
                    "country": document["name"],
                    "country_code": "",
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
        f"\nГотово! "
        f"Записей: {len(stations)}"
    )

    print(
        f"Файл: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
