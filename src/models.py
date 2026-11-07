"""数据模型：一条收支记录 Record（基于 pydantic v2）。

字段与作业需求一一对应：
    id / date / amount / category / remark / type

关于「备注」字段的命名（重要，改之前先看这里）：
    作业需求里叫 remark，而仓库中已经写好的 storage.py、validator.py、
    import_export.py、web 前端和单元测试统一使用历史字段名 note。
    为了让两边的代码都不用改，本模型这样处理：
      1. 模型字段正式名为 remark；
      2. 反序列化时 note / remark / 备注 三种键名都接受（note 优先，
         因为现有模块写入的都是 note）；
      3. to_dict() 同时输出 remark 与 note，二者值始终相同。
    以后若要彻底改名，只需改这些封装点，调用方不受影响。

职责边界：
    本模块只做「类型与格式归一化 + 序列化」，保证 storage 层拿到就能落库；
    金额必须大于 0、类别必须在白名单内等业务规则由 validator.py 负责，
    因此这里允许负数金额（存储层测试也依赖这一点）。
"""

from __future__ import annotations

import json
from datetime import date as date_type, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from src.config import (
    AMOUNT_DECIMAL_PLACES,
    DATE_FORMAT,
    DATETIME_FORMAT,
    DEFAULT_CATEGORY,
    DEFAULT_RECORD_TYPE,
    TYPE_EXPENSE,
    TYPE_INCOME,
)

# 收支类型：只允许这两个值（中文「收入/支出」在归一化阶段就被转换掉）
RecordType = Literal["expense", "income"]

# 类型别名表：兼容中文、大小写、简写，统一归一化成 expense / income
_TYPE_ALIASES = {
    "expense": TYPE_EXPENSE,
    "支出": TYPE_EXPENSE,
    "消费": TYPE_EXPENSE,
    "out": TYPE_EXPENSE,
    "income": TYPE_INCOME,
    "收入": TYPE_INCOME,
    "in": TYPE_INCOME,
}

# 金额里可能混进来的货币符号、千分位逗号和空格，解析前先去掉
_AMOUNT_NOISE = str.maketrans("", "", "¥￥,， \t")

# 日期可能出现的几种写法，归一化成 DATE_FORMAT
_DATE_FORMATS = (DATE_FORMAT, "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d")


def new_id() -> str:
    """生成 12 位十六进制记录 id，例如 3f9a1c7b2e40。"""
    return uuid4().hex[:12]


def now_text() -> str:
    """当前时间字符串，格式见 config.DATETIME_FORMAT。"""
    return datetime.now().strftime(DATETIME_FORMAT)


class Record(BaseModel):
    """一条收支记录，可序列化为 dict，也可从 dict 还原。"""

    # extra="ignore"：忽略 dict 里多余的键，方便导入脏数据时不报错
    # populate_by_name=True：既接受别名 note，也接受字段名 remark
    # str_strip_whitespace=True：字符串统一去掉首尾空格
    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    id: str = Field(
        default_factory=new_id,
        description="记录唯一标识，缺省时自动生成",
    )
    date: str = Field(
        default="",
        description="记账日期，格式 YYYY-MM-DD",
    )
    type: RecordType = Field(
        default=DEFAULT_RECORD_TYPE,
        description="记录类型：expense 支出 / income 收入",
    )
    amount: float = Field(
        default=0.0,
        description="金额（正数），收入还是支出由 type 决定",
    )
    category: str = Field(
        default=DEFAULT_CATEGORY,
        description="类别，例如 饮食 / 交通 / 工资",
    )
    remark: str = Field(
        default="",
        validation_alias=AliasChoices("note", "remark", "备注"),
        description="备注（历史字段名 note）",
    )
    created_at: str = Field(
        default="",
        description="创建时间，格式 YYYY-MM-DD HH:MM:SS",
    )

    # ------------------------------------------------------------------
    # 归一化：把脏输入转成合法值；业务规则留给 validator.py
    # ------------------------------------------------------------------
    @field_validator("id", mode="before")
    @classmethod
    def _fill_id(cls, value: Any) -> str:
        """空 id 自动补一个，保证每条记录都有主键。"""
        text = "" if value is None else str(value).strip()
        return text or new_id()

    @field_validator("date", mode="before")
    @classmethod
    def _normalize_date(cls, value: Any) -> str:
        """date / datetime / 多种日期字符串统一成 YYYY-MM-DD。"""
        if value is None or value == "":
            return ""
        if isinstance(value, datetime):
            return value.strftime(DATE_FORMAT)
        if isinstance(value, date_type):
            return value.strftime(DATE_FORMAT)
        text = str(value).strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(text, fmt).strftime(DATE_FORMAT)
            except ValueError:
                continue
        return text  # 无法识别就原样保留，由 validator.py 报「日期格式错误」

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: Any) -> str:
        """大小写、中文别名统一成 expense / income，无法识别时按支出处理。"""
        text = str(value or DEFAULT_RECORD_TYPE).strip().lower()
        return _TYPE_ALIASES.get(text, DEFAULT_RECORD_TYPE)

    @field_validator("amount", mode="before")
    @classmethod
    def _normalize_amount(cls, value: Any) -> float:
        """允许 "¥12.50"、"1,234.5" 这类输入，转成 float。"""
        if value is None or value == "":
            return 0.0
        if isinstance(value, bool):  # bool 是 int 的子类，单独挡掉
            raise ValueError("金额必须是数字")
        if isinstance(value, str):
            value = value.translate(_AMOUNT_NOISE).strip()
            if not value:
                return 0.0
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"金额必须是数字，当前值：{value!r}") from exc

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: Any) -> str:
        """类别为空时兜底成「其他」，避免写出空类别记录。"""
        text = "" if value is None else str(value).strip()
        return text or DEFAULT_CATEGORY

    @field_validator("remark", "created_at", mode="before")
    @classmethod
    def _to_text(cls, value: Any) -> str:
        """备注、创建时间统一转字符串，None 视为空串。"""
        return "" if value is None else str(value).strip()

    # ------------------------------------------------------------------
    # 序列化 / 反序列化
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """转成可直接 json.dump 的普通字典。

        返回值同时包含 remark（模型正式字段）与 note（历史字段名），
        这样 storage.py、CSV 导入导出、前端和现有测试都不用改动。
        """
        data = self.model_dump()
        data["amount"] = round(float(self.amount), AMOUNT_DECIMAL_PLACES)
        data["note"] = data["remark"]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Record":
        """从 dict 还原一条记录。

        - data 为 None 时返回一条空记录（字段全取默认值）；
        - 多余的键会被忽略（extra="ignore"）；
        - 缺 id 时自动生成，缺 category 时补「其他」。
        """
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise TypeError("Record.from_dict 需要一个 dict")
        return cls.model_validate(data)

    def to_json(self) -> str:
        """序列化成 JSON 字符串（UTF-8 中文不转义），便于写入文件。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    # ------------------------------------------------------------------
    # 便捷属性（不参与序列化）
    # ------------------------------------------------------------------
    @property
    def note(self) -> str:
        """历史字段名别名，便于旧代码用 record.note 读备注。"""
        return self.remark

    @property
    def is_income(self) -> bool:
        """是否为收入记录。"""
        return self.type == TYPE_INCOME

    @property
    def signed_amount(self) -> float:
        """带符号金额：收入为正、支出为负，供统计模块直接累加。"""
        value = self.amount if self.is_income else -self.amount
        return round(float(value), AMOUNT_DECIMAL_PLACES)


def new_record(
    date: str,
    type: str,
    amount: Any,
    category: str,
    note: str = "",
    *,
    remark: str | None = None,
) -> Record:
    """构造一条新记录：自动补 id 与创建时间。

    参数名沿用历史写法 note，同时支持关键字 remark（两者只取其一）。
    """
    return Record(
        date=date,
        type=type,
        amount=amount,
        category=category,
        note=note if remark is None else remark,
        created_at=now_text(),
    )
