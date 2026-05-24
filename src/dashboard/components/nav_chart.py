"""
nav_chart.py
NAV 走勢折線圖元件 — 支援 QQQ/SPY benchmark 疊加
純 Plotly 邏輯，可在 Streamlit 外獨立測試
"""
from typing import Dict, List

import plotly.graph_objects as go


BENCHMARK_COLORS = {
    "QQQ": "#10b981",
    "SPY": "#f59e0b",
}
NAV_COLOR = "#1a56db"


def build_nav_chart(
    nav_history: List[dict],
    benchmark_series: Dict[str, List[dict]] = None,
    title: str = "NAV 走勢（相對起始值）",
) -> go.Figure:
    """
    建立 NAV 走勢折線圖（Plotly Figure）。

    參數：
        nav_history      : [{"date": "...", "nav": 100000}, ...]
        benchmark_series : {sym: [{"date": "...", "close_norm": 1.02}]}
                           傳入空 dict 或 None 表示不疊加 benchmark
    回傳：
        plotly.graph_objects.Figure（可直接傳給 st.plotly_chart）
    """
    fig = go.Figure()

    # ── NAV 曲線（正規化）──────────────────────────────────────────────────
    if nav_history:
        base = nav_history[0]["nav"]
        if base:
            dates   = [e["date"] for e in nav_history]
            nav_norm = [round(e["nav"] / base, 6) for e in nav_history]
            fig.add_trace(go.Scatter(
                x=dates, y=nav_norm,
                name="NAV",
                mode="lines",
                line=dict(color=NAV_COLOR, width=2.5),
            ))

    # ── Benchmark 曲線 ────────────────────────────────────────────────────
    for sym, series in (benchmark_series or {}).items():
        if series:
            fig.add_trace(go.Scatter(
                x=[e["date"] for e in series],
                y=[e["close_norm"] for e in series],
                name=sym,
                mode="lines",
                line=dict(color=BENCHMARK_COLORS.get(sym, "#888"), width=1.5, dash="dot"),
            ))

    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis_title="相對起始值（1.0 = 起始日）",
        height=320,
        margin=dict(l=0, r=10, t=40, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )
    return fig


def filter_benchmarks(
    benchmark_series: Dict[str, List[dict]],
    selected: List[str],
) -> Dict[str, List[dict]]:
    """
    依使用者勾選過濾 benchmark。
    selected = ["QQQ"]   → 只保留 QQQ，移除 SPY
    selected = []         → 回傳空 dict（不顯示任何 benchmark）
    """
    return {k: v for k, v in benchmark_series.items() if k in selected}
