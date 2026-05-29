"""
history.py
歷史報告查閱頁 — 日期選擇器 + 報告顯示
"""
import datetime

import streamlit as st

from src.dashboard.data_provider import DashboardDataProvider
from src.reports.report_view import ReportView


_view = ReportView()


def render_history(provider: DashboardDataProvider, account_id: str) -> None:
    """歷史報告：選擇日期後顯示完整 HTML 報告內容"""
    st.title("📅 歷史報告查閱")

    available_dates = provider.get_available_dates(account_id)

    if not available_dates:
        st.info("尚無歷史報告。報告由 GitHub Actions 每日自動產生並提交。")
        return



    # ── 日期選擇器 ────────────────────────────────────────────────────────
    latest_date = datetime.date.fromisoformat(available_dates[0])
    selected_dt = st.date_input(
        "選擇日期",
        value=latest_date,
        min_value=datetime.date.fromisoformat(available_dates[-1]),
        max_value=latest_date,
    )
    selected_date = selected_dt.isoformat()

    # ── 載入並顯示報告 ────────────────────────────────────────────────────
    report = provider.load_history_report(account_id, selected_date)
    if report is None:
        st.warning(f"找不到 {selected_date} 的報告（可能該日為假日或報告尚未產生）。")
        return

    # 即時生成的報告加上提示標籤
    if report.get("live"):
        st.info("📡 今日報告為即時快照（GitHub Actions 尚未產生正式報告）", icon="ℹ️")

    s = report["summary"]
    def _pct(v): return f"{v * 100:+.2f}%"
    def _usd(v): return f"${v:,.2f}"

    # ── 指標摘要 ──────────────────────────────────────────────────────────
    st.subheader(f"📋 {selected_date} 報告摘要")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("NAV",      _usd(s["nav"]))
    c2.metric("今日損益", _usd(s["daily_pnl"]),  _pct(s["daily_pnl_pct"]))
    c3.metric("總報酬",   _pct(s["total_return_pct"]))
    c4.metric("最大回撤", _pct(s["max_drawdown_pct"]))

    # ── 完整 HTML 報告（內嵌） ────────────────────────────────────────────
    with st.expander("查看完整 HTML 報告", expanded=False):
        html = _view.render_html(report)
        st.components.v1.html(html, height=800, scrolling=True)

    # ── 下載按鈕 ──────────────────────────────────────────────────────────
    import json
    st.download_button(
        label="⬇️ 下載 JSON 報告",
        data=json.dumps(report, ensure_ascii=False, indent=2),
        file_name=f"{account_id}_{selected_date}.json",
        mime="application/json",
    )
