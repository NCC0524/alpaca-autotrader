"""
data_provider.py
儀表板資料提供層 — 彙整帳戶、持倉、NAV 等資料，與 Streamlit 顯示層完全分離
支援 Streamlit Cloud 與本地環境，透過 config.py 讀取憑證
"""
import datetime
import json
import os
from typing import Dict, List, Optional

from src.core.account_manager import AccountManager
from src.reports.report_model import ReportModel


class DashboardDataProvider:
    """
    儀表板的唯一資料入口。
    - 不直接呼叫任何 st.* 函式（方便單元測試）
    - 透過 account_manager 取得各帳戶的 AlpacaClient
    - 透過 report_model 讀取 / 存取歷史 JSON 報告
    """

    def __init__(self, account_manager: AccountManager, report_model: ReportModel):
        self.account_manager = account_manager
        self.report_model    = report_model

    # ── 工廠方法：自動從 config 初始化（雲端部署推薦用法）──────────────────
    @classmethod
    def from_config(cls, reports_dir: str = None) -> "DashboardDataProvider":
        """
        從 config.py 自動建立 Provider，不需手動傳入任何依賴。
        Streamlit Cloud 部署時，憑證自動從 st.secrets 讀取。
        """
        from src.dashboard.config import get_accounts_registry_path, get_reports_dir
        am = AccountManager(registry_path=get_accounts_registry_path())
        rm = ReportModel(reports_dir=reports_dir or get_reports_dir())
        return cls(account_manager=am, report_model=rm)

    # ── 帳戶摘要 ────────────────────────────────────────────────────────────
    def get_account_summary(self, account_id: str) -> dict:
        """
        取得帳戶摘要：NAV、現金、損益等。
        優先使用當日 JSON 報告；報告不存在時，直接從 Alpaca API 計算。
        - daily_pnl：Alpaca API 的 last_equity（前一交易日收盤）作為基準
        - total / annual return：使用 account_registry 的 inception_nav
        - weekly / monthly：使用最新可用報告的 nav_history
        """
        from src.reports.report_model import ReportModel  # 避免循環引用

        client  = self.account_manager.get_client(account_id)
        account = client.get_account()
        nav         = float(account.get("portfolio_value", 0))
        cash        = float(account.get("cash", 0))
        last_equity = float(account.get("last_equity") or nav)

        today  = datetime.date.today().isoformat()
        report = self.report_model.load(account_id, today)

        # ── 情況 A：當日報告存在 → 直接使用 ──────────────────────────────
        if report and report.get("summary"):
            s = report["summary"]
            return {
                "account_id":        account_id,
                "nav":               round(nav, 2),
                "cash":              round(cash, 2),
                "invested":          round(nav - cash, 2),
                "daily_pnl":         float(s.get("daily_pnl", 0.0)),
                "daily_pnl_pct":     float(s.get("daily_pnl_pct", 0.0)),
                "weekly_pnl_pct":    float(s.get("weekly_pnl_pct", 0.0)),
                "monthly_pnl_pct":   float(s.get("monthly_pnl_pct", 0.0)),
                "total_return_pct":  float(s.get("total_return_pct", 0.0)),
                "annual_return_pct": float(s.get("annual_return_pct", 0.0)),
                "max_drawdown_pct":  float(s.get("max_drawdown_pct", 0.0)),
                "days_elapsed":      int(s.get("days_elapsed", 0)),
                "active_strategy":   self.account_manager.get_active_strategy(account_id),
            }

        # ── 情況 B：無當日報告 → 即時計算 ────────────────────────────────
        # 今日損益：以 Alpaca last_equity（前一交易日收盤）為基準
        daily_pnl     = nav - last_equity
        daily_pnl_pct = (daily_pnl / last_equity) if last_equity else 0.0

        # 起始資料：從 account_registry 讀取
        acc_cfg       = self.account_manager.get_account_config(account_id)
        inception_nav = float(acc_cfg.get("inception_nav") or last_equity or nav)
        inception_date = acc_cfg.get("inception_date") or acc_cfg.get("created_at") or today

        days_elapsed = max(
            (datetime.date.today() - datetime.date.fromisoformat(inception_date)).days,
            1,
        )
        total_return_pct  = (nav / inception_nav - 1) if inception_nav else 0.0
        annual_return_pct = (
            (nav / inception_nav) ** (365.0 / days_elapsed) - 1
            if inception_nav and days_elapsed > 0 else 0.0
        )

        # 週 / 月 / 最大回撤：優先歷史報告，其次 Alpaca portfolio/history API
        nav_history: list = []
        available_dates = self.report_model.list_dates(account_id)
        if available_dates:
            latest = self.report_model.load(account_id, available_dates[0])
            if latest:
                nav_history = latest.get("nav_history", [])

        if not nav_history:
            try:
                nav_history = client.get_portfolio_history(period="1M", timeframe="1D")
            except Exception:
                nav_history = []

        weekly_pnl_pct  = ReportModel._period_return(nav_history, nav, days=7)
        monthly_pnl_pct = ReportModel._period_return(nav_history, nav, days=30)
        max_drawdown_pct = ReportModel._calc_max_drawdown(nav_history) if nav_history else 0.0

        return {
            "account_id":        account_id,
            "nav":               round(nav, 2),
            "cash":              round(cash, 2),
            "invested":          round(nav - cash, 2),
            "daily_pnl":         round(daily_pnl, 2),
            "daily_pnl_pct":     round(daily_pnl_pct, 6),
            "weekly_pnl_pct":    round(weekly_pnl_pct, 6),
            "monthly_pnl_pct":   round(monthly_pnl_pct, 6),
            "total_return_pct":  round(total_return_pct, 6),
            "annual_return_pct": round(annual_return_pct, 6),
            "max_drawdown_pct":  round(max_drawdown_pct, 6),
            "days_elapsed":      days_elapsed,
            "active_strategy":   self.account_manager.get_active_strategy(account_id),
        }

    # ── 持倉 ────────────────────────────────────────────────────────────────
    def get_positions(self, account_id: str) -> list:
        """取得持倉清單，每筆含完整欄位，按市值由大到小排序"""
        client = self.account_manager.get_client(account_id)
        raw    = client.get_positions()
        nav    = client.get_portfolio_value()
        return ReportModel._format_positions(raw, nav)

    # ── NAV 歷史 ─────────────────────────────────────────────────────────────
    def get_nav_history(self, account_id: str) -> List[dict]:
        """
        取得 NAV 歷史（多資料點，供走勢圖與回撤圖使用）。

        優先順序：
        1. 當日 JSON 報告的 nav_history（GitHub Actions 每日提交）
        2. Alpaca portfolio/history API（最近 1 個月日線）
        3. fallback：僅含今日一筆
        """
        today  = datetime.date.today().isoformat()
        report = self.report_model.load(account_id, today)
        if report and report.get("nav_history"):
            return report["nav_history"]

        # ── fallback：直接從 Alpaca API 取歷史 NAV ─────────────────────────
        client = self.account_manager.get_client(account_id)
        try:
            history = client.get_portfolio_history(period="1M", timeframe="1D")
            if history:
                # 補上今日最新 NAV（API 可能不含當日未收盤資料）
                nav_today = client.get_portfolio_value()
                if history[-1]["date"] != today:
                    history.append({"date": today, "nav": round(nav_today, 2)})
                else:
                    history[-1]["nav"] = round(nav_today, 2)
                return history
        except Exception:
            pass  # API 失敗時 fallback 到單一資料點

        nav = client.get_portfolio_value()
        return [{"date": today, "nav": round(nav, 2)}]

    # ── Benchmark 序列 ───────────────────────────────────────────────────────
    def get_benchmark_series(
        self,
        account_id: str,
        symbols: List[str],
        start: str,
        end: str,
    ) -> Dict[str, List[dict]]:
        """
        取得 QQQ / SPY 等指數的日線資料，正規化為起始值 = 1.0。
        回傳 {sym: [{"date": "...", "close_norm": 1.02}, ...]}
        """
        client = self.account_manager.get_client(account_id)
        result: Dict[str, List[dict]] = {}
        for sym in symbols:
            bars = client.get_historical_bars(sym, start, end, "1Day")
            normed = self._normalize_bars(bars)
            if normed:
                result[sym] = normed
        return result

    @staticmethod
    def _normalize_bars(bars: list) -> list:
        """將股價序列正規化，第一筆 close = 1.0"""
        if not bars:
            return []
        base = bars[0].get("close", 0)
        if not base:
            return []
        return [
            {"date": b["date"], "close_norm": round(b["close"] / base, 6)}
            for b in bars
        ]

    # ── 回撤序列 ─────────────────────────────────────────────────────────────
    @staticmethod
    def calc_drawdown_series(nav_history: List[dict]) -> List[dict]:
        """
        計算每日回撤序列，用於繪製 Drawdown 曲線圖。
        回傳 [{"date": "...", "drawdown": -0.023}, ...]
        所有回撤值 <= 0（0 表示當日正處於歷史高點）。
        """
        if not nav_history:
            return []
        peak   = nav_history[0]["nav"]
        result = []
        for entry in nav_history:
            nav = entry["nav"]
            if nav > peak:
                peak = nav
            dd = (nav - peak) / peak if peak else 0.0
            result.append({"date": entry["date"], "drawdown": round(dd, 8)})
        return result

    # ── 歷史報告 ─────────────────────────────────────────────────────────────
    def get_available_dates(self, account_id: str) -> List[str]:
        """列出有歷史報告的所有日期（由新到舊）"""
        return self.report_model.list_dates(account_id)

    def load_history_report(self, account_id: str, date: str) -> Optional[dict]:
        """載入指定日期的歷史報告，找不到回傳 None"""
        return self.report_model.load(account_id, date)

    # ── 自動刷新設定 ─────────────────────────────────────────────────────────
    @staticmethod
    def get_refresh_interval_ms() -> int:
        """自動刷新間隔（毫秒），來源：config/settings.json"""
        from src.dashboard.config import get_refresh_interval_seconds
        return get_refresh_interval_seconds() * 1000
