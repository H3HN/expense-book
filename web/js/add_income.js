import { api, formatMoney, refreshApp, toast, todayString } from "./api.js";

const TYPE = "income";
const TYPE_LABEL = "收入";
const FORM_ID = "income";
const MAX_NOTE_LENGTH = 100;
const DEFAULT_HINT = "日期默认今天，金额需大于 0 且最多保留两位小数。";
const AMOUNT_PATTERN = /^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/;
const FIELD_ORDER = ["date", "amount", "category", "note"];

function isValidDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function parseAmount(raw) {
  const normalized = String(raw ?? "").replace(/[¥￥,]/g, "").trim();
  if (!normalized) {
    return { error: "请输入金额" };
  }
  if (!AMOUNT_PATTERN.test(normalized)) {
    if (/^\d*\.\d{3,}$/.test(normalized)) {
      return { error: "金额最多保留两位小数" };
    }
    return { error: "请输入有效金额，例如 25.50" };
  }

  const amount = Number(normalized);
  if (!Number.isFinite(amount) || amount <= 0) {
    return { error: "金额必须大于 0" };
  }

  const cents = Math.round(amount * 100);
  if (!Number.isSafeInteger(cents)) {
    return { error: "金额过大，请检查输入" };
  }
  return { value: cents / 100 };
}

function renderMarkup() {
  return `
    <section class="form-card form-card-income" aria-labelledby="${FORM_ID}-form-title">
      <header class="form-head">
        <div>
          <p class="form-kicker">INCOME</p>
          <h3 class="form-title" id="${FORM_ID}-form-title">记一笔收入</h3>
        </div>
        <span class="form-badge form-badge-income">收入</span>
      </header>

      <form class="record-form" id="${FORM_ID}-form" novalidate autocomplete="off">
        <div class="form-grid">
          <div class="field">
            <label class="field-label" for="${FORM_ID}-date">日期</label>
            <input class="field-input" id="${FORM_ID}-date" type="date" name="date"
                   required autocomplete="off" aria-describedby="${FORM_ID}-hint">
          </div>

          <div class="field">
            <label class="field-label" for="${FORM_ID}-amount">金额</label>
            <input class="field-input" id="${FORM_ID}-amount" type="text" name="amount"
                   inputmode="decimal" placeholder="0.00" autocomplete="off"
                   spellcheck="false" required aria-describedby="${FORM_ID}-hint">
          </div>

          <div class="field">
            <label class="field-label" for="${FORM_ID}-category">类别</label>
            <select class="field-input" id="${FORM_ID}-category" name="category"
                    required disabled aria-describedby="${FORM_ID}-hint">
              <option value="" selected>正在加载类别…</option>
            </select>
          </div>

          <div class="field field-wide">
            <label class="field-label" for="${FORM_ID}-note">备注</label>
            <input class="field-input" id="${FORM_ID}-note" type="text" name="note"
                   maxlength="${MAX_NOTE_LENGTH}" placeholder="例如：工资、兼职、奖学金"
                   autocomplete="off" aria-describedby="${FORM_ID}-hint">
          </div>
        </div>

        <p class="form-hint" id="${FORM_ID}-hint" data-hint role="status" aria-live="polite">
          正在加载记账类别…
        </p>
        <button class="btn btn-ghost btn-sm hidden" type="button" data-retry>
          重新加载类别
        </button>
        <button class="btn btn-income btn-block" type="submit" disabled aria-busy="false">
          <span class="btn-text">保存收入</span>
          <span class="btn-loader" aria-hidden="true"></span>
        </button>
      </form>
    </section>
  `;
}

export function mount(container) {
  if (!container) {
    return;
  }

  container.innerHTML = renderMarkup();

  const form = container.querySelector("form");
  const dateInput = form.querySelector('[name="date"]');
  const amountInput = form.querySelector('[name="amount"]');
  const categorySelect = form.querySelector('[name="category"]');
  const noteInput = form.querySelector('[name="note"]');
  const submitButton = form.querySelector('button[type="submit"]');
  const submitText = submitButton.querySelector(".btn-text");
  const retryButton = form.querySelector("[data-retry]");
  const hint = form.querySelector("[data-hint]");

  const fields = {
    date: dateInput,
    amount: amountInput,
    category: categorySelect,
    note: noteInput,
  };

  let configReady = false;
  let configLoading = false;
  let submitting = false;
  let dateTouched = false;
  let allowedCategories = [];

  dateInput.value = todayString();

  function setStatus(message, isError = false) {
    hint.textContent = message;
    hint.classList.toggle("is-error", isError);
    hint.setAttribute("aria-live", isError ? "assertive" : "polite");
  }

  function setFieldInvalid(field, invalid) {
    field.setAttribute("aria-invalid", invalid ? "true" : "false");
    field.style.borderColor = invalid ? "var(--coral)" : "";
    field.style.boxShadow = invalid ? "0 0 0 3px rgba(198, 91, 72, 0.11)" : "";
  }

  function clearFieldErrors() {
    FIELD_ORDER.forEach((key) => setFieldInvalid(fields[key], false));
  }

  function updateSubmitState() {
    submitButton.disabled = !configReady || submitting;
  }

  function setSubmitting(loading) {
    submitting = loading;
    submitButton.classList.toggle("is-loading", loading);
    submitButton.setAttribute("aria-busy", loading ? "true" : "false");
    submitText.textContent = loading ? "正在保存…" : "保存收入";
    updateSubmitState();
  }

  function populateCategories(categories) {
    const previous = categorySelect.value;
    const uniqueCategories = [...new Set(categories)];
    const options = uniqueCategories.map((category) => {
      const option = document.createElement("option");
      option.value = category;
      option.textContent = category;
      return option;
    });
    categorySelect.replaceChildren(...options);
    categorySelect.disabled = false;
    if (uniqueCategories.includes(previous)) {
      categorySelect.value = previous;
    }
    allowedCategories = uniqueCategories;
  }

  async function loadConfig(force = false) {
    if (configLoading) {
      return;
    }
    configLoading = true;
    configReady = false;
    categorySelect.disabled = true;
    retryButton.classList.add("hidden");
    updateSubmitState();
    setStatus("正在加载记账类别…");

    try {
      const config = await api.getConfig(force);
      if (!form.isConnected) {
        return;
      }

      const categories = Array.isArray(config.income_categories)
        ? config.income_categories.filter(
            (category) => typeof category === "string" && category.trim()
          )
        : [];
      if (!categories.length) {
        throw new Error("后端未返回可用的收入类别");
      }

      populateCategories(categories);
      if (!dateTouched && isValidDate(String(config.today || ""))) {
        dateInput.value = config.today;
      }
      configReady = true;
      setStatus(DEFAULT_HINT);
    } catch (error) {
      if (!form.isConnected) {
        return;
      }
      setStatus(`类别加载失败：${error.message || "未知错误"}。请重新加载。`, true);
      retryButton.classList.remove("hidden");
    } finally {
      configLoading = false;
      updateSubmitState();
    }
  }

  function validate() {
    const errors = {};

    const date = dateInput.value.trim();
    if (!date) {
      errors.date = "请选择记账日期";
    } else if (!isValidDate(date)) {
      errors.date = "日期格式应为 YYYY-MM-DD";
    }

    const parsedAmount = parseAmount(amountInput.value);
    if (parsedAmount.error) {
      errors.amount = parsedAmount.error;
    }

    const category = categorySelect.value;
    if (!configReady) {
      errors.category = "记账类别还没有加载完成";
    } else if (!category || !allowedCategories.includes(category)) {
      errors.category = "请选择有效类别";
    }

    const note = noteInput.value.trim();
    if (note.length > MAX_NOTE_LENGTH) {
      errors.note = `备注不能超过 ${MAX_NOTE_LENGTH} 字`;
    }

    return {
      errors,
      payload: {
        date,
        type: TYPE,
        amount: parsedAmount.value,
        category,
        note,
      },
    };
  }

  function showFieldErrors(errors) {
    clearFieldErrors();
    const messages = [];

    FIELD_ORDER.forEach((key) => {
      if (!errors[key]) {
        return;
      }
      messages.push(errors[key]);
      setFieldInvalid(fields[key], true);
    });

    if (!messages.length) {
      return;
    }

    setStatus(messages.join("；"), true);
    const firstInvalid = FIELD_ORDER.find((key) => Boolean(errors[key]));
    if (firstInvalid) {
      fields[firstInvalid].focus();
    }
  }

  function showServerError(error) {
    clearFieldErrors();
    const messages =
      Array.isArray(error.errors) && error.errors.length
        ? error.errors
        : [error.message || "保存失败，请稍后重试"];
    const joined = messages.join(" ");

    if (/日期/.test(joined)) {
      setFieldInvalid(fields.date, true);
    }
    if (/金额/.test(joined)) {
      setFieldInvalid(fields.amount, true);
    }
    if (/类别/.test(joined)) {
      setFieldInvalid(fields.category, true);
    }
    if (/备注/.test(joined)) {
      setFieldInvalid(fields.note, true);
    }

    setStatus(messages.join("；"), true);

    if (error.status !== 400) {
      toast(messages[0], "error");
    }
  }

  function handleEdit(event) {
    if (submitting || !configReady) {
      return;
    }
    if (!(event.target instanceof HTMLElement)) {
      return;
    }
    if (!event.target.matches("input, select")) {
      return;
    }
    clearFieldErrors();
    setStatus(DEFAULT_HINT);
  }

  dateInput.addEventListener("change", () => {
    dateTouched = true;
  });
  amountInput.addEventListener("blur", () => {
    const parsed = parseAmount(amountInput.value);
    if (!parsed.error) {
      amountInput.value = parsed.value.toFixed(2);
    }
  });
  form.addEventListener("input", handleEdit);
  form.addEventListener("change", handleEdit);
  retryButton.addEventListener("click", () => {
    loadConfig(true);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitting) {
      return;
    }
    if (!configReady) {
      setStatus("记账类别还没有加载完成，请稍后再试。", true);
      return;
    }

    const { errors, payload } = validate();
    if (Object.keys(errors).length) {
      showFieldErrors(errors);
      return;
    }

    clearFieldErrors();
    setStatus(`正在保存${TYPE_LABEL}…`);
    setSubmitting(true);

    try {
      const result = await api.createRecord(payload);
      const saved = result && result.record ? result.record : payload;

      if (!form.isConnected) {
        return;
      }

      toast(
        `已记录${TYPE_LABEL} ${formatMoney(saved.amount)} · ${saved.category}`,
        "success"
      );
      amountInput.value = "";
      noteInput.value = "";
      setStatus("已保存，可继续记录下一笔。");
      amountInput.focus();
      refreshApp().catch(() => {});
    } catch (error) {
      if (form.isConnected) {
        showServerError(error);
      }
    } finally {
      setSubmitting(false);
    }
  });

  loadConfig();
}
