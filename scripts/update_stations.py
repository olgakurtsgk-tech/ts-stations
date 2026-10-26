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
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/153.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 60

# ============================================================
# COUNTRIES
# ============================================================

COUNTRIES = {
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

EXCLUDED_COUNTRIES = {"IR", "CN", "CZ", "KR", "RO", "LA"}
ACTIVE_COUNTRIES = {
    code: name for code, name in COUNTRIES.items()
    if code not in EXCLUDED_COUNTRIES
}


# ============================================================
# FALLBACK PDF URLS
#
# ВАЖНО: Эти ссылки имеют НАИВЫСШИЙ приоритет.
# Если сайт ОСЖД вернёт неверную ссылку, скрипт будет
# использовать ту, что указана здесь.
# ============================================================

FALLBACK_PDFS = {
    # Прямая ссылка на PDF Грузии (проверена: содержит станции Грузии, включая Батуми)
    "GE": "https://osjd.org/api/media/resources/2814?action=download",
    "IR": "https://osjd.org/api/media/resources/9608?action=download",
    "CN": "https://osjd.org/api/media/resources/1537?action=download",
    "KR": "https://osjd.org/api/media/resources/1637529?action=download",
    "RO": "https://osjd.org/api/media/resources/2813?action=download",
    "CZ": "https://osjd.org/api/media/resources/3904?action=download",
    "EE": "https://osjd.org/api/media/resources/1671839?action=download",
}


# ============================================================
# NAME MATCHING
# ============================================================

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
    if not value:
        return ""
    value = value.replace("\xa0", " ").replace("\u200b", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_code(value: str) -> str | None:
    if not value:
        return None
    value = value.strip()
    if re.fullmatch(r"\d{6}", value):
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) == 6:
        return digits
    return None


def is_noise_name(value: str) -> bool:
    if not value:
        return True
    text = normalize_space(value)
    if len(text) < 2:
        return True
    lower = text.lower()
    bad_fragments = [
        "наименование станции", "код станции", "код погранич", "производимые коммерческие",
        "операции", "страница", "содержание", "раздел ", "перечень грузовых станций",
        "железной дороги", "железных дорог", "код ", "наименование", "государственном языке",
    ]
    if any(fragment in lower for fragment in bad_fragments):
        return True
    if re.fullmatch(r"[\d\s.,;:/()\-]+", text):
        return True
    return False


def clean_station_name(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r"^[|;:,]+", "", value)
    value = re.sub(r"[|;:,]+$", "", value)
    return normalize_space(value)


def looks_like_operations(value: str) -> bool:
    """
    Усиленная проверка на коды операций (например: "1; 4;9 (ТП)", "8н,10н").
    Если в строке есть цифры и нет нормальных слов (длиннее 2 букв) — это мусор.
    """
    if not value:
        return False
    text = normalize_space(value)
    if re.search(r"[А-Яа-яЁёA-Za-z]{3,}", text):
        return False
    if re.search(r"\d", text):
        return True
    return False


def valid_name(value: str) -> bool:
    value = clean_station_name(value)
    if is_noise_name(value) or len(value) > 150:
        return False
    if looks_like_operations(value):
        return False
    if not re.search(r"[A-Za-zА-Яа-яЁё]", value):
        return False
    return True


def strict_station_name(value: str, script: str) -> bool:
    value = clean_station_name(value)
    if not valid_name(value):
        return False
    if re.search(r"(?<!\d)\d{6}(?!\d)", value):
        return False
    if script == "ru" and not re.search(r"[А-Яа-яЁё]", value):
        return False
    if script == "latin" and not re.search(r"[A-Za-z]", value):
        return False
    if len(value.split()) > 8:
        return False
    return True


# ============================================================
# HTTP & DISCOVERY
# ============================================================

def download_pdf(url: str) -> bytes:
    print("\n" + "-" * 70)
    print("DOWNLOAD\n" + url)
    try:
        response = requests.get(url, headers=HEADERS, timeout=(10, 30))
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Network error downloading {url}: {exc}")

    print("HTTP STATUS:", response.status_code)
    print("SIZE:", len(response.content))
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"URL did not return PDF: {url}")

    return response.content


def discover_osjd_links() -> dict[str, str]:
    print("\n" + "=" * 70)
    print("DISCOVERING OSJD PDF LINKS (for reference)")
    print("=" * 70)
    response = requests.get(OSJD_PAGE, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    result = {}

    for link in soup.find_all("a"):
        href = link.get("href")
        if not href:
            continue
        text = normalize_space(link.get_text(" ", strip=True))
        combined = f"{text} {href}".lower()

        if "api/media/resources" not in combined and ".pdf" not in combined:
            continue
        if href.startswith("/"):
            href = "https://osjd.org" + href

        resource_match = re.search(r"/api/media/resources/(\d+)", href)
        if resource_match:
            pdf_url = f"https://osjd.org/api/media/resources/{resource_match.group(1)}?action=download"
        else:
            pdf_url = href.split("#", 1)[0]

        for country_code, aliases in COUNTRY_ALIASES.items():
            if country_code in result:
                continue
            if any(alias in combined for alias in aliases):
                result[country_code] = pdf_url
                print(f"  FOUND {country_code}: {text[:80]}")
                print(f"         {pdf_url}")
                break
    return result


def get_pdf_urls() -> dict[str, str]:
    """
    Возвращает словарь URL для скачивания PDF.
    Ссылки из FALLBACK_PDFS имеют наивысший приоритет.
    """
    discovered = discover_osjd_links()
    urls = dict(discovered)
    # Приоритет: FALLBACK_PDFS перезаписывает всё, что найдено на странице
    urls.update(FALLBACK_PDFS)

    print("\n" + "=" * 70)
    print("FINAL PDF SOURCES (after fallback override)")
    print("=" * 70)
    for code in sorted(ACTIVE_COUNTRIES):
        if code in urls:
            print(f"  {code}: {urls[code]}")
        else:
            print(f"  {code}: NO SOURCE")

    return urls


# ============================================================
# PARSERS (WORDS, BLOCKS, DICT)
# ============================================================

def words_to_lines(words: list[tuple]) -> list[dict[str, Any]]:
    if not words:
        return []
    groups = []
    sorted_words = sorted(words, key=lambda item: (round(float(item[1]), 1), float(item[0])))
    for word in sorted_words:
        x0, y0, x1, y1, text = word[:5]
        text = normalize_space(str(text))
        if not text:
            continue
        placed = False
        for group in groups[-30:]:
            if abs(float(y0) - group["avg_y"]) <= 5.0:
                group["words"].append(word)
                group["avg_y"] = sum(float(w[1]) for w in group["words"]) / len(group["words"])
                placed = True
                break
        if not placed:
            groups.append({"avg_y": float(y0), "words": [word]})
    lines = []
    for group in groups:
        row = sorted(group["words"], key=lambda item: float(item[0]))
        lines.append({"words": row, "text": normalize_space(" ".join(str(item[4]) for item in row))})
    return lines


def extract_latin_name(right: str) -> str:
    right = normalize_space(right)
    if not right:
        return ""
    right = re.split(r"(?<!\d)\d{4}(?!\d)", right, maxsplit=1)[0]
    right = re.split(r"(?<!\S)\d+\s*[A-Za-zА-Яа-яЁё]?(?:\s*[,;./]\s*\d+\s*[A-Za-zА-Яа-яЁё]?)*", right, maxsplit=1)[0]
    right = re.sub(r"\s*\(?\s*(?:ТП|TП|TP)\s*\)?\s*$", "", right, flags=re.IGNORECASE)
    return clean_station_name(right)


def make_record(country_code, code, ru, lat, operations="", border_code=""):
    ru = clean_station_name(ru)
    lat = clean_station_name(lat)
    code = normalize_code(code) or ""
    if not code or not valid_name(ru) or not valid_name(lat):
        return None

    rec = {"name": ru, "code": code, "country": COUNTRIES[country_code], "country_code": country_code, "latin_name": lat}
    if operations: rec["operations"] = normalize_space(operations)
    if border_code and normalize_code(border_code): rec["border_code"] = normalize_code(border_code)
    return rec


def parse_words_page(words: list[tuple], country_code: str) -> list[dict]:
    records = []
    lines = words_to_lines(words)
    
    for line in lines:
        row = line["words"]
        for index, word in enumerate(row):
            raw = str(word[4])
            code = normalize_code(raw)
            skip = 1
            
            if not code and index + 1 < len(row):
                code = normalize_code(raw + str(row[index + 1][4]))
                skip = 2
                
            if not code:
                continue

            left = clean_station_name(" ".join(str(w[4]) for w in row[:index]))
            right = clean_station_name(" ".join(str(w[4]) for w in row[index + skip:]))
            
            if not left or not right:
                continue

            latin = extract_latin_name(right)
            if not strict_station_name(left, "ru") or not strict_station_name(latin, "latin"):
                continue

            border = re.findall(r"(?<!\d)\d{4}(?!\d)", right)
            rec = make_record(country_code, code, left, latin, border_code=border[0] if border else "")
            if rec:
                records.append(rec)
    return records


def parse_blocks_page(blocks: list[tuple], country_code: str) -> list[dict]:
    records = []
    code_items = []
    for block in blocks:
        if len(block) < 5: continue
        x0, y0, x1, y1, text = block[:5]
        text = normalize_space(str(text))
        for match in re.finditer(r"(?<!\d)\d{6}(?!\d)", text):
            code_items.append({"code": match.group(0), "x0": float(x0), "y0": float(y0), "x1": float(x1), "text": text})

    for item in code_items:
        same_line = []
        for block in blocks:
            if len(block) < 5: continue
            x0, y0, x1, y1, text = block[:5]
            if abs(float(y0) - item["y0"]) <= 2.5:
                same_line.append({"x0": float(x0), "x1": float(x1), "text": normalize_space(str(text))})

        left = [b for b in same_line if b["x1"] <= item["x0"] and strict_station_name(b["text"], "ru")]
        right = [b for b in same_line if b["x0"] >= item["x1"] and strict_station_name(extract_latin_name(b["text"]), "latin")]

        if not left or not right: continue
        left.sort(key=lambda b: item["x0"] - b["x1"])
        right.sort(key=lambda b: b["x0"] - item["x1"])
        
        rec = make_record(country_code, item["code"], left[0]["text"], extract_latin_name(right[0]["text"]))
        if rec: records.append(rec)
    return records


def parse_dict_page(dictionary: dict, country_code: str) -> list[dict]:
    records = []
    text = normalize_space(" ".join(span["text"] for block in dictionary.get("blocks", []) if block.get("type") == 0 for line in block.get("lines", []) for span in line.get("spans", [])))
    if not text: return records

    for match in re.finditer(r"(?<!\d)(\d{6})(?!\d)", text):
        code = match.group(1)
        before = normalize_space(text[max(0, match.start() - 150):match.start()])
        after = normalize_space(text[match.end():match.end() + 150])
        
        ru = clean_station_name(" ".join(before.split()[-10:]))
        lat = extract_latin_name(" ".join(after.split()[:10]))
        
        if not valid_name(ru) or not valid_name(lat): continue
        rec = make_record(country_code, code, ru, lat)
        if rec: records.append(rec)
    return records


# ============================================================
# MAIN EXTRACTION & VALIDATION
# ============================================================

def parse_pdf(pdf_bytes: bytes, country_code: str) -> list[dict]:
    print(f"\nPARSING COUNTRY: {country_code} {COUNTRIES[country_code]}")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    methods = {"words": [], "blocks": [], "dict": []}
    for page in doc:
        methods["words"].append(page.get_text("words"))
        methods["blocks"].append(page.get_text("blocks"))
        methods["dict"].append(page.get_text("dict"))
    doc.close()

    w_recs, b_recs, d_recs = [], [], []
    for p in methods["words"]:
        if p: w_recs.extend(parse_words_page(p, country_code))
    for p in methods["blocks"]:
        if p: b_recs.extend(parse_blocks_page(p, country_code))
    for p in methods["dict"]:
        if p: d_recs.extend(parse_dict_page(p, country_code))

    print(f"  WORD: {len(w_recs)}, BLOCK: {len(b_recs)}, DICT: {len(d_recs)}")

    final = []
    seen = set()
    for source in (w_recs, b_recs, d_recs):
        for r in source:
            if r["code"] not in seen:
                final.append(r)
                seen.add(r["code"])
                
    print("  FINAL PARSED:", len(final))
    return final


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


def validate_all(stations: list[dict]):
    counters = Counter(s.get("country_code") for s in stations)
    missing = [c for c in ACTIVE_COUNTRIES if counters.get(c, 0) == 0]
    
    if missing:
        print("MISSING COUNTRIES:", missing)
        raise RuntimeError("Отсутствуют некоторые страны!")

    invalid = [s for s in stations if not re.fullmatch(r"\d{6}", str(s.get("code", "")))]
    if invalid:
        raise RuntimeError(f"Найдено {len(invalid)} некорректных кодов!")


# ============================================================
# MAIN
# ============================================================

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
            raise RuntimeError(f"Нет PDF для {code}")

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
            if not old_count:
                raise RuntimeError(f"Фатальная ошибка: нет данных для {code}")

    # Объединение
    new_countries = {r["country_code"] for r in all_new}
    merged = [r for r in existing if r.get("country_code") not in new_countries]
    merged.extend(all_new)
    
    validate_all(merged)
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        
    print(f"\nSUCCESS! Всего записей: {len(merged)}")


if __name__ == "__main__":
    main()
