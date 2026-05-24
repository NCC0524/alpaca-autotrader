"""
overview.py
帳戶總覽頁 — NAV / 損益 / 回撤圖
"""
import datetime

import streamlit as st

from src.dashboard.data_provider import DashboardDataProvider
from src.dashboard.components.nav_chart import build_nav_chart, filter_benchmarks
from src.dashboard.components.drawdown_chart import build_drawdown_chart
from src.dashboard.config import get_benchmark_symbols


def render_overview(provider: DashboardDataProvider, account_id: str) -> None:
    """帳戶總覽：指標卡 + NAV 走勢圖 + 回撤圖"""
    st.title(f"📊 帳戶總覽")

    # ── 即時指標 ──────────────────────────────────────────────────────────
    with st.spinner("讀取帳戶資料..."):
        summary = provider.get_account_summary(account_id)

    def _pct(v):  return f"{v * 100:+.2f}%"
    def _usd(v):  return f"${v:,.2f}"
    def _delta(v):return f"{v * 100:+.2f}%"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 NAV 淨值",    _usd(summary["nav"]),    f"現金 {_usd(summary['cash'])}")
    c2.metric("📅 今日損益",    _usd(summary["daily_pnl"]),  _delta(summary["daily_pnl_pct"]))
    c3.metric("📈 總報酬率",    _pct(summary["total_return_pct"]),
              f"投資 {summary['days_elapsed']} 天")
    c4.metric("🗓 年化收益率",  _pct(summary["annual_return_pct"]),
              f"最大回撤 {_pct(summary['max_drawdown_pct'])}")

    # ── 週 / 月損益 ───────────────────────────────────────────────────────
    w1, w2 = st.columns(2)
    w1.metric("📆 週報酬",  _pct(summary["weekly_pnl_pct"]))
    w2.metric("📆 月報酬",  _pct(summary["monthly_pnl_pct"]))

    st.divider()

    # ── NAV 走勢圖 ────────────────────────────────────────────────────────
    st.subheader("📉 NAV 走勢")
    nav_history = provider.get_nav_history(account_id)

    avail_benchmarks = get_benchmark_symbols()
    selected = st.multiselect(
        "疊加比較指數",
        options=avail_benchmarks,
        default=[],
        help="勾選後自動疊加指數曲線（正規化比較）",
    )

    benchmark_series: dict = {}
    if selected and nav_history:
        inception = nav_history[0]["date"]
        today     = datetime.date.today().isoformat()
        with st.spinner("載入 benchmark 資料..."):
            all_series = provider.get_benchmark_series(account_id, selected, inception, today)
            benchmark_series = filter_benchmarks(all_series, selected)

    st.plotly_chart(
        build_nav_chart(nav_history, benchmark_series),
        use_container_width=True,
    )

    # ── 回撤曲線 ──────────────────────────────────────────────────────────
    st.subheader("📉 回撤曲線（Drawdown）")
    dd_series = DashboardDataProvider.calc_drawdown_series(nav_history)
    st.plotly_chart(
        build_drawdown_chart(dd_series),
        use_container_width=True,
    )
