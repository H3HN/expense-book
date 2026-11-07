import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.stats import daily_totals, summary, totals
from src.stats_by_category import by_category, top_categories


def build():
    return [
        {"date": "2026-11-01", "type": "income", "amount": 2000, "category": "生活费"},
        {"date": "2026-11-01", "type": "expense", "amount": 25, "category": "饮食"},
        {"date": "2026-11-02", "type": "expense", "amount": 75, "category": "饮食"},
        {"date": "2026-11-02", "type": "expense", "amount": 50, "category": "交通"},
    ]


def test_totals():
    result = totals(build())
    assert result["income"] == 2000
    assert result["expense"] == 150
    assert result["balance"] == 1850


def test_summary_range():
    result = summary(build(), date(2026, 11, 2), date(2026, 11, 2))
    assert result["expense"] == 125
    assert result["income"] == 0
    assert result["count"] == 2


def test_daily_totals_sorted():
    rows = daily_totals(build())
    assert [r["date"] for r in rows] == ["2026-11-01", "2026-11-02"]
    assert rows[0]["balance"] == 1975


def test_by_category_order_and_ratio():
    rows = by_category(build(), "expense")
    assert rows[0]["category"] == "饮食"
    assert rows[0]["amount"] == 100
    assert rows[0]["ratio"] == 0.6667


def test_top_categories_limit():
    assert len(top_categories(build(), n=1)) == 1