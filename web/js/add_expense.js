import { api, formatMoney, refreshApp, toast, todayString } from "./api.js";

function fillCategories(select, categories, keepValue) {
  select.innerHTML = categories
    .map((category) => `<option value="${category}">${category}</option>`)
    .join("");
  if (keepValue && categories.includes(keepValue)) {
    select.value = keepValue;
  }
}

export function mount(container) {
  container.innerHTML = `
    <section class="form-card form-card-expense">
      <header class="form-head">
        <div>
          <p class="form-kicker">EXPENSE</p>
          <h3 class="form-title">记一笔支出</h3>
        </div>
        <span class="form-badge form-badge-expense">支出</span>
      </header>

      <form class="record-form" novalidate>
        <div class="form-grid">
          <label class="field">
            <span class="field-label">日期</span>
            <input class="field-input" type="date" name="date" required>
          </label>
          <label class="field">
            <span class="field-label">金额</span>
            <input class="field-input" type="number" name="amount" min="0.01" step="0.01" placeholder="0.00" required>
          </label>
          <label class="field">
            <span class="field-label">类别</span>
            <select class="field-input" name="category"></select>
          </label>
          <label class="field field-wide">
            <span class="field-label">备注</span>
            <input class="field-input" type="text" name="note" maxlength="100" placeholder="例如：午饭、地铁、奶茶">
          </label>
        </div>
        <p class="form-hint" data-hint>金额必须大于 0，日期默认今天。</p>
        <button class="btn btn-expense" type="submit">
          <span class="btn-text">保存支出</span>
          <span class="btn-loader" aria-hidden="true"></span>
        </button>
      </form>
    </section>
  `;

  const form = container.querySelector("form");
  const dateInput = form.querySelector('[name="date"]');
  const amountInput = form.querySelector('[name="amount"]');
  const categorySelect = form.querySelector('[name="category"]');
  const submitButton = form.querySelector("button[type=submit]");
  const hint = container.querySelector("[data-hint]");

  dateInput.value = todayString();

  api
    .getConfig()
    .then((config) => {
      dateInput.value = config.today || todayString();
      fillCategories(categorySelect, config.expense_categories);
    })
    .catch((error) => toast(error.message, "error"));

  function setLoading(loading) {
    submitButton.disabled = loading;
    submitButton.classList.toggle("is-loading", loading);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const date = dateInput.value;
    const amount = Number(amountInput.value);
    const category = categorySelect.value;

    if (!date) {
      hint.textContent = "请选择日期";
      hint.classList.add("is-error");
      dateInput.focus();
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      hint.textContent = "金额必须大于 0";
      hint.classList.add("is-error");
      amountInput.focus();
      return;
    }
    if (!category) {
      hint.textContent = "请选择类别";
      hint.classList.add("is-error");
      return;
    }

    hint.classList.remove("is-error");
    hint.textContent = "金额必须大于 0，日期默认今天。";

    setLoading(true);
    try {
      const result = await api.createRecord({
        date,
        type: "expense",
        amount: Number(amount.toFixed(2)),
        category,
        note: form.querySelector('[name="note"]').value.trim(),
      });
      toast(`已记录支出 ${formatMoney(result.record.amount)} · ${result.record.category}`);
      amountInput.value = "";
      form.querySelector('[name="note"]').value = "";
      await refreshApp();
    } catch (error) {
      toast(error.message, "error");
    } finally {
      setLoading(false);
    }
  });
}