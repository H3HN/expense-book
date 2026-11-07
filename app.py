from datetime import date, timedelta

import streamlit as st

from src.add_expense import render_add_expense
from src.add_income import render_add_income
from src.charts import render_charts
from src.config import CURRENCY
from src.data_page import render_data_page
from src.models import new_record
from src.nl_parser import parse_text
from src.records_view import render_records
from src.stats import daily_totals, summary, totals
from src.stats_by_category import by_category
from src.storage import add_record, load_records
from src.validator import validate_record

st.set_page_config(page_title="简易记账本 · 福大智联", page_icon="🧾", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 2.2rem; max-width: 1180px;}
    h1, h2, h3 {letter-spacing: .5px;}
    div[data-testid="stMetricValue"] {font-size: 1.7rem;}
    div[data-testid="stMetric"] {
        background: #FFFFFF; border: 1px solid #E3DDD1; border-left: 4px solid #2F6F5E;
        border-radius: 12px; padding: 14px 18px;
    }
    .stTabs [data-baseweb="tab-list"] {gap: 6px;}
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0; padding: 8px 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

records = load_records()
total = totals(records)

st.title("简易记账本")
st.caption("福大智联 · 2026 秋软件工程现场编程 · Python + Streamlit")

col1, col2, col3, col4 = st.columns(4)
col1.metric("总收入", f"{CURRENCY}{total['income']:,.2f}")
col2.metric("总支出", f"{CURRENCY}{total['expense']:,.2f}")
col3.metric("结余", f"{CURRENCY}{total['balance']:,.2f}")
col4.metric("记录笔数", f"{len(records)} 笔")

with st.sidebar:
    st.header("快速记一笔")
    quick = st.text_input("一句话记账", placeholder="午饭 25")
    if st.button("解析并保存", use_container_width=True):
        parsed = parse_text(quick)
        if not parsed:
            st.error("没识别出金额，试试“午饭 25”")
        else:
            payload = {**parsed, "date": date.today().strftime("%Y-%m-%d")}
            errors = validate_record(payload)
            if errors:
                for error in errors:
                    st.error(error)
            else:
                add_record(new_record(payload["date"], payload["type"], payload["amount"], payload["category"], payload["note"]))
                st.success(f"已记录：{payload['note']} {CURRENCY}{payload['amount']:.2f}")
                st.rerun()

    st.divider()
    st.caption("数据结构：JSON 本地文件")
    st.caption(f"数据文件：data/records.json")

tab_add, tab_records, tab_stats, tab_charts, tab_data = st.tabs(["记账", "明细", "统计", "图表", "数据"])

with tab_add:
    left, right = st.columns(2)
    with left:
        render_add_expense()
    with right:
        render_add_income()

with tab_records:
    render_records()

with tab_stats:
    st.subheader("收支统计")
    col1, col2 = st.columns(2)
    start = col1.date_input("起始日期", value=date.today() - timedelta(days=30), key="stats_start")
    end = col2.date_input("结束日期", value=date.today(), key="stats_end")

    if start > end:
        st.warning("起始日期不能晚于结束日期")
    else:
        result = summary(records, start, end)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("区间收入", f"{CURRENCY}{result['income']:,.2f}")
        c2.metric("区间支出", f"{CURRENCY}{result['expense']:,.2f}")
        c3.metric("区间结余", f"{CURRENCY}{result['balance']:,.2f}")
        c4.metric("笔数", result["count"])

        left, right = st.columns(2)
        with left:
            st.markdown("**支出类别排行**")
            st.dataframe(by_category(records, "expense"), use_container_width=True, hide_index=True)
        with right:
            st.markdown("**收入类别排行**")
            st.dataframe(by_category(records, "income"), use_container_width=True, hide_index=True)

with tab_charts:
    render_charts(records, daily_totals(records), by_category(records, "expense"))

with tab_data:
    render_data_page(records)