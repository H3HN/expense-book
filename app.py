from datetime import date, datetime
from typing import Optional

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from src import storage
from src.config import (
    CURRENCY,
    DATE_FORMAT,
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    RECORD_TYPES,
    STORAGE_ENGINE,
    WEB_DIR,
)
from src.import_export import from_csv, to_csv
from src.models import new_record
from src.nl_parser import parse_text
from src.stats import daily_totals, filter_by_range, summary, totals
from src.stats_by_category import by_category
from src.validator import validate_record

app = FastAPI(
    title="福大智联 · 简易记账本 API",
    description="2026 秋软件工程现场编程 · FastAPI + SQLite3 + 原生 ES Modules",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_day(value, field):
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(str(value), DATE_FORMAT).date()
    except ValueError:
        raise HTTPException(status_code=400, detail={"errors": [f"{field} 格式应为 YYYY-MM-DD"]})


def _sort_records(records):
    return sorted(
        records,
        key=lambda r: (str(r.get("date", "")), str(r.get("created_at", ""))),
        reverse=True,
    )


def _all_totals():
    return totals(storage.load_records())


def _storage_meta():
    persisted = storage.storage_info()
    return {
        "engine": STORAGE_ENGINE,
        "db_file": persisted["db_file"],
        "data_file": persisted["data_file"],
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "expense-book",
        "version": app.version,
        "engine": STORAGE_ENGINE,
    }


@app.get("/api/config")
def get_config():
    meta = _storage_meta()
    return {
        "expense_categories": EXPENSE_CATEGORIES,
        "income_categories": INCOME_CATEGORIES,
        "record_types": RECORD_TYPES,
        "currency": CURRENCY,
        "today": date.today().strftime(DATE_FORMAT),
        "date_format": DATE_FORMAT,
        "engine": meta["engine"],
        "db_file": meta["db_file"],
        "storage": meta,
    }


@app.get("/api/records")
def list_records(
    type: Optional[str] = Query(None, description="expense / income / all"),
    category: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=1000),
):
    start_day = _parse_day(start, "start")
    end_day = _parse_day(end, "end")
    if start_day and end_day and start_day > end_day:
        raise HTTPException(status_code=400, detail={"errors": ["起始日期不能晚于结束日期"]})

    records = _sort_records(
        filter_by_range(storage.load_records(), start_day, end_day, type, category, keyword)
    )
    if limit:
        records = records[:limit]
    return {
        "records": records,
        "count": len(records),
        "totals": _all_totals(),
        "storage": _storage_meta(),
    }


@app.post("/api/records", status_code=201)
def create_record(payload: dict = Body(...)):
    errors = validate_record(payload)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    record = new_record(
        payload["date"],
        payload["type"],
        payload["amount"],
        payload["category"],
        payload.get("note", ""),
    )
    saved = storage.add_record(record)
    return {"record": saved, "totals": _all_totals()}


@app.put("/api/records/{record_id}")
def update_record(record_id: str, payload: dict = Body(...)):
    current = storage.get_record(record_id)
    if current is None:
        raise HTTPException(status_code=404, detail={"errors": ["记录不存在"]})

    merged = dict(current)
    for key in ("date", "type", "amount", "category", "note"):
        if key in payload:
            merged[key] = payload[key]

    errors = validate_record(merged)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    updated = storage.update_record(record_id, merged)
    if updated is None:
        raise HTTPException(status_code=404, detail={"errors": ["记录不存在"]})
    return {"record": updated, "totals": _all_totals()}


@app.delete("/api/records/{record_id}")
def delete_record(record_id: str):
    if not storage.delete_record(record_id):
        raise HTTPException(status_code=404, detail={"errors": ["记录不存在"]})
    return {"deleted": record_id, "totals": _all_totals()}


@app.post("/api/nl-parse")
def nl_parse(payload: dict = Body(...)):
    text = str(payload.get("text", ""))
    auto_save = bool(payload.get("auto_save", False))
    parsed = parse_text(text)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail={"errors": ["没能识别出有效金额，试试「午饭 25」或「兼职 300 元」"]},
        )

    parsed["date"] = str(payload.get("date") or date.today().strftime(DATE_FORMAT))
    if not auto_save:
        return {"parsed": parsed, "saved": None, "totals": _all_totals()}

    errors = validate_record(parsed)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    record = new_record(
        parsed["date"], parsed["type"], parsed["amount"], parsed["category"], parsed["note"]
    )
    saved = storage.add_record(record)
    return {"parsed": parsed, "saved": saved, "totals": _all_totals()}


@app.get("/api/stats")
def get_stats(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    start_day = _parse_day(start, "start")
    end_day = _parse_day(end, "end")
    if start_day and end_day and start_day > end_day:
        raise HTTPException(status_code=400, detail={"errors": ["起始日期不能晚于结束日期"]})

    records = storage.load_records()
    scoped = filter_by_range(records, start_day, end_day)
    return {
        "summary": summary(scoped),
        "daily_totals": daily_totals(scoped),
        "expense_by_category": by_category(scoped, "expense"),
        "income_by_category": by_category(scoped, "income"),
        "totals": totals(records),
        "range": {
            "start": start_day.strftime(DATE_FORMAT) if start_day else None,
            "end": end_day.strftime(DATE_FORMAT) if end_day else None,
            "count": len(scoped),
        },
    }


@app.get("/api/export/csv")
def export_csv():
    data = to_csv(storage.load_records())
    headers = {"Content-Disposition": 'attachment; filename="records.csv"'}
    return Response(content=data, media_type="text/csv; charset=utf-8", headers=headers)


@app.post("/api/import/csv")
async def import_csv(file: UploadFile = File(...)):
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail={"errors": ["只支持 .csv 文件"]})

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail={"errors": ["文件为空"]})

    incoming = from_csv(raw)
    if not incoming:
        raise HTTPException(status_code=400, detail={"errors": ["没有通过校验的有效记录"]})

    storage.upsert_records(incoming)
    merged = storage.load_records()
    return {
        "imported": len(incoming),
        "total": len(merged),
        "totals": totals(merged),
        "engine": STORAGE_ENGINE,
    }


@app.get("/", include_in_schema=False)
def index():
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        {
            "message": "前端尚未部署，可访问 /docs 查看接口文档",
            "docs": "/docs",
            "api_prefix": "/api",
        }
    )


for _mount_path, _subdir in (("/js", "js"), ("/assets", "assets")):
    _target = WEB_DIR / _subdir
    if _target.is_dir():
        app.mount(_mount_path, StaticFiles(directory=_target), name=_subdir)