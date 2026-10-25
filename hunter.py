"""book-hunter: בודק את רשימת המבוקשים מול חנויות יד שנייה ופותח Issue ב-GitHub על עותקים חדשים.

הרצה:
    python hunter.py                 ריצה רגילה
    python hunter.py --dry-run       בלי לפתוח Issue ובלי לשמור מצב
    python hunter.py --catalog f.json   (לבדיקות) קטלוג גולדמונד מקובץ מקומי
"""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import notify
from matcher import match, normalize
from sources import SOURCES, SkipRun, goldmund

ROOT = Path(__file__).parent
WISHLIST = ROOT / "books.csv"
STATE = ROOT / "state.json"


def load_wishlist(path=WISHLIST):
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    for row in csv.DictReader(lines):
        title = (row.get("title") or "").strip()
        author = (row.get("author") or "").strip()
        # שורה בלי שם ספר אבל עם מחבר = כל הספרים של המחבר
        if title or author:
            rows.append({
                "title": title,
                "author": author,
                "max_price": (row.get("max_price") or "").strip(),
            })
    return rows


def copy_key(item):
    """מזהה לעותק: שילוב השדות, ובאתרים שיש להם מזהה לכל עותק (סיפור חוזר) גם המזהה."""
    raw = "|".join([item["source"], normalize(item["title"]), normalize(item["author"]),
                    item.get("condition", ""), item.get("price", "")])
    if item.get("id"):
        raw += "|" + str(item["id"])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                     encoding="utf-8")


def run(dry_run=False, catalog_file=None):
    wishlist = load_wishlist()
    if not wishlist:
        print("books.csv is empty - nothing to look for")
        return 0
    print(f"wishlist: {len(wishlist)} books")

    state = load_state()
    new_state = {}
    found_new = []
    errors = []
    skipped = 0

    for source in SOURCES:
        try:
            if catalog_file and source is goldmund:
                data = json.loads(Path(catalog_file).read_text(encoding="utf-8"))
                items = goldmund.parse(data)
            elif getattr(source, "NEEDS_WISHLIST", False):
                items = source.fetch(wishlist)
            else:
                items = source.fetch()
        except SkipRun as why:
            # המקור לא נבדק הפעם: שומרים את מה שידוע עליו, בלי לדווח כשגיאה
            print(f"[{source.NAME}] skipped: {why}")
            skipped += 1
            new_state[source.NAME] = state.get(source.NAME, {})
            continue
        except Exception as exc:  # תקלה באתר אחד לא מפילה את השאר
            errors.append(f"{source.NAME}: {exc}")
            print(f"[{source.NAME}] ERROR: {exc}", file=sys.stderr)
            # שומרים את המצב הקודם של המקור, כדי לא לשלוח הכל מחדש בריצה הבאה
            new_state[source.NAME] = state.get(source.NAME, {})
            continue

        print(f"[{source.NAME}] {len(items)} items in catalog")
        seen_before = state.get(source.NAME, {})
        current = {}
        for item in items:
            for wanted in wishlist:
                m = match(wanted, item)
                if not m:
                    continue
                key = copy_key(item)
                current[key] = f"{item['title']} | {item['author']} | {item['price']}"
                if key not in seen_before:
                    found_new.append({"wanted": wanted, "item": item, "match": m})
                # עותק שתואם לכמה שורות (למשל ספר מסוים וגם "כל ספרי המחבר") מדווח פעם אחת
                break
        # במצב נשמרים רק העותקים שקיימים עכשיו: עותק שנמכר וחזר ייחשב חדש
        new_state[source.NAME] = current
                # פרטים נוספים (למשל סניפים) רק לעותקים החדשים, כדי לא להוסיף בקשות מיותרות
        if hasattr(source, "enrich"):
            for f in found_new:
                if f["item"]["source"] == source.NAME:
                    try:
                        source.enrich(f["item"])
                    except Exception as exc:
                        print(f"[{source.NAME}] no details for {f['item']['url']}: {exc}")
        print(f"[{source.NAME}] {len(current)} matching copies, "
              f"{sum(1 for f in found_new if f['item']['source'] == source.NAME)} new")

    if found_new:
        if dry_run:
            print("\n--- dry run: issue would be ---")
            print(notify.build_subject(found_new))
            print(notify.build_body(found_new))
        else:
            notify.send(found_new)
    else:
        print("no new copies")

    if not dry_run:
        save_state(new_state)

    # אם כל המקורות שנבדקו נכשלו, מחזירים קוד שגיאה כדי ש-GitHub ישלח התראת כישלון
    return 1 if errors and len(errors) == len(SOURCES) - skipped else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--catalog", help="local catalog.json for testing")
    args = ap.parse_args()
    sys.exit(run(dry_run=args.dry_run, catalog_file=args.catalog))
