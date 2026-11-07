import json
import sqlite3
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


def test_sqlite_database_created(temp_data_file):
    storage.load_records()
    db_file = temp_data_file.parent / "records.db"
    assert db_file.exists()
    with sqlite3.connect(db_file) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "records" in tables


def test_sqlite_indexes_created(temp_data_file):
    storage.load_records()
    db_file = temp_data_file.parent / "records.db"
    with sqlite3.connect(db_file) as conn:
        indexes = {row[1] for row in conn.execute("PRAGMA index_list('records')")}
    assert "idx_records_date" in indexes
    assert "idx_records_type" in indexes


def test_json_seed_is_migrated_on_first_load(temp_data_file):
    seed = [
        {
            "id": "seed-1",
            "date": "2026-11-07",
            "type": "expense",
            "amount": 25,
            "category": "饮食",
            "note": "种子数据",
            "created_at": "2026-11-07 09:00:00",
        }
    ]
    temp_data_file.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    records = storage.load_records()
    assert len(records) == 1
    assert records[0]["note"] == "种子数据"


def test_json_seed_migrated_only_once(temp_data_file):
    seed = [{"id": "seed-1", "date": "2026-11-07", "type": "expense", "amount": 25, "category": "饮食", "note": "种子数据"}]
    temp_data_file.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    storage.load_records()
    storage.delete_record("seed-1")
    assert storage.load_records() == []


def test_json_backup_synced_after_add(temp_data_file):
    storage.add_record(new_record("2026-11-07", "expense", 18.5, "饮食", "晚饭"))
    snapshot = json.loads(temp_data_file.read_text(encoding="utf-8"))
    assert len(snapshot) == 1
    assert snapshot[0]["note"] == "晚饭"


def test_json_backup_synced_after_update(temp_data_file):
    saved = storage.add_record(new_record("2026-11-07", "expense", 10, "交通", "公交"))
    storage.update_record(saved["id"], {"amount": 30, "note": "打车"})
    snapshot = json.loads(temp_data_file.read_text(encoding="utf-8"))
    assert snapshot[0]["amount"] == 30
    assert snapshot[0]["note"] == "打车"


def test_json_backup_synced_after_delete(temp_data_file):
    first = storage.add_record(new_record("2026-11-07", "expense", 10, "交通"))
    storage.add_record(new_record("2026-11-07", "expense", 20, "饮食"))
    storage.delete_record(first["id"])
    snapshot = json.loads(temp_data_file.read_text(encoding="utf-8"))
    assert len(snapshot) == 1
    assert snapshot[0]["category"] == "饮食"


def test_upsert_records_merges_by_primary_key():
    first = new_record("2026-11-07", "expense", 10, "交通", "公交").to_dict()
    second = {**first, "amount": 15, "note": "地铁"}
    assert storage.upsert_records([first, second]) == 2
    records = storage.load_records()
    assert len(records) == 1
    assert records[0]["amount"] == 15


def test_upsert_records_empty_list():
    assert storage.upsert_records([]) == 0


def test_storage_info_reports_engine():
    info = storage.storage_info()
    assert info["engine"] == "SQLite3 + JSON Backup"
    assert info["db_file"].endswith("records.db")
    assert info["data_file"].endswith("records.json")


def test_records_isolated_between_test_directories(tmp_path, monkeypatch):
    first_file = tmp_path / "a" / "records.json"
    monkeypatch.setattr(storage, "DATA_FILE", first_file)
    monkeypatch.setattr(storage, "DATA_DIR", first_file.parent)
    storage.add_record(new_record("2026-11-07", "expense", 12, "饮食", "A"))

    second_file = tmp_path / "b" / "records.json"
    monkeypatch.setattr(storage, "DATA_FILE", second_file)
    monkeypatch.setattr(storage, "DATA_DIR", second_file.parent)

    assert storage.load_records() == []
    assert (second_file.parent / "records.db").exists()

def seed_query_rows():
    rows = [
        ("2026-10-29", "income", 2000, "生活费", "本月生活费"),
        ("2026-10-29", "expense", 18, "饮食", "午饭"),
        ("2026-10-30", "expense", 6, "交通", "地铁"),
        ("2026-10-30", "expense", 45, "娱乐", "电影"),
        ("2026-10-31", "expense", 128.5, "购物", "冬装"),
    ]
    for day, rtype, amount, category, note in rows:
        storage.add_record(new_record(day, rtype, amount, category, note))


def test_query_records_returns_all_sorted_by_date_desc():
    seed_query_rows()
    records = storage.query_records()
    assert len(records) == 5
    dates = [record["date"] for record in records]
    assert dates == sorted(dates, reverse=True)


def test_query_records_by_type():
    seed_query_rows()
    records = storage.query_records(rtype="income")
    assert len(records) == 1
    assert records[0]["category"] == "生活费"


def test_query_records_by_category():
    seed_query_rows()
    records = storage.query_records(category="交通")
    assert len(records) == 1
    assert records[0]["amount"] == 6


def test_query_records_by_date_range():
    seed_query_rows()
    records = storage.query_records(start="2026-10-30", end="2026-10-30")
    assert len(records) == 2
    assert {record["date"] for record in records} == {"2026-10-30"}


def test_query_records_accepts_date_objects():
    seed_query_rows()
    from datetime import date

    records = storage.query_records(start=date(2026, 10, 31), end=date(2026, 10, 31))
    assert len(records) == 1
    assert records[0]["category"] == "购物"


def test_query_records_by_keyword():
    seed_query_rows()
    records = storage.query_records(keyword="地铁")
    assert len(records) == 1
    assert records[0]["note"] == "地铁"


def test_query_records_keyword_is_parameterized():
    seed_query_rows()
    assert storage.query_records(keyword="' OR 1=1 --") == []


def test_query_records_limit():
    seed_query_rows()
    records = storage.query_records(limit=2)
    assert len(records) == 2
    assert records[0]["date"] == "2026-10-31"


def test_query_records_combined_filters():
    seed_query_rows()
    records = storage.query_records(
        start="2026-10-29",
        end="2026-10-30",
        rtype="expense",
        category="饮食",
        keyword="午饭",
        limit=10,
    )
    assert len(records) == 1
    assert records[0]["amount"] == 18


def test_query_records_no_match():
    seed_query_rows()
    assert storage.query_records(keyword="不存在的备注") == []


def test_query_records_ignores_all_placeholder():
    seed_query_rows()
    assert len(storage.query_records(rtype="all", category="all")) == 5