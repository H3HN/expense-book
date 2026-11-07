"""边界与异常用例：补齐主流程测试没有覆盖到的分支。

主测试集（test_acceptance / test_storage / test_stats，69 项）覆盖的是正常流程，
本文件专门盯住四类容易被忽略的边界：

1. 健康检查接口 —— 演示前第一个要 curl 的接口，之前无人验证；
2. 日期参数非法 / 区间倒置 —— `_parse_day` 和 start>end 的 400 分支；
3. limit 截断与 totals 全量的语义差异 —— 接口设计上的关键约定；
4. 校验器与模型层的兜底 —— 备注超长、非法 type、缺字段的脏数据。
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app
from src import storage
from src.models import Record
from src.validator import validate_record


@pytest.fixture
def client(tmp_path, monkeypatch):
    """与 test_acceptance 一致：把数据文件指到临时目录，避免污染演示数据。"""
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "DATA_FILE", tmp_path / "records.json")
    storage.save_records([])
    with TestClient(app) as test_client:
        yield test_client


def _payload(**kwargs):
    base = {"date": "2026-11-07", "type": "expense", "amount": 25, "category": "饮食", "note": "午饭"}
    base.update(kwargs)
    return base


# --------------------------------------------------------------------------- #
# 1. 健康检查
# --------------------------------------------------------------------------- #
def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "expense-book"
    assert "SQLite" in body["engine"]


# --------------------------------------------------------------------------- #
# 2. 日期参数与区间校验
# --------------------------------------------------------------------------- #
def test_api_records_rejects_malformed_date(client):
    response = client.get("/api/records", params={"start": "2026/11/07"})
    assert response.status_code == 400
    assert any("格式应为" in message for message in response.json()["detail"]["errors"])


def test_api_records_rejects_reversed_range(client):
    response = client.get("/api/records", params={"start": "2026-11-09", "end": "2026-11-01"})
    assert response.status_code == 400
    assert any("起始日期不能晚于结束日期" in message for message in response.json()["detail"]["errors"])


def test_api_stats_rejects_reversed_range(client):
    response = client.get("/api/stats", params={"start": "2026-11-09", "end": "2026-11-01"})
    assert response.status_code == 400
    assert any("起始日期不能晚于结束日期" in message for message in response.json()["detail"]["errors"])


# --------------------------------------------------------------------------- #
# 3. limit 只截断返回列表，totals 仍是全量
# --------------------------------------------------------------------------- #
def test_api_records_limit_keeps_global_totals(client):
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        assert client.post("/api/records", json=_payload(date=day, amount=10)).status_code == 201

    body = client.get("/api/records", params={"limit": 2}).json()
    assert body["count"] == 2          # 返回列表被截断
    assert len(body["records"]) == 2
    assert body["totals"]["count"] == 3   # 顶部指标卡要用全量，不能被 limit 影响
    assert body["totals"]["expense"] == 30


# --------------------------------------------------------------------------- #
# 4. CSV 导入的边界
# --------------------------------------------------------------------------- #
def test_api_import_empty_file(client):
    response = client.post("/api/import/csv", files={"file": ("empty.csv", b"", "text/csv")})
    assert response.status_code == 400
    assert any("文件为空" in message for message in response.json()["detail"]["errors"])


# --------------------------------------------------------------------------- #
# 5. 校验器与模型层的兜底
# --------------------------------------------------------------------------- #
def test_validate_rejects_note_too_long():
    errors = validate_record(_payload(note="备注" * 60))   # 120 字
    assert any("备注" in message for message in errors)


def test_validate_rejects_unknown_type():
    errors = validate_record(_payload(type="transfer"))
    assert any("类型" in message for message in errors)


def test_record_from_dict_fills_defaults():
    """脏 JSON（缺字段）不能让整个列表接口 500，必须给出安全默认值。"""
    record = Record.from_dict({})
    assert record.id
    assert record.type == "expense"
    assert record.category == "其他"
    assert record.note == ""
    assert record.amount == 0.0
