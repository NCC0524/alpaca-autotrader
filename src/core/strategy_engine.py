"""
strategy_engine.py
策略引擎 — 從 JSON 載入、驗證、執行策略
新增策略：只需在 strategies/ 目錄新增 JSON 檔，不需修改 Python 程式碼
"""

import json
import os
from typing import Optional

import jsonschema

# ── JSON Schema 驗證規則 ──────────────────────────────────────────────────
STRATEGY_SCHEMA = {
    "type": "object",
    "required": ["strategy_id", "strategy_name", "universe", "allocation", "execution"],
    "properties": {
        "strategy_id":   {"type": "string", "minLength": 1},
        "strategy_name": {"type": "string", "minLength": 1},
        "version":       {"type": "string"},
        "universe": {
            "type": "object",
            "required": ["symbols"],
            "properties": {
                "source":  {"type": "string"},
                "symbols": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "top_n":   {"type": "integer", "minimum": 1},
            }
        },
        "allocation": {
            "type": "object",
            "required": ["method", "per_stock_pct", "integer_shares_only"],
            "properties": {
                "method":               {"type": "string", "enum": ["equal_weight"]},
                "per_stock_pct":        {"type": "number", "minimum": 0.1, "maximum": 100},
                "integer_shares_only":  {"type": "boolean"},
                "cash_buffer_pct":      {"type": "number", "minimum": 0},
            }
        },
        "rebalance": {"type": "object"},
        "risk":      {"type": "object"},
        "execution": {
            "type": "object",
            "required": ["order_type", "time_in_force"],
            "properties": {
                "order_type":    {"type": "string", "enum": ["market", "limit"]},
                "time_in_force": {"type": "string", "enum": ["day", "gtc", "ioc", "fok"]},
                "sell_before_buy": {"type": "boolean"},
            }
        }
    }
}


class StrategyError(Exception):
    """策略相關錯誤"""
    pass

class StrategyValidationError(StrategyError):
    """策略 JSON 格式驗證失敗"""
    pass

class StrategyNotFoundError(StrategyError):
    """找不到策略檔案"""
    pass


class StrategyEngine:
    """
    策略引擎。
    - 從 strategies/ 目錄動態載入 JSON 策略
    - 驗證 JSON 格式（使用 jsonschema）
    - 計算目標持倉（整數股、等權重）
    - 判斷是否需要再平衡
    """

    def __init__(self, strategies_dir: str = "strategies"):
        self.strategies_dir = strategies_dir
        self._cache: dict = {}  # strategy_id → strategy dict

    # ── 載入策略 ────────────────────────────────────────────────────────────
    def load(self, strategy_id: str) -> dict:
        """
        載入並驗證策略 JSON。
        策略會被快取，避免重複讀檔。
        """
        if strategy_id in self._cache:
            return self._cache[strategy_id]

        path = os.path.join(self.strategies_dir, f"{strategy_id}.json")
        if not os.path.exists(path):
            raise StrategyNotFoundError(
                f"找不到策略檔案：{path}\n"
                f"請確認 {self.strategies_dir}/ 目錄下有 {strategy_id}.json"
            )

        with open(path, encoding="utf-8") as f:
            try:
                strategy = json.load(f)
            except json.JSONDecodeError as e:
                raise StrategyValidationError(f"策略 JSON 格式錯誤：{e}")

        self._validate(strategy)
        self._cache[strategy_id] = strategy
        return strategy

    def _validate(self, strategy: dict):
        """使用 jsonschema 驗證策略格式"""
        try:
            jsonschema.validate(instance=strategy, schema=STRATEGY_SCHEMA)
        except jsonschema.ValidationError as e:
            sid = strategy.get("strategy_id", "（未知）")
            raise StrategyValidationError(
                f"策略 {sid} 格式驗證失敗：{e.message}"
            )

    def list_available(self) -> list:
        """列出所有可用的策略 ID"""
        if not os.path.exists(self.strategies_dir):
            return []
        return [
            f[:-5] for f in os.listdir(self.strategies_dir)
            if f.endswith(".json")
        ]

    # ── 目標持倉計算 ─────────────────────────────────────────────────────────
    def calc_target_positions(self, strategy: dict, portfolio_value: float, prices: dict) -> dict:
        """
        計算目標持倉（整數股）。

        參數：
            strategy:        策略 dict
            portfolio_value: 帳戶總市值（USD）
            prices:          {symbol: price} 目前股價

        回傳：
            {symbol: target_qty}  整數股數
        """
        if portfolio_value <= 0:
            raise StrategyError("portfolio_value 必須 > 0")

        alloc      = strategy["allocation"]
        per_pct    = alloc["per_stock_pct"] / 100.0
        symbols    = strategy["universe"]["symbols"]
        int_only   = alloc.get("integer_shares_only", True)
        buffer_pct = alloc.get("cash_buffer_pct", 0) / 100.0

        investable = portfolio_value * (1 - buffer_pct)
        result = {}

        for sym in symbols:
            price = prices.get(sym)
            if not price or price <= 0:
                result[sym] = 0
                continue
            raw_qty = (investable * per_pct) / price
            qty = int(raw_qty) if int_only else round(raw_qty, 4)
            result[sym] = qty

        return result

    # ── 差異計算（再平衡用）────────────────────────────────────────────────
    def calc_rebalance_orders(
        self,
        target: dict,
        current: dict,
    ) -> dict:
        """
        計算需要下的訂單。

        參數：
            target:  {symbol: target_qty}
            current: {symbol: current_qty}

        回傳：
            {"buy": [(sym, qty), ...], "sell": [(sym, qty), ...]}
        """
        buys, sells = [], []

        all_symbols = set(target) | set(current)
        for sym in all_symbols:
            t = int(target.get(sym, 0))
            c = int(current.get(sym, 0))
            diff = t - c
            if diff > 0:
                buys.append((sym, diff))
            elif diff < 0:
                sells.append((sym, abs(diff)))

        return {"buy": buys, "sell": sells}

    # ── 再平衡觸發判斷 ──────────────────────────────────────────────────────
    def needs_rebalance(
        self,
        strategy: dict,
        current_weights: dict,
        target_weights: dict,
    ) -> bool:
        """
        判斷是否需要再平衡（漂移超過閾值）。

        current_weights / target_weights：{symbol: weight_pct}
        """
        threshold = strategy.get("rebalance", {}).get("drift_threshold_pct", 5)
        for sym, target_w in target_weights.items():
            current_w = current_weights.get(sym, 0)
            if abs(current_w - target_w) > threshold:
                return True
        return False
