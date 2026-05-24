"""
watchlist.py
三大關注類別股票元件
"""
import streamlit as st
from typing import Dict, List


WATCHLIST_CATEGORIES = {
    "🏢 科技龍頭": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
    "💾 半導體":   ["NVDA", "AMD", "AVGO", "QCOM", "INTC"],
    "🤖 AI 概念":  ["NVDA", "MSFT", "PLTR", "AI", "SOUN"],
}


def render_watchlist(prices: Dict[str, float], header: str = "📌 三大關注類別"):
    """
    渲染三大關注類別股票，顯示最新價格。

    參數：
        prices : {sym: price} — 從 AlpacaClient.get_latest_prices() 取得
    """
    st.subheader(header)
    cols = st.columns(len(WATCHLIST_CATEGORIES))
    for col, (category, symbols) in zip(cols, WATCHLIST_CATEGORIES.items()):
        with col:
            st.markdown(f"**{category}**")
            for sym in symbols:
                price = prices.get(sym)
                if price:
                    st.markdown(f"• `{sym}` &nbsp; **${price:,.2f}**", unsafe_allow_html=True)
                else:
                    st.markdown(f"• `{sym}` &nbsp; —", unsafe_allow_html=True)


def get_all_watchlist_symbols() -> List[str]:
    """取得所有關注股票 symbol（去重）"""
    seen = set()
    result = []
    for symbols in WATCHLIST_CATEGORIES.values():
        for sym in symbols:
            if sym not in seen:
                seen.add(sym)
                result.append(sym)
    return result
