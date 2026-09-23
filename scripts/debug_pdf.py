import requests
import fitz

URL = "https://osjd.org/api/media/resources/3062?action=download"

headers = {
    "User-Agent": "Mozilla/5.0 (compatible; TS-Stations/1.0)"
}

print("Скачиваем PDF России...")

response = requests.get(
    URL,
    headers=headers,
    timeout=120
)

response.raise_for_status()

print("Размер PDF:", len(response.content), "байт")

document = fitz.open(
    stream=response.content,
    filetype="pdf"
)

print("Количество страниц:", len(document))

for page_number in range(min(8, len(document))):

    page = document[page_number]

    text = page.get_text("text")

    print("\n")
    print("=" * 70)
    print("СТРАНИЦА", page_number + 1)
    print("=" * 70)
    print(text[:10000])

document.close()
