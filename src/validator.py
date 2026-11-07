"""数据合法性校验器。

统一拦截脏日期、脏金额、非法类型/类别与超长备注，供 API 新增/修改、
一句话记账以及 CSV 导入共用。

对外契约：
    validate_record(data) -> list[str]
    返回空列表表示校验通过；返回错误文案列表表示被拦截（最多可同时返回多条）。
"""

import math
from datetime import datetime

from src.config import (
    DATE_FORMAT,
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    MAX_NOTE_LENGTH,
    RECORD_TYPES,
)

# 金额里允许出现的装饰字符：货币符号、千分位逗号、常见人民币单位
_AMOUNT_NOISE = ("¥", "￥", "$", ",", "，", "元", "圆", "块")


def _to_amount(value):
    """把用户输入转成 float；无法转换或非有限数值时抛出 ValueError。
    支持的写法：25、25.5、"25"、" ￥1,200 "、"36元"；
    明确拒绝：None、bool、空串、NaN、Infinity。
    """
    if value is None or isinstance(value, bool):
        raise ValueError("金额必须是数字")

    if isinstance(value, str):
        text = value.strip()
        for noise in _AMOUNT_NOISE:
            text = text.replace(noise, "")
        text = text.strip()
        if not text:
            raise ValueError("金额必须是数字")
        value = text

    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ValueError("金额必须是数字")

    if math.isnan(amount) or math.isinf(amount):
        raise ValueError("金额必须是数字")
    return amount


def _validate_date(value, errors):
    """日期必须是 YYYY-MM-DD 且真实存在（如 2026-02-30 会被拦截）。"""
    date_text = str(value or "").strip()
    try:
        datetime.strptime(date_text, DATE_FORMAT)
    except ValueError:
        errors.append("日期格式应为 YYYY-MM-DD")


def _validate_amount(value, errors):
    """金额必须是大于 0.01 的有效数字（保留两位小数后仍需大于 0）。"""
    try:
        amount = _to_amount(value)
    except (TypeError, ValueError):
        errors.append("金额必须是数字")
        return

    if amount <= 0:
        errors.append("金额必须大于 0")
    elif round(amount, 2) <= 0:
        errors.append("金额必须大于 0.01")


def _validate_type_and_category(data, errors):
    """类型只能是 expense / income，类别必须落在该类型的类别清单内。"""
    record_type = data.get("type")
    if record_type not in RECORD_TYPES:
        errors.append("类型只能是 expense 或 income")
        return

    allowed = EXPENSE_CATEGORIES if record_type == "expense" else INCOME_CATEGORIES
    if data.get("category") not in allowed:
        errors.append("类别不在允许范围内")


def _validate_note(value, errors):
    """备注可为空，但长度不能超过 MAX_NOTE_LENGTH。"""
    note = str(value or "")
    if len(note) > MAX_NOTE_LENGTH:
        errors.append(f"备注不能超过 {MAX_NOTE_LENGTH} 字")


def validate_record(data):
    """校验一条记录，返回错误列表；空列表代表合法。"""
    if not isinstance(data, dict):
        return ["记录必须是对象"]

    errors = []
    _validate_date(data.get("date"), errors)
    _validate_amount(data.get("amount"), errors)
    _validate_type_and_category(data, errors)
    _validate_note(data.get("note"), errors)
    return errors
