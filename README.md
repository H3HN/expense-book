# 福大智联 · 简易记账本（前后端分离版）

2026 秋《软件工程与软件工程实践》现场编程作业。

FastAPI 提供 RESTful JSON API 并托管静态前端；前端为原生 HTML + Tailwind CSS + ES Modules + Apache ECharts，**无需 npm、无需打包**。

## 一键启动

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

- 应用：http://127.0.0.1:8000
- 接口文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

## 架构

```
浏览器
  web/index.html          单页外壳
  web/js/api.js           统一 fetch 封装 + 全局状态派发
  web/js/*.js             5 个业务 ES Module 组件
        │  JSON / REST
        ▼
FastAPI  app.py            9 组 API + 静态资源托管
        │
src/    storage.py         JSON 持久化（线程锁 + 原子写）
        stats*.py          统计引擎
        nl_parser.py       自然语言解析
        import_export.py   CSV 导入导出
        models/validator   模型与校验
        ▼
data/records.json          本地数据文件
```

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/config` | 收支类别、类型、货币、今日日期 |
| GET | `/api/records` | 筛选记录（type / category / start / end / keyword / limit）+ 全局 totals |
| POST | `/api/records` | 新增记录，校验失败返回 400 |
| PUT | `/api/records/{id}` | 修改记录 |
| DELETE | `/api/records/{id}` | 删除记录 |
| POST | `/api/nl-parse` | 一句话记账，支持 `auto_save` |
| GET | `/api/stats` | 区间 summary / 每日趋势 / 收支类别排行 |
| GET | `/api/export/csv` | 导出 CSV 文件流 |
| POST | `/api/import/csv` | 上传 CSV，按 id 去重合并 |

## 测试

```bash
pytest -q
```

覆盖存储 CRUD 与 `update_record`、统计与区间筛选、自然语言多数字误判、CSV 脏数据过滤，以及全部 FastAPI 接口（TestClient）。当前 43 项全绿。

前端 ECharts 已本地化到 `web/js/vendor/echarts.min.js`，断网演示可正常出图；Tailwind 由 CDN 加速，样式本身为内置 CSS，CDN 失败不影响布局。

启动、13 人分支与提交步骤见 [docs/本地启动与提交清单.md](docs/本地启动与提交清单.md)。

## 目录

| 路径 | 负责人 | 内容 |
| --- | --- | --- |
| `app.py` | 黄俊翔 | FastAPI 路由装配与静态挂载 |
| `src/models.py`、`src/config.py` | 黄炜杰 | 数据模型与配置 |
| `src/nl_parser.py` | 金若曦 | 自然语言记账 |
| `src/import_export.py` | 越长智 | CSV 导出与安全导入 |
| `src/storage.py` | 洪豊幀 | JSON 持久化（含 update） |
| `src/stats.py` | 王世豪 | 收支统计 |
| `src/stats_by_category.py` | 谭段昊 | 类别排行 |
| `web/js/add_expense.js` | 邱福铭 | 支出录入 |
| `web/js/add_income.js` | 王伟浩 | 收入录入 |
| `web/js/records_view.js` | 陈封 | 明细筛选与编辑 |
| `web/js/charts.js` | 陈韦融 | ECharts 图表 |
| `web/js/data_page.js` | 王泽炜 | 导入导出 |
| `tests/` | 邓杰 | 单元与接口测试 |

`src/` 下旧的 Streamlit 组件文件保留为迁移声明，指向对应的前端模块。

## 团队

福大智联 · 第七组 · 13 人，一人一个模块。详见 [docs/分工.md](docs/分工.md)。