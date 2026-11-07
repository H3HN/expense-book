from datetime import datetime

from src.config import DATE_FORMAT, EXPENSE_CATEGORIES, INCOME_CATEGORIES, RECORD_TYPES


def validate_record(data):
    errors = []

    date_text = str(data.get("date", "")).strip()
    try:
        datetime.strptime(date_text, DATE_FORMAT)
    except ValueError:
        errors.append("日期格式应为 YYYY-MM-DD")

    try:
        amount = float(data.get("amount", 0))
        if amount <= 0:
            errors.append("金额必须大于 0")
    except (TypeError, ValueError):
        errors.append("金额必须是数字")

    record_type = data.get("type")
    if record_type not in RECORD_TYPES:
        errors.append("类型只能是 expense 或 income")
    else:
        allowed = EXPENSE_CATEGORIES if record_type == "expense" else INCOME_CATEGORIES
        if data.get("category") not in allowed:
            errors.append("类别不在允许范围内")

    note = str(data.get("note", ""))
    if len(note) > 100:
        errors.append("备注不能超过 100 字")

    return errors