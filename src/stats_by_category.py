from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


_CENT = Decimal("0.01")
_RATIO_UNITS = 10_000  # Store ratios to four decimal places (1.0000 == 100%).


def _amount_in_cents(value):
    """Convert a valid positive currency amount to integer cents."""
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0:
            return None
        cents = int(amount.quantize(_CENT, rounding=ROUND_HALF_UP) * 100)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None
    return cents if cents > 0 else None


def by_category(records, rtype="expense"):
    buckets = defaultdict(lambda: {"amount_cents": 0, "count": 0})
    for record in records or []:
        if not isinstance(record, dict):
            continue
        if record.get("type") != rtype:
            continue
        amount_cents = _amount_in_cents(record.get("amount"))
        if amount_cents is None:
            continue
        category = str(record.get("category") or "其他").strip() or "其他"
        buckets[category]["amount_cents"] += amount_cents
        buckets[category]["count"] += 1

    total_cents = sum(item["amount_cents"] for item in buckets.values())
    if not total_cents:
        return []

    # Allocate rounded 0.0001 ratio units by largest remainder so the full
    # category list always adds up to exactly 1.0000 (100%).
    ratio_units = {}
    remainders = []
    allocated_units = 0
    for category, item in buckets.items():
        units, remainder = divmod(item["amount_cents"] * _RATIO_UNITS, total_cents)
        ratio_units[category] = units
        allocated_units += units
        remainders.append((category, remainder))

    units_left = _RATIO_UNITS - allocated_units
    for category, _ in sorted(remainders, key=lambda pair: (-pair[1], pair[0]))[:units_left]:
        ratio_units[category] += 1

    rows = []
    for category, item in buckets.items():
        rows.append({
            "category": category,
            "amount": item["amount_cents"] / 100,
            "count": item["count"],
            "ratio": ratio_units[category] / _RATIO_UNITS,
        })
    return sorted(rows, key=lambda row: (-buckets[row["category"]]["amount_cents"], row["category"]))


def top_categories(records, n=5, rtype="expense"):
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        return []
    return by_category(records, rtype)[:n]
