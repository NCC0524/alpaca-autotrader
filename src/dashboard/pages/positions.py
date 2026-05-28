"""
positions.py
持倉明細頁
"""
import streamlit as st
import pandas as pd

from src.dashboard.data_provider import DashboardDataProvider


def render_positions(provider: DashboardDataProvider, account_id: str) -> None:
    """持倉明細：表格 + 資產配置圓餅圖"""
    st.title("📋 持倉明細")

    with st.spinner("載入持倉..."):
        positions = provider.get_positions(account_id)

    if not positions:
        st.info("目前尚無持倉。")
        return

    # ── 表格 ──────────────────────────────────────────────────────────────
    df = pd.DataFrame(positions)
    display_cols = {
        "symbol":          "股票",
        "current_price":   "現價",
        "avg_entry_price": "均價",
        "qty":             "股數",
        "market_value":    "市值",
        "weight_pct":      "權重 %",
        "pnl_pct":         "損益 %",
        "pnl_amount":      "損益金額",
    }
    df = df[[c for c in display_cols if c in df.columns]]
    df = df.rename(columns=display_cols)

    def color_pnl(val):
        if isinstance(val, (int, float)):
            color = "#059669" if val >= 0 else "#dc2626"
            return f"color: {color}; font-weight: bold"
        return ""

    styled = df.style.map(color_pnl, subset=["損益 %", "損益金額"]) \
                     .format({
                         "現價":    "${:,.2f}",
                         "均價":    "${:,.2f}",
                         "市值":    "${:,.2f}",
                         "損益金額": "${:,.2f}",
                         "權重 %":  "{:.2f}%",
                         "損益 %":  "{:.2%}",
                     })
    st.dataframe(styled, use_container_width=True)

    # ── 資產配置 ──────────────────────────────────────────────────────────
    st.subheader("🥧 資產配置")
    import plotly.graph_objects as go
    fig = go.Figure(go.Pie(
        labels=[p["symbol"] for p in positions],
        values=[p["market_value"] for p in positions],
        hole=0.4,
    ))
    fig.update_layout(height=300, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig, use_container_width=True)
