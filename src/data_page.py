import streamlit as st

from src.import_export import from_csv, to_csv
from src.storage import save_records


def render_data_page(records):
    st.subheader("导入 / 导出")
    st.caption("导出的 CSV 可直接用 Excel 打开；再次导入时按记录 ID 去重合并。")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "导出全部记录（CSV）",
            data=to_csv(records),
            file_name="records.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col2:
        st.metric("当前可导出", f"{len(records)} 条")

    uploaded = st.file_uploader("导入 CSV（与导出格式一致）", type=["csv"])
    if uploaded is not None and st.button("确认导入", use_container_width=True):
        incoming = from_csv(uploaded.getvalue())
        if not incoming:
            st.warning("文件里没有可识别的记录，请检查表头 date/amount 等字段。")
            return
        merged = {item["id"]: item for item in records}
        for item in incoming:
            merged[item["id"]] = item
        save_records(list(merged.values()))
        st.success(f"已导入 {len(incoming)} 条记录")
        st.rerun()