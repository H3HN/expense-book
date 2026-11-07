# 前端改进说明：API 封装与数据管理页（王泽炜）

> 分支：`feat/wangzewei-api-datapage`
> 涉及文件：`web/js/api.js`、`web/js/data_page.js`（均为本人分工模块，未改动其他成员文件）
> 日期：2026-11-07

## 一、改动清单

### 1. 请求超时控制（api.js）

- 新增常量 `REQUEST_TIMEOUT = 10000`（10 秒）。
- `request()` 内部接入 `AbortController`，超时自动中断请求。
- 超时与断网分别提示：
  - 超时：`请求超时，请检查后端是否正常运行`
  - 断连：`无法连接后端，请确认 uvicorn 已启动`
- `request()` 新增可选参数 `timeout`，调用方可以按需覆盖默认值。

### 2. CSV 导出失败可感知（api.js + data_page.js）

- `api.js` 新增 `api.exportCsv(timeout)` 方法：`fetch` 请求 `/api/export/csv`，检查 `response.ok`，成功返回 `Blob`；网络错误、超时、非 2xx 均抛出带中文说明的 `Error`。
- `data_page.js` 导出按钮改为异步流程：`fetch` → `blob` → `URL.createObjectURL` 触发下载，结束后 `revokeObjectURL` 释放内存。
- 导出期间按钮进入 `is-loading` 并禁用，防止重复点击；失败时 `toast` 报错，不再出现"点了没反应 / 浏览器下载到错误页"的情况。
- 原 `api.exportCsvUrl()` 保留，签名不变，不影响其他模块。

### 3. 导入文件大小限制（data_page.js）

- 新增常量 `MAX_IMPORT_SIZE = 5 * 1024 * 1024`（5MB）。
- `importFile()` 在扩展名校验之后增加体积校验：超限文件直接拦截，提示 `文件过大，最大支持 5MB`，状态栏显示实际大小与上限，不再把超大文件直接上传到后端。

### 4. Toast 支持点击关闭（api.js）

- `toast()` 生成的提示条现在可点击手动关闭（`pointer-events: auto`，带"点击关闭"提示）。
- 抽出统一的 `dismiss()` 函数，手动关闭与 2.8s 自动消失共用同一套离场动画，并通过 `removed` 标记防止重复移除 DOM。

## 二、兼容性与边界

- `api.js` 所有对外导出（`api / on / emit / state / refreshApp / toast / formatMoney / formatPercent / escapeHtml / todayString`）**签名与行为保持向后兼容**，陈韦融、黄炜杰、金若曦的模块无需任何改动。
- 仅新增导出 `api.exportCsv`，未删除或修改既有接口。
- 改动均为纯前端增强，不涉及接口契约（docs/分工.md 第三节）变更。

## 三、验证记录

环境：`pip install -r requirements.txt` 后 `uvicorn app:app --port 8000`。

| 用例 | 结果 |
| --- | --- |
| 首页渲染（4 张指标卡、5 个页签、收支双表单） | 通过 |
| 「数据」页渲染（导出按钮、拖拽区） | 通过 |
| 点击「下载 records.csv」：请求 `/api/export/csv` 成功，弹出提示，无错误 | 通过 |
| 控制台无 error 级日志（仅 Tailwind CDN 生产环境警告） | 通过 |

## 四、建议提交拆分

```bash
# api.js 的三处改动一次提交；如需再细分可用 git add -p 分块暂存
git add web/js/api.js
git commit -m "feat(api): 请求超时控制、导出方法与 Toast 点击关闭"

git add web/js/data_page.js
git commit -m "feat(data): 导出失败提示、加载态与导入 5MB 大小限制"
```
