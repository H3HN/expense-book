from dataclasses import dataclass, asdict
from datetime import datetime
from uuid import uuid4


@dataclass
class Record:
    id: str
    date: str
    type: str
    amount: float
    category: str
    note: str = ""
    created_at: str = ""

    def to_dict(self):
        data = asdict(self)
        data["amount"] = round(float(self.amount), 2)
        return data

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=str(data.get("id") or uuid4().hex[:12]),
            date=str(data.get("date", "")),
            type=str(data.get("type", "expense")),
            amount=float(data.get("amount", 0)),
            category=str(data.get("category", "其他")),
            note=str(data.get("note", "")),
            created_at=str(data.get("created_at", "")),
        )


def new_record(date, type, amount, category, note=""):
    return Record(
        id=uuid4().hex[:12],
        date=date,
        type=type,
        amount=round(float(amount), 2),
        category=category,
        note=(note or "").strip(),
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )