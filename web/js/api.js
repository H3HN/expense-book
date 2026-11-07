const API_BASE = "";

const listeners = new Map();

let configCache = null;

export const state = {
  config: null,
  totals: { income: 0, expense: 0, balance: 0, count: 0 },
  activeTab: "ledger",
};

export function on(event, handler) {
  if (!listeners.has(event)) {
    listeners.set(event, new Set());
  }
  listeners.get(event).add(handler);
  return () => listeners.get(event).delete(handler);
}

export function emit(event, detail) {
  const handlers = listeners.get(event);
  if (!handlers) {
    return;
  }
  handlers.forEach((handler) => {
    try {
      handler(detail);
    } catch (error) {
      console.error(`[emit:${event}]`, error);
    }
  });
}

const REQUEST_TIMEOUT = 10000;

async function request(path, { method = "GET", body, headers, timeout = REQUEST_TIMEOUT } = {}) {
  const isFormData = body instanceof FormData;
  const options = { method };
  if (isFormData) {
    options.body = body;
  } else if (body !== undefined) {
    options.headers = { "Content-Type": "application/json", ...(headers || {}) };
    options.body = JSON.stringify(body);
  } else if (headers) {
    options.headers = headers;
  }

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeout);
  options.signal = controller.signal;

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (networkError) {
    const isTimeout = networkError && networkError.name === "AbortError";
    const error = new Error(isTimeout ? "请求超时，请检查后端是否正常运行" : "无法连接后端，请确认 uvicorn 已启动");
    error.status = 0;
    error.errors = [error.message];
    throw error;
  } finally {
    window.clearTimeout(timer);
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : payload;
    let messages = [];
    if (detail && Array.isArray(detail.errors)) {
      messages = detail.errors;
    } else if (Array.isArray(detail)) {
      messages = detail.map((item) => item.msg || String(item));
    } else if (detail && typeof detail === "object") {
      messages = [detail.message || JSON.stringify(detail)];
    } else if (detail) {
      messages = [String(detail)];
    } else {
      messages = [`请求失败 (${response.status})`];
    }
    const error = new Error(messages.join("；"));
    error.status = response.status;
    error.errors = messages;
    throw error;
  }

  return payload;
}

function buildQuery(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "" || value === "all") {
      return;
    }
    search.append(key, value);
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

export const api = {
  async getConfig(force = false) {
    if (configCache && !force) {
      return configCache;
    }
    const config = await request("/api/config");
    configCache = config;
    return configCache;
  },

  getRecords(params = {}) {
    return request(`/api/records${buildQuery(params)}`);
  },

  createRecord(data) {
    return request("/api/records", { method: "POST", body: data });
  },

  updateRecord(id, data) {
    return request(`/api/records/${encodeURIComponent(id)}`, { method: "PUT", body: data });
  },

  deleteRecord(id) {
    return request(`/api/records/${encodeURIComponent(id)}`, { method: "DELETE" });
  },

  nlParse(text, autoSave = false) {
    return request("/api/nl-parse", { method: "POST", body: { text, auto_save: autoSave } });
  },

  getStats(params = {}) {
    return request(`/api/stats${buildQuery({ start: params.start, end: params.end })}`);
  },

  exportCsvUrl() {
    return `${API_BASE}/api/export/csv`;
  },

  async exportCsv(timeout = REQUEST_TIMEOUT) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeout);
    let response;
    try {
      response = await fetch(`${API_BASE}/api/export/csv`, { signal: controller.signal });
    } catch (networkError) {
      const isTimeout = networkError && networkError.name === "AbortError";
      throw new Error(isTimeout ? "导出超时，请检查后端是否正常运行" : "无法连接后端，请确认 uvicorn 已启动");
    } finally {
      window.clearTimeout(timer);
    }
    if (!response.ok) {
      throw new Error(`导出失败 (${response.status})`);
    }
    return response.blob();
  },

  importCsv(file) {
    const form = new FormData();
    form.append("file", file);
    return request("/api/import/csv", { method: "POST", body: form });
  },
};

export function formatMoney(value) {
  const number = Number(value || 0);
  return `¥${number.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

export function escapeHtml(value) {
  return String(value === undefined || value === null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function todayString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function updateMetricCards() {
  const mapping = {
    "metric-income": formatMoney(state.totals.income),
    "metric-expense": formatMoney(state.totals.expense),
    "metric-balance": formatMoney(state.totals.balance),
    "metric-count": `${Number(state.totals.count || 0)} 笔`,
  };
  Object.entries(mapping).forEach(([id, text]) => {
    const node = document.getElementById(id);
    if (!node) {
      return;
    }
    if (node.textContent !== text) {
      node.classList.add("metric-flash");
      window.setTimeout(() => node.classList.remove("metric-flash"), 520);
    }
    node.textContent = text;
  });
}

export async function refreshApp() {
  try {
    const [config, data] = await Promise.all([api.getConfig(), api.getRecords()]);
    state.config = config;
    state.totals = data.totals;
    updateMetricCards();
    emit("app:changed", { totals: state.totals, records: data.records });
    return state.totals;
  } catch (error) {
    toast(error.message, "error");
    throw error;
  }
}

export function toast(message, type = "success") {
  const container = document.getElementById("toast-container");
  if (!container) {
    return;
  }
  const item = document.createElement("div");
  item.className = `toast toast-${type}`;
  const icon = type === "error" ? "!" : type === "info" ? "i" : "✓";
  item.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-text">${escapeHtml(message)}</span>`;
  item.style.pointerEvents = "auto";
  item.style.cursor = "pointer";
  item.title = "点击关闭";

  let removed = false;
  const dismiss = () => {
    if (removed) {
      return;
    }
    removed = true;
    item.classList.remove("is-visible");
    item.classList.add("is-leaving");
    window.setTimeout(() => item.remove(), 320);
  };
  item.addEventListener("click", dismiss);

  container.appendChild(item);

  requestAnimationFrame(() => item.classList.add("is-visible"));

  window.setTimeout(dismiss, 2800);
}

export default api;