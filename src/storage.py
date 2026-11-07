import json

from src.config import DATA_DIR, DATA_FILE
from src.models import Record


def _ensure_file():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text("[]", encoding="utf-8")


def load_records():
    _ensure_file()
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8") or "[]")
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    return [Record.from_dict(item).to_dict() for item in raw if isinstance(item, dict)]


def save_records(records):
    _ensure_file()
    payload = [Record.from_dict(item).to_dict() for item in records]
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)


def add_record(record):
    data = record.to_dict() if isinstance(record, Record) else Record.from_dict(record).to_dict()
    records = load_records()
    records.append(data)
    save_records(records)
    return data


def delete_record(record_id):
    records = load_records()
    remain = [item for item in records if item.get("id") != record_id]
    if len(remain) == len(records):
        return False
    save_records(remain)
    return True