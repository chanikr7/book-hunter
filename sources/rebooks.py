"""מתאם לסיפור חוזר (rebooks.org.il).

אין לאתר קובץ קטלוג, אז מחפשים כל שורה ברשימה בנפרד דרך דף החיפוש:
- שורה עם שם ספר: חיפוש לפי שם ספר (עמוד אחד, החדשים ראשונים).
  רק אם בתוצאות אין אף עותק של הספר, גם זמין וגם שאזל, מחפשים גם לפי
  המחבר. כך נתפסים ספרים שהשם שלהם כתוב אחרת, בלי להכפיל את מספר הבקשות.
- שורה עם מחבר בלבד: חיפוש לפי מחבר (עד MAX_PAGES עמודים).
ההתאמה הסופית נעשית אחר כך ב-hunter, כמו בכל מקור.

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

from matcher import match
from . import SkipRun

NAME = "rebooks"
DISPLAY_NAME = "סיפור חוזר"
NEEDS_WISHLIST = True
LOCATION = "אחד הסניפים (משלוח או איסוף מהסניף)"
SEARCH_URL = "https://rebooks.org.il/"

# הריצות המתוזמנות הן כל 3 שעות. חלון של 3 שעות סביב כל מועד
# מבטיח ריצה אחת בבוקר ואחת אחר הצהריים גם אם GitHub מתעכב.
RUN_HOURS_UTC = {6, 7, 8, 15, 16, 17}   # כ-08:00-11:00 ו-17:00-20:00 שעון ישראל
DELAY_SECONDS = 2
MAX_PAGES = 3                 # רק לשורות של מחבר בלבד
REQUEST_TIMEOUT = 20
TIME_BUDGET_SECONDS = 20 * 60  # אם האתר איטי במיוחד, עוצרים ושומרים את המצב הקודם

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


def _log(msg):
    print(f"[{NAME}] {msg}", flush=True)


def _text(el):
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def parse(html):
    """כל העותקים בדף (זמינים ושאזלו), בלי הכפילויות: כל עותק מופיע בדף פעמיים."""
    soup = BeautifulSoup(html, "html.parser")
    cards, seen = [], set()
    for card in soup.select("div.wd-product[data-id]"):
        pid = card.get("data-id")
        if pid in seen:
            continue
        seen.add(pid)
        link = card.select_one("h3.wd-entities-title a")
        if not link:
            continue
        price = _text(card.select_one("span.price bdi")).replace("₪", "").strip()
        cards.append({
            "source": NAME,
            "source_name": DISPLAY_NAME,
            "id": pid,
            "title": _text(link),
            "author": ", ".join(_text(a) for a in card.select(".wd-product-brands-links a")),
            "price": price,
            "condition": _text(card.select_one(".publication")),  # הוצאה ושנה
            "location": LOCATION,
            "url": link.get("href", ""),
            "in_stock": "instock" in card.get("class", []),
        })
    return cards


def _get(query, search_in, page):
    params = {"s": query, "post_type": "product", "dgwt_wcas": "1",
              "search_in": search_in, "orderby": "date"}
    if page > 1:
        params["paged"] = str(page)
    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _author_query(author):
    if "," in author:  # "Pratchett, Terry" -> "Terry Pratchett"
        last, _, first = author.partition(",")
        author = f"{first.strip()} {last.strip()}"
    return author.strip()


class _Searcher:
    def __init__(self):
        self.started = time.monotonic()
        self.requests = 0
        self.cache = {}

    def search(self, query, search_in, max_pages):
        key = (query, search_in)
        if key in self.cache:
            return self.cache[key]
        cards, ids = [], set()
        for page in range(1, max_pages + 1):
            if time.monotonic() - self.started > TIME_BUDGET_SECONDS:
                raise TimeoutError(f"stopped after {self.requests} requests - site too slow")
            if self.requests:
                time.sleep(DELAY_SECONDS)
            self.requests += 1
            t0 = time.monotonic()
            try:
                html = _get(query, search_in, page)
            except urllib.error.HTTPError as exc:
                if page > 1 and exc.code == 404:   # אין עמוד נוסף
                    break
                raise
            page_cards = parse(html)
            new = [c for c in page_cards if c["id"] not in ids]
            cards += new
            ids |= {c["id"] for c in new}
            _log(f"'{query}' ({search_in}, page {page}): {len(page_cards)} results, "
                 f"{sum(c['in_stock'] for c in page_cards)} in stock, {time.monotonic() - t0:.1f}s")
            # עמוד חלקי, או עמוד שחוזר על תוצאות קודמות = אין עמודים נוספים
            if len(page_cards) < 12 or not new:
                break
        self.cache[key] = cards
        return cards


def fetch(wishlist):
    if not _should_run():
        raise SkipRun("checked only twice a day")

    s = _Searcher()
    found = {}
    for wanted in wishlist:
        title = (wanted.get("title") or "").strip()
        author = _author_query(wanted.get("author") or "")
        if title:
            cards = s.search(title, "name", 1)
            # בודקים אם הספר מופיע בתוצאות (גם אם אזל), בלי להתחשב במחיר המקסימלי
            loose = dict(wanted, max_price="")
            if author and not any(match(loose, c) for c in cards):
                cards = cards + s.search(author, "author", 1)
        else:
            cards = s.search(author, "author", MAX_PAGES)
        for c in cards:
            if c["in_stock"]:
                found[c["id"]] = c

    _log(f"done: {s.requests} requests in {time.monotonic() - s.started:.0f}s")
    return list(found.values())
