"""记账本存储层：SQLite 主存储 + JSON 全量备份。

兼容旧接口（load_records / save_records / add_record(Record) / query_records /
upsert_records / storage_info）与新接口（get_all_records / add_record(date, ...)）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from src.config import DATE_FORMAT
from src.models import Record

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "records.db"
JSON_PATH = DATA_DIR / "records.json"

DATA_FILE = JSON_PATH
DB_FILE = DB_PATH

_LOCK = threading.RLock()

FIELDS = "id, date, type, amount, category, note, created_at"

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    date TEXT,
    type TEXT,
    amount REAL,
    category TEXT,
    note TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_records_date ON records(date);
CREATE INDEX IF NOT EXISTS idx_records_type ON records(type);
"""


def _json_path() -> Path:
    return Path(DATA_FILE)


def _db_path() -> Path:
    data_file = _json_path()
    configured = Path(DB_FILE)
    if configured.parent == data_file.parent:
        return configured
    return data_file.with_name("records.db")


def _read_json() -> list[dict[str, Any]]:
    path = _json_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "[]")
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    return [Record.from_dict(item).to_dict() for item in raw if isinstance(item, dict)]


def _row(record: dict[str, Any]) -> tuple:
    return (
        str(record.get("id", "")),
        str(record.get("date", "")),
        str(record.get("type", "expense")),
        float(record.get("amount", 0) or 0),
        str(record.get("category", "其他") or "其他"),
        str(record.get("note", "") or ""),
        str(record.get("created_at", "") or ""),
    )


def _insert_many(conn: sqlite3.Connection, records: list[dict[str, Any]]) -> None:
    conn.executemany(
        f"INSERT OR REPLACE INTO records ({FIELDS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [_row(record) for record in records],
    )


def _bootstrap(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    if count:
        return
    seeds = _read_json()
    if seeds:
        _insert_many(conn, seeds)


def _fetch_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"SELECT {FIELDS} FROM records ORDER BY date DESC, created_at DESC"
    ).fetchall()
    return [Record.from_dict(dict(row)).to_dict() for row in rows]


def _write_json(records: list[dict[str, Any]]) -> None:
    path = _json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    json_path = _json_path()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    if not json_path.exists():
        json_path.write_text("[]", encoding="utf-8")

    conn = sqlite3.connect(str(_db_path()), timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        _bootstrap(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _LOCK, _connect() as conn:
        _write_json(_fetch_all(conn))


def export_json() -> list[dict[str, Any]]:
    with _LOCK, _connect() as conn:
        records = _fetch_all(conn)
        _write_json(records)
        return records


def _insert_record(record: dict[str, Any]) -> dict[str, Any]:
    with _LOCK, _connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO records ({FIELDS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
            _row(record),
        )
        _write_json(_fetch_all(conn))
    return record


def add_record(date, type=None, amount=None, category="", note=""):
    if isinstance(date, (Record, dict)) or not isinstance(date, str):
        record = date.to_dict() if isinstance(date, Record) else Record.from_dict(date).to_dict()
        return _insert_record(record)

    if type is None or amount is None:
        raise TypeError("add_record 需要 date、type、amount 三个参数")

    record = {
        "id": uuid.uuid4().hex,
        "date": date,
        "type": type,
        "amount": float(amount),
        "category": category or "其他",
        "note": note or "",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return _insert_record(record)


def get_record(record_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            f"SELECT {FIELDS} FROM records WHERE id = ?", (record_id,)
        ).fetchone()
    return Record.from_dict(dict(row)).to_dict() if row else None


def get_all_records() -> list[dict[str, Any]]:
    with _connect() as conn:
        return _fetch_all(conn)


def load_records() -> list[dict[str, Any]]:
    return get_all_records()


def save_records(records) -> None:
    payload = [Record.from_dict(item).to_dict() for item in records]
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM records")
        _insert_many(conn, payload)
        _write_json(_fetch_all(conn))


def update_record(record_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(updates, dict):
        return None

    allowed_fields = {"date", "type", "amount", "category", "note"}
    fields = {key: value for key, value in updates.items() if key in allowed_fields}

    if not fields:
        return get_record(record_id)

    if "amount" in fields:
        fields["amount"] = float(fields["amount"])

    set_sql = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [record_id]

    with _LOCK, _connect() as conn:
        cursor = conn.execute(f"UPDATE records SET {set_sql} WHERE id = ?", values)
        if cursor.rowcount == 0:
            return None
        _write_json(_fetch_all(conn))
        row = conn.execute(
            f"SELECT {FIELDS} FROM records WHERE id = ?", (record_id,)
        ).fetchone()

    return Record.from_dict(dict(row)).to_dict() if row else None


def delete_record(record_id: str) -> bool:
    with _LOCK, _connect() as conn:
        cursor = conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
        if cursor.rowcount == 0:
            return False
        _write_json(_fetch_all(conn))
    return True


def upsert_records(records) -> int:
    payload = [Record.from_dict(item).to_dict() for item in records]
    if not payload:
        return 0
    with _LOCK, _connect() as conn:
        _insert_many(conn, payload)
        _write_json(_fetch_all(conn))
    return len(payload)


def _date_param(value) -> str | None:
    if value is None or value == "":
        return None
    if hasattr(value, "strftime"):
        return value.strftime(DATE_FORMAT)
    return str(value)


def query_records(
    start=None,
    end=None,
    rtype=None,
    category=None,
    keyword=None,
    limit=None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    start_value = _date_param(start)
    end_value = _date_param(end)
    if start_value:
        clauses.append("date >= ?")
        params.append(start_value)
    if end_value:
        clauses.append("date <= ?")
        params.append(end_value)
    if rtype and rtype != "all":
        clauses.append("type = ?")
        params.append(rtype)
    if category and category != "all":
        clauses.append("category = ?")
        params.append(category)
    keyword = (keyword or "").strip()
    if keyword:
        clauses.append("note LIKE ?")
        params.append(f"%{keyword}%")

    sql = f"SELECT {FIELDS} FROM records"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY date DESC, created_at DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))

    with _LOCK, _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [Record.from_dict(dict(row)).to_dict() for row in rows]


def storage_info() -> dict[str, str]:
    return {
        "engine": "SQLite3 + JSON Backup",
        "db_file": f"data/{_db_path().name}",
        "data_file": f"data/{_json_path().name}",
    }


init_db()