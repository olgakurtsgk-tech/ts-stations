#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""
OSJD railway freight stations parser.

Получает PDF-перечни грузовых станций ОСЖД,
извлекает станции несколькими способами и обновляет
data/stations.json только после успешной проверки
всех 25 стран.

Исключены из проекта:
KR — Республика Корея
RO — Румыния
LA — Лаос
"""

from **future** import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin

import fitz
import requests
from bs4 import BeautifulSoup

# ============================================================

# CONFIG

# ============================================================

BASE_DIR = Path(**file**).resolve().parent.parent
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

# 25 COUNTRIES

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
"LV": "Латвия",
"LT": "Литва",
"MD": "Молдова",
"MN": "Монголия",
"PL": "Польша",
"RU": "Россия",
"SK": "Словакия",
"TJ": "Таджикистан",
"TM": "Туркменистан",
"UZ": "Узбекистан",
"UA": "Украина",
"CZ": "Чехия",
"EE": "Эстония",
}

# ============================================================

# FALLBACK PDF URLS

# ============================================================

FALLBACK_PDFS = {
"IR": "https://osjd.org/api/media/resources/9608?action=download",
"CN": "https://osjd.org/api/media/resources/1537?action=download",
"CZ": "https://osjd.org/api/media/resources/3904?action=download",
"EE": "https://osjd.org/api/media/resources/1671839?action=download",
}

# ============================================================

# NAME MATCHING

# ============================================================

COUNTRY_ALIASES = {
"AZ": [
"азербайджан",
"азербайджанских железных дорог",
],
"AF": [
"афганистан",
"железной дороги исламской республики афганистан",
],
"BY": [
"беларус",
"белорусской железной дороги",
],
"BG": [
"болгар",
"болгарских государственных железных дорог",
],
"HU": [
"венгр",
"венгерских государственных железных дорог",
],
"VN": [
"вьетнам",
"вьетнамской железной дороги",
],
"GE": [
"груз",
"грузинской железной дороги",
],
"IR": [
"иран",
"железной дороги исламской республики иран",
],
"KZ": [
"казахстан",
"железных дорог казахстан",
],
"CN": [
"китай",
"китайских железных дорог",
],
"KP": [
"кндр",
"корейской народно-демократической республики",
],
"KG": [
"кыргыз",
"кыргызской железной дороги",
],
"LV": [
"латв",
"латвийской железной дороги",
],
"LT": [
"литв",
"литовских железных дорог",
],
"MD": [
"молдов",
"железной дороги молдовы",
],
"MN": [
"монгол",
"улан-баторской железной дороги",
],
"PL": [
"поль",
"польских государственных железных дорог",
],
"RU": [
"россий",
"российских железных дорог",
],
"SK": [
"словац",
"словацкой республики",
],
"TJ": [
"таджик",
"таджикской железной дороги",
],
"TM": [
"туркмен",
"туркмендемиреллары",
],
"UZ": [
"узбек",
"узбекистан",
"узбекских железных дорог",
],
"UA": [
"украин",
"украинской железной дороги",
],
"CZ": [
"чеш",
"чешских железных дорог",
],
"EE": [
"эстон",
"эстонской железной дороги",
],
}

# ============================================================

# HELPERS

# ============================================================

def normalize_space(value: str) -> str:
if not value:
return ""

```
value = value.replace("\xa0", " ")
value = value.replace("\u200b", "")
value = re.sub(r"\s+", " ", value)

return value.strip()
```

def normalize_code(value: str) -> str | None:
"""
Извлекает ровно 6 цифр.

```
Исправляет варианты:
123 456
123-456
123.456
"""

if not value:
    return None

value = str(value).strip()

if re.fullmatch(r"\d{6}", value):
    return value

digits = re.sub(r"\D", "", value)

if len(digits) == 6:
    return digits

return None
```

def is_noise_name(value: str) -> bool:
if not value:
return True

```
text = normalize_space(value)

if len(text) < 2:
    return True

lower = text.lower()

bad_fragments = [
    "наименование станции",
    "код станции",
    "код погранич",
    "производимые коммерческие",
    "операции",
    "страница",
    "содержание",
    "раздел ",
    "перечень грузовых станций",
    "железной дороги",
    "железных дорог",
    "код ",
    "наименование",
]

if any(fragment in lower for fragment in bad_fragments):
    return True

if re.fullmatch(r"[\d\s.,;:/()\-]+", text):
    return True

return False
```

def clean_station_name(value: str) -> str:
value = normalize_space(value)

```
value = re.sub(r"^[|;:,]+", "", value)
value = re.sub(r"[|;:,]+$", "", value)

value = normalize_space(value)

return value
```

def looks_like_operations(value: str) -> bool:
if not value:
return False

```
text = normalize_space(value)

if re.fullmatch(
    r"[\d,\s./()«»\"'А-Яа-яA-Za-z№#*КкНн\-]+",
    text,
):
    digits = re.findall(r"\d+", text)

    if digits:
        return True

return False
```

def valid_name(value: str) -> bool:
value = clean_station_name(value)

```
if is_noise_name(value):
    return False

if len(value) > 150:
    return False

if not re.search(r"[A-Za-zА-Яа-яЁё]", value):
    return False

return True
```

def score_name(value: str) -> int:
value = clean_station_name(value)

```
if not valid_name(value):
    return -100

score = 0

if 2 <= len(value) <= 80:
    score += 10

if re.search(r"[А-Яа-яЁё]", value):
    score += 5

if re.search(r"[A-Za-z]", value):
    score += 3

if "(" in value or ")" in value:
    score += 1

return score
```

# ============================================================

# OSJD URL NORMALIZATION

# ============================================================

def normalize_osjd_pdf_url(url: str) -> str:
"""
Преобразует URL просмотрщика ОСЖД
в прямой URL media resource.
"""

```
if not url:
    return ""

url = unquote(str(url).strip())
url = url.split("#", 1)[0]

match = re.search(
    r"(?:[?&])file=([^#]+)",
    url,
    flags=re.IGNORECASE,
)

if match:
    file_part = unquote(match.group(1))

    if file_part.startswith(("http://", "https://")):
        url = file_part

    elif file_part.startswith("/"):
        url = urljoin(
            "https://osjd.org",
            file_part,
        )

    else:
        url = urljoin(
            "https://osjd.org/",
            file_part,
        )

    url = url.split("#", 1)[0]

if
```
