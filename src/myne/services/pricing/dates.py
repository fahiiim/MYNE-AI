import re
from datetime import date, datetime

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

_RELATIVE = re.compile(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", re.I)
_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


def parse_published(text: str | None, *, today: date) -> date | None:
    """Parse search-engine dates such as '3 weeks ago', 'yesterday' or 'Mar 5, 2026'."""
    if not text:
        return None
    lowered = text.strip().lower()
    if lowered in {"today", "just now"}:
        return today
    if lowered == "yesterday":
        return today - relativedelta(days=1)
    if match := _RELATIVE.search(lowered):
        count, unit = int(match.group(1)), match.group(2)
        offsets = {
            "day": relativedelta(days=count),
            "week": relativedelta(weeks=count),
            "month": relativedelta(months=count),
            "year": relativedelta(years=count),
        }
        return today - offsets.get(unit, relativedelta())
    try:
        parsed = date_parser.parse(text, default=datetime(today.year, 1, 1)).date()
    except (ValueError, OverflowError):
        return None
    return parsed if parsed <= today else None


def parse_month(value: str | None) -> date | None:
    if not value or not (match := _MONTH.match(value.strip())):
        return None
    year, month = int(match.group(1)), int(match.group(2))
    return date(year, month, 1) if 1 <= month <= 12 else None
