from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.config import CURRENCY, EXPENSE_CATEGORIES, INCOME_CATEGORIES, RECORD_TYPES
from src.storage import delete_record, load_records


def render_records():
    records = load_records()
    st.subheader("收支明细")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        rtype = st.selectbox("类型", ["全部", "expense", "income"], key="view_type")
    with col2:
        start = st.date_input("起始日期", value=date.today() - timedelta(days=30), key="view_start")
    with col3:
        limit = st.slider("显示最近", 5, 100, 20, step=5, key="view_limit")

    selected = [r for r in records if r.get("date", "") >= start.strftime("%Y-%m-%d")]
    if rtype != "全部":
        selected = [r for r in selected if r.get("type") == rtype]
    selected.sort(key=lambda r: (r.get("date", ""), r.get("created_at", "")), reverse=True)

    if not selected:
        st.info("该范围内还没有记录，去左侧记一笔吧。")
        return

    table = pd.DataFrame([
        {
            "日期": r["date"],
            "类型": RECORD_TYPES.get(r["type"], r["type"]),
            "类别": r["category"],
            "金额": round(float(r["amount"]), 2),
            "备注": r.get("note", ""),
        }
        for r in selected[:limit]
    ])
    st.dataframe(table, use_container_width=True, hide_index=True)

    with st.expander("删除记录"):
        options = {f"{r['date']} {RECORD_TYPES.get(r['type'])} {CURRENCY}{float(r['amount']):.2f} {r['category']}": r["id"] for r in selected[:limit]}
        label = st.selectbox("选择要删除的记录", list(options.keys()), key="delete_label")
        if st.button("删除", key="delete_button"):
            if delete_record(options[label]):
                st.success("已删除")
                st.rerun()