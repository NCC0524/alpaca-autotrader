"""
executor.py
交易執行器 — 根據策略指令執行買賣訂單
"""
import time
from typing import List, Tuple

from src.core.alpaca_client import AlpacaClient, AlpacaAPIError


class ExecutionError(Exception):
    pass


class TradeExecutor:
    """
    依照策略指令執行市價單。
    原則：先賣後買（避免保證金不足）
    """

    def __init__(self, client: AlpacaClient, delay_ms: int = 300):
        self.client   = client
        self.delay_ms = delay_ms  # 每筆訂單之間的等待（毫秒）

    def execute(self, orders: dict, dry_run: bool = False) -> List[dict]:
        """
        執行再平衡訂單。

        orders = {"sell": [(sym, qty), ...], "buy": [(sym, qty), ...]}
        dry_run = True 時只印出訂單，不實際下單（用於測試）
        """
        results = []
        self.client.cancel_all_orders()
        time.sleep(0.5)

        # 先賣
        for sym, qty in orders.get("sell", []):
            result = self._place(sym, qty, "sell", dry_run)
            results.append(result)

        time.sleep(1)

        # 再買
        for sym, qty in orders.get("buy", []):
            result = self._place(sym, qty, "buy", dry_run)
            results.append(result)

        return results

    def _place(self, symbol: str, qty: int, side: str, dry_run: bool) -> dict:
        icon = "📉" if side == "sell" else "📈"
        print(f"  {icon} {side.upper():<4} {qty:>5} 股  {symbol:<6}")

        if dry_run:
            return {"symbol": symbol, "qty": qty, "side": side, "status": "dry_run"}

        try:
            result = self.client.place_order(symbol, qty, side)
            time.sleep(self.delay_ms / 1000)
            return {
                "symbol":   symbol,
                "qty":      qty,
                "side":     side,
                "order_id": result.get("id", ""),
                "status":   result.get("status", "submitted"),
            }
        except AlpacaAPIError as e:
            print(f"    ❌ {symbol} 下單失敗：{e}")
            return {"symbol": symbol, "qty": qty, "side": side, "status": "failed", "error": str(e)}
