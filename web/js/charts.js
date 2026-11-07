import { api, formatMoney, on, toast } from "./api.js";

const COLORS = {
  income: "#2F6F5E",
  expense: "#C05746",
  balance: "#A98A5B",
  text: "#2B2B2B",
  muted: "#7A7468",
  grid: "#EAE4D9",
};

const RING_PALETTE = ["#2F6F5E", "#7FA99B", "#C05746", "#E0A458", "#6B7A8F", "#B8AFA0", "#9C6B7A", "#4C6B54"];

let trendChart = null;
let ringChart = null;
let ringType = "expense";
let latestStats = null;
let active = false;
let host = null;
let resizeBound = false;
let resizeTimer = null;
let rangeStart = "";
let rangeEnd = "";

function hasEcharts() {
  return typeof window !== "undefined" && typeof window.echarts !== "undefined";
}

function showFallback(message) {
  const trendBox = host.querySelector("#trend-chart");
  const ringBox = host.querySelector("#ring-chart");
  [trendBox, ringBox].forEach((box) => {
    if (box) {
      box.innerHTML = `<div class="chart-fallback"><span>◇</span><p>${message}</p></div>`;
    }
  });
}

function initCharts() {
  if (trendChart && ringChart) {
    return true;
  }
  if (!hasEcharts()) {
    showFallback("ECharts 未加载成功，请检查网络或改用本地 echarts.min.js");
    return false;
  }
  const trendBox = host.querySelector("#trend-chart");
  const ringBox = host.querySelector("#ring-chart");
  if (!trendBox || !ringBox) {
    return false;
  }
  trendBox.innerHTML = "";
  ringBox.innerHTML = "";
  trendChart = window.echarts.init(trendBox);
  ringChart = window.echarts.init(ringBox);
  return true;
}

function emptyGraphic(text) {
  return {
    type: "text",
    left: "center",
    top: "middle",
    style: {
      text,
      fill: COLORS.muted,
      fontSize: 13,
      fontFamily: "Microsoft YaHei, PingFang SC, sans-serif",
    },
  };
}

function trendOption(rows) {
  if (!rows.length) {
    return {
      graphic: [emptyGraphic("该区间暂无数据")],
      tooltip: { show: false },
    };
  }

  const dates = rows.map((row) => row.date);
  const income = rows.map((row) => row.income);
  const expense = rows.map((row) => row.expense);
  const balance = rows.map((row) => row.balance);

  return {
    color: [COLORS.income, COLORS.expense, COLORS.balance],
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255,255,255,.96)",
      borderColor: COLORS.grid,
      borderWidth: 1,
      textStyle: { color: COLORS.text, fontSize: 12 },
      axisPointer: { type: "line", lineStyle: { color: "#CFC7B8", type: "dashed" } },
      formatter(params) {
        const lines = [`<strong>${params[0].axisValue}</strong>`];
        params.forEach((item) => {
          lines.push(`${item.marker}${item.seriesName}　${formatMoney(item.value)}`);
        });
        return lines.join("<br/>");
      },
    },
    legend: {
      top: 4,
      right: 8,
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 6,
      textStyle: { color: COLORS.muted, fontSize: 12 },
    },
    grid: { left: 12, right: 18, top: 42, bottom: 28, containLabel: true },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: COLORS.grid } },
      axisTick: { show: false },
      axisLabel: { color: COLORS.muted, fontSize: 11, hideOverlap: true },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: COLORS.grid, type: "dashed" } },
      axisLabel: { color: COLORS.muted, fontSize: 11 },
    },
    series: [
      {
        name: "收入",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 5,
        data: income,
        lineStyle: { width: 2.4 },
        areaStyle: {
          color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(47,111,94,.22)" },
            { offset: 1, color: "rgba(47,111,94,.02)" },
          ]),
        },
      },
      {
        name: "支出",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 5,
        data: expense,
        lineStyle: { width: 2.4 },
        areaStyle: {
          color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(192,87,70,.20)" },
            { offset: 1, color: "rgba(192,87,70,.02)" },
          ]),
        },
      },
      {
        name: "结余",
        type: "line",
        smooth: true,
        symbol: "none",
        data: balance,
        lineStyle: { width: 1.6, type: "dashed" },
      },
    ],
  };
}

function ringRows() {
  if (!latestStats) {
    return [];
  }
  return ringType === "income" ? latestStats.income_by_category : latestStats.expense_by_category;
}

function ringTotal(rows) {
  return rows.reduce((sum, row) => sum + Number(row.amount || 0), 0);
}

function ringOption(rows) {
  const title = ringType === "income" ? "收入构成" : "支出构成";
  if (!rows.length) {
    return {
      title: {
        text: title,
        subtext: "该区间暂无数据",
        left: "center",
        top: "38%",
        textStyle: { color: COLORS.text, fontSize: 13, fontWeight: 600 },
        subtextStyle: { color: COLORS.muted, fontSize: 11 },
      },
      graphic: [emptyGraphic("暂无数据")],
      tooltip: { show: false },
    };
  }

  const total = ringTotal(rows);
  return {
    color: RING_PALETTE,
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(255,255,255,.96)",
      borderColor: COLORS.grid,
      borderWidth: 1,
      textStyle: { color: COLORS.text, fontSize: 12 },
      formatter: (item) => `${item.marker}${item.name}<br/>${formatMoney(item.value)} · ${item.percent}%`,
    },
    legend: {
      bottom: 0,
      icon: "circle",
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: COLORS.muted, fontSize: 11 },
    },
    title: {
      text: formatMoney(total),
      subtext: ringType === "income" ? "收入合计" : "支出合计",
      left: "center",
      top: "35%",
      textStyle: { color: COLORS.text, fontSize: 15, fontWeight: 600 },
      subtextStyle: { color: COLORS.muted, fontSize: 11 },
    },
    series: [
      {
        name: title,
        type: "pie",
        radius: ["46%", "68%"],
        center: ["50%", "46%"],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: "#FFFFFF", borderWidth: 2, borderRadius: 5 },
        label: { show: false },
        emphasis: {
          scale: true,
          scaleSize: 4,
          itemStyle: { shadowBlur: 14, shadowColor: "rgba(47,111,94,.20)" },
        },
        data: rows.map((row) => ({
          name: row.category,
          value: Number(row.amount || 0),
        })),
      },
    ],
  };
}

function render() {
  if (!latestStats || !trendChart || !ringChart) {
    return;
  }
  trendChart.setOption(trendOption(latestStats.daily_totals || []), true);
  ringChart.setOption(ringOption(ringRows()), true);

  const titleNode = host.querySelector("[data-ring-title]");
  if (titleNode) {
    titleNode.textContent = ringType === "income" ? "收入构成" : "支出构成";
  }
  host.querySelectorAll("[data-ring]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.ring === ringType);
  });

  const hint = host.querySelector("[data-range-hint]");
  if (hint) {
    const days = (latestStats.daily_totals || []).length;
    hint.textContent = `${latestStats.summary.count} 笔 · ${days} 天有收支`;
  }

  host.querySelectorAll("[data-range-quick]").forEach((button) => {
    const quick = button.dataset.rangeQuick;
    const isAll = quick === "all" && !rangeStart && !rangeEnd;
    button.classList.toggle("is-active", isAll);
  });
}

function shiftDate(days) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function todayString() {
  return shiftDate(0);
}

function syncRangeInputs() {
  const startInput = host.querySelector("[data-chart-start]");
  const endInput = host.querySelector("[data-chart-end]");
  if (startInput) {
    startInput.value = rangeStart;
  }
  if (endInput) {
    endInput.value = rangeEnd;
  }
}

async function load(range) {
  if (range && typeof range === "object") {
    rangeStart = range.start || "";
    rangeEnd = range.end || "";
  }
  syncRangeInputs();

  if (rangeStart && rangeEnd && rangeStart > rangeEnd) {
    toast("图表起始日期不能晚于结束日期", "error");
    return;
  }

  try {
    latestStats = await api.getStats({ start: rangeStart, end: rangeEnd });
    render();
  } catch (error) {
    toast(error.message, "error");
  }
}

function resizeCharts() {
  if (trendChart) {
    trendChart.resize();
  }
  if (ringChart) {
    ringChart.resize();
  }
}

function waitForEcharts(timeout = 8000) {
  return new Promise((resolve) => {
    const started = Date.now();
    const tick = () => {
      if (hasEcharts()) {
        resolve(true);
        return;
      }
      if (Date.now() - started >= timeout) {
        resolve(false);
        return;
      }
      window.setTimeout(tick, 150);
    };
    tick();
  });
}

export async function activate() {
  active = true;

  if (!hasEcharts()) {
    showFallback("正在加载图表引擎…");
    const ready = await waitForEcharts();
    if (!ready) {
      showFallback("ECharts 未加载成功，请检查网络或改用本地 echarts.min.js");
      return;
    }
  }

  if (!initCharts()) {
    return;
  }

  if (!resizeBound) {
    resizeBound = true;
    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(resizeCharts, 160);
    });
  }

  resizeCharts();
  await load();
}

export function mount(container) {
  host = container;
  container.innerHTML = `
    <section class="charts-card">
      <header class="records-head">
        <div>
          <p class="form-kicker">INSIGHT</p>
          <h3 class="form-title">可视化洞察</h3>
        </div>
        <div class="ring-switch" role="group" aria-label="环形图类别切换">
          <button type="button" data-ring="expense" class="is-active">支出构成</button>
          <button type="button" data-ring="income">收入构成</button>
        </div>
      </header>

      <div class="chart-range">
        <span class="chart-range-label">统计区间</span>
        <input class="field-input" type="date" data-chart-start aria-label="图表起始日期">
        <span class="range-arrow">→</span>
        <input class="field-input" type="date" data-chart-end aria-label="图表结束日期">
        <button type="button" class="btn btn-ghost btn-sm" data-range-quick="7">近 7 天</button>
        <button type="button" class="btn btn-ghost btn-sm" data-range-quick="30">近 30 天</button>
        <button type="button" class="btn btn-ghost btn-sm" data-range-quick="all">全部</button>
        <span class="chart-range-hint" data-range-hint></span>
      </div>

      <div class="charts-grid">
        <div class="chart-box chart-box-wide">
          <h4 class="chart-title">每日收支与结余趋势</h4>
          <div id="trend-chart" class="chart-canvas"></div>
        </div>
        <div class="chart-box">
          <h4 class="chart-title" data-ring-title>支出构成</h4>
          <div id="ring-chart" class="chart-canvas"></div>
        </div>
      </div>
    </section>
  `;

  container.addEventListener("click", (event) => {
    const ringButton = event.target.closest("[data-ring]");
    if (ringButton && ringButton.dataset.ring !== ringType) {
      ringType = ringButton.dataset.ring;
      render();
      return;
    }

    const quickButton = event.target.closest("[data-range-quick]");
    if (!quickButton) {
      return;
    }
    const quick = quickButton.dataset.rangeQuick;
    if (quick === "all") {
      rangeStart = "";
      rangeEnd = "";
    } else {
      rangeStart = shiftDate(-(Number(quick) - 1));
      rangeEnd = todayString();
    }
    load();
  });

  container.addEventListener("change", (event) => {
    const target = event.target;
    if (target.matches("[data-chart-start]")) {
      rangeStart = target.value;
      load();
    } else if (target.matches("[data-chart-end]")) {
      rangeEnd = target.value;
      load();
    }
  });

  on("app:changed", () => {
    if (active) {
      load();
    }
  });

  return { activate, reload: load, resize: resizeCharts };
}