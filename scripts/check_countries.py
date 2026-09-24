import json
from pathlib import Path


INPUT = Path("data/stations.json")


# ============================================================
# ОЖИДАЕМЫЕ СТРАНЫ ОСЖД
# ============================================================

EXPECTED_COUNTRIES = {
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


def main():

    print()
    print("=" * 70)
    print("ПРОВЕРКА СТРАН В БАЗЕ СТАНЦИЙ")
    print("=" * 70)

    if not INPUT.exists():

        raise RuntimeError(
            f"Файл не найден: {INPUT}"
        )

    with INPUT.open(
        "r",
        encoding="utf-8"
    ) as f:

        stations = json.load(f)

    print()
    print(
        f"Всего записей в stations.json: "
        f"{len(stations)}"
    )

    # --------------------------------------------------------
    # Считаем станции по country_code
    # --------------------------------------------------------

    country_counts = {}

    for station in stations:

        code = station.get(
            "country_code",
            ""
        )

        country_counts[code] = (
            country_counts.get(
                code,
                0
            )
            + 1
        )

    print()
    print("=" * 70)
    print("ВСЕ 28 СТРАН ОСЖД")
    print("=" * 70)

    missing = []
    present = []

    for country, code in sorted(
        EXPECTED_COUNTRIES.items()
    ):

        count = country_counts.get(
            code,
            0
        )

        if count > 0:

            print(
                f"✓ {country:25} "
                f"{code:2} "
                f"{count:6} станций"
            )

            present.append(
                country
            )

        else:

            print(
                f"✗ {country:25} "
                f"{code:2} "
                f"НЕТ"
            )

            missing.append(
                country
            )

    # --------------------------------------------------------
    # Страны, которых нет в нашем ожидаемом списке
    # --------------------------------------------------------

    expected_codes = set(
        EXPECTED_COUNTRIES.values()
    )

    unexpected = []

    for code, count in sorted(
        country_counts.items()
    ):

        if code not in expected_codes:

            unexpected.append(
                (code, count)
            )

    if unexpected:

        print()
        print("=" * 70)
        print("НЕОЖИДАННЫЕ КОДЫ СТРАН")
        print("=" * 70)

        for code, count in unexpected:

            print(
                f"? {code}: "
                f"{count} станций"
            )

    # --------------------------------------------------------
    # Итог
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("ИТОГ")
    print("=" * 70)

    print(
        f"Ожидаемых стран ОСЖД: "
        f"{len(EXPECTED_COUNTRIES)}"
    )

    print(
        f"Стран найдены: "
        f"{len(present)}"
    )

    print(
        f"Стран отсутствуют: "
        f"{len(missing)}"
    )

    if missing:

        print()
        print("ОТСУТСТВУЮТ:")

        for country in missing:

            code = EXPECTED_COUNTRIES[country]

            print(
                f"  ✗ {country} ({code})"
            )

    else:

        print()
        print(
            "🎉 ВСЕ 28 СТРАН ПРИСУТСТВУЮТ В БАЗЕ!"
        )

    if unexpected:

        print()
        print(
            "ВНИМАНИЕ: найдены неизвестные "
            "коды стран."
        )

    print()
    print("=" * 70)

    if missing:

        print(
            "РЕЗУЛЬТАТ: НУЖНО ПРОВЕРИТЬ "
            "ОТСУТСТВУЮЩИЕ СТРАНЫ"
        )

    else:

        print(
            "РЕЗУЛЬТАТ: ПРОВЕРКА СТРАН ПРОЙДЕНА"
        )

    print("=" * 70)


if __name__ == "__main__":
    main()
