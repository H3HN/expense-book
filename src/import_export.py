"""CSV 导入导出模块（负责人：陈封 · 102402119）。

职责边界
--------
只做“CSV 文本 <-> 记录字典”的转换，不直接碰数据库：

- ``to_csv`` 把记录列表编码成 UTF-8 BOM 的 CSV 字节流，供 ``/api/export/csv`` 下载；
- ``from_csv`` 把上传的 CSV 清洗、校验、过滤后交给 ``/api/import/csv`` 合并入库。

设计要点
--------
1. 固定 7 列表头 ``id,date,type,amount,category,note,created_at``，UTF-8 BOM +
   CRLF 行尾，Excel 双击即可打开且中文不乱码。
2. 脏行整行丢弃：金额非数字 / 小于等于 0、日期非法、类别越界、备注超长等，
   一律不进入结果；``parse_csv`` 还会给出每一行的跳过原因。
3. 合法行往返不丢字段：``from_csv(to_csv(rows))`` 保留 id、日期、类型、金额、
   类别、备注、创建时间，导出的文件可以直接当备份再导入。
4. 常见脏格式兜底：GB18030 / UTF-16 编码、中文或大小写表头、带单位表头、
   ``2026/11/07``、``2026年11月7日``、Excel 日期序列号、``¥1,234.50``、全角数字。
5. 去重：同一文件里 id 相同的行只保留最后一条；没有 id 的行按内容指纹生成
   稳定 id（同文件内重复内容自动加序号），于是真实重复的两笔不会丢，
   同一份 CSV 重复导入也不会重复记账（配合存储层 ``INSERT OR REPLACE``）。
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, datetime, timedelta

from src.config import DATE_FORMAT
from src.models import Record
from src.validator import validate_record

# 对外冻结的列顺序，导出表头与解析结果都以此为准。
FIELDS = ["id", "date", "type", "amount", "category", "note", "created_at"]

# 表头别名（已做小写、去空格、去单位处理）。导入时中英文表头都能识别。
_HEADER_ALIASES = {
    "id": ("id", "编号", "序号", "记录id", "记录编号", "recordid", "record_id"),
    "date": ("date", "日期", "记账日期", "交易日期", "消费日期", "时间"),
    "type": ("type", "类型", "收支", "收支类型", "账目类型", "记账类型"),
    "amount": ("amount", "金额", "数额", "钱数", "价格", "花费"),
    "category": ("category", "类别", "分类", "类目", "科目"),
    "note": ("note", "备注", "说明", "摘要", "注释", "描述"),
    "created_at": ("created_at", "createdat", "创建时间", "录入时间", "记录时间"),
}
_HEADER_LOOKUP = {
    alias: field for field, aliases in _HEADER_ALIASES.items() for alias in aliases
}

# 收支类型的中英文别名，统一归一化成 expense / income。
_TYPE_ALIASES = {
    "expense": {"expense", "支出", "花费", "消费", "支", "out", "付款"},
    "income": {"income", "收入", "进账", "入账", "收", "in", "收款"},
}

_ISO_DATE_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")
_CN_DATE_RE = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日?$")
_AMOUNT_PREFIX_RE = re.compile(r"^(?:人民币|rmb|cny)", re.IGNORECASE)
_AMOUNT_SUFFIX_RE = re.compile(r"(?:元|块|圆|人民币|rmb|cny)(?:整|正)?$", re.IGNORECASE)
_TIME_PART_RE = re.compile(r"[ T]")

# 无表头 CSV 的兜底列布局：按列数推断字段顺序（仅在没有可识别表头时启用）。
_POSITIONAL_LAYOUTS = {
    7: tuple(FIELDS),
    6: ("date", "type", "amount", "category", "note", "created_at"),
    5: ("date", "type", "amount", "category", "note"),
    4: ("date", "type", "amount", "category"),
}
_POSITIONAL_WITH_ID_6 = ("id", "date", "type", "amount", "category", "note")


def _clean_cell(value):
    """单元格转字符串：去 BOM、去首尾空白，None 视为空串。"""
    if value is None:
        return ""
    return str(value).replace("\ufeff", "").strip()


def _decode(source):
    """把 bytes / 文件对象 / str 统一成文本。

    Excel 在中文 Windows 下常把 CSV 存成 GB18030，这里按
    UTF-16 BOM -> UTF-8 BOM -> GB18030 -> UTF-8 替换模式 依次尝试。
    """
    if source is None:
        return ""
    if hasattr(source, "read"):
        source = source.read()
    if isinstance(source, str):
        return source

    raw = bytes(source)
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return raw.decode("utf-16")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8-sig", errors="replace")


def _normalize_header(value):
    """表头归一化：全角转半角、小写、去空格、去掉“（元）”“：”这类装饰。"""
    text = unicodedata.normalize("NFKC", _clean_cell(value)).lower()
    text = re.sub(r"\s+", "", text)
    previous = None
    while previous != text:
        previous = text
        text = text.strip(":：*")
        text = re.sub(r"\([^)]*\)$", "", text)
    return text


def _map_header(row):
    """把表头行映射成 {字段名: 列下标}，同一字段取第一次出现的列。"""
    mapping = {}
    for index, cell in enumerate(row):
        field = _HEADER_LOOKUP.get(_normalize_header(cell))
        if field and field not in mapping:
            mapping[field] = index
    return mapping


def _split_header(rows):
    """拆出表头与数据行。

    Returns:
        (mapping, data_rows, first_row_number)
        mapping 为 None 表示没有识别到表头，按无表头模式处理。
    """
    for index, row in enumerate(rows):
        if not any(_clean_cell(cell) for cell in row):
            continue
        mapping = _map_header(row)
        recognized = len(mapping)
        if recognized >= 2 and ("date" in mapping or "amount" in mapping):
            return mapping, rows[index + 1 :], index + 2
        return None, rows[index:], index + 1
    return None, [], 1


def _looks_like_date(value):
    text = unicodedata.normalize("NFKC", _clean_cell(value))
    if not text:
        return False
    head = _TIME_PART_RE.split(text, maxsplit=1)[0]
    if _ISO_DATE_RE.match(head) or _CN_DATE_RE.match(head):
        return True
    return bool(re.fullmatch(r"\d{8}", text))


def _positional_layout(row):
    """没有表头时按列数推断字段顺序，列数不认识则返回 None（整行判脏）。"""
    count = len(row)
    if count == 6:
        if _looks_like_date(row[0]):
            return _POSITIONAL_LAYOUTS[6]
        return _POSITIONAL_WITH_ID_6
    return _POSITIONAL_LAYOUTS.get(count)


def _normalize_date(value):
    """日期归一化成 YYYY-MM-DD。

    兼容 ``2026/11/07``、``2026.11.07``、``2026年11月7日``、``20261107``、
    ``2026-11-07 10:00:00`` 以及 Excel 日期序列号；无法识别时原样返回，
    交给校验器判脏。
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime(DATE_FORMAT)
    if isinstance(value, date):
        return value.strftime(DATE_FORMAT)

    text = unicodedata.normalize("NFKC", str(value)).strip()
    if not text:
        return ""
    text = _TIME_PART_RE.split(text, maxsplit=1)[0]

    matched = _ISO_DATE_RE.match(text) or _CN_DATE_RE.match(text)
    if matched:
        year, month, day = (int(part) for part in matched.groups())
        try:
            return date(year, month, day).strftime(DATE_FORMAT)
        except ValueError:
            return text

    if text.isdigit():
        if len(text) == 8:
            try:
                return datetime.strptime(text, "%Y%m%d").strftime(DATE_FORMAT)
            except ValueError:
                return text
        if len(text) == 5 and 25569 <= int(text) <= 73415:
            # Excel 日期序列号（1970-01-01 ~ 2100-12-31）。限定范围是为了不把
            # “20261”这类脏值误判成 1955 年的日期。
            return (date(1899, 12, 30) + timedelta(days=int(text))).strftime(DATE_FORMAT)
    return text


def _normalize_type(value):
    """收支类型归一化；无法识别时原样返回，交给校验器判脏。"""
    text = unicodedata.normalize("NFKC", _clean_cell(value)).lower()
    for canonical, aliases in _TYPE_ALIASES.items():
        if text in aliases:
            return canonical
    return text


def _normalize_amount(value):
    """金额清洗：去货币符号、千分位、单位、空格，全角数字转半角。

    只做清洗不做判断，正负与非法内容仍交给 ``validate_record``。
    """
    if value is None or isinstance(value, bool):
        return "" if value is None else str(value)
    if isinstance(value, (int, float)):
        return str(value)

    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"\s+", "", text)
    text = _AMOUNT_PREFIX_RE.sub("", text)
    text = _AMOUNT_SUFFIX_RE.sub("", text)
    for symbol in ("¥", "￥", "$", "€"):
        text = text.replace(symbol, "")
    return text.replace(",", "").replace("，", "")


def _normalize_candidate(candidate):
    """把一行原始单元格清洗成待校验的记录字典。"""
    normalized = {
        "date": _normalize_date(candidate.get("date")),
        "amount": _normalize_amount(candidate.get("amount")),
        "category": _clean_cell(candidate.get("category")),
        "note": _clean_cell(candidate.get("note")),
        "created_at": _clean_cell(candidate.get("created_at")),
    }
    # 表里完全没有 type 列时沿用旧行为，默认按支出处理；有列但为空则判脏。
    normalized["type"] = (
        _normalize_type(candidate["type"]) if "type" in candidate else "expense"
    )
    identifier = _clean_cell(candidate.get("id"))
    if identifier:
        normalized["id"] = identifier
    return normalized


def _fingerprint_id(candidate):
    """无 id 的行按内容生成稳定 id，保证重复导入同一份 CSV 不重复记账。"""
    amount = candidate.get("amount")
    try:
        amount_text = f"{float(amount):.2f}"
    except (TypeError, ValueError):
        amount_text = str(amount)
    payload = "\x1f".join(
        [
            str(candidate.get("date", "")),
            str(candidate.get("type", "")),
            amount_text,
            str(candidate.get("category", "")),
            str(candidate.get("note", "")),
            str(candidate.get("created_at", "")),
        ]
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    return f"imp-{digest}"


def _cells_to_candidate(row, columns):
    return {field: row[index] if index < len(row) else "" for field, index in columns.items()}


def _dedupe(records):
    """同一批数据里 id 重复时保留最后一条（导出后再导入的幂等基础）。"""
    unique = {}
    for record in records:
        unique[record["id"]] = record
    return list(unique.values())


def parse_csv(source):
    """解析 CSV 并返回带过滤报告的结果。

    Args:
        source: bytes、str 或**同步**文件对象（如 ``io.BytesIO``）；
            FastAPI 的 ``UploadFile`` 是异步的，请先 ``await file.read()`` 再传入。

    Returns:
        dict: ``records`` 为通过校验的记录列表；``skipped`` 为被丢弃的脏行及原因；
        ``skipped_count``、``duplicates`` 便于接口层展示导入质量。
    """
    text = _decode(source)
    if not text.strip():
        return {"records": [], "valid_rows": 0, "skipped": [], "skipped_count": 0, "duplicates": 0}

    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        # 例如单元格超过 csv 模块默认的字段长度上限，整份文件按“无法解析”处理，
        # 由接口层返回 400，而不是抛出 500。
        return {
            "records": [],
            "valid_rows": 0,
            "skipped": [{"row": 0, "errors": ["CSV 格式错误，无法解析"]}],
            "skipped_count": 1,
            "duplicates": 0,
        }
    mapping, data_rows, first_row_number = _split_header(rows)

    candidates = []
    skipped = []
    occurrences = {}
    for offset, row in enumerate(data_rows):
        row_number = first_row_number + offset
        if not any(_clean_cell(cell) for cell in row):
            continue

        if mapping:
            columns = mapping
        else:
            layout = _positional_layout(row)
            if layout is None:
                skipped.append({"row": row_number, "errors": ["列数不正确，无法对应字段"]})
                continue
            columns = {field: index for index, field in enumerate(layout)}

        candidate = _normalize_candidate(_cells_to_candidate(row, columns))
        errors = validate_record(candidate)
        if errors:
            skipped.append({"row": row_number, "errors": errors})
            continue

        if not candidate.get("id"):
            base = _fingerprint_id(candidate)
            occurrences[base] = occurrences.get(base, 0) + 1
            suffix = occurrences[base]
            candidate["id"] = base if suffix == 1 else f"{base}-{suffix}"
        candidates.append(Record.from_dict(candidate).to_dict())

    records = _dedupe(candidates)
    return {
        "records": records,
        "valid_rows": len(candidates),
        "skipped": skipped,
        "skipped_count": len(skipped),
        "duplicates": len(candidates) - len(records),
    }


def from_csv(source):
    """导入入口：只返回合法记录，脏行静默过滤（细节见 ``parse_csv``）。"""
    return parse_csv(source)["records"]


def _format_amount(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return ""


def _export_row(item):
    if isinstance(item, Record):
        data = item.to_dict()
    elif isinstance(item, dict):
        data = item
    elif hasattr(item, "to_dict"):
        data = item.to_dict()
    else:
        raise TypeError("records 的元素必须是 dict 或 Record")

    return {
        "id": _clean_cell(data.get("id")),
        "date": _normalize_date(data.get("date")),
        "type": _normalize_type(data.get("type")),
        "amount": _format_amount(data.get("amount")),
        "category": _clean_cell(data.get("category")),
        "note": _clean_cell(data.get("note")),
        "created_at": _clean_cell(data.get("created_at")),
    }


def to_csv(records):
    """把记录导出成 UTF-8 BOM 的 CSV 字节流。

    参数可以是 ``Record`` / 字典的列表，也可以是单个 ``Record`` 或字典；
    金额统一保留两位小数，字段顺序固定为 ``FIELDS``。
    """
    if isinstance(records, (dict, Record)):
        records = [records]
    if records is None:
        records = []

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=FIELDS,
        extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()
    for item in records:
        writer.writerow(_export_row(item))
    return buffer.getvalue().encode("utf-8-sig")
