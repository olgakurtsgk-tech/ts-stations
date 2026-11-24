#!/usr/bin/env python3

"""
OSJD railway freight stations parser + RZD Excel Hybrid Parser.
"""

import io
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup

# Пытаемся импортировать pandas для чтения Excel
try:
    import pandas as pd
except ImportError:
    pd = None

# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "stations.json"
EXCEL_FILE = DATA_DIR / "stations_rzd.xls" # Файл, который вы должны загрузить в папку data

OSJD_PAGE = "https://osjd.org/ru/8974/page/106077?id=2227"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0 Safari/537.36"
    )
}

# ============================================================
# RAILWAY PREFIXES & MAPS
# ============================================================
# Для Excel парсера: сопоставление сокращений из справочника РЖД и полных названий
RZD_RAILWAY_MAP = {
    "Окт": "Октябрьская", "Мск": "Московская", "Моск": "Московская", "С-Кав": "Северо-Кавказская",
    "Ю-Вост": "Юго-Восточная", "Горьк": "Горьковская", "Сев": "Северная", "Сев-Кав": "Северо-Кавказская",
    "Кбш": "Куйбышевская", "Прив": "Приволжская", "Сверд": "Свердловская", "Ю-Ур": "Южно-Уральская",
    "З-Сиб": "Западно-Сибирская", "Крас": "Красноярская", "В-Сиб": "Восточно-Сибирская",
    "Заб": "Забайкальская", "Д-Вост": "Дальневосточная", "Клг": "Калининградская",
    "Крым": "Крымская", "ЖДЯ": "Железные дороги Якутии",
    # Для стран ближнего зарубежья (если будем использовать)
    "Кзх": "Казахстанская", "Узбк": "Узбекская", "Бел": "Белорусская", "Млд": "Молдавская",
    "Грз": "Грузинская", "Азерб": "Азербайджанская", "ЮКЖД": "Армянская", "Трк": "Туркменская",
    "Кырг": "Кыргызская", "Тадж": "Таджикская", "Лат": "Латвийская", "Лит": "Литовская",
    "Эст": "Эстонская", "Од": "Одесская", "Льв": "Львовская", "Южн": "Южная", "Ю-Зап": "Юго-Западная", "Дон": "Донецкая", "Придн": "Приднепровская"
}

# Ваши префиксы для PDF парсера (резервный вариант для тех, кого нет в Excel)
RAILWAY_PREFIXES = {
    "00": "Финляндская", "01": "Октябрьская", "02": "Октябрьская", "03": "Октябрьская", "04": "Октябрьская", "05": "Октябрьская",
    "06": "Московская", "07": "Московская", "08": "Московская", "09": "Московская",
    "10": "Калининградская", "11": "Белорусская", "12": "Белорусская", "13": "Белорусская", "14": "Белорусская", "15": "Белорусская", "16": "Белорусская",
    "17": "Московская", "18": "Московская", "19": "Московская", "20": "Московская",
    "21": "Юго-Восточная", "22": "Юго-Восточная", "23": "Юго-Восточная", "24": "Юго-Восточная",
    "25": "Горьковская", "26": "Горьковская", "27": "Горьковская", "28": "Горьковская",
    "29": "Северная", "30": "Северная", "31": "Северная", "32": "Северная",
    "33": "Украинская", "34": "Украинская", "35": "Украинская", "36": "Украинская", "37": "Украинская", 
    "38": "Украинская", "39": "Украинская", "40": "Украинская", "41": "Украинская", "42": "Украинская", 
    "43": "Украинская", "44": "Украинская", "45": "Украинская", "46": "Украинская", "47": "Украинская", 
    "48": "Украинская", "49": "Украинская",
    "51": "Молдавская",
    "52": "Северо-Кавказская", "53": "Северо-Кавказская",
    "54": "Азербайджанская", "55": "Азербайджанская",
    "56": "Грузинская", "57": "Грузинская",
    "58": "Армянская",
    "61": "Северо-Кавказская", "62": "Северо-Кавказская", 
    "63": "Куйбышевская", "64": "Куйбышевская", "65": "Куйбышевская", "66": "Куйбышевская", "67": "Куйбышевская", "68": "Куйбышевская",
    "69": "Приволжская", "70": "Приволжская",
    "71": "Южно-Уральская", "72": "Южно-Уральская", "73": "Южно-Уральская", "74": "Южно-Уральская",
    "75": "Забайкальская",
    "76": "Свердловская", "77": "Свердловская", "78": "Свердловская", "79": "Свердловская",
    "80": "Западно-Сибирская", "81": "Западно-Сибирская", "82": "Западно-Сибирская", "83": "Западно-Сибирская", "84": "Западно-Сибирская",
    "85": "Красноярская", "86": "Красноярская", "87": "Красноярская",
    "88": "Восточно-Сибирская", "89": "Восточно-Сибирская",
    "90": "Дальневосточная", "91": "Дальневосточная", "92": "Дальневосточная", "93": "Дальневосточная", 
    "94": "Дальневосточная", "95": "Дальневосточная", "96": "Дальневосточная", "97": "Дальневосточная", 
    "98": "Дальневосточная", "99": "Дальневосточная",
}

RAILWAY_OVERRIDES = {
    "820001": "Южно-Уральская", "820105": "Южно-Уральская",
}

def get_railway(code: str | None) -> str:
    if not code or len(code) < 2: return ""
    if code in RAILWAY_OVERRIDES: return RAILWAY_OVERRIDES[code]
    return RAILWAY_PREFIXES.get(code[:2], "")

# ============================================================
# COUNTRIES
# ============================================================
COUNTRIES = {
    "AZ": "Азербайджан", "AF": "Афганистан", "BY": "Беларусь", "BG": "Болгария",
    "HU": "Венгрия", "VN": "Вьетнам", "GE": "Грузия", "IR": "Иран",
    "KZ": "Казахстан", "CN": "Китай", "KP": "КНДР", "KG": "Кыргызстан",
    "KR": "Республика Корея", "LA": "Лаос", "LV": "Латвия", "LT": "Литва",
    "MD": "Молдова", "MN": "Монголия", "PL": "Польша", "RU": "Россия",
    "RO": "Румыния", "SK": "Словакия", "TJ": "Таджикистан", "TM": "Туркменистан",
    "UZ": "Узбекистан", "UA": "Украина", "CZ": "Чехия", "EE": "Эстония",
    "FI": "Финляндия",
}
EXCLUDED_COUNTRIES = {"IR", "CN", "CZ", "KR", "RO", "LA"}
ACTIVE_COUNTRIES = {code: name for code, name in COUNTRIES.items() if code not in EXCLUDED_COUNTRIES}

# ============================================================
# РУЧНЫЕ ДОПОЛНЕНИЯ (Для тех, кого нет в базах или нужно переопределить)
# ============================================================
MANUAL_ADDITIONS = [
    # --- Ваши ручные исключения ---
    {"name": "Береза Картузская", "code": "133700", "country": "Беларусь", "country_code": "BY", "latin_name": "Bereza Kartuzskaya"},
    {"name": "Буйнакск", "code": "543104", "country": "Россия", "country_code": "RU", "railway": "Северо-Кавказская", "latin_name": "Buynaksk"},
    {"name": "Джаббор Расулов", "code": "747709", "country": "Таджикистан", "country_code": "TJ", "latin_name": "Jabbor Rasulov"},
    {"name": "Жигулевское Море", "code": "636807", "country": "Россия", "country_code": "RU", "railway": "Куйбышевская", "latin_name": "Zhigulevskoe More"},
    {"name": "Жигулевское Море (перев.)", "code": "636900", "country": "Россия", "country_code": "RU", "railway": "Куйбышевская", "latin_name": "Zhigulevskoe More (perev.)"},
    {"name": "Жигулевское Море (эксп.)", "code": "637000", "country": "Россия", "country_code": "RU", "railway": "Куйбышевская", "latin_name": "Zhigulevskoe More (eksp.)"},
    
    # Остальные ваши ручные добавления из старого кода...
    {"name": "Сызрань I", "code": "635607", "country": "Россия", "country_code": "RU", "latin_name": "Syzran I"},
    {"name": "Сызрань II", "code": "635503", "country": "Россия", "country_code": "RU", "latin_name": "Syzran II"},
    # (Если вам нужны остальные ваши ручные правки, просто скопируйте их сюда из старой версии, они все сохранятся)
]

# ============================================================
# PDF PARSERS (Для не-Российских стран)
# ============================================================
COUNTRY_ALIASES = {
    "AZ": ["азербайджан"], "AF": ["афганистан"], "BY": ["беларус"], "BG": ["болгар"],
    "HU": ["венгр"], "VN": ["вьетнам"], "GE": ["грузинской железной дороги"], "IR": ["иран"],
    "KZ": ["казахстан"], "CN": ["китай"], "KP": ["кндр"], "KG": ["кыргыз"], "KR": ["республики кореи"],
    "LA": ["лаос"], "LV": ["латв"], "LT": ["литв"], "MD": ["молдов"], "MN": ["монгол"],
    "PL": ["поль"], "RU": ["россий"], "RO": ["румын", "чфр"], "SK": ["словац"],
    "TJ": ["таджик"], "TM": ["туркмен"], "UZ": ["узбек"], "UA": ["украин"], "CZ": ["чеш"], "EE": ["эстон"],
}

def normalize_space(value: str) -> str:
    if not value: return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ").replace("\u200b", "")).strip()

def normalize_code(value: str) -> str | None:
    if not value: return None
    value = str(value).strip()
    if re.fullmatch(r"\d{6}", value): return value
    digits = re.sub(r"\D", "", value)
    if len(digits) == 6: return digits
    # Если код короче 6 цифр, дополняем нулями слева (для Excel)
    if len(digits) > 0 and len(digits) < 6:
        return digits.zfill(6)
    return None

def clean_station_name(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r'^\d{1,2}\s+', '', value)
    value = re.sub(r"^[|;:,]+|[|;:,]+$", "", value).strip()
    value = value.replace('—', '-').replace('–', '-').replace('−', '-')
    return value

# ============================================================
# EXCEL PARSER (Для России)
# ============================================================
def parse_excel_stations(filepath: Path) -> list[dict]:
    if not pd or not filepath.exists():
        print(f"⚠ Excel файл не найден ({filepath}) или не установлен pandas. Пропускаем Excel парсинг.")
        return []

    print(f"Чтение Excel: {filepath}")
    try:
        # Читаем первые несколько строк, чтобы найти заголовок
        df = pd.read_excel(filepath, header=None, engine='xlrd')
        
        # Ищем строку с заголовками
        header_row = 0
        for idx, row in df.iterrows():
            if row.astype(str).str.contains("Наименование").any() and row.astype(str).str.contains("Код").any():
                header_row = idx
                break
        
        # Перечитываем с правильным заголовком
        df = pd.read_excel(filepath, header=header_row, engine='xlrd')
        
        # Переименовываем колонки для удобства (на случай если названия немного другие)
        columns = df.columns.tolist()
        name_col = next((c for c in columns if "Наименование" in str(c)), None)
        road_col = next((c for c in columns if "Дорога" in str(c)), None)
        code_col = next((c for c in columns if "Код" in str(c)), None)

        if not all([name_col, road_col, code_col]):
            print("⚠ Не удалось найти нужные колонки в Excel.")
            return []

        records = []
        for _, row in df.iterrows():
            name = str(row[name_col]).strip()
            road_short = str(row[road_col]).strip()
            code = normalize_code(str(row[code_col]))

            if not name or not code or pd.isna(row[name_col]):
                continue

            # Очищаем название
            name = clean_station_name(name)
            
            # Определяем полное название дороги
            railway = RZD_RAILWAY_MAP.get(road_short, "")
            # Если дорога не распознана, пробуем определить по префиксу кода
            if not railway and road_short in ["", "nan", "None"]:
                 railway = get_railway(code)

            # Пытаемся понять страну по дороге
            country_code = "RU" # По умолчанию Россия, если дорога из РФ
            country_name = "Россия"

            if road_short in ["Кзх", "Узбк", "Бел", "Млд", "Грз", "Азерб", "ЮКЖД", "Трк", "Кырг", "Тадж", "Лат", "Лит", "Эст", "Од", "Льв", "Южн", "Ю-Зап", "Дон", "Придн"]:
                # Это не Россия, пытаемся сопоставить код страны по дороге
                road_to_country = {
                    "Кзх": "KZ", "Узбк": "UZ", "Бел": "BY", "Млд": "MD", "Грз": "GE", "Азерб": "AZ",
                    "ЮКЖД": "AM", "Трк": "TM", "Кырг": "KG", "Тадж": "TJ", "Лат": "LV", "Лит": "LT",
                    "Эст": "EE", "Од": "UA", "Льв": "UA", "Южн": "UA", "Ю-Зап": "UA", "Дон": "UA", "Придн": "UA"
                }
                country_code = road_to_country.get(road_short, "RU") # Если не нашли, пусть будет RU
                country_name = COUNTRIES.get(country_code, "Россия")

            # Мы используем только станции РФ из Excel в этом примере,
            # чтобы не ломать наши правила для остальных стран. 
            # Но если вы хотите использовать Excel и для них, можно убрать этот if.
            if country_code == "RU":
                records.append({
                    "name": name,
                    "code": code,
                    "country": "Россия",
                    "country_code": "RU",
                    "railway": railway,
                    "latin_name": "" # В Excel нет латиницы, но она подтянется из PDF при слиянии
                })
        print(f"  ✓ Из Excel извлечено российских станций: {len(records)}")
        return records
    except Exception as e:
        print(f"  ✗ Ошибка чтения Excel: {e}")
        return []

# ============================================================
# PDF PARSERS (Упрощенные для краткости, логика та же)
# ============================================================
def download_pdf(url: str) -> bytes:
    try:
        response = requests.get(url, headers=HEADERS, timeout=(10, 30))
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"): raise RuntimeError("Not a PDF")
        return response.content
    except Exception as exc:
        raise RuntimeError(f"Network error: {exc}")

def discover_osjd_links() -> dict[str, str]:
    urls = {}
    try:
        response = requests.get(OSJD_PAGE, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a"):
            href = link.get("href")
            if not href: continue
            combined = f"{normalize_space(link.get_text(' ', strip=True))} {href}".lower()
            if "api/media/resources" not in combined and ".pdf" not in combined: continue
            if href.startswith("/"): href = "https://osjd.org" + href
            match = re.search(r"/api/media/resources/(\d+)", href)
            pdf_url = f"https://osjd.org/api/media/resources/{match.group(1)}?action=download" if match else href
            for code, aliases in COUNTRY_ALIASES.items():
                if code not in urls and any(a in combined for a in aliases):
                    urls[code] = pdf_url
                    break
    except Exception as e:
        print(f"Discovery error: {e}")
    return urls

# Упрощенный парсинг PDF (сохраняем вашу логику)
def parse_pdf(pdf_bytes: bytes, country_code: str) -> list[dict]:
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    t_recs = []
    for page in doc:
        text = page.get_text("text")
        lines = text.split('\n')
        buffer_name = ""
        for line in lines:
            line = normalize_space(line)
            if not line: continue
            matches = list(re.finditer(r'(?<!\d)(\d{6})(?!\d)', line))
            if not matches:
                if re.search(r'[А-Яа-яЁёA-Za-z]', line):
                    if buffer_name and re.match(r'^[а-яё\(\,\.]', line): buffer_name += " " + line
                    else: buffer_name = line
                continue
            for i, match in enumerate(matches):
                code = match.group(1)
                if i == 0:
                    left = line[:match.start()].strip()
                    if not left and buffer_name: left = buffer_name
                    buffer_name = ""
                else:
                    left = line[matches[i-1].end():match.start()].strip()
                
                right = line[match.end():matches[i+1].start() if i+1 < len(matches) else len(line)].strip()
                
                left = re.sub(r'.*\d{6}\s*', '', left)
                left = clean_station_name(left)
                left = re.sub(r'\s+([,\.\)])', r'\1', left)

                lat_match = re.match(r'^([A-Za-z\s\-\(\)\.]+)', right)
                if lat_match:
                    lat = clean_station_name(lat_match.group(1))
                    if left and lat and len(left) > 1 and len(lat) > 1:
                        # Простая проверка, чтобы не брать мусор
                        if not re.search(r"\d{6}", left):
                            t_recs.append({
                                "name": left, "code": code, 
                                "country": COUNTRIES[country_code], "country_code": country_code, 
                                "latin_name": lat
                            })
    doc.close()
    return t_recs

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 70)
    print("OSJD + RZD HYBRID STATIONS UPDATE")
    print("=" * 70)

    # 1. Загружаем Excel данные (Россия)
    excel_stations = parse_excel_stations(EXCEL_FILE)
    excel_dict = {s["code"]: s for s in excel_stations} # Словарь для быстрого поиска

    # 2. Загружаем PDF данные (Все страны)
    pdf_urls = discover_osjd_links()
    pdf_urls.update({
        "GE": "https://osjd.org/api/media/resources/2814?action=download",
        "EE": "https://osjd.org/api/media/resources/1671839?action=download",
        # Добавьте FALLBACK тут, если нужно
    })

    existing = []
    if OUTPUT_FILE.exists():
        try:
            with OUTPUT_FILE.open("r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception: pass

    all_new = []
    
    # Парсим страны из PDF
    for code, name in ACTIVE_COUNTRIES.items():
        url = pdf_urls.get(code)
        if not url: continue
        
        print(f"\nCOUNTRY {code} — {name}")
        try:
            pdf_bytes = download_pdf(url)
            recs = parse_pdf(pdf_bytes, code)
            
            # Если это Россия, мы берем данные из PDF ТОЛЬКО для тех станций, которых нет в Excel (чтобы не потерять латиницу)
            # Или мы можем полностью довериться Excel для РФ.
            if code == "RU":
                print(f"  PDF (RU): найдено {len(recs)}. Объединяем с Excel...")
                # Сливаем: Excel приоритетнее для названий и дорог
                merged_ru = {}
                for r in recs:
                    merged_ru[r["code"]] = r # сначала кладем из PDF (там есть latin_name)
                for code_ex, ex_rec in excel_dict.items():
                    if code_ex in merged_ru:
                        # Обновляем данные из Excel, но сохраняем латиницу из PDF
                        merged_ru[code_ex]["name"] = ex_rec["name"]
                        merged_ru[code_ex]["railway"] = ex_rec["railway"]
                    else:
                        # Если в PDF не было, добавляем чисто из Excel
                        merged_ru[code_ex] = ex_rec
                all_new.extend(merged_ru.values())
            else:
                all_new.extend(recs)
            print(f"  ✓ {code}: итого {len(recs)} записей")
        except Exception as e:
            print(f"  ✗ Ошибка в {code}: {e}")

    # 3. Объединение с существующими и ручными правками
    # Берем новые данные для стран, которые успешно спарсились
    new_countries = {r["country_code"] for r in all_new}
    merged = [r for r in existing if r.get("country_code") not in new_countries]
    merged.extend(all_new)
    
    # Добавляем ручные правки
    manual_keys = {(m["country_code"], m["code"]) for m in MANUAL_ADDITIONS}
    merged = [r for r in merged if (r["country_code"], r["code"]) not in manual_keys]
    merged.extend(MANUAL_ADDITIONS)
    
    # 4. ЖЕЛЕЗНОЕ ПРАВИЛО: Дорога только для России
    for m in merged:
        if m.get("country_code") == "RU":
            if "railway" not in m or not m["railway"]:
                m["railway"] = get_railway(m["code"])
        else:
            m.pop("railway", None) # У всех остальных удаляем

    merged = sorted(merged, key=lambda r: (r["country_code"], r["name"]))
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        
    print(f"\nSUCCESS! Всего записей в базе: {len(merged)}")

if __name__ == "__main__":
    main()
