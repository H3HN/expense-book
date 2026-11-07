"""记账本存储层：SQLite 主存储 + JSON 全量备份。

对 FastAPI 的调用方式（示例）：
    from src import storage

    record = storage.add_record("2026-11-07", "expense", 25.5, "餐饮", "午饭")
    records = storage.get_all_records()

说明：
1. 数据库固定保存在项目根目录下的 data/records.db；
2. 每次新增、修改、删除后，都会把 records 表的全部数据导出到
   data/records.json，作为可直接查看的双写备份；
3. 每次操作使用独立的 SQLite 连接，避免 FastAPI 多线程下的连接复用问题。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

# 以项目根目录为基准，避免从不同工作目录启动 FastAPI 时数据库路径错乱
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "records.db"
JSON_PATH = DATA_DIR / "records.json"

# 写操作串行执行，保证 SQLite 写入和 JSON 导出的顺序一致
_LOCK = threading.RLock()

# 建表语句：字段与课程作业要求保持一致
SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    date TEXT,
    type TEXT,
    amount REAL,
    category TEXT,
    note TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_records_date ON records(date);
CREATE INDEX IF NOT EXISTS idx_records_type ON records(type);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """打开数据库连接，正常结束时提交，出错时回滚，最后关闭连接。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row  # 查询结果可以按列名转成字典
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _fetch_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """查询全部记录，按日期倒序；同一天内按创建时间倒序。"""
    rows = conn.execute(
        """
        SELECT id, date, type, amount, category, note, created_at
        FROM records
        ORDER BY date DESC, created_at DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _write_json(records: list[dict[str, Any]]) -> None:
    """把全部记录原子地写入 JSON 文件，避免写入中断留下半个文件。"""
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = JSON_PATH.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(JSON_PATH)  # 同目录替换，Windows/Linux 均适用


def init_db() -> None:
    """初始化数据表、索引，并生成一份与数据库一致的 JSON 备份。"""
    with _LOCK, _connect() as conn:
        conn.executescript(SCHEMA)
        _write_json(_fetch_all(conn))


def export_json() -> list[dict[str, Any]]:
    """手动导出全部记录到 JSON；一般由写操作自动调用，也可用于修复备份。"""
    with _LOCK, _connect() as conn:
        records = _fetch_all(conn)
        _write_json(records)
        return records


def add_record(
    date: str,
    type: str,
    amount: float,
    category: str = "",
    note: str = "",
) -> dict[str, Any]:
    """新增一条记录并返回完整记录。

    参数：
        date:     日期，建议使用 "YYYY-MM-DD"
        type:     类型，例如 "income"（收入）或 "expense"（支出）
        amount:   金额
        category: 分类
        note:     备注
    """
    record = {
        "id": uuid.uuid4().hex,
        "date": date,
        "type": type,
        "amount": float(amount),
        "category": category,
        "note": note,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    with _LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO records (id, date, type, amount, category, note, created_at)
            VALUES (:id, :date, :type, :amount, :category, :note, :created_at)
            """,
            record,
        )
        _write_json(_fetch_all(conn))

    return record


def get_record(record_id: str) -> dict[str, Any] | None:
    """根据 id 查询一条记录，不存在时返回 None。"""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, date, type, amount, category, note, created_at
            FROM records
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()

    return dict(row) if row else None


def get_all_records() -> list[dict[str, Any]]:
    """查询全部记录。"""
    with _connect() as conn:
        return _fetch_all(conn)


def update_record(
    record_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """按 id 更新记录，支持只传需要修改的字段；记录不存在时返回 None。

    updates 中可以包含 date、type、amount、category、note；
    id 和 created_at 由系统维护，不允许通过此函数修改。
    """
    allowed_fields = {"date", "type", "amount", "category", "note"}
    fields = {key: value for key, value in updates.items() if key in allowed_fields}

    # 没有需要更新的字段时，直接返回原记录
    if not fields:
        return get_record(record_id)

    if "amount" in fields:
        fields["amount"] = float(fields["amount"])

    # 字段名来自上面的白名单，值全部使用 ? 参数，避免 SQL 注入
    set_sql = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [record_id]

    with _LOCK, _connect() as conn:
        cursor = conn.execute(
            f"UPDATE records SET {set_sql} WHERE id = ?",
            values,
        )
        if cursor.rowcount == 0:
            return None

        _write_json(_fetch_all(conn))
        row = conn.execute(
            """
            SELECT id, date, type, amount, category, note, created_at
            FROM records
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()

    return dict(row) if row else None


def delete_record(record_id: str) -> bool:
    """按 id 删除记录；删除成功返回 True，记录不存在返回 False。"""
    with _LOCK, _connect() as conn:
        cursor = conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
        if cursor.rowcount == 0:
            return False

        _write_json(_fetch_all(conn))

    return True


# 模块首次导入时自动初始化，FastAPI 直接 import 即可使用
init_db()
