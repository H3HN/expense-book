from datetime import date

import streamlit as st

from src.config import CURRENCY, INCOME_CATEGORIES
from src.models import new_record
from src.storage import add_record
from src.validator import validate_record


def render_add_income():
    st.subheader("记一笔收入")
    with st.form("income_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            day = st.date_input("日期", value=date.today(), key="income_date")
            category = st.selectbox("类别", INCOME_CATEGORIES, key="income_category")
        with col2:
            amount = st.number_input("金额", min_value=0.0, step=10.0, format="%.2f", key="income_amount")
            note = st.text_input("备注", max_chars=100, placeholder="例如：兼职家教", key="income_note")
        submitted = st.form_submit_button("保存收入", use_container_width=True)

    if not submitted:
        return

    payload = {"date": day.strftime("%Y-%m-%d"), "type": "income", "amount": amount, "category": category, "note": note}
    errors = validate_record(payload)
    if errors:
        for error in errors:
            st.error(error)
        return

    record = new_record(payload["date"], payload["type"], payload["amount"], payload["category"], payload["note"])
    add_record(record)
    st.success(f"已记录收入 {CURRENCY}{amount:.2f} · {category}")