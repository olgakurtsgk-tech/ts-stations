#!/usr/bin/env python3

"""
OSJD railway freight stations parser.
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


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "stations.json"

OSJD_PAGE = "https://osjd.org/ru/8974/page/106077?id=2227"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0 Safari/537.36"
    )
}

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
}

EXCLUDED_COUNTRIES = {"IR", "CN", "CZ", "KR", "RO", "LA"}
ACTIVE_COUNTRIES = {code: name for code, name in COUNTRIES.items() if code not in EXCLUDED_COUNTRIES}

# ============================================================
# FALLBACK PDF URLS (Наивысший приоритет)
# ============================================================

FALLBACK_PDFS = {
    "GE": "https://osjd.org/api/media/resources/2814?action=download",
    "IR": "https://osjd.org/api/media/resources/9608?action=download",
    "CN": "https://osjd.org/api/media/resources/1537?action=download",
    "KR": "https://osjd.org/api/media/resources/1637529?action=download",
    "RO": "https://osjd.org/api/media/resources/2813?action=download",
    "CZ": "https://osjd.org/api/media/resources/3904?action=download",
    "EE": "https://osjd.org/api/media/resources/1671839?action=download",
}

COUNTRY_ALIASES = {
    "AZ": ["азербайджан", "азербайджанских железных дорог"],
    "AF": ["афганистан", "железной дороги исламской республики афганистан"],
    "BY": ["беларус", "белорусской железной дороги"],
    "BG": ["болгар", "болгарских государственных железных дорог"],
    "HU": ["венгр", "венгерских государственных железных дорог"],
    "VN": ["вьетнам", "вьетнамской железной дороги"],
    "GE": ["грузовых станций грузинской железной дороги", "перечень грузовых станций грузинской", "грузинской железной дороги"],
    "IR": ["иран", "железной дороги исламской республики иран"],
    "KZ": ["казахстан", "железных дорог казахстан"],
    "CN": ["китай", "китайских железных дорог"],
    "KP": ["кндр", "корейской народно-демократической республики"],
    "KG": ["кыргыз", "кыргызской железной дороги"],
    "KR": ["республики кореи", "республика корея", "железных дорог республики кореи"],
    "LA": ["лаос", "лаосской национальной железной дороги"],
    "LV": ["латв", "латвийской железной дороги"],
    "LT": ["литв", "литовских железных дорог"],
    "MD": ["молдов", "железной дороги молдовы"],
    "MN": ["монгол", "улан-баторской железной дороги"],
    "PL": ["поль", "польских государственных железных дорог"],
    "RU": ["россий", "российских железных дорог"],
    "RO": ["румын", "румынских ж", "чфр"],
    "SK": ["словац", "словацкой республики"],
    "TJ": ["таджик", "таджикской железной дороги"],
    "TM": ["туркмен", "туркмендемиреллары"],
    "UZ": ["узбек", "узбекистан", "узбекских железных дорог"],
    "UA": ["украин", "украинской железной дороги"],
    "CZ": ["чеш", "чешских железных дорог"],
    "EE": ["эстон", "эстонской железной дороги"],
}

# ============================================================
# HELPERS
# ============================================================

def normalize_space(value: str) -> str:
    if not value: return ""
    value = value.replace("\xa0", " ").replace("\u200b", "")
    return re.sub(r"\s+", " ", value).strip()

def normalize_code(value: str) -> str | None:
    if not value: return None
    value = value.strip()
    if re.fullmatch(r"\d{6}", value): return value
    digits = re.sub(r"\D", "", value)
    if len(digits) == 6: return digits
    return None

def is_noise_name(value: str) -> bool:
    if not value: return True
    lower = value.lower()
    bad_fragments = ["наименование станции", "код станции", "операции", "страница", "содержание", "перечень грузовых станций"]
    if any(f in lower for f in bad_fragments): return True
    return False

def clean_station_name(value: str) -> str:
    value = normalize_space(value)
    return re.sub(r"^[|;:,]+|[|;:,]+$", "", value).strip()

def valid_name(value: str) -> bool:
    value = clean_station_name(value)
    if is_noise_name(value) or len(value) > 150 or len(value) < 2: return False
    if not re.search(r"[A-Za-zА-Яа-яЁё]", value): return False
    return True

def strict_station_name(value: str, script: str) -> bool:
    value = clean_station_name(value)
    if not valid_name(value): return False
    if re.search(r"(?<!\d)\d{6}(?!\d)", value): return False
    if script == "ru" and not re.search(r"[А-Яа-яЁё]", value): return False
    if script == "latin" and not re.search(r"[A-Za-z]", value): return False
    return True

def make_record(country_code, code, ru, lat, border_code=""):
    ru = clean_station_name(ru)
    lat = clean_station_name(lat)
    if not normalize_code(code) or not valid_name(ru) or not valid_name(lat): return None
    rec = {"name": ru, "code": normalize_code(code), "country": COUNTRIES[country_code], "country_code": country_code, "latin_name": lat}
    if border_code and normalize_code(border_code): rec["border_code"] = normalize_code(border_code)
    return rec

# ============================================================
# HARD TIMEOUT HTTP
# ============================================================

def download_pdf(url: str) -> bytes:
    print(f"\nDownloading: {url}")
    start_time = time.time()
    try:
        response = requests.get(url, headers=HEADERS, timeout=(10, 30), stream=True)
        response.raise_for_status()
        
        content = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            content.extend(chunk)
            if time.time() - start_time > 60:
                raise RuntimeError("Download timeout (>60s)")

        if not content.startswith(b"%PDF"):
            raise RuntimeError("Not a PDF file")
            
        print(f"SIZE: {len(content)} bytes")
        return bytes(content)
    except Exception as exc:
        raise RuntimeError(f"Network error: {exc}")

def discover_osjd_links() -> dict[str, str]:
    try:
        response = requests.get(OSJD_PAGE, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        result = {}
        for link in soup.find_all("a"):
            href = link.get("href")
            if not href: continue
            text = normalize_space(link.get_text(" ", strip=True))
            combined = f"{text} {href}".lower()
            if "api/media/resources" not in combined and ".pdf" not in combined: continue
            if href.startswith("/"): href = "https://osjd.org" + href
            match = re.search(r"/api/media/resources/(\d+)", href)
            pdf_url = f"https://osjd.org/api/media/resources/{match.group(1)}?action=download" if match else href.split("#", 1)[0]
            
            for code, aliases in COUNTRY_ALIASES.items():
                if code not in result and any(a in combined for a in aliases):
                    result[code] = pdf_url
                    break
        return result
    except Exception as e:
        print(f"Discovery error: {e}")
        return {}

def get_pdf_urls() -> dict[str, str]:
    urls = discover_osjd_links()
    urls.update(FALLBACK_PDFS)
    return urls

# ============================================================
# PARSERS
# ============================================================

def parse_text_page(text: str, country_code: str) -> list[dict]:
    """Парсит сплошной текст (вытаскивает названия слева и справа от 6-значного кода)."""
    records = []
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        line = normalize_space(line)
        if len(line) < 10: continue
        
        match = re.search(r'(?<!\d)(\d{6})(?!\d)', line)
        if not match: continue
        
        code = match.group(1)
        left = line[:match.start()].strip()
        right = line[match.end():].strip()
        
        # Если слева пусто, берем предыдущую строку (название съехало наверх)
        if not left and i > 0:
            prev_line = normalize_space(lines[i-1])
            if prev_line and not re.search(r'\d{6}', prev_line):
                left = prev_line
                
        # Оставляем только русскую часть в левой колонке (убираем грузинский текст)
        if left:
            ru_match = re.search(r'[А-Яа-яЁё][А-Яа-яЁё\s\-\(\)\.,]*$', left)
            if ru_match:
                left = ru_match.group(0).strip()
                
        lat_match = re.match(r'^([A-Za-z\s\-\(\)\.]+)', right)
        if not lat_match: continue
        
        ru = clean_station_name(left)
        lat = clean_station_name(lat_match.group(1))
        
        if strict_station_name(ru, "ru") and strict_station_name(lat, "latin"):
            rec = make_record(country_code, code, ru, lat)
            if rec: records.append(rec)
            
    return records

def parse_words_page(words: list[tuple], country_code: str) -> list[dict]:
    records = []
    if not words: return records
    
    groups = []
    # Увеличили допуск по Y до 10.0, чтобы склеивать слова на одной визуальной строке
    for word in sorted(words, key=lambda i: (round(float(i[1]), 1), float(i[0]))):
        placed = False
        for g in groups[-30:]:
            if abs(float(word[1]) - g["y"]) <= 10.0:
                g["words"].append(word); g["y"] = sum(float(w[1]) for w in g["words"])/len(g["words"]); placed=True; break
        if not placed: groups.append({"y": float(word[1]), "words": [word]})
        
    for g in groups:
        row = sorted(g["words"], key=lambda i: float(i[0]))
        for i, w in enumerate(row):
            code = normalize_code(str(w[4]))
            skip = 1
            if not code and i+1 < len(row):
                code = normalize_code(str(w[4]) + str(row[i+1][4])); skip = 2
            if not code: continue
            
            left = " ".join(str(x[4]) for x in row[:i])
            right = " ".join(str(x[4]) for x in row[i+skip:])
            
            # Очистка левой части от грузинского текста
            if left:
                ru_match = re.search(r'[А-Яа-яЁё][А-Яа-яЁё\s\-\(\)\.,]*$', left)
                if ru_match:
                    left = ru_match.group(0).strip()
            
            lat_match = re.match(r'^([A-Za-z\s\-\(\)\.]+)', right)
            if not lat_match: continue
            
            ru = clean_station_name(left)
            lat = clean_station_name(lat_match.group(1))
            if strict_station_name(ru, "ru") and strict_station_name(lat, "latin"):
                rec = make_record(country_code, code, ru, lat)
                if rec: records.append(rec)
    return records

def parse_pdf(pdf_bytes: bytes, country_code: str) -> list[dict]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    t_recs, w_recs = [], []
    for page in doc:
        text = page.get_text("text")
        words = page.get_text("words")
        
        t_recs.extend(parse_text_page(text, country_code))
        w_recs.extend(parse_words_page(words, country_code))
    doc.close()

    final = []
    seen = set()
    # Отдаем приоритет парсеру текста (он точнее собирает полные названия)
    for source in (t_recs, w_recs):
        for r in source:
            if r["code"] not in seen:
                final.append(r)
                seen.add(r["code"])
                
    print(f"  PARSED: {len(final)} (Text: {len(t_recs)}, Words: {len(w_recs)})")
    return final

# ============================================================
# VALIDATION & MAIN
# ============================================================

def deduplicate(records: list[dict]) -> list[dict]:
    seen = set()
    return [r for r in records if (r["country_code"], r["code"]) not in seen and not seen.add((r["country_code"], r["code"]))]

def load_existing() -> list[dict]:
    if not OUTPUT_FILE.exists(): return []
    try:
        with OUTPUT_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def main():
    print("=" * 70)
    print("OSJD STATIONS UPDATE")
    print("=" * 70)

    pdf_urls = get_pdf_urls()
    existing = load_existing()
    all_new = []
    
    for code, name in ACTIVE_COUNTRIES.items():
        url = pdf_urls.get(code)
        if not url:
            print(f"  ✗ {code}: Нет ссылки")
            continue

        print(f"\nCOUNTRY {code} — {name}")
        try:
            pdf_bytes = download_pdf(url)
            recs = deduplicate(parse_pdf(pdf_bytes, code))
            
            old_count = len([r for r in existing if r.get("country_code") == code])
            if old_count and len(recs) < math.ceil(old_count * 0.65):
                print(f"  ⚠ {code}: Мало записей ({len(recs)} < {old_count}). Оставляем старые.")
                continue
                
            all_new.extend(recs)
            print(f"  ✓ {code}: {len(recs)} записей")
        except Exception as e:
            print(f"  ✗ Ошибка в {code}: {e}")
            old_count = len([r for r in existing if r.get("country_code") == code])
            if not old_count:
                raise RuntimeError(f"Фатальная ошибка: нет данных для {code}")

    new_countries = {r["country_code"] for r in all_new}
    merged = [r for r in existing if r.get("country_code") not in new_countries]
    merged.extend(all_new)
    
    counters = Counter(s.get("country_code") for s in merged)
    missing = [c for c in ACTIVE_COUNTRIES if counters.get(c, 0) == 0]
    if missing:
        raise RuntimeError(f"Отсутствуют страны: {missing}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        
    print(f"\nSUCCESS! Всего записей: {len(merged)}")

if __name__ == "__main__":
    main()
