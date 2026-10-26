#!/usr/bin/env python3
import json
import csv
from pathlib import Path

# Пути к файлам
BASE_DIR = Path(__file__).resolve().parent
STATIONS_JSON = BASE_DIR / "data" / "stations.json" # Ваш рабочий файл
REFERENCE_CSV = BASE_DIR / "reference.csv"          # Сюда положите файл от Росжелдора

def load_json_codes():
    if not STATIONS_JSON.exists():
        print(f"Ошибка: не найден {STATIONS_JSON}")
        return set()
    with open(STATIONS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
        return {str(station["code"]) for station in data}

def load_csv_codes():
    if not REFERENCE_CSV.exists():
        print(f"Ошибка: не найден {REFERENCE_CSV}. Скачайте официальный список и положите его сюда.")
        return {}

    codes = {}
    # В файлах Росжелдора обычно используется разделитель ';'
    with open(REFERENCE_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            # Ищем колонки с кодом и названием (они могут называться по-разному)
            code = row.get("КОД_СТАНЦИИ") or row.get("CODE") or row.get("Код")
            name = row.get("НАИМЕНОВАНИЕ") or row.get("NAME") or row.get("Название")
            
            if code and name:
                # Очищаем код от лишних символов
                clean_code = ''.join(filter(str.isdigit, str(code)))
                if len(clean_code) == 6:
                    codes[clean_code] = name.strip()
    return codes

def main():
    print("Загрузка вашей базы данных...")
    existing_codes = load_json_codes()
    print(f"В вашей базе: {len(existing_codes)} станций")

    print("Загрузка официального списка...")
    reference_data = load_csv_codes()
    print(f"В официальном списке: {len(reference_data)} станций")

    if not reference_data:
        return

    missing = []
    for code, name in reference_data.items():
        if code not in existing_codes:
            missing.append((code, name))

    print("\n" + "="*50)
    print(f"НАЙДЕНО ПРОПУЩЕННЫХ СТАНЦИЙ: {len(missing)}")
    print("="*50)
    
    if missing:
        # Сохраняем результат в файл для удобства
        with open("missing_stations.txt", "w", encoding="utf-8") as f:
            for code, name in sorted(missing, key=lambda x: x[1]):
                line = f"{name} (Код: {code})"
                print(line)
                f.write(line + "\n")
        print("\nСписок сохранен в файл 'missing_stations.txt'")
        print("Вы можете брать оттуда названия и коды для добавления в MANUAL_ADDITIONS.")
    else:
        print("Отлично! Все станции из официального списка есть в вашей базе.")

if __name__ == "__main__":
    main()
