import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


# ============================================================
# OSJD SOURCE DIAGNOSTIC
# Проверяем, какие перечни грузовых станций видит сайт ОСЖД
# ============================================================

OSJD_URLS = [
    "https://osjd.org/ru/",
    "https://osjd.org/ru/8984",
    "https://en.osjd.org/en/",
]


EXPECTED_COUNTRIES = {
    "AZ": "Азербайджан",
    "AF": "Афганистан",
    "BY": "Беларусь",
    "BG": "Болгария",
    "HU": "Венгрия",
    "VN": "Вьетнам",
    "GE": "Грузия",
    "IR": "Иран",
    "KZ": "Казахстан",
    "CN": "Китай",
    "KP": "КНДР",
    "KG": "Кыргызстан",
    "KR": "Республика Корея",
    "LA": "Лаос",
    "LV": "Латвия",
    "LT": "Литва",
    "MD": "Молдова",
    "MN": "Монголия",
    "PL": "Польша",
    "RU": "Россия",
    "RO": "Румыния",
    "SK": "Словакия",
    "TJ": "Таджикистан",
    "TM": "Туркменистан",
    "UZ": "Узбекистан",
    "UA": "Украина",
    "CZ": "Чехия",
    "EE": "Эстония",
}


# Дополнительные варианты написания названий.
# Это нужно, потому что на сайте ОСЖД страна может называться
# немного иначе, чем в нашей базе.

COUNTRY_ALIASES = {
    "Азербайджан": ["азербайджан", "azerbaijan"],
    "Афганистан": ["афганистан", "afghanistan"],
    "Беларусь": ["беларусь", "belarus", "byelorussian"],
    "Болгария": ["болгария", "bulgaria", "bulgarian"],
    "Венгрия": ["венгрия", "hungary", "hungarian"],
    "Вьетнам": ["вьетнам", "vietnam", "vietnamese"],
    "Грузия": ["грузия", "georgia", "georgian"],
    "Иран": ["иран", "iran", "iranian"],
    "Казахстан": ["казахстан", "kazakhstan"],
    "Китай": ["китай", "china", "chinese"],
    "КНДР": [
        "кндр",
        "корейская народно-демократическая республика",
        "democratic people's republic of korea",
        "dprk",
    ],
    "Кыргызстан": [
        "кыргызстан",
        "кыргызская республика",
        "kyrgyz republic",
        "kyrgyzstan",
    ],
    "Республика Корея": [
        "республика корея",
        "южная корея",
        "republic of korea",
        "south korea",
        "korail",
    ],
    "Лаос": [
        "лаос",
        "лаосская народно-демократическая республика",
        "lao people's democratic republic",
        "laos",
    ],
    "Латвия": ["латвия", "latvia", "latvian"],
    "Литва": ["литва", "lithuania", "lithuanian"],
    "Молдова": ["молдова", "moldova", "moldovan"],
    "Монголия": ["монголия", "mongolia", "mongolian"],
    "Польша": ["польша", "poland", "polish"],
    "Россия": [
        "россия",
        "российская федерация",
        "russia",
        "russian federation",
    ],
    "Румыния": ["румыния", "romania", "romanian"],
    "Словакия": [
        "словакия",
        "slovak republic",
        "slovakia",
        "slovakian",
    ],
    "Таджикистан": [
        "таджикистан",
        "tajikistan",
        "tajik",
    ],
    "Туркменистан": [
        "туркменистан",
        "turkmenistan",
        "turkmen",
    ],
    "Узбекистан": [
        "узбекистан",
        "uzbekistan",
        "uzbek",
    ],
    "Украина": ["украина", "ukraine", "ukrainian"],
    "Чехия": [
        "чехия",
        "чешская республика",
        "czech republic",
        "czechia",
        "czech",
    ],
    "Эстония": ["эстония", "estonia", "estonian"],
}


# ============================================================
# Заголовок
# ============================================================

print()
print("=" * 70)
print("OSJD FREIGHT STATION SOURCE DIAGNOSTIC")
print("=" * 70)
print()


# ============================================================
# HTTP настройки
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/128.0 Safari/537.36"
    )
}


# ============================================================
# Скачиваем страницы ОСЖД
# ============================================================

all_links = []


for page_url in OSJD_URLS:

    print()
    print("-" * 70)
    print(f"OPENING: {page_url}")
    print("-" * 70)

    try:

        response = requests.get(
            page_url,
            headers=HEADERS,
            timeout=30
        )

        print(
            f"HTTP STATUS: {response.status_code}"
        )

        print(
            f"CONTENT TYPE: "
            f"{response.headers.get('content-type', '')}"
        )

        if response.status_code != 200:
            print(
                "WARNING: page returned "
                f"HTTP {response.status_code}"
            )
            continue

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        links_found = 0

        for link in soup.find_all("a"):

            href = link.get("href")

            if not href:
                continue

            text = " ".join(
                link.stripped_strings
            ).strip()

            absolute_url = urljoin(
                page_url,
                href
            )

            combined = (
                f"{text} {absolute_url}"
            ).lower()

            # Ищем ссылки на PDF
            # и всё, что связано с грузовыми станциями.

            if (
                ".pdf" in absolute_url.lower()
                or "station" in combined
                or "станц" in combined
                or "грузов" in combined
                or "freight" in combined
            ):

                all_links.append(
                    {
                        "text": text,
                        "url": absolute_url,
                        "source_page": page_url,
                    }
                )

                links_found += 1

        print(
            f"Potential links found: {links_found}"
        )

    except Exception as error:

        print(
            f"ERROR: {error}"
        )


# ============================================================
# Удаляем дубликаты
# ============================================================

unique_links = {}

for item in all_links:

    unique_links[item["url"]] = item


all_links = list(
    unique_links.values()
)


# ============================================================
# Вывод найденных источников
# ============================================================

print()
print("=" * 70)
print("FOUND OSJD DOCUMENT LINKS")
print("=" * 70)
print()

print(
    f"Total unique links: {len(all_links)}"
)

print()


for number, item in enumerate(
    all_links,
    start=1
):

    print(
        f"[{number}]"
    )

    print(
        f"TEXT: {item['text']}"
    )

    print(
        f"URL:  {item['url']}"
    )

    print(
        f"PAGE: {item['source_page']}"
    )

    print()


# ============================================================
# Ищем страны в найденных ссылках
# ============================================================

print()
print("=" * 70)
print("COUNTRY SOURCE MATCHING")
print("=" * 70)
print()


found_country_matches = {}


for code, country_name in EXPECTED_COUNTRIES.items():

    aliases = COUNTRY_ALIASES.get(
        country_name,
        [country_name.lower()]
    )

    matches = []

    for item in all_links:

        combined = (
            f"{item['text']} "
            f"{item['url']}"
        ).lower()

        for alias in aliases:

            if alias.lower() in combined:

                matches.append(item)

                break

    found_country_matches[code] = matches

    if matches:

        print(
            f"✓ {code} | "
            f"{country_name} | "
            f"{len(matches)} possible source(s)"
        )

        for item in matches[:5]:

            print(
                f"    {item['url']}"
            )

    else:

        print(
            f"✗ {code} | "
            f"{country_name} | "
            f"NO SOURCE FOUND"
        )

    print()


# ============================================================
# Особое внимание отсутствующим 7 странам
# ============================================================

print()
print("=" * 70)
print("IMPORTANT: MISSING 7 COUNTRIES")
print("=" * 70)
print()


missing_codes = [
    "BG",
    "IR",
    "CN",
    "KR",
    "RO",
    "CZ",
    "EE",
]


for code in missing_codes:

    country_name = EXPECTED_COUNTRIES[
        code
    ]

    matches = found_country_matches.get(
        code,
        []
    )

    print(
        f"{code} — {country_name}"
    )

    if not matches:

        print(
            "    >>> NO MATCHING SOURCE LINK FOUND"
        )

    else:

        print(
            f"    >>> FOUND {len(matches)} SOURCE(S)"
        )

        for item in matches:

            print(
                f"    {item['url']}"
            )

    print()


# ============================================================
# Итог
# ============================================================

print()
print("=" * 70)
print("DIAGNOSTIC FINISHED")
print("=" * 70)
print()

print(
    "IMPORTANT:"
)

print(
    "This script DOES NOT modify stations.json."
)

print(
    "It only checks which OSJD document links "
    "are visible on the website."
)

print()
