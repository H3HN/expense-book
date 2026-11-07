from datetime import date

import streamlit as st

from src.config import CURRENCY, EXPENSE_CATEGORIES
from src.models import new_record
from src.storage import add_record
from src.validator import validate_record


def render_add_expense():
    st.subheader("记一笔支出")
    with st.form("expense_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            day = st.date_input("日期", value=date.today(), key="expense_date")
            category = st.selectbox("类别", EXPENSE_CATEGORIES, key="expense_category")
        with col2:
            amount = st.number_input("金额", min_value=0.0, step=1.0, format="%.2f", key="expense_amount")
            note = st.text_input("备注", max_chars=100, placeholder="例如：午饭", key="expense_note")
        submitted = st.form_submit_button("保存支出", use_container_width=True)

    if not submitted:
        return

    payload = {"date": day.strftime("%Y-%m-%d"), "type": "expense", "amount": amount, "category": category, "note": note}
    errors = validate_record(payload)
    if errors:
        for error in errors:
            st.error(error)
        return

    record = new_record(payload["date"], payload["type"], payload["amount"], payload["category"], payload["note"])
    add_record(record)
    st.success(f"已记录支出 {CURRENCY}{amount:.2f} · {category}")