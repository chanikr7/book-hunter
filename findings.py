"""דף הממצאים: היסטוריה של כל העותקים שנמצאו, ודף FINDINGS.md שמציג אותה.

findings.json  - הנתונים (הכלי קורא וכותב אותו, לא צריך לגעת בו)
FINDINGS.md    - הדף לקריאה. GitHub מציג אותו כדף מעוצב, גם באפליקציה.

לכל עותק נשמר: החנות, הסניף, המחיר, מתי נמצא לראשונה, מתי נראה לאחרונה,
ומתי נעלם (אם נעלם). עותקים שנעלמו נשמרים KEEP_GONE_DAYS ימים ואז נמחקים.
חנות שלא נבדקה בריצה (דילוג או תקלה) לא משתנה, כדי שלא ייראה כאילו הכל נמכר.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Jerusalem")
except Exception:  # אם אין נתוני אזורי זמן במחשב
    TZ = timezone(timedelta(hours=2))

ROOT = Path(__file__).parent
DATA = ROOT / "findings.json"
PAGE = ROOT / "FINDINGS.md"
KEEP_GONE_DAYS = 90
UNKNOWN_PLACE = "אחד הסניפים (משלוח או איסוף מהסניף)"


def wanted_key(wanted):
    return f"{wanted.get('title', '')}|{wanted.get('author', '')}"


def wanted_label(wanted):
    title, author = wanted.get("title", ""), wanted.get("author", "")
    if not title:
        return f"כל הספרים של {author}"
    return title + (f" / {author}" if author else "")


def _now():
    return datetime.now(TZ)


def _fmt(iso):
    if not iso:
        return ""
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d.%m.%y %H:%M")


def load():
    if DATA.exists():
        return json.loads(DATA.read_text(encoding="utf-8"))
    return {"copies": {}, "last_run": None, "sources": {}}


def save(data):
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8")


def update(data, wishlist, checked, statuses):
    """checked: {שם חנות: [ {key, wanted, item}, ... ]} רק לחנויות שנבדקו בהצלחה.
    statuses: {שם חנות: טקסט מצב לריצה הזו}."""
    now = _now()
    now_iso = now.isoformat(timespec="minutes")
    copies = data.setdefault("copies", {})

    for source_name, matches in checked.items():
        present = set()
        for m in matches:
            key, item, wanted = m["key"], m["item"], m["wanted"]
            present.add(key)
            rec = copies.get(key)
            location = item.get("location") or ""
            if rec is None:
                rec = copies[key] = {"first_seen": now_iso}
            elif location == UNKNOWN_PLACE and rec.get("location"):
                location = rec["location"]  # לא מוחקים סניף שכבר ידוע
            rec.update({
                "source": item["source"],
                "source_name": item["source_name"],
                "wanted": wanted_key(wanted),
                "wanted_label": wanted_label(wanted),
                "title": item["title"],
                "author": item.get("author", ""),
                "price": item.get("price", ""),
                "condition": item.get("condition", ""),
                "location": location,
                "url": item.get("url", ""),
                "last_seen": now_iso,
                "gone_since": None,
            })
        for key, rec in copies.items():
            if rec["source"] == source_name and key not in present and not rec.get("gone_since"):
                rec["gone_since"] = now_iso

    # ניקוי: עותקים שנעלמו מזמן, ועותקים של ספרים שהוסרו מהרשימה
    wanted_now = {wanted_key(w) for w in wishlist}
    cutoff = now - timedelta(days=KEEP_GONE_DAYS)
    for key in list(copies):
        rec = copies[key]
        gone = rec.get("gone_since")
        if rec["wanted"] not in wanted_now or (gone and datetime.fromisoformat(gone) < cutoff):
            del copies[key]

    data["last_run"] = now_iso
    data.setdefault("sources", {}).update(statuses)


def _md(text):
    return (text or "").replace("|", "\\|").replace("\n", " ")


def _price_sort(rec):
    try:
        return float(rec.get("price"))
    except (TypeError, ValueError):
        return float("inf")


def render(data, wishlist):
    copies = list(data.get("copies", {}).values())
    by_wanted = {}
    for rec in copies:
        by_wanted.setdefault(rec["wanted"], []).append(rec)

    available = [c for c in copies if not c.get("gone_since")]
    lines = ["# 📚 ממצאים", ""]
    lines.append(f"**ריצה אחרונה:** {_fmt(data.get('last_run'))} &nbsp;·&nbsp; "
                 f"**זמינים עכשיו:** {len(available)} עותקים של "
                 f"{len({c['wanted'] for c in available})} ספרים מהרשימה")
    lines.append("")
    for name, status in sorted(data.get("sources", {}).items()):
        lines.append(f"- {status}")
    lines.append("")

    missing = []
    for wanted in wishlist:
        recs = by_wanted.get(wanted_key(wanted), [])
        if not recs:
            missing.append(wanted_label(wanted))
            continue
        now_recs = sorted([r for r in recs if not r.get("gone_since")], key=_price_sort)
        gone_recs = sorted([r for r in recs if r.get("gone_since")],
                           key=lambda r: r["gone_since"], reverse=True)
        lines.append(f"## {wanted_label(wanted)}")
        lines.append("")
        if now_recs:
            lines.append("| ✅ זמין | מחבר | מחיר | פרטים | איפה | נמצא לראשונה |")
            lines.append("|---|---|---|---|---|---|")
            for r in now_recs:
                where = f"[{_md(r['source_name'])}]({r['url']})" if r.get("url") else _md(r["source_name"])
                if r.get("location"):
                    where += f", {_md(r['location'])}"
                lines.append(f"| {_md(r['title'])} | {_md(r['author']) or '?'} | {_md(r['price'])} | "
                             f"{_md(r['condition'])} | {where} | {_fmt(r['first_seen'])} |")
            lines.append("")
        if gone_recs:
            lines.append("<details><summary>❌ עותקים שנעלמו (כנראה נמכרו)</summary>")
            lines.append("")
            lines.append("| כותר | חנות | מחיר | נמצא | נעלם |")
            lines.append("|---|---|---|---|---|")
            for r in gone_recs:
                lines.append(f"| {_md(r['title'])} | {_md(r['source_name'])} | {_md(r['price'])} | "
                             f"{_fmt(r['first_seen'])} | {_fmt(r['gone_since'])} |")
            lines.append("")
            lines.append("</details>")
            lines.append("")

    if missing:
        lines.append("## עוד לא נמצאו")
        lines.append("")
        for label in missing:
            lines.append(f"- {label}")
        lines.append("")

    lines.append("---")
    lines.append(f"הדף מתעדכן אוטומטית בכל ריצה. עותקים שנעלמו נשמרים {KEEP_GONE_DAYS} יום.")
    PAGE.write_text("\n".join(lines) + "\n", encoding="utf-8")
