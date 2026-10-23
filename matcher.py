"""התאמה בין ספר מבוקש לפריט בקטלוג.

כללים:
- משווים את "ליבת" הכותרת (בלי כותרת משנה אחרי נקודתיים, מקף או סוגריים,
  ובלי The/A/An בהתחלה), כך ש-"Dune: Deluxe Edition" תואם ל-"Dune"
  אבל "Dune Messiah" לא.
- אם צוין מחבר, שם המשפחה שלו חייב להופיע בשם המחבר בקטלוג
  (סדר השמות לא משנה: "Coben, Harlan" תואם ל-"Harlan Coben").
- אם בקטלוג אין מחבר, מקבלים רק התאמת כותרת מלאה ומסמנים "לא ודאי".
"""

import re
import unicodedata

from rapidfuzz import fuzz

TITLE_THRESHOLD = 90      # ציון מינימלי להתאמת ליבת הכותרת (0-100)
AUTHOR_THRESHOLD = 85     # ציון מינימלי להתאמת שם משפחה

_ARTICLES = ("the ", "a ", "an ")
_SUBTITLE_RE = re.compile(r"\s*(?::|\s-\s|\s–\s|\(|\[).*$")
_NON_WORD_RE = re.compile(r"[^\w\s]")
_SPACE_RE = re.compile(r"\s+")


def normalize(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("&", " and ")
    text = _NON_WORD_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def title_core(text):
    """ליבת הכותרת: בלי כותרת משנה ובלי מילית יידוע בהתחלה."""
    if not text:
        return ""
    core = _SUBTITLE_RE.sub("", text.strip()) or text
    core = normalize(core)
    for art in _ARTICLES:
        if core.startswith(art):
            core = core[len(art):]
            break
    return core


def _last_name(author):
    """שם המשפחה של המחבר המבוקש. תומך גם ב-"Martin, George"."""
    if "," in author:
        author = author.split(",")[0]
    tokens = normalize(author).split()
    return tokens[-1] if tokens else ""


def author_matches(wanted_author, item_author):
    last = _last_name(wanted_author)
    if not last:
        return True
    tokens = normalize(item_author).split()
    return any(fuzz.ratio(last, tok) >= AUTHOR_THRESHOLD for tok in tokens)

def full_author_matches(wanted_author, item_author):
    """כל חלקי השם צריכים להופיע (כדי ש-George R.R. Martin לא יתפוס את Steve Martin)."""
    if "," in wanted_author:
        last, _, first = wanted_author.partition(",")
        wanted_author = f"{first} {last}"
    wanted_tokens = [t for t in normalize(wanted_author).split() if len(t) > 1]
    item_tokens = normalize(item_author).split()
    if not wanted_tokens or not item_tokens:
        return False
    for wt in wanted_tokens:
        if not any(fuzz.ratio(wt, it) >= AUTHOR_THRESHOLD or (len(it) == 1 and it == wt[0])
                   for it in item_tokens):
            return False
    return True
def _price_value(price):
    try:
        return float(price)
    except (TypeError, ValueError):
        return None


def match(wanted, item):
    """מחזיר None אם אין התאמה, או מילון עם ציון ודגל ודאות."""
    w_core = title_core(wanted["title"])
    i_core = title_core(item["title"])
    if not w_core or not i_core:
        return None

    score = fuzz.ratio(w_core, i_core)
    if score < TITLE_THRESHOLD:
        return None

    certain = True
    wanted_author = (wanted.get("author") or "").strip()
    if wanted_author:
        if item.get("author"):
            if not author_matches(wanted_author, item["author"]):
                return None
        else:
            # אין מחבר בקטלוג: דורשים כותרת זהה ומסמנים כלא ודאי
            if score < 100:
                return None
            certain = False

    max_price = _price_value(wanted.get("max_price"))
    item_price = _price_value(item.get("price"))
    if max_price is not None and item_price is not None and item_price > max_price:
        return None

    return {"score": score, "certain": certain}
