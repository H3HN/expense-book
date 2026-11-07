# 福大智联 · 简易记账本

2026 秋《软件工程与软件工程实践》现场编程作业。

基于 **FastAPI + SQLite3 + 原生 ES Modules** 的前后端分离记账本：后端 RESTful API 与静态托管，前端零构建（无 npm / webpack / vite）。数据以 SQLite 为主存储，自动同步 JSON 快照备份。

## 一键启动

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

- 应用：http://127.0.0.1:8000
- 接口文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

首次启动会自动把 `data/records.json` 中的演示数据迁移进 `data/records.db`，git clone 后即有数据。

## 架构

```
浏览器
  web/index.html            3页外壳（陈韦融）
  web/js/api.js             统一 fetch 封装 + 全局状态派发（王泽炜）
  web/js/*.js               5 个业务 ES Module 组件
        │  JSON / REST
        ▼
FastAPI  app.py             9 组 API + 静态资源托管（黄俊翔）
        │
src/    storage.py          SQLite3 持久化 + JSON 双写备份（越长智）
        stats*.py           统计引擎（王世豪 / 谭段昊）
        nl_parser.py        自然语言解析（王伟浩）
        import_export.py    CSV 导入导出（陈封）
        models/config       模型与配置（洪豊幀）
        validator.py        字段校验（邓杰）
        ▼
data/records.db  ──同步──▶  data/records.json
```

存储表结构：

```sql
CREATE TABLE records (
  id TEXT PRIMARY KEY, date TEXT, type TEXT, amount REAL,
  category TEXT, note TEXT, created_at TEXT
);
CREATE INDEX idx_records_date ON records(date);
CREATE INDEX idx_records_type ON records(type);
```

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/config` | 类别、类型、货币、存储引擎信息 |
| GET | `/api/records` | 筛选记录 + 全局 totals |
| POST | `/api/records` | 新增记录，校验失败 400 |
| PUT | `/api/records/{id}` | 修改记录 |
| DELETE | `/api/records/{id}` | 删除记录 |
| POST | `/api/nl-parse` | 一句话记账，支持 `auto_save` |
| GET | `/api/stats` | 区间汇总 / 每日趋势 / 类别排行 |
| GET | `/api/export/csv` | 导出 CSV 文件流 |
| POST | `/api/import/csv` | 上传 CSV，`INSERT OR REPLACE` 合并 |

## 测试

```bash
pytest -q
```

当前 **58 项全绿**，覆盖 SQLite 建表与索引、JSON 种子迁移、双写备份、CRUD 与 `update_record`、区间筛选、多数字 NL 解析、CSV 脏数据过滤，以及全部 FastAPI 接口（TestClient）。

前端 ECharts 已本地化到 `web/js/vendor/echarts.min.js`，断网也能出图；Tailwind 由 CDN 加速，关键样式内置，CDN 失败不影响布局。

启动、13 人分支与提交步骤见 [docs/本地启动与提交清单.md](docs/本地启动与提交清单.md)。

## 分工

| 姓名 | 学号 | 模块 | 文件 |
| --- | --- | --- | --- |
| 黄俊翔 | 102402125 | FastAPI 路由装配、统筹、演示 | `app.py` |
| 洪豊幀 | 102402124 | 数据模型与配置 | `src/models.py`、`src/config.py` |
| 邓杰 | 102402122 | 数据合法性校验器 | `src/validator.py` |
| 越长智 | 102402143 | SQLite 存储层 + JSON 双写 | `src/storage.py` |
| 谭段昊 | 102402133 | 类别排行与占比统计 | `src/stats_by_category.py` |
| 王世豪 | 102402134 | 收支区间统计引擎 | `src/stats.py` |
| 王伟浩 | 102402135 | 自然语言快速记账 | `src/nl_parser.py` |
| 陈封 | 102402119 | CSV 导入导出解析 | `src/import_export.py` |
| 邱福铭 | 102402132 | 单元测试与端到端验收 | `tests/` |
| 陈韦融 | 102402121 | 前端外壳 + ECharts 图表 | `web/index.html`、`web/js/charts.js` |
| 王泽炜 | 102302113 | API 封装 + 数据管理页 | `web/js/api.js`、`web/js/data_page.js` |
| 黄炜杰 | 102402126 | 支出 / 收入录入组件 | `web/js/add_expense.js`、`web/js/add_income.js` |
| 金若曦 | 102402127 | 明细表格、多维筛选、编辑删除 | `web/js/records_view.js` |

完整分工、接口契约与评分表见 [docs/分工.md](docs/分工.md)。
