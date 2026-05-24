"""
alpaca_client.py
Alpaca Markets API 封裝層 — 所有 HTTP 請求統一由此處理
"""

import json
import time
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError


# ── 自訂例外 ──────────────────────────────────────────────────────────────
class AlpacaError(Exception):
    """Alpaca 相關錯誤基底類別"""
    pass

class AlpacaAPIError(AlpacaError):
    """HTTP 層級錯誤（4xx / 5xx）"""
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code

class AlpacaConnectionError(AlpacaError):
    """網路連線錯誤"""
    pass

class AlpacaAuthError(AlpacaAPIError):
    """認證失敗（401 / 403）"""
    pass


# ── 主類別 ────────────────────────────────────────────────────────────────
class AlpacaClient:
    """
    Alpaca REST API 封裝。
    支援自動重試（指數退避）、統一錯誤處理。
    """

    PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"
    LIVE_BASE_URL  = "https://api.alpaca.markets/v2"
    DATA_URL       = "https://data.alpaca.markets/v2"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = None,
        data_url: str = None,
        timeout: int = 15,
        max_retries: int = 3,
    ):
        if not api_key or not api_secret:
            raise AlpacaAuthError("api_key 與 api_secret 不可為空")

        self.api_key    = api_key
        self.api_secret = api_secret
        self.base_url   = (base_url or self.PAPER_BASE_URL).rstrip("/")
        self.data_url   = (data_url or self.DATA_URL).rstrip("/")
        self.timeout    = timeout
        self.max_retries = max_retries

        self._headers = {
            "APCA-API-KEY-ID":     api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Content-Type":        "application/json",
            "Accept":              "application/json",
        }

    # ── 核心請求 ───────────────────────────────────────────────────────────
    def _request(self, method: str, endpoint: str, base: str = None, data: dict = None) -> dict:
        url  = (base or self.base_url) + endpoint
        body = json.dumps(data).encode("utf-8") if data else None
        req  = Request(url, data=body, headers=self._headers, method=method)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                with urlopen(req, timeout=self.timeout) as resp:
                    content = resp.read()
                    return json.loads(content) if content else {}

            except HTTPError as e:
                body_text = e.read().decode("utf-8", errors="replace")
                if e.code in (401, 403):
                    raise AlpacaAuthError(
                        f"認證失敗 ({e.code})：API Key 或 Secret 不正確", code=e.code
                    )
                if e.code == 429:
                    # Rate limit：等待再重試
                    wait = 2 ** attempt
                    time.sleep(wait)
                    last_error = AlpacaAPIError(f"Rate limit ({e.code})", code=e.code)
                    continue
                raise AlpacaAPIError(
                    f"API 錯誤 {e.code}: {body_text[:300]}", code=e.code
                )

            except URLError as e:
                last_error = AlpacaConnectionError(f"網路連線失敗: {e.reason}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error

            except TimeoutError:
                last_error = AlpacaConnectionError(f"請求超時（{self.timeout}s），已重試 {attempt + 1} 次")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise last_error

        raise last_error or AlpacaError("未知錯誤")

    def get(self, endpoint: str, base: str = None) -> dict:
        return self._request("GET", endpoint, base=base)

    def post(self, endpoint: str, data: dict) -> dict:
        return self._request("POST", endpoint, data=data)

    def delete(self, endpoint: str) -> dict:
        return self._request("DELETE", endpoint)

    def patch(self, endpoint: str, data: dict) -> dict:
        return self._request("PATCH", endpoint, data=data)

    # ── 帳戶 ──────────────────────────────────────────────────────────────
    def get_account(self) -> dict:
        """取得帳戶資訊（NAV、現金、狀態等）"""
        return self.get("/account")

    def get_positions(self) -> list:
        """取得所有持倉"""
        result = self.get("/positions")
        return result if isinstance(result, list) else []

    def get_position(self, symbol: str) -> dict:
        """取得單一股票持倉"""
        return self.get(f"/positions/{symbol}")

    def close_position(self, symbol: str) -> dict:
        """清空某檔持倉"""
        return self.delete(f"/positions/{symbol}")

    def get_clock(self) -> dict:
        """取得市場時鐘（是否開市）"""
        return self.get("/clock")

    def get_calendar(self, start: str = None, end: str = None) -> list:
        """取得交易日曆"""
        ep = "/calendar"
        if start and end:
            ep += f"?start={start}&end={end}"
        result = self.get(ep)
        return result if isinstance(result, list) else []

    def get_cash(self) -> float:
        """取得可用現金"""
        acct = self.get_account()
        return float(acct.get("cash", 0))

    def get_portfolio_value(self) -> float:
        """取得帳戶總市值（NAV）"""
        acct = self.get_account()
        return float(acct.get("portfolio_value", 0))

    def get_account_status(self) -> str:
        """取得帳戶狀態字串"""
        acct = self.get_account()
        return acct.get("status", "UNKNOWN")

    # ── 訂單 ──────────────────────────────────────────────────────────────
    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
    ) -> dict:
        """下單（整數股）"""
        if qty <= 0:
            raise ValueError(f"下單數量必須 > 0，收到 {qty}")
        if side not in ("buy", "sell"):
            raise ValueError(f"side 必須為 buy 或 sell，收到 {side}")
        return self.post("/orders", {
            "symbol":         symbol,
            "qty":            str(int(qty)),
            "side":           side,
            "type":           order_type,
            "time_in_force":  time_in_force,
        })

    def get_orders(self, status: str = "all", limit: int = 50) -> list:
        """取得訂單列表"""
        result = self.get(f"/orders?status={status}&limit={limit}")
        return result if isinstance(result, list) else []

    def cancel_all_orders(self) -> dict:
        """取消所有待執行訂單"""
        return self.delete("/orders")

    def cancel_order(self, order_id: str) -> dict:
        """取消單一訂單"""
        return self.delete(f"/orders/{order_id}")

    # ── 市場資料 ───────────────────────────────────────────────────────────
    def get_latest_prices(self, symbols: list) -> dict:
        """
        取得多檔股票最新收盤價
        回傳：{"AAPL": 195.2, "NVDA": 131.5, ...}
        """
        sym_str = ",".join(symbols)
        r = self.get(f"/stocks/bars/latest?symbols={sym_str}&feed=iex", base=self.data_url)
        return {
            sym: round(float(bar["c"]), 2)
            for sym, bar in r.get("bars", {}).items()
        }

    def get_historical_bars(self, symbol: str, start: str, end: str, timeframe: str = "1Day") -> list:
        """
        取得單一股票歷史 K 線
        回傳：[{"date": "2026-01-02", "close": 195.2}, ...]
        """
        ep = (
            f"/stocks/{symbol}/bars"
            f"?start={start}&end={end}"
            f"&timeframe={timeframe}&feed=iex&limit=500"
        )
        r = self.get(ep, base=self.data_url)
        return [
            {"date": b["t"][:10], "close": round(float(b["c"]), 2)}
            for b in r.get("bars", [])
        ]

    def get_snapshot(self, symbols: list) -> dict:
        """取得多檔股票即時快照（含 OHLCV）"""
        sym_str = ",".join(symbols)
        return self.get(
            f"/stocks/snapshots?symbols={sym_str}&feed=iex",
            base=self.data_url
        )

    def __repr__(self):
        return f"AlpacaClient(base={self.base_url}, key=***{self.api_key[-4:]})"
