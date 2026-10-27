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
    "FI": "Финляндия",
}

EXCLUDED_COUNTRIES = {"IR", "CN", "CZ", "KR", "RO", "LA"}
ACTIVE_COUNTRIES = {code: name for code, name in COUNTRIES.items() if code not in EXCLUDED_COUNTRIES}

# ============================================================
# РУЧНЫЕ ДОПОЛНЕНИЯ И ИСПРАВЛЕНИЯ
# ============================================================
MANUAL_ADDITIONS = [
    # --- ВАШИ ПРОВЕРЕННЫЕ СТАНЦИИ (Внесены вручную) ---
    {"name": "Лахти", "code": "001000", "country": "Финляндия", "country_code": "FI", "latin_name": "Lahti"},
    {"name": "Пори", "code": "002200", "country": "Финляндия", "country_code": "FI", "latin_name": "Pori"},
    {"name": "Алхолма", "code": "003080", "country": "Финляндия", "country_code": "FI", "latin_name": "Alholma"},
    {"name": "Контиомяки", "code": "003900", "country": "Финляндия", "country_code": "FI", "latin_name": "Kontiomaki"},
    {"name": "Лаппеенранта", "code": "004950", "country": "Финляндия", "country_code": "FI", "latin_name": "Lappeenranta"},
    {"name": "Еруу", "code": "010322", "country": "Монголия", "country_code": "MN", "latin_name": "Eruu"},
    {"name": "Толгойт", "code": "010769", "country": "Монголия", "country_code": "MN", "latin_name": "Tolgoit"},
    {"name": "Улаанбаатар", "code": "010843", "country": "Монголия", "country_code": "MN", "latin_name": "Ulaanbaatar"},
    {"name": "Хутул", "code": "010934", "country": "Монголия", "country_code": "MN", "latin_name": "Khutul"},
    {"name": "Шарын гол", "code": "011163", "country": "Монголия", "country_code": "MN", "latin_name": "Sharyngol"},
    {"name": "Эрдэнэт", "code": "011254", "country": "Монголия", "country_code": "MN", "latin_name": "Erdenet"},
    {"name": "Олон-Овоо", "code": "011346", "country": "Монголия", "country_code": "MN", "latin_name": "Olon-Ovoo"},
    {"name": "Санкт-Петербург-Сорт.-Московский", "code": "030006", "country": "Россия", "country_code": "RU", "latin_name": "Sankt-Peterburg-Sort.-Moskovskiy"},
    {"name": "Нелазское", "code": "046201", "country": "Россия", "country_code": "RU", "latin_name": "Nelazskoe"},
    {"name": "Тапа", "code": "080005", "country": "Эстония", "country_code": "EE", "latin_name": "Tapa"},
    {"name": "Маарду (эксп. через порт Мийдуранна)", "code": "081703", "country": "Эстония", "country_code": "EE", "latin_name": "Maardu (eksp. cherez port Miyduranna)"},
    {"name": "Аэгвийду", "code": "082602", "country": "Эстония", "country_code": "EE", "latin_name": "Aegviidu"},
    {"name": "Вайвара (эксп.)", "code": "083501", "country": "Эстония", "country_code": "EE", "latin_name": "Vaivara (eksp.)"},
    {"name": "Нарва", "code": "084006", "country": "Эстония", "country_code": "EE", "latin_name": "Narva"},
    {"name": "Йыгева", "code": "084400", "country": "Эстония", "country_code": "EE", "latin_name": "Jogeva"},
    {"name": "Кяркна", "code": "084608", "country": "Эстония", "country_code": "EE", "latin_name": "Karkna"},
    {"name": "Тарту", "code": "084805", "country": "Эстония", "country_code": "EE", "latin_name": "Tartu"},
    {"name": "Реола", "code": "084909", "country": "Эстония", "country_code": "EE", "latin_name": "Reola"},
    {"name": "Пиуза", "code": "085403", "country": "Эстония", "country_code": "EE", "latin_name": "Piusa"},
    {"name": "Лийва", "code": "088308", "country": "Эстония", "country_code": "EE", "latin_name": "Liiva"},
    {"name": "Рапла", "code": "088505", "country": "Эстония", "country_code": "EE", "latin_name": "Rapla"},
    {"name": "Тюри", "code": "088702", "country": "Эстония", "country_code": "EE", "latin_name": "Turi"},
    {"name": "Пярну", "code": "089103", "country": "Эстония", "country_code": "EE", "latin_name": "Parnu"},
    {"name": "Земитаны (3 км Рига-Краста)", "code": "094900", "country": "Латвия", "country_code": "LV", "latin_name": "Zemitany (3 km Riga-Krasta)"},
    {"name": "Мозырь", "code": "151605", "country": "Беларусь", "country_code": "BY", "latin_name": "Mozyr"},
    {"name": "Белово", "code": "862305", "country": "Россия", "country_code": "RU", "latin_name": "Belovo"},
    {"name": "Люблино-Сортировочное", "code": "190008", "country": "Россия", "country_code": "RU", "latin_name": "Lyublino-Sortirovochnoe"},
    {"name": "Нижний Новгород-Сортировочный", "code": "260003", "country": "Россия", "country_code": "RU", "latin_name": "Nizhniy Novgorod-Sortirovochnyy"},
    {"name": "Никольская Слободка", "code": "320702", "country": "Украина", "country_code": "UA", "latin_name": "Nikolskaya Slobodka"},
    {"name": "Васильков-Центр", "code": "321300", "country": "Украина", "country_code": "UA", "latin_name": "Vasilkov-Tsentr"},
    {"name": "Середина-Буда", "code": "328808", "country": "Украина", "country_code": "UA", "latin_name": "Seredina-Buda"},
    {"name": "Звягель I", "code": "348002", "country": "Украина", "country_code": "UA", "latin_name": "Zvyagel I"},
    {"name": "ШЕПТИЦКИЙ", "code": "371305", "country": "Украина", "country_code": "UA", "latin_name": "Sheptitskiy"},
    {"name": "ГОЛТА", "code": "407605", "country": "Украина", "country_code": "UA", "latin_name": "Golta"},
    {"name": "Шаблино", "code": "413707", "country": "Украина", "country_code": "UA", "latin_name": "Shablino"},
    {"name": "ВИТОВСКАЯ", "code": "417503", "country": "Украина", "country_code": "UA", "latin_name": "Vitovskaya"},
    {"name": "Чорный", "code": "429106", "country": "Украина", "country_code": "UA", "latin_name": "Chornyy"},
    {"name": "Берестин", "code": "441606", "country": "Украина", "country_code": "UA", "latin_name": "Berestin"},
    {"name": "Новое (рзд)", "code": "442647", "country": "Украина", "country_code": "UA", "latin_name": "Novoe (rzd)"},
    {"name": "Лимановка", "code": "442904", "country": "Украина", "country_code": "UA", "latin_name": "Limanovka"},
    {"name": "ЗЛАТОПИЛЬ", "code": "443300", "country": "Украина", "country_code": "UA", "latin_name": "Zlatopil"},
    {"name": "ПРОВИДНА", "code": "451701", "country": "Украина", "country_code": "UA", "latin_name": "Providna"},
    {"name": "САМАР-ДНЕПРОВСКИЙ", "code": "452009", "country": "Украина", "country_code": "UA", "latin_name": "Samar-Dneprovskiy"},
    {"name": "ЯВОРНИЦКОЕ", "code": "453406", "country": "Украина", "country_code": "UA", "latin_name": "Yavornitskoe"},
    {"name": "КАРАЧУНЫ", "code": "457500", "country": "Украина", "country_code": "UA", "latin_name": "Karachuny"},
    {"name": "Челюскин", "code": "821409", "country": "Россия", "country_code": "RU", "latin_name": "Chelyuskin"},
    {"name": "НЕЗАЛЕЖНА", "code": "466904", "country": "Украина", "country_code": "UA", "latin_name": "Nezalezhna"},
    {"name": "Кировская", "code": "869003", "country": "Россия", "country_code": "RU", "latin_name": "Kirovskaya"},
    {"name": "Краснофлотская", "code": "869107", "country": "Россия", "country_code": "RU", "latin_name": "Krasnoflotskaya"},
    {"name": "Красноперекопск", "code": "869501", "country": "Россия", "country_code": "RU", "latin_name": "Krasnoperekopsk"},
    {"name": "Партизаны", "code": "821803", "country": "Россия", "country_code": "RU", "latin_name": "Partizany"},
    {"name": "БЛАГОДАТНОЕ", "code": "424244", "country": "Украина", "country_code": "UA", "latin_name": "Blagodatnoe"},
    {"name": "Кутейниково", "code": "901507", "country": "Россия", "country_code": "RU", "latin_name": "Kuteynikovo"},
    {"name": "Легендарная", "code": "958103", "country": "Россия", "country_code": "RU", "latin_name": "Legendarnaya"},

    # --- СТАРЫЕ РУЧНЫЕ ДОПОЛНЕНИЯ ---
    {"name": "Илецк I (эксп.)", "code": "666501", "country": "Казахстан", "country_code": "KZ", "latin_name": "Iletsk I"},
    {"name": "Ак-Булак", "code": "667307", "country": "Казахстан", "country_code": "KZ", "latin_name": "Ak-Bulak"},
    {"name": "Чашкан", "code": "667203", "country": "Казахстан", "country_code": "KZ", "latin_name": "Chashkan"},
    {"name": "Зыряновск", "code": "714601", "country": "Казахстан", "country_code": "KZ", "latin_name": "Zyryanovsk"},
    {"name": "Бопай", "code": "664506", "country": "Казахстан", "country_code": "KZ", "latin_name": "Bopay"},
    {"name": "Болашак", "code": "664600", "country": "Казахстан", "country_code": "KZ", "latin_name": "Bolashak"},
    {"name": "Арал Тенизи", "code": "670309", "country": "Казахстан", "country_code": "KZ", "latin_name": "Aral Tenizi"},
    {"name": "Актобе I", "code": "689503", "country": "Казахстан", "country_code": "KZ", "latin_name": "Aktobe I"},
    {"name": "Актобе II", "code": "689607", "country": "Казахстан", "country_code": "KZ", "latin_name": "Aktobe II"}, 
    {"name": "Достык", "code": "708403", "country": "Казахстан", "country_code": "KZ", "latin_name": "Dostyk"},
    {"name": "Достык (эксп.)", "code": "708507", "country": "Казахстан", "country_code": "KZ", "latin_name": "Dostyk (eksp.)"},
    {"name": "Достык (эксп. перев.)", "code": "710403", "country": "Казахстан", "country_code": "KZ", "latin_name": "Dostyk (eksp. perev.)"},
    {"name": "Достык (эксп. перев. авто)", "code": "710102", "country": "Казахстан", "country_code": "KZ", "latin_name": "Dostyk (eksp. perev. avto)"},
    {"name": "Карталы I", "code": "816203", "country": "Россия", "country_code": "RU", "latin_name": "Kartaly I"},
    {"name": "Карталы I (эксп.)", "code": "816504", "country": "Россия", "country_code": "RU", "latin_name": "Kartaly I (eksp.)"},
    {"name": "Орск", "code": "810006", "country": "Россия", "country_code": "RU", "latin_name": "Orsk"},
    {"name": "Соль-Илецк I", "code": "811905", "country": "Россия", "country_code": "RU", "latin_name": "Sol-Iletsk I"},
    {"name": "Суземка (эксп.)", "code": "204408", "country": "Россия", "country_code": "RU", "latin_name": "Suzemka (eksp.)"},
    {"name": "Астрахань I", "code": "616803", "country": "Россия", "country_code": "RU", "latin_name": "Astrakhan I"},
    {"name": "Астрахань II", "code": "616907", "country": "Россия", "country_code": "RU", "latin_name": "Astrakhan II"},
    {"name": "Смоленск", "code": "170108", "country": "Россия", "country_code": "RU", "latin_name": "Smolensk"},
    {"name": "Рославль I", "code": "177408", "country": "Россия", "country_code": "RU", "latin_name": "Roslavl I"},
    {"name": "Светлогорск-на-Березине", "code": "154209", "country": "Беларусь", "country_code": "BY", "latin_name": "Svetlogorsk-na-Berezine"},
    {"name": "Забайкальск", "code": "946801", "country": "Россия", "country_code": "RU", "latin_name": "Zabaykalsk"},
    {"name": "Наушки", "code": "937200", "country": "Россия", "country_code": "RU", "latin_name": "Naushki"},
    {"name": "Сухэ-Батор", "code": "010686", "country": "Монголия", "country_code": "MN", "latin_name": "Sukhbaatar"},
    {"name": "Салхит", "code": "010694", "country": "Монголия", "country_code": "MN", "latin_name": "Salkhit"},
    {"name": "Астара (эксп.)", "code": "554503", "country": "Азербайджан", "country_code": "AZ", "latin_name": "Astara (eksp.)"},
    {"name": "Гаджи Зайналабдин", "code": "546302", "country": "Азербайджан", "country_code": "AZ", "latin_name": "Hacı Zeynalabdin"},
    {"name": "Имишли", "code": "552207", "country": "Азербайджан", "country_code": "AZ", "latin_name": "Imishli"},
    {"name": "Автово (перев.)", "code": "035404", "country": "Россия", "country_code": "RU", "latin_name": "Avtovo (perev.)"},
    {"name": "Туапсе-Сортировочная (перев.)", "code": "533600", "country": "Россия", "country_code": "RU", "latin_name": "Tuapse-Sortirovochnaya (perev.)"},
    {"name": "Туапсе-Сортировочная (слив.)", "code": "533507", "country": "Россия", "country_code": "RU", "latin_name": "Tuapse-Sortirovochnaya (sliv.)"},
    {"name": "Поти", "code": "572107", "country": "Грузия", "country_code": "GE", "latin_name": "Poti"},
    {"name": "Поти (эксп.)", "code": "576201", "country": "Грузия", "country_code": "GE", "latin_name": "Poti (exp.)"},
    {"name": "Поти (порт, эксп.)", "code": "572200", "country": "Грузия", "country_code": "GE", "latin_name": "Poti (port, exp.)"},
    {"name": "Поти (паромная-эксп. на Керчь)", "code": "576409", "country": "Грузия", "country_code": "GE", "latin_name": "Poti (parom, exp., Kerch)"},
    {"name": "Поти (паром эксп. на Кавказ)", "code": "576108", "country": "Грузия", "country_code": "GE", "latin_name": "Poti (parom, exp., Kavkaz)"},
    {"name": "Поти (паром, эксп. на Констанцу)", "code": "572605", "country": "Грузия", "country_code": "GE", "latin_name": "Poti (parom, exp. Konstantsa)"},
    {"name": "Поти (паром, эксп. на Паромная)", "code": "572304", "country": "Грузия", "country_code": "GE", "latin_name": "Poti (parom, exp. Paromnaya)"},
    {"name": "Поти (паром, эксп. на Варну)", "code": "572003", "country": "Грузия", "country_code": "GE", "latin_name": "Poti (parom, exp.Varna)"},
    {"name": "Санкт-Петербург-Тов.-Московский", "code": "031808", "country": "Россия", "country_code": "RU", "latin_name": "Sankt-Peterburg-Tov.-Moskovskiy"},
    {"name": "Санкт-Петербург-Товарный-Витебский", "code": "033502", "country": "Россия", "country_code": "RU", "latin_name": "Sankt-Peterburg-Tovarnyy-Vitebskiy"},
    {"name": "Москва-Товарная-Курская", "code": "191509", "country": "Россия", "country_code": "RU", "latin_name": "Moskva-Tovarnaya-Kurskaya"},
    {"name": "Москва-Товарная-Павелецкая", "code": "193504", "country": "Россия", "country_code": "RU", "latin_name": "Moskva-Tovarnaya-Paveletskaya"},
    {"name": "Москва-Товарная-Рязанская", "code": "194009", "country": "Россия", "country_code": "RU", "latin_name": "Moskva-Tovarnaya-Ryazanskaya"},
    {"name": "Москва-Товарная-Смоленская", "code": "198207", "country": "Россия", "country_code": "RU", "latin_name": "Moskva-Tovarnaya-Smolenskaya"},
    {"name": "Москва-Товарная-Киевская", "code": "198002", "country": "Россия", "country_code": "RU", "latin_name": "Moskva-Tovarnaya-Kievskaya"},
    {"name": "Гатчина-Товарная-Балтийская", "code": "034007", "country": "Россия", "country_code": "RU", "latin_name": "Gatchina-Tovarnaya-Baltiyskaya"},
    
    # Кыргызстан
    {"name": "Ала-Тоо (эксп.)", "code": "719802", "country": "Кыргызстан", "country_code": "KG", "latin_name": "Ala-Too (eksp.)"},
]

# ============================================================
# FALLBACK PDF URLS
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

def fix_ocr_and_case(text: str) -> str:
    if not text:
        return ""
    
    # 1. Исправляем битые суффиксы (еКзр.}, эКзР, эксп.)*)
    text = re.sub(r'\(\s*[еeE]\s*[КкKk]\s*[з3]\s*[рpP]\s*\.?\s*[\)\}\*]?', '(эксп.)', text, flags=re.IGNORECASE)
    text = re.sub(r'\(\s*экз[рr]\.?\s*[\)\}\*]?', '(эксп.)', text, flags=re.IGNORECASE)
    
    # 2. Убираем мусорные символы в начале и конце строки
    text = re.sub(r'^[\*\]\}\)\|]+|[\*\]\}\)\|]+$', '', text).strip()
    
    # 3. Заменяем разные виды тире на стандартный дефис
    text = text.replace('—', '-').replace('–', '-').replace('−', '-')
    
    # 4. Умный регистр (Title Case), если вся строка капсом
    if text.isupper() and len(text) > 3:
        words = text.title().split()
        abbreviations = ["I", "II", "III", "IV", "Рзд", "Эксп", "Перев", "Сорт", "Бп", "Пп", "Оп"]
        for i, w in enumerate(words):
            if w.upper() in abbreviations or w.upper() in ["I", "II", "III", "IV"]:
                words[i] = w.upper()
        text = " ".join(words)

    return text

def clean_station_name(value: str) -> str:
    value = normalize_space(value)
    # Удаляем одиночные буквы/цифры в начале (артефакты PDF)
    value = re.sub(r'^[А-Яа-яЁёA-Za-z0-9]{1,2}\s+', '', value)
    value = re.sub(r"^[|;:,]+|[|;:,]+$", "", value).strip()
    # Применяем OCR-фиксы
    value = fix_ocr_and_case(value)
    return value

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
    if len(value.split()) > 10: return False 
    return True

def make_record(country_code, code, ru, lat, border_code=""):
    ru = clean_station_name(ru)
    lat = clean_station_name(lat)
    
    # Сначала удаляем старые/битые скобки, чтобы не было дублей
    ru = re.sub(r'\(\s*[^)]*\s*\)', '', ru).strip()
    
    ru_lower = ru.lower()
    lat_lower = lat.lower()
    
    # Синхронизируем суффиксы
    if "eksp" in lat_lower or "exp" in lat_lower:
        ru += " (эксп.)"
    elif "perev" in lat_lower or "perevoz" in lat_lower:
        ru += " (перев.)"
    elif "sliv" in lat_lower:
        ru += " (слив.)"
    elif "sort" in lat_lower:
        ru += " (сорт.)"
    elif "port" in lat_lower:
        ru += " (порт)"
    elif "parom" in lat_lower:
        ru += " (паром)"
        
    if not normalize_code(code) or not valid_name(ru) or not valid_name(lat): 
        return None
        
    rec = {
        "name": ru, 
        "code": normalize_code(code), 
        "country": COUNTRIES[country_code], 
        "country_code": country_code, 
        "latin_name": lat
    }
    if border_code and normalize_code(border_code): 
        rec["border_code"] = normalize_code(border_code)
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
    records = []
    lines = text.split('\n')
    buffer_name = ""

    for line in lines:
        line = normalize_space(line)
        if not line: continue

        matches = list(re.finditer(r'(?<!\d)(\d{6})(?!\d)', line))
        
        if not matches:
            if re.search(r'[А-Яа-яЁёA-Za-z]', line):
                if buffer_name and re.match(r'^[а-яё\(\,\.]', line):
                    buffer_name += " " + line
                else:
                    buffer_name = line
            continue

        for i, match in enumerate(matches):
            code = match.group(1)
            
            if i == 0:
                left = line[:match.start()].strip()
                if not left and buffer_name:
                    left = buffer_name
                elif left and buffer_name and re.match(r'^[а-яё\(\,\.]', left):
                    left = buffer_name + " " + left
                buffer_name = ""
            else:
                left = line[matches[i-1].end():match.start()].strip()

            if i + 1 < len(matches):
                right = line[match.end():matches[i+1].start()].strip()
            else:
                right = line[match.end():].strip()

            left = re.sub(r'.*\d{6}\s*', '', left)
            left = re.sub(r'\s+([,\.\)])', r'\1', left)
            left = re.sub(r'([\(])\s+', r'\1', left)
            left = re.sub(r'^[А-Яа-яЁёA-Za-z0-9]{1,2}\s+', '', left)

            lat_match = re.match(r'^([A-Za-z\s\-\(\)\.]+)', right)
            if lat_match:
                lat = lat_match.group(1).strip()
                if strict_station_name(left, "ru") and strict_station_name(lat, "latin"):
                    rec = make_record(country_code, code, left, lat)
                    if rec: records.append(rec)
    return records

def parse_words_page(words: list[tuple], country_code: str) -> list[dict]:
    records = []
    if not words: return records
    groups = []
    for word in sorted(words, key=lambda i: (round(float(i[1]), 1), float(i[0]))):
        placed = False
        for g in groups[-30:]:
            if abs(float(word[1]) - g["y"]) <= 5.0:
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
            
            left = clean_station_name(" ".join(str(x[4]) for x in row[:i]))
            right = " ".join(str(x[4]) for x in row[i+skip:])
            
            if left:
                ru_match = re.search(r'([А-Яа-яЁё][А-Яа-яЁё\s\-\(\)\.,]*)$', left)
                if ru_match:
                    left = ru_match.group(1).strip()
                    left = re.sub(r'\s+([,\.\)])', r'\1', left)
                    left = re.sub(r'([\(])\s+', r'\1', left)
                    left = re.sub(r'^[А-Яа-яЁёA-Za-z0-9]{1,2}\s+', '', left)
            
            lat_match = re.match(r'^([A-Za-z\s\-\(\)\.]+)', right)
            if not lat_match: continue
            
            lat = clean_station_name(lat_match.group(1))
            if strict_station_name(left, "ru") and strict_station_name(lat, "latin"):
                rec = make_record(country_code, code, left, lat)
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
                print(f"  ⚠ Фатальная ошибка: нет данных для {code}. Пропускаем.")

    new_countries = {r["country_code"] for r in all_new}
    merged = [r for r in existing if r.get("country_code") not in new_countries]
    merged.extend(all_new)
    
    manual_keys = {(m["country_code"], m["code"]) for m in MANUAL_ADDITIONS}
    merged = [r for r in merged if (r["country_code"], r["code"]) not in manual_keys]
    merged.extend(MANUAL_ADDITIONS)
    
    merged = sorted(merged, key=lambda r: (r["country_code"], r["name"]))
    
    counters = Counter(s.get("country_code") for s in merged)
    missing = [c for c in ACTIVE_COUNTRIES if counters.get(c, 0) == 0]
    if missing:
        print(f"\n⚠ ВНИМАНИЕ: Не удалось спарсить данные для стран: {missing}.")
        print("Скрипт сохранит всё остальное. (Возможно, для этих стран нет PDF или он в виде картинки).")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        
    print(f"\nSUCCESS! Всего записей в базе: {len(merged)}")

if __name__ == "__main__":
    main()
