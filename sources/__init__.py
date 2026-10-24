"""כל מתאם הוא מודול עם NAME, DISPLAY_NAME ו-fetch() שמחזיר פריטים במבנה אחיד:
source, source_name, title, author, price, condition, location, url (ו-id אם יש).

מתאם שצריך את רשימת הספרים (כי הוא מחפש כל ספר בנפרד) מגדיר NEEDS_WISHLIST = True,
ואז fetch מקבל את הרשימה.

כדי להוסיף אתר: כותבים מודול חדש כאן ומוסיפים אותו לרשימה למטה.
"""


class SkipRun(Exception):
    """המקור לא נבדק בריצה הזו (למשל כי הוא נבדק רק פעמיים ביום)."""


from . import goldmund, rebooks  # noqa: E402

SOURCES = [goldmund, rebooks]
