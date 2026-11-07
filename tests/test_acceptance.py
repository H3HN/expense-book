import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app
from src import storage
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


def test_parse_skips_date_number():
    parsed = parse_text("2月15日午饭 25")
    assert parsed["amount"] == 25
    assert parsed["category"] == "饮食"


def test_parse_prefers_unit_amount():
    parsed = parse_text("买2杯奶茶 36元")
    assert parsed["amount"] == 36
    assert parsed["category"] == "饮食"


def test_parse_skips_quantifier_without_unit():
    parsed = parse_text("买2杯奶茶 36")
    assert parsed["amount"] == 36


def test_validate_rejects_bad_date():
    errors = validate_record({"date": "2026/11/07", "type": "expense", "amount": 10, "category": "饮食"})
    assert any("日期" in e for e in errors)


def test_validate_rejects_zero():
    errors = validate_record({"date": "2026-11-07", "type": "expense", "amount": 0, "category": "饮食"})
    assert any("金额" in e for e in errors)


def test_validate_rejects_non_numeric_amount():
    errors = validate_record({"date": "2026-11-07", "type": "expense", "amount": "abc", "category": "饮食"})
    assert any("金额" in e for e in errors)


def test_csv_roundtrip():
    rows = [{"id": "a1", "date": "2026-11-07", "type": "expense", "amount": 12.5, "category": "饮食", "note": "早饭", "created_at": ""}]
    parsed = from_csv(to_csv(rows))
    assert parsed[0]["id"] == "a1"
    assert parsed[0]["amount"] == 12.5
    assert parsed[0]["note"] == "早饭"


def test_csv_filters_dirty_rows():
    csv_text = (
        "date,type,amount,category,note\n"
        "2026-11-07,expense,12.5,饮食,早饭\n"
        "2026-11-07,expense,abc,饮食,脏数据\n"
        "2026-11-07,expense,-3,饮食,负数\n"
        "2026-11-07,expense,8,不存在类别,脏数据\n"
        "bad-date,expense,9,饮食,坏日期\n"
    )
    rows = from_csv(csv_text)
    assert len(rows) == 1
    assert rows[0]["note"] == "早饭"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "DATA_FILE", tmp_path / "records.json")
    storage.save_records([])
    with TestClient(app) as test_client:
        yield test_client


def _payload(**kwargs):
    base = {"date": "2026-11-07", "type": "expense", "amount": 25, "category": "饮食", "note": "午饭"}
    base.update(kwargs)
    return base


def test_api_config(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert "饮食" in body["expense_categories"]
    assert body["record_types"]["expense"] == "支出"


def test_api_config_reports_sqlite(client):
    body = client.get("/api/config").json()
    assert body["engine"] == "SQLite3 + JSON Backup"
    assert body["db_file"].endswith("records.db")
    assert body["storage"]["engine"] == body["engine"]


def test_api_create_and_totals(client):
    response = client.post("/api/records", json=_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["record"]["amount"] == 25
    assert body["totals"]["expense"] == 25
    assert body["totals"]["count"] == 1


def test_api_create_rejects_invalid(client):
    response = client.post("/api/records", json=_payload(amount=0))
    assert response.status_code == 400
    assert response.json()["detail"]["errors"]


def test_api_list_filters(client):
    client.post("/api/records", json=_payload())
    client.post("/api/records", json=_payload(type="income", amount=2000, category="生活费", note="家里打钱"))

    response = client.get("/api/records", params={"type": "income", "keyword": "家里"})
    body = response.json()
    assert body["count"] == 1
    assert body["records"][0]["category"] == "生活费"
    assert body["totals"]["count"] == 2


def test_api_update(client):
    created = client.post("/api/records", json=_payload()).json()["record"]
    response = client.put(f"/api/records/{created['id']}", json={"amount": 30, "note": "晚饭"})
    assert response.status_code == 200
    assert response.json()["record"]["amount"] == 30
    assert response.json()["totals"]["expense"] == 30


def test_api_update_missing(client):
    assert client.put("/api/records/nope", json={"amount": 10}).status_code == 404


def test_api_delete(client):
    created = client.post("/api/records", json=_payload()).json()["record"]
    assert client.delete(f"/api/records/{created['id']}").status_code == 200
    assert client.delete(f"/api/records/{created['id']}").status_code == 404


def test_api_nl_preview_and_save(client):
    preview = client.post("/api/nl-parse", json={"text": "2月15日午饭 25", "auto_save": False})
    assert preview.status_code == 200
    assert preview.json()["parsed"]["amount"] == 25
    assert preview.json()["saved"] is None

    saved = client.post("/api/nl-parse", json={"text": "买2杯奶茶 36元", "auto_save": True})
    assert saved.status_code == 200
    assert saved.json()["saved"]["amount"] == 36
    assert saved.json()["totals"]["count"] == 1


def test_api_nl_invalid(client):
    assert client.post("/api/nl-parse", json={"text": "今天很开心"}).status_code == 400


def test_api_stats_by_range(client):
    client.post("/api/records", json=_payload(date="2026-11-01", amount=10, category="饮食"))
    client.post("/api/records", json=_payload(date="2026-11-02", amount=90, category="交通"))
    client.post("/api/records", json=_payload(date="2026-11-09", amount=500, category="购物"))

    response = client.get("/api/stats", params={"start": "2026-11-01", "end": "2026-11-02"})
    body = response.json()
    assert response.status_code == 200
    assert body["summary"]["expense"] == 100
    assert body["summary"]["count"] == 2
    assert body["expense_by_category"][0]["category"] == "交通"
    assert len(body["daily_totals"]) == 2
    assert body["totals"]["expense"] == 600


def test_api_export_and_import(client):
    client.post("/api/records", json=_payload())
    exported = client.get("/api/export/csv")
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")

    response = client.post(
        "/api/import/csv",
        files={"file": ("records.csv", exported.content, "text/csv")},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["imported"] == 1
    assert body["total"] == 1


def test_api_import_rejects_non_csv(client):
    response = client.post(
        "/api/import/csv",
        files={"file": ("records.txt", b"date,amount\n", "text/plain")},
    )
    assert response.status_code == 400

def test_api_import_is_idempotent(client):
    client.post("/api/records", json=_payload())
    exported = client.get("/api/export/csv").content

    first = client.post("/api/import/csv", files={"file": ("records.csv", exported, "text/csv")})
    second = client.post("/api/import/csv", files={"file": ("records.csv", exported, "text/csv")})

    assert first.json()["total"] == 1
    assert second.json()["total"] == 1
    assert second.json()["imported"] == 1
    assert client.get("/api/records").json()["totals"]["count"] == 1


def test_api_update_syncs_json_backup(client):
    created = client.post("/api/records", json=_payload()).json()["record"]
    client.put(f"/api/records/{created['id']}", json={"amount": 33, "note": "改后备份"})

    snapshot = json.loads(Path(storage.DATA_FILE).read_text(encoding="utf-8"))
    assert len(snapshot) == 1
    assert snapshot[0]["amount"] == 33
    assert snapshot[0]["note"] == "改后备份"


def test_api_create_writes_sqlite_file(client):
    client.post("/api/records", json=_payload())
    db_file = Path(storage.DATA_FILE).with_name("records.db")
    assert db_file.exists()
    assert db_file.stat().st_size > 0