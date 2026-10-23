"""התראה דרך GitHub: כל ריצה שמוצאת עותקים חדשים פותחת Issue במאגר.

ב-GitHub Actions הכל מוגדר אוטומטית ואין צורך בשום סיסמה:
    GITHUB_TOKEN            הטוקן המובנה של הריצה (מועבר ב-workflow)
    GITHUB_REPOSITORY       owner/repo, מוגדר אוטומטית
    GITHUB_REPOSITORY_OWNER בעל המאגר, מתויג ב-Issue כדי שתגיע התראה

מחוץ ל-GitHub Actions (למשל בהרצה מקומית) ההודעה מודפסת למסך ולא נשלחת.
"""

import json
import os
import urllib.request

API = "https://api.github.com"


def _price_sort(price):
    try:
        return float(price)
    except (TypeError, ValueError):
        return float("inf")


def _group(found):
    groups = {}
    for f in found:
        key = (f["wanted"]["title"], f["wanted"].get("author") or "")
        groups.setdefault(key, []).append(f)
    for copies in groups.values():
        copies.sort(key=lambda f: _price_sort(f["item"].get("price")))
    return groups


def _md(text):
    """מנטרל תווים ששוברים טבלת Markdown."""
    return (text or "?").replace("|", "\\|").replace("\n", " ")


def build_subject(found):
    titles = sorted({f["wanted"]["title"] or f"ספרים של {f['wanted']['author']}" for f in found})
    if len(titles) == 1:
        return f"📚 נמצא: {titles[0]}"
    return f"📚 נמצאו {len(titles)} ספרים מהרשימה שלך: " + ", ".join(titles)[:150]


def build_body(found, mention=""):
    lines = []
    if mention:
        lines.append(f"@{mention}")
        lines.append("")
    lines.append("נמצאו עותקים חדשים של ספרים מהרשימה שלך:")
    for (title, author), copies in _group(found).items():
        lines.append("")
        lines.append(f"### {title} / {author}" if title else f"### כל הספרים של {author}")
        lines.append("")
        lines.append("| כותר בקטלוג | מחבר | מחיר | מצב | איפה |")
        lines.append("|---|---|---|---|---|")
        for f in copies:
            it = f["item"]
            warn = " ⚠️ אין מחבר בקטלוג, כדאי לוודא" if not f["match"]["certain"] else ""
            lines.append(
                f"| {_md(it['title'])}{warn} | {_md(it['author'])} | {_md(it['price'])} | "
                f"{_md(it['condition'])} | [{_md(it['source_name'])}]({it['url']}), {_md(it['location'])} |")
    lines.append("")
    lines.append("---")
    lines.append("נפתח אוטומטית על ידי book-hunter. העותקים האלה לא ידווחו שוב. "
                 "אפשר לסגור את ה-Issue אחרי שטיפלת בו.")
    return "\n".join(lines)


def send(found):
    if not found:
        return
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "").strip()

    subject = build_subject(found)
    body = build_body(found, mention=owner)

    if not token or not repo:
        print("[notify] not running in GitHub Actions - printing instead of opening an issue\n")
        print(subject)
        print(body)
        return

    req = urllib.request.Request(
        f"{API}/repos/{repo}/issues",
        data=json.dumps({"title": subject, "body": body}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "book-hunter",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        issue = json.loads(resp.read().decode("utf-8"))
    print(f"[notify] opened issue #{issue.get('number')}: {issue.get('html_url')}")
