import { api, escapeHtml, formatMoney, on, refreshApp, toast } from "./api.js";

const filters = {
  type: "all",
  category: "all",
  start: "",
  end: "",
  keyword: "",
  limit: "20",
};

let config = null;
let records = [];
let host = null;
let keywordTimer = null;
let pendingDelete = null;
let pendingDeleteTimer = null;

const TYPE_LABELS = { expense: "支出", income: "收入" };

function categoryOptions() {
  if (!config) {
    return '<option value="all">全部类别</option>';
  }
  const merged = Array.from(new Set([...config.expense_categories, ...config.income_categories]));
  return ['<option value="all">全部类别</option>']
    .concat(merged.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`))
    .join("");
}

function renderShell() {
  host.innerHTML = `
    <section class="records-card">
      <header class="records-head">
        <div>
          <p class="form-kicker">LEDGER</p>
          <h3 class="form-title">收支明细</h3>
        </div>
        <button class="btn btn-ghost btn-sm" data-action="reset">重置筛选</button>
      </header>

      <div class="filter-bar">
        <label class="filter-field">
          <span class="field-label">类型</span>
          <select class="field-input" data-filter="type">
            <option value="all">全部</option>
            <option value="expense">支出</option>
            <option value="income">收入</option>
          </select>
        </label>
        <label class="filter-field">
          <span class="field-label">类别</span>
          <select class="field-input" data-filter="category">${categoryOptions()}</select>
        </label>
        <label class="filter-field">
          <span class="field-label">起始日期</span>
          <input class="field-input" type="date" data-filter="start">
        </label>
        <label class="filter-field">
          <span class="field-label">结束日期</span>
          <input class="field-input" type="date" data-filter="end">
        </label>
        <label class="filter-field filter-field-wide">
          <span class="field-label">备注关键词</span>
          <input class="field-input" type="search" data-filter="keyword" placeholder="搜索备注，例如：午饭">
        </label>
        <label class="filter-field">
          <span class="field-label">显示最近</span>
          <select class="field-input" data-filter="limit">
            <option value="20">20 笔</option>
            <option value="50">50 笔</option>
            <option value="100">100 笔</option>
            <option value="all">全部</option>
          </select>
        </label>
      </div>

      <div class="records-summary" data-summary></div>

      <div class="table-wrap">
        <table class="records-table">
          <thead>
            <tr>
              <th>日期</th>
              <th>类型</th>
              <th>类别</th>
              <th class="align-right">金额</th>
              <th>备注</th>
              <th class="align-right">操作</th>
            </tr>
          </thead>
          <tbody data-rows></tbody>
        </table>
        <div class="empty-state" data-empty hidden>
          <span class="empty-icon">◇</span>
          <p>当前筛选条件下没有记录</p>
          <span class="empty-hint">试试放宽日期区间或清空关键词</span>
        </div>
      </div>
    </section>
  `;
}

function applyFilterInputs() {
  host.querySelector('[data-filter="type"]').value = filters.type;
  host.querySelector('[data-filter="category"]').value = filters.category;
  host.querySelector('[data-filter="start"]').value = filters.start;
  host.querySelector('[data-filter="end"]').value = filters.end;
  host.querySelector('[data-filter="keyword"]').value = filters.keyword;
  host.querySelector('[data-filter="limit"]').value = filters.limit;
}

function renderRows(data) {
  const tbody = host.querySelector("[data-rows]");
  const empty = host.querySelector("[data-empty]");
  const summary = host.querySelector("[data-summary]");

  let income = 0;
  let expense = 0;
  records.forEach((record) => {
    if (record.type === "income") {
      income += Number(record.amount || 0);
    } else {
      expense += Number(record.amount || 0);
    }
  });

  summary.innerHTML = `
    <span class="summary-pill">共 <strong>${data.count}</strong> 条</span>
    <span class="summary-pill summary-income">收入 ${formatMoney(income)}</span>
    <span class="summary-pill summary-expense">支出 ${formatMoney(expense)}</span>
  `;

  if (!records.length) {
    tbody.innerHTML = "";
    empty.hidden = false;
    return;
  }

  empty.hidden = true;
  tbody.innerHTML = records
    .map((record) => {
      const isIncome = record.type === "income";
      const amountClass = isIncome ? "amount-income" : "amount-expense";
      const sign = isIncome ? "+" : "-";
      return `
        <tr data-id="${escapeHtml(record.id)}">
          <td class="cell-date">${escapeHtml(record.date)}</td>
          <td><span class="type-tag ${isIncome ? "type-income" : "type-expense"}">${TYPE_LABELS[record.type] || record.type}</span></td>
          <td>${escapeHtml(record.category)}</td>
          <td class="align-right ${amountClass}">${sign}${formatMoney(record.amount)}</td>
          <td class="cell-note">${escapeHtml(record.note || "—")}</td>
          <td class="align-right cell-actions">
            <button class="row-action" data-action="edit" data-id="${escapeHtml(record.id)}">编辑</button>
            <button class="row-action danger" data-action="delete" data-id="${escapeHtml(record.id)}">删除</button>
          </td>
        </tr>
      `;
    })
    .join("");
}

async function loadRecords() {
  try {
    const params = {
      type: filters.type,
      category: filters.category,
      start: filters.start,
      end: filters.end,
      keyword: filters.keyword,
      limit: filters.limit === "all" ? undefined : filters.limit,
    };
    const data = await api.getRecords(params);
    records = data.records;
    renderRows(data);
  } catch (error) {
    toast(error.message, "error");
  }
}

function resetDeleteConfirm() {
  if (!pendingDelete) {
    return;
  }
  pendingDelete.dataset.confirming = "0";
  pendingDelete.textContent = "删除";
  pendingDelete.classList.remove("is-confirming");
  pendingDelete = null;
  if (pendingDeleteTimer) {
    window.clearTimeout(pendingDeleteTimer);
    pendingDeleteTimer = null;
  }
}

async function handleDelete(button) {
  const id = button.dataset.id;
  if (button.dataset.confirming !== "1") {
    resetDeleteConfirm();
    button.dataset.confirming = "1";
    button.textContent = "确认删除？";
    button.classList.add("is-confirming");
    pendingDelete = button;
    pendingDeleteTimer = window.setTimeout(() => {
      if (pendingDelete === button) {
        resetDeleteConfirm();
      }
    }, 3000);
    return;
  }

  resetDeleteConfirm();
  button.disabled = true;
  try {
    await api.deleteRecord(id);
    toast("记录已删除");
    await refreshApp();
  } catch (error) {
    toast(error.message, "error");
    button.disabled = false;
  }
}

function openEditModal(record) {
  const modal = document.getElementById("edit-modal");
  if (!modal) {
    return;
  }
  if (!config) {
    toast("配置尚未加载完成，请稍后再试", "error");
    return;
  }
  const form = modal.querySelector("#edit-form");
  form.querySelector('[name="id"]').value = record.id;
  form.querySelector('[name="date"]').value = record.date;
  form.querySelector('[name="type"]').value = record.type;
  form.querySelector('[name="amount"]').value = record.amount;
  form.querySelector('[name="note"]').value = record.note || "";

  const categorySelect = form.querySelector('[name="category"]');
  const categories = record.type === "income" ? config.income_categories : config.expense_categories;
  categorySelect.innerHTML = categories
    .map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`)
    .join("");
  categorySelect.value = record.category;

  modal.classList.add("is-open");
  modal.setAttribute("aria-hidden", "false");
  form.querySelector('[name="amount"]').focus();
}

function closeEditModal() {
  const modal = document.getElementById("edit-modal");
  if (!modal) {
    return;
  }
  modal.classList.remove("is-open");
  modal.setAttribute("aria-hidden", "true");
}

function bindEditModal() {
  const modal = document.getElementById("edit-modal");
  if (!modal || modal.dataset.bound === "1") {
    return;
  }
  modal.dataset.bound = "1";

  const form = modal.querySelector("#edit-form");
  const typeSelect = form.querySelector('[name="type"]');
  const categorySelect = form.querySelector('[name="category"]');

  typeSelect.addEventListener("change", () => {
    if (!config) {
      return;
    }
    const categories = typeSelect.value === "income" ? config.income_categories : config.expense_categories;
    categorySelect.innerHTML = categories
      .map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`)
      .join("");
  });

  modal.querySelectorAll("[data-action=cancel]").forEach((button) => {
    button.addEventListener("click", closeEditModal);
  });
  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      closeEditModal();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeEditModal();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = form.querySelector('[name="id"]').value;
    const payload = {
      date: form.querySelector('[name="date"]').value,
      type: typeSelect.value,
      amount: Number(form.querySelector('[name="amount"]').value),
      category: categorySelect.value,
      note: form.querySelector('[name="note"]').value.trim(),
    };

    if (!payload.date) {
      toast("请选择日期", "error");
      return;
    }
    if (!Number.isFinite(payload.amount) || payload.amount <= 0) {
      toast("金额必须大于 0", "error");
      return;
    }

    const saveButton = form.querySelector("button[type=submit]");
    saveButton.disabled = true;
    try {
      await api.updateRecord(id, payload);
      toast("记录已更新");
      closeEditModal();
      await refreshApp();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      saveButton.disabled = false;
    }
  });
}

export function mount(container) {
  host = container;
  renderShell();
  bindEditModal();

  api
    .getConfig()
    .then((data) => {
      config = data;
      const select = host.querySelector('[data-filter="category"]');
      select.innerHTML = categoryOptions();
      select.value = filters.category;
    })
    .catch((error) => toast(error.message, "error"));

  host.addEventListener("change", (event) => {
    const target = event.target.closest("[data-filter]");
    if (!target) {
      return;
    }
    if (target.dataset.filter === "keyword") {
      return;
    }
    filters[target.dataset.filter] = target.value;
    loadRecords();
  });

  host.addEventListener("input", (event) => {
    const target = event.target.closest('[data-filter="keyword"]');
    if (!target) {
      return;
    }
    filters.keyword = target.value.trim();
    if (keywordTimer) {
      window.clearTimeout(keywordTimer);
    }
    keywordTimer = window.setTimeout(() => loadRecords(), 300);
  });

  host.addEventListener("click", (event) => {
    const reset = event.target.closest('[data-action="reset"]');
    if (reset) {
      filters.type = "all";
      filters.category = "all";
      filters.start = "";
      filters.end = "";
      filters.keyword = "";
      filters.limit = "20";
      applyFilterInputs();
      loadRecords();
      return;
    }

    const action = event.target.closest("[data-action]");
    if (!action || !action.dataset.id) {
      return;
    }

    if (action.dataset.action === "delete") {
      handleDelete(action);
      return;
    }

    if (action.dataset.action === "edit") {
      const record = records.find((item) => item.id === action.dataset.id);
      if (record) {
        openEditModal(record);
      }
    }
  });

  on("app:changed", () => {
    loadRecords();
  });

  loadRecords();
}