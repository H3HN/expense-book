import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import storage
from src.models import new_record


@pytest.fixture(autouse=True)
def temp_data_file(tmp_path, monkeypatch):
    data_file = tmp_path / "records.json"
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "DATA_FILE", data_file)
    yield data_file


def test_load_empty_creates_file(temp_data_file):
    assert storage.load_records() == []
    assert temp_data_file.exists()


def test_add_and_load_roundtrip():
    record = new_record("2026-11-07", "expense", 25.5, "饮食", "午饭")
    storage.add_record(record)
    records = storage.load_records()
    assert len(records) == 1
    assert records[0]["amount"] == 25.5
    assert records[0]["note"] == "午饭"


def test_save_records_persists_unicode(tmp_path):
    rows = [new_record("2026-11-07", "income", 100, "兼职", "家教").to_dict()]
    storage.save_records(rows)
    raw = json.loads(storage.DATA_FILE.read_text(encoding="utf-8"))
    assert raw[0]["category"] == "兼职"


def test_delete_record():
    first = storage.add_record(new_record("2026-11-07", "expense", 10, "交通"))
    storage.add_record(new_record("2026-11-07", "expense", 20, "饮食"))
    assert storage.delete_record(first["id"]) is True
    assert len(storage.load_records()) == 1
    assert storage.delete_record("not-exist") is False


def test_negative_amount_is_stored_as_given():
    storage.add_record(new_record("2026-11-07", "expense", -5, "其他"))
    assert storage.load_records()[0]["amount"] == -5.0

def test_update_record_changes_fields():
    saved = storage.add_record(new_record("2026-11-07", "expense", 10, "交通", "公交"))
    updated = storage.update_record(saved["id"], {"amount": 12.5, "note": "地铁", "category": "交通"})
    assert updated["id"] == saved["id"]
    assert updated["amount"] == 12.5
    assert updated["note"] == "地铁"
    assert storage.load_records()[0]["amount"] == 12.5


def test_update_record_keeps_id_and_created_at():
    saved = storage.add_record(new_record("2026-11-07", "expense", 10, "交通"))
    updated = storage.update_record(saved["id"], {"amount": 88})
    assert updated["created_at"] == saved["created_at"]
    assert updated["date"] == "2026-11-07"


def test_update_unknown_record_returns_none():
    storage.add_record(new_record("2026-11-07", "expense", 10, "交通"))
    assert storage.update_record("missing-id", {"amount": 20}) is None


def test_update_ignores_unknown_keys():
    saved = storage.add_record(new_record("2026-11-07", "expense", 10, "交通"))
    updated = storage.update_record(saved["id"], {"amount": 11, "hacker": "x"})
    assert "hacker" not in updated


def test_get_record():
    saved = storage.add_record(new_record("2026-11-07", "income", 300, "兼职"))
    assert storage.get_record(saved["id"])["category"] == "兼职"
    assert storage.get_record("nope") is None