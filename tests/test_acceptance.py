import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.import_export import from_csv, to_csv
from src.nl_parser import parse_text
from src.validator import validate_record


def test_parse_expense():
    parsed = parse_text("午饭 25")
    assert parsed["type"] == "expense"
    assert parsed["amount"] == 25
    assert parsed["category"] == "饮食"


def test_parse_income():
    parsed = parse_text("兼职收入 300 元")
    assert parsed["type"] == "income"
    assert parsed["amount"] == 300


def test_parse_without_amount():
    assert parse_text("今天心情不错") is None


def test_validate_rejects_bad_date():
    errors = validate_record({"date": "2026/11/07", "type": "expense", "amount": 10, "category": "饮食"})
    assert any("日期" in e for e in errors)


def test_validate_rejects_zero():
    errors = validate_record({"date": "2026-11-07", "type": "expense", "amount": 0, "category": "饮食"})
    assert any("金额" in e for e in errors)


def test_csv_roundtrip():
    rows = [{"id": "a1", "date": "2026-11-07", "type": "expense", "amount": 12.5, "category": "饮食", "note": "早饭", "created_at": ""}]
    parsed = from_csv(to_csv(rows))
    assert parsed[0]["id"] == "a1"
    assert parsed[0]["amount"] == 12.5
    assert parsed[0]["note"] == "早饭"