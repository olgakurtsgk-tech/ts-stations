import json
import re
from collections import Counter, defaultdict
from pathlib import Path


INPUT = Path("data/stations.json")


REQUIRED_FIELDS = [
    "name",
    "name_lat",
    "code",
    "operations",
    "border_code",
    "country",
    "country_code",
    "railway",
]


def load_data():
    if not INPUT.exists():
        raise RuntimeError(
            f"Файл не найден: {INPUT}"
        )

    with INPUT.open(
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise RuntimeError(
            "stations.json должен содержать JSON-массив"
        )

    return data


def print_header(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main():

    print_header(
        "ПРОВЕРКА БАЗЫ ЖЕЛЕЗНОДОРОЖНЫХ СТАНЦИЙ"
    )

    stations = load_data()

    total = len(stations)

    print(f"Файл: {INPUT}")
    print(f"Всего записей: {total}")

    # --------------------------------------------------------
    # 1. ПРОВЕРКА ОБЯЗАТЕЛЬНЫХ ПОЛЕЙ
    # --------------------------------------------------------

    print_header("1. ОБЯЗАТЕЛЬНЫЕ ПОЛЯ")

    missing_fields = []

    for index, station in enumerate(stations, start=1):

        for field in REQUIRED_FIELDS:

            if field not in station:
                missing_fields.append(
                    (index, field)
                )

    if missing_fields:

        print(
            f"ОШИБКА: отсутствуют поля: "
            f"{len(missing_fields)}"
        )

        for item in missing_fields[:20]:
            print(
                f"  запись {item[0]}: "
                f"нет поля {item[1]}"
            )

    else:

        print("✓ Все обязательные поля присутствуют")

    # --------------------------------------------------------
    # 2. СТРАНЫ
    # --------------------------------------------------------

    print_header("2. СТАНЦИИ ПО СТРАНАМ")

    country_counter = Counter(
        station.get(
            "country",
            "НЕ УКАЗАНО"
        )
        for station in stations
    )

    for country, count in sorted(
        country_counter.items(),
        key=lambda x: (-x[1], x[0])
    ):

        print(
            f"{country:25} "
            f"{count:7}"
        )

    print()
    print(
        f"Количество стран: "
        f"{len(country_counter)}"
    )

    # --------------------------------------------------------
    # 3. КОДЫ СТАНЦИЙ
    # --------------------------------------------------------

    print_header("3. ПРОВЕРКА КОДОВ")

    invalid_codes = []

    for station in stations:

        code = str(
            station.get(
                "code",
                ""
            )
        )

        if not re.fullmatch(
            r"\d{6}",
            code
        ):
            invalid_codes.append(
                station
            )

    print(
        f"Некорректных кодов: "
        f"{len(invalid_codes)}"
    )

    if invalid_codes:

        for station in invalid_codes[:20]:

            print(
                f"  {station.get('name')} "
                f"→ {station.get('code')}"
            )

    else:

        print(
            "✓ Все коды имеют формат 6 цифр"
        )

    # --------------------------------------------------------
    # 4. УНИКАЛЬНОСТЬ КОДОВ ВНУТРИ СТРАН
    # --------------------------------------------------------

    print_header(
        "4. ДУБЛИ КОДОВ ВНУТРИ СТРАН"
    )

    code_groups = defaultdict(list)

    for station in stations:

        key = (
            station.get("country_code"),
            station.get("code")
        )

        code_groups[key].append(
            station
        )

    duplicate_groups = {
        key: values
        for key, values in code_groups.items()
        if len(values) > 1
    }

    print(
        f"Групп дублей: "
        f"{len(duplicate_groups)}"
    )

    if duplicate_groups:

        for key, values in list(
            duplicate_groups.items()
        )[:30]:

            print()
            print(
                f"  {key[0]} / {key[1]}"
            )

            for station in values:

                print(
                    f"    - "
                    f"{station.get('name')} "
                    f"| "
                    f"{station.get('name_lat')}"
                )

    else:

        print(
            "✓ Дубликатов кодов внутри стран не найдено"
        )

    # --------------------------------------------------------
    # 5. ПОЛНЫЕ ДУБЛИ
    # --------------------------------------------------------

    print_header("5. ПОЛНЫЕ ДУБЛИ")

    station_keys = Counter()

    for station in stations:

        key = (
            station.get("country_code"),
            station.get("code"),
            station.get("name"),
            station.get("name_lat"),
        )

        station_keys[key] += 1

    full_duplicates = {
        key: count
        for key, count in station_keys.items()
        if count > 1
    }

    print(
        f"Групп полных дублей: "
        f"{len(full_duplicates)}"
    )

    if full_duplicates:

        for key, count in list(
            full_duplicates.items()
        )[:20]:

            print(
                f"  {count} × "
                f"{key[0]} | "
                f"{key[1]} | "
                f"{key[2]}"
            )

    else:

        print(
            "✓ Полных дублей не найдено"
        )

    # --------------------------------------------------------
    # 6. ПУСТЫЕ НАЗВАНИЯ
    # --------------------------------------------------------

    print_header("6. НАЗВАНИЯ")

    empty_name = []

    empty_name_lat = []

    for station in stations:

        if not str(
            station.get(
                "name",
                ""
            )
        ).strip():

            empty_name.append(
                station
            )

        if not str(
            station.get(
                "name_lat",
                ""
            )
        ).strip():

            empty_name_lat.append(
                station
            )

    print(
        f"Без русского названия: "
        f"{len(empty_name)}"
    )

    print(
        f"Без латинского названия: "
        f"{len(empty_name_lat)}"
    )

    # --------------------------------------------------------
    # 7. СЛУЖЕБНЫЕ НАЗВАНИЯ
    # --------------------------------------------------------

    print_header(
        "7. ПОДОЗРИТЕЛЬНЫЕ / СЛУЖЕБНЫЕ НАЗВАНИЯ"
    )

    suspicious_words = [
        "(терминал)",
        "(экспорт)",
        "(импорт)",
        "(транзит)",
        "(переход)",
        "эксп.",
        "имп.",
        "терминал",
    ]

    suspicious = []

    for station in stations:

        name = str(
            station.get(
                "name",
                ""
            )
        ).lower()

        for word in suspicious_words:

            if word in name:

                suspicious.append(
                    station
                )

                break

    print(
        f"Подозрительных записей: "
        f"{len(suspicious)}"
    )

    if suspicious:

        for station in suspicious[:50]:

            print(
                f"  {station.get('country')}: "
                f"{station.get('name')} "
                f"| "
                f"{station.get('code')}"
            )

    # --------------------------------------------------------
    # 8. СТАНЦИИ БЕЗ ОПЕРАЦИЙ
    # --------------------------------------------------------

    print_header(
        "8. КОММЕРЧЕСКИЕ ОПЕРАЦИИ"
    )

    without_operations = []

    with_operations = []

    for station in stations:

        operations = station.get(
            "operations",
            []
        )

        if operations:

            with_operations.append(
                station
            )

        else:

            without_operations.append(
                station
            )

    print(
        f"С операциями: "
        f"{len(with_operations)}"
    )

    print(
        f"Без операций: "
        f"{len(without_operations)}"
    )

    # --------------------------------------------------------
    # 9. ПОГРАНИЧНЫЕ КОДЫ
    # --------------------------------------------------------

    print_header(
        "9. ПОГРАНИЧНЫЕ ПЕРЕХОДЫ"
    )

    border_stations = []

    for station in stations:

        border_code = str(
            station.get(
                "border_code",
                ""
            )
        ).strip()

        if border_code:

            border_stations.append(
                station
            )

    print(
        f"С пограничным кодом: "
        f"{len(border_stations)}"
    )

    for station in border_stations[:30]:

        print(
            f"  {station.get('country')}: "
            f"{station.get('name')} "
            f"| "
            f"{station.get('code')} "
            f"| переход "
            f"{station.get('border_code')}"
        )

    # --------------------------------------------------------
    # 10. ПРИМЕРЫ ПО СТРАНАМ
    # --------------------------------------------------------

    print_header(
        "10. ПЕРВЫЕ 3 СТАНЦИИ ПО КАЖДОЙ СТРАНЕ"
    )

    by_country = defaultdict(list)

    for station in stations:

        by_country[
            station.get(
                "country",
                "НЕ УКАЗАНО"
            )
        ].append(
            station
        )

    for country in sorted(
        by_country
    ):

        print()
        print(
            f"--- {country} "
            f"({len(by_country[country])}) ---"
        )

        for station in by_country[country][:3]:

            print(
                f"  "
                f"{station.get('name')} "
                f"| "
                f"{station.get('code')} "
                f"| "
                f"{station.get('name_lat')}"
            )

    # --------------------------------------------------------
    # 11. ФИНАЛЬНЫЙ ВЕРДИКТ
    # --------------------------------------------------------

    print_header(
        "ИТОГОВАЯ ПРОВЕРКА"
    )

    errors = []

    if not stations:

        errors.append(
            "Файл не содержит записей"
        )

    if missing_fields:

        errors.append(
            "Есть записи без обязательных полей"
        )

    if invalid_codes:

        errors.append(
            "Есть некорректные коды"
        )

    if errors:

        print(
            "❌ БАЗА ТРЕБУЕТ ИСПРАВЛЕНИЯ"
        )

        print()

        for error in errors:

            print(
                f"  • {error}"
            )

    else:

        print(
            "✅ БАЗА ПРОШЛА ОСНОВНУЮ ПРОВЕРКУ"
        )

        print()
        print(
            f"Всего станций: {total}"
        )

        print(
            f"Стран: {len(country_counter)}"
        )

        print(
            f"Некорректных кодов: "
            f"{len(invalid_codes)}"
        )

        print(
            f"Дублей кодов внутри стран: "
            f"{len(duplicate_groups)}"
        )

        print(
            f"Полных дублей: "
            f"{len(full_duplicates)}"
        )

        print()
        print(
            "Подозрительные записи "
            "выведены отдельно выше."
        )


if __name__ == "__main__":
    main()
