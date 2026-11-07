from collections import defaultdict
from datetime import date, datetime

from src.config import DATE_FORMAT


def _safe_amount(value):
    if value is None or value == "" or isinstance(value, bool):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date) or (
        hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day")
    ):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in (DATE_FORMAT, "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def totals(records):
    if not records:
        return {"income": 0.0, "expense": 0.0, "balance": 0.0, "count": 0}
    income = sum(_safe_amount(r.get("amount", 0)) for r in records if r.get("type") == "income")
    expense = sum(_safe_amount(r.get("amount", 0)) for r in records if r.get("type") == "expense")
    return {
        "income": round(income, 2),
        "expense": round(expense, 2),
        "balance": round(income - expense, 2),
        "count": len(records),
    }


def in_range(record, start=None, end=None):
    if not isinstance(record, dict):
        return False
    day = _as_date(record.get("date", ""))
    if day is None:
        return False
    start_day = _as_date(start)
    end_day = _as_date(end)
    if start_day and end_day and start_day > end_day:
        start_day, end_day = end_day, start_day
    if start_day and day < start_day:
        return False
    if end_day and day > end_day:
        return False
    return True


def summary(records, start=None, end=None):
    selected = [r for r in records if in_range(r, start, end)]
    result = totals(selected)
    result["count"] = len(selected)
    return result


def filter_by_range(records, start=None, end=None, rtype=None, category=None, keyword=None):
    keyword = (keyword or "").strip().lower()
    result = []
    for record in records:
        if not in_range(record, start, end):
            continue
        if rtype and rtype != "all" and record.get("type") != rtype:
            continue
        if category and category != "all" and record.get("category") != category:
            continue
        if keyword and keyword not in str(record.get("note", "")).lower():
            continue
        result.append(record)
    return result


def daily_totals(records):
    buckets = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for record in records:
        record_type = record.get("type")
        if record_type not in ("expense", "income"):
            continue
        day = record.get("date", "")
        buckets[day][record_type] += float(record.get("amount", 0))
    rows = []
    for day in sorted(buckets):
        income = round(buckets[day]["income"], 2)
        expense = round(buckets[day]["expense"], 2)
        rows.append({
            "date": day,
            "income": income,
            "expense": expense,
            "balance": round(income - expense, 2),
        })
    return rows