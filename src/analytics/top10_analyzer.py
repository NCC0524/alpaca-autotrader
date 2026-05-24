"""
top10_analyzer.py
Top10 持股分析器 — 整合策略股票池、即時股價、基本面資料與動量評分，
產出完整的快照資料供 Dashboard 顯示使用。

回傳結構（每支股票）：
  {
    "symbol":       str,
    "name":         str,
    "price":        float,
    "market_cap_M": float,    # 市值（百萬美元）
    "pe_ratio":     float or None,
    "momentum":     float,    # 0.0 ~ 1.0
    "direction":    str,      # "up" / "down" / "neutral"
    "confidence":   float,
  }
"""
import logging
import os
import sys
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 確保 project root 在 path
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class Top10Analyzer:
    """
    Top10 持股快照分析器。

    參數：
        client          — AlpacaClient 實例（get_latest_prices、get_bars）
        strategy_engine — StrategyEngine 實例（load strategy）
        pe_calculator   — PECalculator 實例（可選，預設自動建立）
        momentum_scorer — MomentumScorer 實例（可選）
        predictor       — Predictor 實例（可選）
        bars_days       — 取 K 線天數（預設 30，用於動量/預測）

    使用範例：
        analyzer = Top10Analyzer(client=client, strategy_engine=se)
        snapshot = analyzer.get_top10_snapshot("tech_top10")
    """

    def __init__(
        self,
        client,
        strategy_engine,
        pe_calculator=None,
        momentum_scorer=None,
        predictor=None,
        bars_days: int = 30,
    ):
        self._client   = client
        self._se       = strategy_engine
        self._bars_days = bars_days

        # 延遲建立（讓測試可以 mock）
        if pe_calculator is None:
            from src.analytics.pe_calculator import PECalculator
            pe_calculator = PECalculator()
        if momentum_scorer is None:
            from src.analytics.momentum_scorer import MomentumScorer
            momentum_scorer = MomentumScorer()
        if predictor is None:
            from src.analytics.predictor import Predictor
            predictor = Predictor(scorer=momentum_scorer)

        self._pe   = pe_calculator
        self._mom  = momentum_scorer
        self._pred = predictor

    # ── 核心方法 ──────────────────────────────────────────────────────────────

    def get_top10_snapshot(self, strategy_id: str) -> List[dict]:
        """
        為指定策略的所有股票產生快照列表。
        依 market_cap_M 由大到小排序，回傳最多 10 支。

        回傳：
            List[{
              "symbol":       str,
              "name":         str,
              "price":        float,
              "market_cap_M": float,
              "pe_ratio":     float or None,
              "momentum":     float,
              "direction":    str,
              "confidence":   float,
            }]
        """
        strategy = self._se.load(strategy_id)
        symbols  = strategy["universe"]["symbols"]

        prices = self._client.get_latest_prices(symbols)
        items  = []

        for symbol in symbols:
            price = prices.get(symbol)
            if price is None:
                logger.warning("[Top10Analyzer] %s 無法取得價格，跳過", symbol)
                continue

            item = self._build_item(symbol, float(price))
            items.append(item)

        # 依市值排序（大→小），取前 10
        items.sort(key=lambda x: x.get("market_cap_M") or 0, reverse=True)
        return items[:10]

    # ── 單股建構 ──────────────────────────────────────────────────────────────

    def _build_item(self, symbol: str, price: float) -> dict:
        """為單一股票建構快照 dict。"""
        pe         = self._pe.calculate(symbol, price)
        market_cap = self._pe.calculate_market_cap(symbol, price)
        name       = self._get_name(symbol)

        # 取 K 線資料計算動量 & 預測
        bars       = self._get_bars(symbol)
        mom_detail = self._mom.score_detail(bars)
        pred       = self._pred.predict(bars)

        return {
            "symbol":       symbol,
            "name":         name,
            "price":        round(price, 2),
            "market_cap_M": round(market_cap, 2) if market_cap is not None else None,
            "pe_ratio":     pe,
            "momentum":     mom_detail["score"],
            "direction":    pred["direction"],
            "confidence":   pred["confidence"],
        }

    def _get_name(self, symbol: str) -> str:
        """嘗試從 PECalculator 基本面檔取得公司名稱；找不到回傳 symbol。"""
        try:
            import json
            fundamental_file = self._pe._fundamental_file
            if os.path.exists(fundamental_file):
                with open(fundamental_file, encoding="utf-8") as f:
                    data = json.load(f)
                entry = data.get(symbol.upper(), {})
                return entry.get("name", symbol)
        except Exception:
            pass
        return symbol

    def _get_bars(self, symbol: str) -> List[dict]:
        """
        取得最近 bars_days 天的 K 線資料。
        AlpacaClient.get_bars(symbol, days) 回傳：
          [{"date": "YYYY-MM-DD", "close": float}, ...]
        若 client 不支援或 API 失敗，回傳空 list（動量 → 0.5 中性）。
        """
        try:
            bars = self._client.get_bars(symbol, self._bars_days)
            return bars or []
        except Exception as exc:
            logger.warning("[Top10Analyzer] %s get_bars 失敗：%s", symbol, exc)
            return []

    # ── 工廠方法 ──────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, strategy_id: str = None) -> "Top10Analyzer":
        """
        從環境設定自動建立 Top10Analyzer（供 Dashboard 使用）。
        """
        from src.dashboard.config import get_accounts_registry_path, _project_root
        from src.core.account_manager import AccountManager
        from src.core.strategy_engine import StrategyEngine

        am = AccountManager(registry_path=get_accounts_registry_path())
        # 取第一個啟用帳戶的 client
        for _, client, _ in am.iter_enabled_accounts():
            break
        else:
            raise RuntimeError("沒有啟用中的帳戶，無法建立 Top10Analyzer")

        se = StrategyEngine(
            strategies_dir=os.path.join(_project_root(), "strategies")
        )
        return cls(client=client, strategy_engine=se)
