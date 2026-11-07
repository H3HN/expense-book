import json
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

from src.config import DATA_DIR, DATA_FILE, DB_FILE, DATE_FORMAT
from src.models import Record

_LOCK = threading.RLock()

_FIELDS = "id, date, type, amount, category, note, created_at"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    type TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_records_date ON records(date);
CREATE INDEX IF NOT EXISTS idx_records_type ON records(type);
"""


def _data_file():
    return Path(DATA_FILE)


def _db_file():
    data_file = Path(DATA_FILE)
    configured = Path(DB_FILE)
    if configured.parent == data_file.parent:
        return configured
    return data_file.with_name("records.db")


def _ensure():
    data_file = _data_file()
    data_file.parent.mkdir(parents=True, exist_ok=True)
    if not data_file.exists():
        data_file.write_text("[]", encoding="utf-8")
    db_file = _db_file()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    return data_file, db_file


def _connect(db_file):
    conn = sqlite3.connect(str(db_file), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_schema(conn):
    conn.executescript(_SCHEMA)
    conn.commit()


def _read_json(data_file):
    try:
        raw = json.loads(data_file.read_text(encoding="utf-8") or "[]")
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    return [Record.from_dict(item).to_dict() for item in raw if isinstance(item, dict)]


def _row(record):
    return (
        str(record.get("id", "")),
        str(record.get("date", "")),
        str(record.get("type", "expense")),
        float(record.get("amount", 0)),
        str(record.get("category", "其他")),
        str(record.get("note", "") or ""),
        str(record.get("created_at", "") or ""),
    )


def _insert_many(conn, records):
    conn.executemany(
        f"INSERT OR REPLACE INTO records ({_FIELDS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [_row(record) for record in records],
    )


def _fetch_all(conn):
    rows = conn.execute(f"SELECT {_FIELDS} FROM records ORDER BY rowid ASC").fetchall()
    return [Record.from_dict(dict(row)).to_dict() for row in rows]


def _fetch_one(conn, record_id):
    row = conn.execute(f"SELECT {_FIELDS} FROM records WHERE id = ?", (record_id,)).fetchone()
    return Record.from_dict(dict(row)).to_dict() if row else None


def _bootstrap(conn, data_file):
    count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    if count:
        return
    seeds = _read_json(data_file)
    if not seeds:
        return
    with conn:
        _insert_many(conn, seeds)


def _write_snapshot(records, data_file):
    tmp = data_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(data_file)


def load_records():
    with _LOCK:
        data_file, db_file = _ensure()
        with closing(_connect(db_file)) as conn:
            _init_schema(conn)
            _bootstrap(conn, data_file)
            return _fetch_all(conn)


def save_records(records):
    payload = [Record.from_dict(item).to_dict() for item in records]
    with _LOCK:
        data_file, db_file = _ensure()
        with closing(_connect(db_file)) as conn:
            _init_schema(conn)
            with conn:
                conn.execute("DELETE FROM records")
                _insert_many(conn, payload)
            _write_snapshot(payload, data_file)


def add_record(record):
    data = record.to_dict() if isinstance(record, Record) else Record.from_dict(record).to_dict()
    with _LOCK:
        data_file, db_file = _ensure()
        with closing(_connect(db_file)) as conn:
            _init_schema(conn)
            _bootstrap(conn, data_file)
            with conn:
                conn.execute(
                    f"INSERT OR REPLACE INTO records ({_FIELDS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    _row(data),
                )
            _write_snapshot(_fetch_all(conn), data_file)
    return data


def update_record(record_id, new_data):
    if not isinstance(new_data, dict):
        return None
    with _LOCK:
        data_file, db_file = _ensure()
        with closing(_connect(db_file)) as conn:
            _init_schema(conn)
            _bootstrap(conn, data_file)
            current = _fetch_one(conn, record_id)
            if current is None:
                return None
            merged = dict(current)
            for key in ("date", "type", "amount", "category", "note"):
                if key in new_data and new_data[key] is not None:
                    merged[key] = new_data[key]
            merged["id"] = record_id
            merged["created_at"] = current.get("created_at", "")
            updated = Record.from_dict(merged).to_dict()
            with conn:
                conn.execute(
                    "UPDATE records SET date = ?, type = ?, amount = ?, category = ?, note = ? WHERE id = ?",
                    (
                        updated["date"],
                        updated["type"],
                        updated["amount"],
                        updated["category"],
                        updated["note"],
                        record_id,
                    ),
                )
            _write_snapshot(_fetch_all(conn), data_file)
            return updated


def delete_record(record_id):
    with _LOCK:
        data_file, db_file = _ensure()
        with closing(_connect(db_file)) as conn:
            _init_schema(conn)
            _bootstrap(conn, data_file)
            with conn:
                cursor = conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
            if cursor.rowcount == 0:
                return False
            _write_snapshot(_fetch_all(conn), data_file)
            return True


def upsert_records(records):
    payload = [Record.from_dict(item).to_dict() for item in records]
    if not payload:
        return 0
    with _LOCK:
        data_file, db_file = _ensure()
        with closing(_connect(db_file)) as conn:
            _init_schema(conn)
            _bootstrap(conn, data_file)
            with conn:
                _insert_many(conn, payload)
            _write_snapshot(_fetch_all(conn), data_file)
    return len(payload)


def get_record(record_id):
    with _LOCK:
        data_file, db_file = _ensure()
        with closing(_connect(db_file)) as conn:
            _init_schema(conn)
            _bootstrap(conn, data_file)
            return _fetch_one(conn, record_id)


def _date_param(value):
    if value is None or value == "":
        return None
    if hasattr(value, "strftime"):
        return value.strftime(DATE_FORMAT)
    return str(value)


def query_records(start=None, end=None, rtype=None, category=None, keyword=None, limit=None):
    clauses = []
    params = []

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

    sql = f"SELECT {_FIELDS} FROM records"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY date DESC, created_at DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))

    with _LOCK:
        data_file, db_file = _ensure()
        with closing(_connect(db_file)) as conn:
            _init_schema(conn)
            _bootstrap(conn, data_file)
            rows = conn.execute(sql, params).fetchall()
            return [Record.from_dict(dict(row)).to_dict() for row in rows]


def storage_info():
    _, db_file = _ensure()
    return {
        "engine": "SQLite3 + JSON Backup",
        "db_file": f"data/{db_file.name}",
        "data_file": f"data/{_data_file().name}",
    }