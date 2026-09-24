import json
from pathlib import Path
from collections import Counter


# ============================================================
# OSJD — список стран, которые должны быть в базе
# ============================================================

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


# ============================================================
# Путь к базе
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
STATIONS_FILE = BASE_DIR / "data" / "stations.json"


# ============================================================
# Заголовок
# ============================================================

print()
print("=" * 60)
print("OSJD COUNTRY CHECK")
print("=" * 60)
print()


# ============================================================
# Проверяем наличие файла
# ============================================================

if not STATIONS_FILE.exists():
    raise SystemExit(
        f"ERROR: file not found: {STATIONS_FILE}"
    )


print(f"Database: {STATIONS_FILE}")
print()


# ============================================================
# Загружаем JSON
# ============================================================

try:
    with STATIONS_FILE.open(
        "r",
        encoding="utf-8"
    ) as f:
        stations = json.load(f)

except Exception as error:
    raise SystemExit(
        f"ERROR: cannot read stations.json: {error}"
    )


# ============================================================
# Проверяем структуру
# ============================================================

if not isinstance(stations, list):
    raise SystemExit(
        "ERROR: stations.json must contain a JSON array"
    )


print(f"Total station records: {len(stations):,}")
print()


# ============================================================
# Считаем страны по country_code
# ============================================================

country_codes = Counter()

for station in stations:
    code = str(
        station.get("country_code", "")
    ).strip().upper()

    if code:
        country_codes[code] += 1


# ============================================================
# Проверяем страны
# ============================================================

print("EXPECTED OSJD COUNTRIES")
print("-" * 60)

missing_countries = []
present_countries = []

for code, country_name in EXPECTED_COUNTRIES.items():

    count = country_codes.get(code, 0)

    if count > 0:
        print(
            f"✓ {code:2} | "
            f"{country_name:<20} | "
            f"{count:,} stations"
        )
        present_countries.append(code)

    else:
        print(
            f"✗ {code:2} | "
            f"{country_name:<20} | "
            f"NOT FOUND"
        )
        missing_countries.append(code)


# ============================================================
# Неожиданные коды стран
# ============================================================

unexpected_codes = sorted(
    code
    for code in country_codes
    if code not in EXPECTED_COUNTRIES
)


print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)

print(
    f"Expected OSJD countries : {len(EXPECTED_COUNTRIES)}"
)

print(
    f"Countries found         : {len(present_countries)}"
)

print(
    f"Countries missing       : {len(missing_countries)}"
)

print()


# ============================================================
# Отсутствующие страны
# ============================================================

if missing_countries:

    print("MISSING COUNTRIES")
    print("-" * 60)

    for code in missing_countries:
        print(
            f"{code} — {EXPECTED_COUNTRIES[code]}"
        )

else:

    print("✓ ALL EXPECTED OSJD COUNTRIES ARE PRESENT")


# ============================================================
# Неизвестные коды
# ============================================================

print()

if unexpected_codes:

    print("UNEXPECTED COUNTRY CODES")
    print("-" * 60)

    for code in unexpected_codes:
        print(
            f"{code} — {country_codes[code]:,} stations"
        )

else:

    print("✓ NO UNEXPECTED COUNTRY CODES")


# ============================================================
# Статистика по всем кодам
# ============================================================

print()
print("ALL COUNTRY CODES IN DATABASE")
print("-" * 60)

for code, count in sorted(
    country_codes.items(),
    key=lambda item: (-item[1], item[0])
):

    country_name = EXPECTED_COUNTRIES.get(
        code,
        "UNKNOWN COUNTRY"
    )

    print(
        f"{code:2} | "
        f"{country_name:<20} | "
        f"{count:,}"
    )


# ============================================================
# Итог
# ============================================================

print()
print("=" * 60)

if missing_countries:

    print(
        "RESULT: DATABASE IS MISSING "
        f"{len(missing_countries)} OSJD COUNTRIES"
    )

    print("=" * 60)
    print()

    # ВАЖНО:
    # На этом этапе мы НЕ останавливаем GitHub Actions.
    # Нам нужно сначала увидеть, какие страны отсутствуют.

else:

    print(
        "RESULT: ALL EXPECTED OSJD COUNTRIES FOUND"
    )

    print("=" * 60)
    print()
