import math
from datetime import datetime

from src.config import (
    DATE_FORMAT,
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    MAX_NOTE_LENGTH,
    RECORD_TYPES,
)


def _to_amount(value):
    if value is None or isinstance(value, bool):
        raise ValueError("金额必须是数字")
    if isinstance(value, str):
        value = value.strip().replace("¥", "").replace("￥", "").replace(",", "")
        if not value:
            raise ValueError("金额必须是数字")
    amount = float(value)
    if math.isnan(amount) or math.isinf(amount):
        raise ValueError("金额必须是有效数字")
    return amount


def validate_record(data):
    errors = []

    if not isinstance(data, dict):
        return ["记录必须是对象"]

    date_text = str(data.get("date", "")).strip()
    try:
        datetime.strptime(date_text, DATE_FORMAT)
    except ValueError:
        errors.append("日期格式应为 YYYY-MM-DD")

    try:
        amount = _to_amount(data.get("amount"))
        if amount <= 0:
            errors.append("金额必须大于 0")
        elif round(amount, 2) <= 0:
            errors.append("金额必须大于 0.01")
    except (TypeError, ValueError):
        errors.append("金额必须是数字")

    record_type = data.get("type")
    if record_type not in RECORD_TYPES:
        errors.append("类型只能是 expense 或 income")
    else:
        allowed = EXPENSE_CATEGORIES if record_type == "expense" else INCOME_CATEGORIES
        if data.get("category") not in allowed:
            errors.append("类别不在允许范围内")

    note = str(data.get("note", "") or "")
    if len(note) > MAX_NOTE_LENGTH:
        errors.append(f"备注不能超过 {MAX_NOTE_LENGTH} 字")

    return errors