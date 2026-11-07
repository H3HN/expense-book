import csv
import io

from src.models import Record
from src.validator import validate_record

FIELDS = ["id", "date", "type", "amount", "category", "note", "created_at"]


def to_csv(records):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        row = dict(record)
        try:
            row["amount"] = round(float(row.get("amount", 0)), 2)
        except (TypeError, ValueError):
            row["amount"] = 0
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")


def from_csv(file_bytes):
    if isinstance(file_bytes, bytes):
        text = file_bytes.decode("utf-8-sig", errors="replace")
    else:
        text = str(file_bytes)

    reader = csv.DictReader(io.StringIO(text))
    records = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        candidate = {key: (value.strip() if isinstance(value, str) else value) for key, value in row.items()}
        candidate.setdefault("type", "expense")

        errors = validate_record(candidate)
        if errors:
            continue
        record = Record.from_dict(candidate).to_dict()
        records.append(record)
    return records