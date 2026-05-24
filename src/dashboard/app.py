"""
app.py
Streamlit Dashboard 主程式
部署方式：
  - 本地：streamlit run streamlit_app.py
  - Streamlit Cloud：連接 GitHub repo，入口為 streamlit_app.py
  - 憑證：.streamlit/secrets.toml（本地）或 Streamlit Cloud App Settings（雲端）
"""
import sys
import os

# 確保專案根目錄在 Python path（本地與雲端環境均適用）
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

from src.dashboard.data_provider import DashboardDataProvider
from src.dashboard.config import get_refresh_interval_seconds

# ── 頁面設定 ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Alpaca Auto Trader",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

REFRESH_INTERVAL_S = get_refresh_interval_seconds()
PAGES = {
    "📊 帳戶總覽":   "overview",
    "📋 持倉明細":   "positions",
    "📈 Top 10 分析": "top10",
    "📅 歷史報告":   "history",
}


@st.cache_resource(show_spinner=False)
def _get_provider() -> DashboardDataProvider:
    """建立並快取 DashboardDataProvider（跨 session 重複使用）"""
    return DashboardDataProvider.from_config()


def main():
    provider = _get_provider()

    # ── Sidebar ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## 🏦 Alpaca Auto Trader")
        st.divider()

        # 帳戶選擇器
        all_ids = provider.account_manager.get_all_account_ids()
        account_id = st.selectbox("🔑 選擇帳戶", all_ids, index=0)

        st.divider()

        # 頁面導航
        page_label = st.radio("📑 頁面", list(PAGES.keys()))
        page_key   = PAGES[page_label]

        st.divider()
        st.caption(f"🔄 自動刷新：每 {REFRESH_INTERVAL_S} 秒")
        if st.button("🔄 立即刷新"):
            st.cache_data.clear()
            st.rerun()

        st.caption("⚠️ 本系統僅供資訊參考，不構成投資建議。")

    # ── 主頁面（使用 fragment 實現自動刷新）─────────────────────────────────
    @st.fragment(run_every=REFRESH_INTERVAL_S)
    def _render_page():
        if page_key == "overview":
            from src.dashboard.pages.overview import render_overview
            render_overview(provider, account_id)
        elif page_key == "positions":
            from src.dashboard.pages.positions import render_positions
            render_positions(provider, account_id)
        elif page_key == "top10":
            from src.dashboard.pages.top10 import render_top10
            render_top10(provider, account_id)
        elif page_key == "history":
            from src.dashboard.pages.history import render_history
            render_history(provider, account_id)

    _render_page()


if __name__ == "__main__":
    main()
