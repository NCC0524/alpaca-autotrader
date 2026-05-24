"""
report_model.py
報告資料層（Model） — 產生標準化 JSON 報告，與顯示層完全分離
"""
import json
import os
import datetime
from typing import Optional

from src.core.alpaca_client import AlpacaClient


class ReportModel:
    """
    每日報告 Model。
    負責：收集資料、計算指標、輸出 JSON。
    不負責：顯示、Email、HTML 渲染（那是 View 的事）
    """

    def __init__(self, client: AlpacaClient, reports_dir: str = "reports/model"):
        self.client      = client
        self.reports_dir = reports_dir

    # ── 主要產生函式 ──────────────────────────────────────────────────────
    def generate(
        self,
        account_id:     str,
        strategy_id:    str,
        nav_history:    list,
        inception_nav:  float,
        inception_date: str,
        watchlist:      dict = None,
    ) -> dict:
        """
        產生完整每日報告 dict（JSON 可序列化）

        參數：
            nav_history    : [{"date": "...", "nav": 100000}, ...]
            inception_nav  : 起始 NAV
            inception_date : "2026-05-24"
        """
        today = datetime.date.today().isoformat()

        # ── 帳戶基本資料 ───────────────────────────────────────────────
        account  = self.client.get_account()
        nav      = float(account.get("portfolio_value", 0))
        cash     = float(account.get("cash", 0))

        # ── 損益計算 ───────────────────────────────────────────────────
        yesterday_nav = self._get_yesterday_nav(nav_history, today)
        daily_pnl     = nav - yesterday_nav
        daily_pnl_pct = daily_pnl / yesterday_nav if yesterday_nav else 0.0

        weekly_pnl_pct  = self._period_return(nav_history, nav, days=7)
        monthly_pnl_pct = self._period_return(nav_history, nav, days=30)

        total_return_pct = (nav / inception_nav - 1) if inception_nav else 0.0
        days_elapsed     = (datetime.date.today() - datetime.date.fromisoformat(inception_date)).days
        annual_return_pct = (
            (nav / inception_nav) ** (365 / max(days_elapsed, 1)) - 1
            if inception_nav else 0.0
        )

        # ── 最大回撤 ───────────────────────────────────────────────────
        max_drawdown_pct = self._calc_max_drawdown(nav_history)

        # ── 持倉 ───────────────────────────────────────────────────────
        positions_raw = self.client.get_positions()
        positions     = self._format_positions(positions_raw, nav)

        # ── 交易紀錄 ───────────────────────────────────────────────────
        orders      = self.client.get_orders(status="all", limit=30)
        trades_today = self._format_trades(orders, today)

        # ── 組合報告 ───────────────────────────────────────────────────
        report = {
            "report_date":    today,
            "account_id":     account_id,
            "strategy_id":    strategy_id,
            "generated_at":   datetime.datetime.now().isoformat(),
            "summary": {
                "nav":               round(nav, 2),
                "cash":              round(cash, 2),
                "invested":          round(nav - cash, 2),
                "inception_nav":     round(inception_nav, 2),
                "inception_date":    inception_date,
                "daily_pnl":         round(daily_pnl, 2),
                "daily_pnl_pct":     round(daily_pnl_pct, 6),
                "weekly_pnl_pct":    round(weekly_pnl_pct, 6),
                "monthly_pnl_pct":   round(monthly_pnl_pct, 6),
                "total_return_pct":  round(total_return_pct, 6),
                "annual_return_pct": round(annual_return_pct, 6),
                "max_drawdown_pct":  round(max_drawdown_pct, 6),
                "days_elapsed":      days_elapsed,
            },
            "positions":     positions,
            "trades_today":  trades_today,
            "nav_history":   nav_history[-365:],  # 最多保留一年
            "watchlist":     watchlist or {},
        }

        return report

    # ── 儲存與載入 ───────────────────────────────────────────────────────
    def save(self, report: dict, account_id: str) -> str:
        """儲存報告 JSON，回傳檔案路徑"""
        date_dir = os.path.join(self.reports_dir, report["report_date"])
        os.makedirs(date_dir, exist_ok=True)
        path = os.path.join(date_dir, f"{account_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return path

    def load(self, account_id: str, date: str) -> Optional[dict]:
        """載入歷史報告，找不到時回傳 None"""
        path = os.path.join(self.reports_dir, date, f"{account_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def list_dates(self, account_id: str) -> list:
        """列出該帳戶所有有報告的日期（由新到舊）"""
        dates = []
        if not os.path.exists(self.reports_dir):
            return dates
        for d in sorted(os.listdir(self.reports_dir), reverse=True):
            path = os.path.join(self.reports_dir, d, f"{account_id}.json")
            if os.path.exists(path):
                dates.append(d)
        return dates

    # ── 計算工具 ─────────────────────────────────────────────────────────
    @staticmethod
    def _get_yesterday_nav(nav_history: list, today: str) -> float:
        """取得昨日 NAV（排除今日）"""
        past = [e for e in nav_history if e["date"] < today]
        return past[-1]["nav"] if past else 0.0

    @staticmethod
    def _period_return(nav_history: list, current_nav: float, days: int) -> float:
        """計算 N 天前到現在的報酬率"""
        if not nav_history or current_nav <= 0:
            return 0.0
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        past   = [e for e in nav_history if e["date"] <= cutoff]
        if not past:
            return 0.0
        base_nav = past[-1]["nav"]
        return (current_nav / base_nav - 1) if base_nav else 0.0

    @staticmethod
    def _calc_max_drawdown(nav_history: list) -> float:
        """
        計算最大回撤（Max Drawdown）。
        說明：從歷史最高點到最低點的跌幅百分比，負值表示虧損幅度。
        """
        if len(nav_history) < 2:
            return 0.0
        navs     = [e["nav"] for e in nav_history]
        peak     = navs[0]
        max_dd   = 0.0
        for nav in navs:
            if nav > peak:
                peak = nav
            dd = (nav - peak) / peak
            if dd < max_dd:
                max_dd = dd
        return max_dd

    @staticmethod
    def _format_positions(positions_raw: list, portfolio_value: float) -> list:
        """格式化持倉資料"""
        result = []
        for p in positions_raw:
            qty   = float(p.get("qty", 0))
            avg   = float(p.get("avg_entry_price", 0))
            cur   = float(p.get("current_price", 0) or avg)
            mv    = qty * cur
            cost  = qty * avg
            pnl_a = mv - cost
            pnl_p = pnl_a / cost if cost else 0.0
            result.append({
                "symbol":          p.get("symbol", ""),
                "qty":             qty,
                "avg_entry_price": round(avg, 2),
                "current_price":   round(cur, 2),
                "market_value":    round(mv, 2),
                "weight_pct":      round(mv / portfolio_value * 100, 2) if portfolio_value else 0,
                "pnl_amount":      round(pnl_a, 2),
                "pnl_pct":         round(pnl_p, 6),
            })
        return sorted(result, key=lambda x: x["market_value"], reverse=True)

    @staticmethod
    def _format_trades(orders: list, today: str) -> list:
        """格式化今日交易紀錄"""
        result = []
        for o in orders:
            submitted = (o.get("submitted_at") or "")[:10]
            if submitted != today:
                continue
            fp = o.get("filled_avg_price")
            result.append({
                "time":       (o.get("submitted_at") or "")[:19].replace("T", " "),
                "symbol":     o.get("symbol", ""),
                "side":       o.get("side", ""),
                "qty":        float(o.get("qty") or 0),
                "filled_qty": float(o.get("filled_qty") or 0),
                "price":      round(float(fp), 2) if fp else 0.0,
                "status":     o.get("status", ""),
                "type":       o.get("type", "market"),
            })
        return result
