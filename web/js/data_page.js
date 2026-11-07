import { api, formatMoney, on, refreshApp, toast } from "./api.js";

let host = null;
let lastResult = null;
let dragDepth = 0;

function renderShell() {
  host.innerHTML = `
    <section class="data-card">
      <header class="records-head">
        <div>
          <p class="form-kicker">DATA</p>
          <h3 class="form-title">数据管理</h3>
        </div>
        <span class="summary-pill" data-total>—</span>
      </header>

      <div class="data-grid">
        <div class="data-panel">
          <h4 class="chart-title">导出台账</h4>
          <p class="data-desc">导出为 UTF-8 BOM 编码的 CSV，可直接用 Excel 打开，也可再次导入。</p>
          <button class="btn btn-primary" type="button" data-action="export">
            <span class="btn-text">下载 records.csv</span>
          </button>
        </div>

        <div class="data-panel">
          <h4 class="chart-title">导入并合并</h4>
          <p class="data-desc">按记录 ID 去重合并，非法行会被自动过滤，不会污染现有数据。</p>
          <div class="drop-zone" data-drop>
            <span class="drop-icon">⇪</span>
            <p class="drop-title">拖拽 CSV 到这里</p>
            <p class="drop-sub">或点击选择文件（仅支持 .csv）</p>
            <input type="file" accept=".csv,text/csv" hidden data-file>
          </div>
          <p class="data-status" data-status>尚未导入文件</p>
        </div>
      </div>
    </section>
  `;
}

function setStatus(text, tone = "") {
  const node = host.querySelector("[data-status]");
  node.textContent = text;
  node.className = `data-status${tone ? ` is-${tone}` : ""}`;
}

function updateTotal(totals) {
  const node = host.querySelector("[data-total]");
  node.textContent = `当前 ${Number(totals.count || 0)} 条 · ${formatMoney(totals.balance)}`;
}

async function importFile(file) {
  if (!file) {
    return;
  }
  if (!file.name.toLowerCase().endsWith(".csv")) {
    toast("只支持 .csv 文件", "error");
    setStatus("文件格式不支持，请选择 .csv", "error");
    return;
  }

  const drop = host.querySelector("[data-drop]");
  drop.classList.add("is-busy");
  setStatus(`正在导入 ${file.name} …`);

  try {
    const result = await api.importCsv(file);
    lastResult = result;
    setStatus(`已导入 ${result.imported} 条，合并后共 ${result.total} 条`, "success");
    toast(`导入成功：新增/更新 ${result.imported} 条`);
    updateTotal(result.totals);
    await refreshApp();
  } catch (error) {
    setStatus(error.message, "error");
    toast(error.message, "error");
  } finally {
    drop.classList.remove("is-busy");
    const input = host.querySelector("[data-file]");
    input.value = "";
  }
}

export function mount(container) {
  host = container;
  renderShell();

  const input = host.querySelector("[data-file]");
  const drop = host.querySelector("[data-drop]");

  host.querySelector('[data-action="export"]').addEventListener("click", () => {
    const link = document.createElement("a");
    link.href = api.exportCsvUrl();
    link.download = "records.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    toast("已开始下载 records.csv", "info");
  });

  drop.addEventListener("click", () => input.click());

  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    importFile(file);
  });

  ["dragenter", "dragover"].forEach((type) => {
    drop.addEventListener(type, (event) => {
      event.preventDefault();
      event.stopPropagation();
      dragDepth += 1;
      drop.classList.add("is-dragover");
    });
  });

  drop.addEventListener("dragleave", (event) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) {
      drop.classList.remove("is-dragover");
    }
  });

  drop.addEventListener("drop", (event) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepth = 0;
    drop.classList.remove("is-dragover");
    const file = event.dataTransfer && event.dataTransfer.files ? event.dataTransfer.files[0] : null;
    importFile(file);
  });

  on("app:changed", ({ totals }) => {
    updateTotal(totals);
  });

  api
    .getRecords()
    .then((data) => {
      updateTotal(data.totals);
    })
    .catch((error) => toast(error.message, "error"));
}