"""
top10.py
Nasdaq Top 10 分析頁 — 策略持股 + 即時價格
"""
import streamlit as st
import pandas as pd

from src.dashboard.data_provider import DashboardDataProvider
from src.dashboard.components.watchlist import render_watchlist, get_all_watchlist_symbols


def render_top10(provider: DashboardDataProvider, account_id: str) -> None:
    """Nasdaq Top 10 分析：策略持股 + 即時報價 + 三大關注類別"""
    st.title("📈 Nasdaq Top 10 分析")

    # ── 策略持股 ──────────────────────────────────────────────────────────
    strategy_id = provider.account_manager.get_active_strategy(account_id)
    if not strategy_id:
        st.warning("此帳戶尚未設定策略。")
        return

    from src.core.strategy_engine import StrategyEngine
    from src.dashboard.config import _project_root
    import os
    engine = StrategyEngine(strategies_dir=os.path.join(_project_root(), "strategies"))
    try:
        strategy = engine.load(strategy_id)
        symbols  = strategy["universe"]["symbols"]
    except Exception as e:
        st.error(f"載入策略失敗：{e}")
        return

    # ── 即時報價 ──────────────────────────────────────────────────────────
    st.subheader(f"策略：{strategy_id}（{len(symbols)} 檔）")
    with st.spinner("取得即時報價..."):
        client = provider.account_manager.get_client(account_id)
        try:
            prices = client.get_latest_prices(symbols)
        except Exception:
            prices = {}

    rows = []
    for i, sym in enumerate(symbols, 1):
        rows.append({
            "排名": i,
            "股票": sym,
            "最新價": prices.get(sym, "—"),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()

    # ── 三大關注類別 ──────────────────────────────────────────────────────
    watchlist_syms = get_all_watchlist_symbols()
    with st.spinner("載入關注股票報價..."):
        try:
            wl_prices = client.get_latest_prices(watchlist_syms)
        except Exception:
            wl_prices = {}

    render_watchlist(wl_prices)
