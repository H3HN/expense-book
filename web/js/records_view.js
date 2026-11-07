import { api, escapeHtml, formatMoney, on, refreshApp, toast } from "./api.js";

const DEFAULT_FILTERS = Object.freeze({
  type: "all",
  category: "all",
  start: "",
  end: "",
  keyword: "",
  limit: "20",
  sort: "date-desc",
});

const filters = { ...DEFAULT_FILTERS };

let config = null;
let records = [];
let host = null;
let keywordTimer = null;
let pendingDelete = null;
let pendingDeleteTimer = null;
let loadRequestId = 0;
let modalReturnFocus = null;
let bodyOverflowBeforeModal = "";
let unsubscribeChanged = null;

const TYPE_LABELS = { expense: "支出", income: "收入" };

function categoriesForType(type = filters.type) {
  if (!config) {
    return [];
  }
  if (type === "expense") {
    return config.expense_categories;
  }
  if (type === "income") {
    return config.income_categories;
  }
  return Array.from(new Set([...config.expense_categories, ...config.income_categories]));
}

function categoryOptions() {
  const categories = categoriesForType();
  return ['<option value="all">全部类别</option>']
    .concat(categories.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`))
    .join("");
}

function syncCategoryFilter() {
  const select = host && host.querySelector('[data-filter="category"]');
  if (!select) {
    return;
  }
  const categories = categoriesForType();
  if (config && filters.category !== "all" && !categories.includes(filters.category)) {
    filters.category = "all";
  }
  select.innerHTML = categoryOptions();
  select.value = filters.category;
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
        <label class="filter-field">
          <span class="field-label">排序</span>
          <select class="field-input" data-filter="sort">
            <option value="date-desc">日期从近到远</option>
            <option value="date-asc">日期从远到近</option>
            <option value="amount-desc">金额从高到低</option>
            <option value="amount-asc">金额从低到高</option>
          </select>
        </label>
      </div>

      <div class="records-summary" data-summary role="status" aria-live="polite"></div>

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
  host.querySelector('[data-filter="sort"]').value = filters.sort;
}

function sortedRecords() {
  const [field, direction] = filters.sort.split("-");
  const multiplier = direction === "asc" ? 1 : -1;
  return [...records].sort((left, right) => {
    if (field === "amount") {
      return (Number(left.amount || 0) - Number(right.amount || 0)) * multiplier;
    }
    const leftKey = `${left.date || ""} ${left.created_at || ""}`;
    const rightKey = `${right.date || ""} ${right.created_at || ""}`;
    return leftKey.localeCompare(rightKey) * multiplier;
  });
}

function validateDateRange(notify = false) {
  const startInput = host.querySelector('[data-filter="start"]');
  const endInput = host.querySelector('[data-filter="end"]');
  const invalid = Boolean(filters.start && filters.end && filters.start > filters.end);
  const message = invalid ? "起始日期不能晚于结束日期" : "";
  startInput.setCustomValidity(message);
  endInput.setCustomValidity(message);
  startInput.setAttribute("aria-invalid", String(invalid));
  endInput.setAttribute("aria-invalid", String(invalid));
  if (invalid && notify) {
    toast(message, "error");
  }
  return !invalid;
}

function setLoading(isLoading) {
  const card = host && host.querySelector(".records-card");
  if (card) {
    card.setAttribute("aria-busy", String(isLoading));
  }
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
  tbody.innerHTML = sortedRecords()
    .map((record) => {
      const isIncome = record.type === "income";
      const amountClass = isIncome ? "amount-income" : "amount-expense";
      const sign = isIncome ? "+" : "-";
      const recordLabel = `${record.date} ${record.category} ${formatMoney(record.amount)}`;
      return `
        <tr data-id="${escapeHtml(record.id)}">
          <td class="cell-date">${escapeHtml(record.date)}</td>
          <td><span class="type-tag ${isIncome ? "type-income" : "type-expense"}">${TYPE_LABELS[record.type] || record.type}</span></td>
          <td>${escapeHtml(record.category)}</td>
          <td class="align-right ${amountClass}">${sign}${formatMoney(record.amount)}</td>
          <td class="cell-note" title="${escapeHtml(record.note || "")}">${escapeHtml(record.note || "—")}</td>
          <td class="align-right cell-actions">
            <button type="button" class="row-action" data-action="edit" data-id="${escapeHtml(record.id)}"
              aria-label="编辑 ${escapeHtml(recordLabel)}">编辑</button>
            <button type="button" class="row-action danger" data-action="delete" data-id="${escapeHtml(record.id)}"
              data-default-label="删除 ${escapeHtml(recordLabel)}" aria-label="删除 ${escapeHtml(recordLabel)}">删除</button>
          </td>
        </tr>
      `;
    })
    .join("");
}

async function loadRecords() {
  const requestId = ++loadRequestId;
  if (!validateDateRange()) {
    return;
  }
  setLoading(true);
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
    if (requestId !== loadRequestId) {
      return;
    }
    records = data.records;
    renderRows(data);
  } catch (error) {
    if (requestId === loadRequestId) {
      toast(error.message, "error");
    }
  } finally {
    if (requestId === loadRequestId) {
      setLoading(false);
    }
  }
}

function resetDeleteConfirm() {
  if (!pendingDelete) {
    return;
  }
  pendingDelete.dataset.confirming = "0";
  pendingDelete.textContent = "删除";
  pendingDelete.setAttribute("aria-label", pendingDelete.dataset.defaultLabel || "删除记录");
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
    button.setAttribute("aria-label", "再次点击确认删除这条记录");
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
  button.textContent = "删除中...";
  button.setAttribute("aria-busy", "true");
  try {
    await api.deleteRecord(id);
    toast("记录已删除");
    await refreshApp();
  } catch (error) {
    toast(error.message, "error");
    button.disabled = false;
    button.textContent = "删除";
    button.removeAttribute("aria-busy");
    button.setAttribute("aria-label", button.dataset.defaultLabel || "删除记录");
  }
}

function editCategories(type) {
  return type === "income" ? config.income_categories : config.expense_categories;
}

function populateEditCategories(type, preferredCategory = "") {
  const modal = document.getElementById("edit-modal");
  const categorySelect = modal.querySelector('#edit-form [name="category"]');
  const categories = editCategories(type);
  categorySelect.innerHTML = categories
    .map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`)
    .join("");
  const fallback = categories.includes("其他") ? "其他" : categories[0];
  categorySelect.value = categories.includes(preferredCategory) ? preferredCategory : fallback;
}

function openEditModal(record, trigger) {
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
  populateEditCategories(record.type, record.category);

  modalReturnFocus = trigger || document.activeElement;
  bodyOverflowBeforeModal = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  modal.classList.add("is-open");
  modal.setAttribute("aria-hidden", "false");
  form.querySelector('[name="amount"]').focus();
}

function closeEditModal() {
  const modal = document.getElementById("edit-modal");
  if (!modal) {
    return;
  }
  if (modal.querySelector("#edit-form").dataset.saving === "1") {
    return;
  }
  modal.classList.remove("is-open");
  modal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = bodyOverflowBeforeModal;
  if (modalReturnFocus && document.contains(modalReturnFocus)) {
    modalReturnFocus.focus();
  }
  modalReturnFocus = null;
}

function bindEditModal() {
  const modal = document.getElementById("edit-modal");
  if (!modal || modal.dataset.bound === "1") {
    return;
  }
  modal.dataset.bound = "1";

  const form = modal.querySelector("#edit-form");
  const typeSelect = form.querySelector('[name="type"]');

  typeSelect.addEventListener("change", () => {
    if (!config) {
      return;
    }
    const currentCategory = form.querySelector('[name="category"]').value;
    populateEditCategories(typeSelect.value, currentCategory);
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
    if (!modal.classList.contains("is-open")) {
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeEditModal();
      return;
    }
    if (event.key === "Tab") {
      const focusable = Array.from(modal.querySelectorAll("button:not([disabled]), input:not([disabled]), select:not([disabled])"));
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const id = form.querySelector('[name="id"]').value;
    const payload = {
      date: form.querySelector('[name="date"]').value,
      type: typeSelect.value,
      amount: Number(form.querySelector('[name="amount"]').value),
      category: form.querySelector('[name="category"]').value,
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
    const saveLabel = saveButton.textContent;
    form.dataset.saving = "1";
    saveButton.disabled = true;
    saveButton.textContent = "保存中...";
    try {
      await api.updateRecord(id, payload);
      toast("记录已更新");
      form.dataset.saving = "0";
      closeEditModal();
      await refreshApp();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      form.dataset.saving = "0";
      saveButton.disabled = false;
      saveButton.textContent = saveLabel;
    }
  });
}

export function mount(container) {
  host = container;
  // Keep the wide table inside its scroll container instead of expanding the page grid on mobile.
  const main = host.closest(".main");
  if (main) {
    main.style.gridTemplateColumns = "minmax(0, 1fr)";
  }
  renderShell();
  applyFilterInputs();
  bindEditModal();

  api
    .getConfig()
    .then((data) => {
      config = data;
      syncCategoryFilter();
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
    const key = target.dataset.filter;
    filters[key] = target.value;
    resetDeleteConfirm();
    if (key === "type") {
      syncCategoryFilter();
    }
    if ((key === "start" || key === "end") && !validateDateRange(true)) {
      ++loadRequestId;
      setLoading(false);
      return;
    }
    if (key === "sort") {
      renderRows({ count: records.length });
      return;
    }
    loadRecords();
  });

  host.addEventListener("input", (event) => {
    const target = event.target.closest('[data-filter="keyword"]');
    if (!target) {
      return;
    }
    filters.keyword = target.value.trim();
    ++loadRequestId;
    setLoading(false);
    if (keywordTimer) {
      window.clearTimeout(keywordTimer);
    }
    keywordTimer = window.setTimeout(() => loadRecords(), 300);
  });

  host.addEventListener("click", (event) => {
    const reset = event.target.closest('[data-action="reset"]');
    if (reset) {
      Object.assign(filters, DEFAULT_FILTERS);
      if (keywordTimer) {
        window.clearTimeout(keywordTimer);
        keywordTimer = null;
      }
      applyFilterInputs();
      syncCategoryFilter();
      validateDateRange();
      resetDeleteConfirm();
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
        openEditModal(record, action);
      }
    }
  });

  if (unsubscribeChanged) {
    unsubscribeChanged();
  }
  unsubscribeChanged = on("app:changed", () => {
    loadRecords();
  });

  loadRecords();
}
