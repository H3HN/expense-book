from collections import defaultdict


def by_category(records, rtype="expense"):
    buckets = defaultdict(lambda: {"amount": 0.0, "count": 0})
    for record in records:
        if record.get("type") != rtype:
            continue
        category = record.get("category") or "其他"
        buckets[category]["amount"] += float(record.get("amount", 0))
        buckets[category]["count"] += 1

    total = sum(item["amount"] for item in buckets.values())
    rows = []
    for category, item in buckets.items():
        rows.append({
            "category": category,
            "amount": round(item["amount"], 2),
            "count": item["count"],
            "ratio": round(item["amount"] / total, 4) if total else 0.0,
        })
    return sorted(rows, key=lambda x: x["amount"], reverse=True)


def top_categories(records, n=5, rtype="expense"):
    return by_category(records, rtype)[:n]