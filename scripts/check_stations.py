import json
from collections import Counter
from pathlib import Path


FILE = Path("data/stations.json")


def main():

    print("")
    print("========================================")
    print("       ПРОВЕРКА БАЗЫ ЖД-СТАНЦИЙ")
    print("========================================")
    print("")

    if not FILE.exists():
        print("ОШИБКА: файл stations.json не найден")
        return

    with open(
        FILE,
        "r",
        encoding="utf-8"
    ) as f:

        stations = json.load(f)

    print(
        f"Всего записей: {len(stations)}"
    )

    print("")

    # -------------------------------------
    # СТРАНЫ
    # -------------------------------------

    countries = Counter(
        station.get("country", "Не указана")
        for station in stations
    )

    print("СТРАНЫ:")
    print("----------------------------------------")

    for country, count in countries.most_common():

        print(
            f"{country}: {count}"
        )

    print("")

    # -------------------------------------
    # УНИКАЛЬНЫЕ КОДЫ
    # -------------------------------------

    codes = [
        station.get("code")
        for station in stations
        if station.get("code")
    ]

    unique_codes = set(codes)

    print(
        f"Всего кодов: {len(codes)}"
    )

    print(
        f"Уникальных кодов: {len(unique_codes)}"
    )

    print("")

    # -------------------------------------
    # НАЗВАНИЯ
    # -------------------------------------

    names = [
        station.get("name", "").strip()
        for station in stations
    ]

    names_filled = [
        name
        for name in names
        if name
    ]

    print(
        f"Записей с названием: "
        f"{len(names_filled)}"
    )

    print(
        f"Записей без названия: "
        f"{len(names) - len(names_filled)}"
    )

    print("")

    # -------------------------------------
    # ЛАТИНСКИЕ НАЗВАНИЯ
    # -------------------------------------

    latin_names = [
        station.get("name_lat", "").strip()
        for station in stations
    ]

    latin_filled = [
        name
        for name in latin_names
        if name
    ]

    print(
        f"Записей с латинским названием: "
        f"{len(latin_filled)}"
    )

    print("")

    # -------------------------------------
    # ЖЕЛЕЗНЫЕ ДОРОГИ
    # -------------------------------------

    railways = Counter(
        station.get("railway", "Не указана")
        for station in stations
    )

    print("ЖЕЛЕЗНЫЕ ДОРОГИ:")
    print("----------------------------------------")

    for railway, count in railways.most_common(30):

        print(
            f"{railway}: {count}"
        )

    print("")

    # -------------------------------------
    # ПЕРВЫЕ 20 ЗАПИСЕЙ
    # -------------------------------------

    print("ПЕРВЫЕ 20 ЗАПИСЕЙ:")
    print("----------------------------------------")

    for number, station in enumerate(
        stations[:20],
        start=1
    ):

        print(
            f"{number}. "
            f"{station.get('name', '')} | "
            f"{station.get('code', '')} | "
            f"{station.get('country', '')}"
        )

    print("")

    # -------------------------------------
    # ПРОВЕРКА ДЛИНЫ КОДОВ
    # -------------------------------------

    wrong_codes = [
        code
        for code in codes
        if len(str(code)) != 6
    ]

    print(
        f"Кодов не из 6 цифр: "
        f"{len(wrong_codes)}"
    )

    if wrong_codes:

        print("Примеры:")

        for code in wrong_codes[:20]:

            print(code)

    print("")

    print("========================================")
    print("             ПРОВЕРКА ОКОНЧЕНА")
    print("========================================")


if __name__ == "__main__":
    main()
