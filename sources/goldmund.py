"""מתאם לגולדמונד ספרים (חיפה).

הקטלוג כולו נטען מקובץ JSON אחד, אז מורידים אותו פעם אחת בכל ריצה
ובודקים מולו את כל רשימת המבוקשים.

מבנה רשומה בקובץ:
    {"title": "...", "author": "...", "price": "25.4", "condition": "טוב"}

אין בקובץ שדה מלאי: ספר שמופיע בקטלוג נחשב זמין.
"""

import html
import json
import re
import time
import urllib.request

NAME = "goldmund"
DISPLAY_NAME = "גולדמונד ספרים (חיפה)"
CATALOG_URL = "https://files.goldmundbooks.com/catalog.json"
CATALOG_PAGE = "https://files.goldmundbooks.com/catalog_cart.html"
LOCATION = "חיפה, עקרון 6 (שוק תלפיות)"

_TAG_RE = re.compile(r"<[^>]*>")
_SPACE_RE = re.compile(r"\s+")


def _clean(text):
    """מסיר תגיות HTML ורווחים כפולים (יש כאלה בחלק מהכותרות)."""
    if not text:
        return ""
    text = html.unescape(str(text))
    text = _TAG_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def parse(records):
    """ממיר את רשומות הקטלוג למבנה האחיד של המערכת."""
    items = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        title = _clean(rec.get("title"))
        if not title:
            continue
        items.append({
            "source": NAME,
            "source_name": DISPLAY_NAME,
            "title": title,
            "author": _clean(rec.get("author")),
            "price": str(rec.get("price") or "").strip(),
            "condition": _clean(rec.get("condition")),
            "location": LOCATION,
            "url": CATALOG_PAGE,
        })
    return items


def fetch(timeout=30):
    """מוריד את הקטלוג ומחזיר רשימת פריטים. זורק חריגה אם משהו השתבש."""
    # אותו פרמטר נגד מטמון שהאתר עצמו מוסיף
    url = f"{CATALOG_URL}?{int(time.time() * 1000)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "book-hunter/1.0 (personal wishlist checker, runs every few hours)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("catalog.json is not a list - the site format may have changed")
    items = parse(data)
    # הגנה: קטלוג ריק או קטן מדי כנראה אומר תקלה ולא שכל הספרים נמכרו
    if len(items) < 50:
        raise ValueError(f"catalog looks too small ({len(items)} items) - skipping this run")
    return items
