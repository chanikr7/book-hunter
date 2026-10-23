"""כל מתאם הוא מודול עם NAME, DISPLAY_NAME ו-fetch() שמחזיר פריטים במבנה אחיד:
source, source_name, title, author, price, condition, location, url.

כדי להוסיף אתר: כותבים מודול חדש כאן ומוסיפים אותו לרשימה למטה.
"""

from . import goldmund

SOURCES = [goldmund]
