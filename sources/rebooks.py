"""מתאם לסיפור חוזר (rebooks.org.il).

אין לאתר קובץ קטלוג, אז מחפשים כל שורה ברשימה בנפרד דרך דף החיפוש:
- שורה עם שם ספר: חיפוש לפי שם ספר, ואם יש מחבר גם חיפוש לפי מחבר
  (כך נתפסים גם ספרים שהשם שלהם כתוב אחרת, למשל בכתיב חסר).
- שורה עם מחבר בלבד: חיפוש לפי מחבר.
ההתאמה עצמה נעשית אחר כך ב-matcher, כמו בכל מקור.

רק עותקים במלאי מוחזרים: האתר מציג בחיפוש גם ספרים שאזלו.
כדי לא להעמיס על האתר, המקור נבדק רק פעמיים ביום (ראו RUN_HOURS_UTC),
עם המתנה בין בקשות. בהרצה ידנית (Run workflow) הוא נבדק תמיד.
"""

import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from . import SkipRun

NAME = "rebooks"
DISPLAY_NAME = "סיפור חוזר"
NEEDS_WISHLIST = True
LOCATION = "אחד הסניפים (משלוח או איסוף מהסניף)"
SEARCH_URL = "https://rebooks.org.il/"

# הריצות המתוזמנות הן כל 3 שעות. חלון של 3 שעות סביב כל מועד
# מבטיח ריצה אחת בבוקר ואחת אחר הצהריים גם אם GitHub מתעכב.
RUN_HOURS_UTC = {6, 7, 8, 15, 16, 17}   # כ-08:00-11:00 ו-17:00-20:00 שעון ישראל
DELAY_SECONDS = 3
MAX_PAGES = 3

HEADERS = {
    "User-Agent": "book-hunter/1.0 (personal wishlist checker, twice a day)",
    "Accept": "text/html",
    "Accept-Language": "he,en;q=0.8",
}


def _should_run():
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return True
    if os.environ.get("REBOOKS_ALWAYS") == "1":
        return True
    return datetime.now(timezone.utc).hour in RUN_HOURS_UTC


def _text(el):
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def parse(html):
    """מוציא מדף תוצאות את העותקים שבמלאי. כל עותק מופיע בדף פעמיים, אז מסננים כפילויות."""
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for card in soup.select("div.wd-product[data-id]"):
        pid = card.get("data-id")
        classes = card.get("class", [])
        if pid in seen:
            continue
        seen.add(pid)
        if "instock" not in classes:
            continue
        link = card.select_one("h3.wd-entities-title a")
        if not link:
            continue
        price = _text(card.select_one("span.price bdi")).replace("₪", "").strip()
        items.append({
            "source": NAME,
            "source_name": DISPLAY_NAME,
            "id": pid,
            "title": _text(link),
            "author": ", ".join(_text(a) for a in card.select(".wd-product-brands-links a")),
            "price": price,
            "condition": _text(card.select_one(".publication")),  # הוצאה ושנה
            "location": LOCATION,
            "url": link.get("href", ""),
        })
    return items, seen


def _queries(wanted):
    title = (wanted.get("title") or "").strip()
    author = (wanted.get("author") or "").strip()
    if "," in author:  # "Pratchett, Terry" -> "Terry Pratchett"
        last, _, first = author.partition(",")
        author = f"{first.strip()} {last.strip()}"
    qs = []
    if title:
        qs.append((title, "name"))
    if author:
        qs.append((author, "author"))
    return qs


def _get(query, search_in, page):
    params = {"s": query, "post_type": "product", "dgwt_wcas": "1",
              "search_in": search_in, "orderby": "date"}
    if page > 1:
        params["paged"] = str(page)
    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch(wishlist):
    if not _should_run():
        raise SkipRun("checked only twice a day")

    found = {}
    done = set()
    first = True
    for wanted in wishlist:
        for query, search_in in _queries(wanted):
            if (query, search_in) in done:
                continue
            done.add((query, search_in))
            ids_so_far = set()
            for page in range(1, MAX_PAGES + 1):
                if not first:
                    time.sleep(DELAY_SECONDS)
                first = False
                try:
                    html = _get(query, search_in, page)
                except urllib.error.HTTPError as exc:
                    if page > 1 and exc.code == 404:   # אין עמוד נוסף
                        break
                    raise
                items, page_ids = parse(html)
                for it in items:
                    found[it["id"]] = it
                # עמוד ריק, עמוד חלקי, או עמוד שחוזר על תוצאות קודמות = אין עמודים נוספים
                if len(page_ids) < 12 or not (page_ids - ids_so_far):
                    break
                ids_so_far |= page_ids
    return list(found.values())
