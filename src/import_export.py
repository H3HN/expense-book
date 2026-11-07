import csv
import io

from src.models import Record

FIELDS = ["id", "date", "type", "amount", "category", "note", "created_at"]


def to_csv(records):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        row = dict(record)
        row["amount"] = round(float(row.get("amount", 0)), 2)
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")


def from_csv(file_bytes):
    text = file_bytes.decode("utf-8-sig") if isinstance(file_bytes, bytes) else str(file_bytes)
    reader = csv.DictReader(io.StringIO(text))
    records = []
    for row in reader:
        if not row.get("date") or not row.get("amount"):
            continue
        row.setdefault("type", "expense")
        records.append(Record.from_dict(row).to_dict())
    return records