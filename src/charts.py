import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.rcParams["axes.edgecolor"] = "#D8D2C6"
matplotlib.rcParams["axes.labelcolor"] = "#3A3A3A"
matplotlib.rcParams["xtick.color"] = "#6B6B6B"
matplotlib.rcParams["ytick.color"] = "#6B6B6B"

INCOME_COLOR = "#2F6F5E"
EXPENSE_COLOR = "#C05746"


def trend_chart(daily_rows):
    fig, ax = plt.subplots(figsize=(7.5, 3.4), dpi=140)
    if not daily_rows:
        ax.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=12, color="#8A8A8A")
        ax.axis("off")
        return fig

    frame = pd.DataFrame(daily_rows)
    x = range(len(frame))
    ax.plot(x, frame["expense"], color=EXPENSE_COLOR, linewidth=2, marker="o", markersize=4, label="支出")
    ax.plot(x, frame["income"], color=INCOME_COLOR, linewidth=2, marker="o", markersize=4, label="收入")
    ax.fill_between(x, frame["expense"], color=EXPENSE_COLOR, alpha=0.08)
    step = max(1, len(frame) // 6)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels(frame["date"][::step], rotation=30, fontsize=8)
    ax.set_ylabel("金额（元）", fontsize=9)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.grid(axis="y", color="#E7E2D8", linewidth=0.8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return fig


def category_chart(rows, kind="expense"):
    fig, ax = plt.subplots(figsize=(5.2, 3.4), dpi=140)
    if not rows:
        ax.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=12, color="#8A8A8A")
        ax.axis("off")
        return fig

    labels = [item["category"] for item in rows]
    values = [item["amount"] for item in rows]
    palette = ["#2F6F5E", "#7FA99B", "#C05746", "#E0A458", "#6B7A8F", "#B8AFA0", "#9C6B7A", "#4C6B54"]
    colors = [palette[i % len(palette)] for i in range(len(labels))]
    ax.pie(values, labels=labels, colors=colors, autopct="%1.0f%%", startangle=90,
           textprops={"fontsize": 9}, wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 1.5})
    ax.set_title("支出构成" if kind == "expense" else "收入构成", fontsize=10, color="#3A3A3A")
    fig.tight_layout()
    return fig


def render_charts(records, daily_rows, category_rows):
    st.subheader("可视化")
    col1, col2 = st.columns([3, 2])
    with col1:
        st.caption("收支趋势")
        st.pyplot(trend_chart(daily_rows), use_container_width=True)
    with col2:
        st.caption("支出类别占比")
        st.pyplot(category_chart(category_rows), use_container_width=True)