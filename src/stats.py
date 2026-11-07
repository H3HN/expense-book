from collections import defaultdict
from datetime import datetime

from src.config import DATE_FORMAT


def totals(records):
    income = sum(float(r["amount"]) for r in records if r.get("type") == "income")
    expense = sum(float(r["amount"]) for r in records if r.get("type") == "expense")
    return {"income": round(income, 2), "expense": round(expense, 2), "balance": round(income - expense, 2)}


def in_range(record, start=None, end=None):
    try:
        day = datetime.strptime(record.get("date", ""), DATE_FORMAT).date()
    except ValueError:
        return False
    if start and day < start:
        return False
    if end and day > end:
        return False
    return True


def summary(records, start=None, end=None):
    selected = [r for r in records if in_range(r, start, end)]
    result = totals(selected)
    result["count"] = len(selected)
    return result


def daily_totals(records):
    buckets = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for record in records:
        day = record.get("date", "")
        buckets[day][record.get("type", "expense")] += float(record.get("amount", 0))
    rows = []
    for day in sorted(buckets):
        income = round(buckets[day]["income"], 2)
        expense = round(buckets[day]["expense"], 2)
        rows.append({"date": day, "income": income, "expense": expense, "balance": round(income - expense, 2)})
    return rows