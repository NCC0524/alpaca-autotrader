"""
pe_calculator.py
P/E 比率計算器 — 根據即時股價與 EPS(TTM) 計算本益比，並支援歷史紀錄儲存與查詢。

資料來源：
  - 股價：由外部傳入（AlpacaClient.get_latest_prices）
  - EPS TTM：data/fundamental_data.json（靜態，需定期手動更新）
"""
import datetime
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data")
)
_FUNDAMENTAL_FILE = os.path.join(_DATA_DIR, "fundamental_data.json")
_PE_HISTORY_FILE  = os.path.join(_DATA_DIR, "pe_history.json")


def _load_fundamental() -> dict:
    """載入 fundamental_data.json；檔案不存在回傳空 dict。"""
    if not os.path.exists(_FUNDAMENTAL_FILE):
        return {}
    with open(_FUNDAMENTAL_FILE, encoding="utf-8") as f:
        return json.load(f)


def _load_pe_history() -> dict:
    """載入 pe_history.json；檔案不存在回傳空 dict。"""
    if not os.path.exists(_PE_HISTORY_FILE):
        return {}
    with open(_PE_HISTORY_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_pe_history(data: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_PE_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class PECalculator:
    """
    P/E 比率計算與歷史管理。

    使用範例：
        calc = PECalculator()
        pe = calc.calculate("AAPL", price=192.5)   # -> 28.52
        calc.save("AAPL", pe, "2026-05-24")
        history = calc.get_history("AAPL", days=30)  # -> [{"date": ..., "pe": ...}, ...]
    """

    def __init__(self, fundamental_file: str = None, pe_history_file: str = None):
        self._fundamental_file = fundamental_file or _FUNDAMENTAL_FILE
        self._pe_history_file  = pe_history_file  or _PE_HISTORY_FILE

    # ── 基本面資料 ────────────────────────────────────────────────────────────

    def get_eps(self, symbol: str) -> Optional[float]:
        """取得股票的 EPS(TTM)；找不到回傳 None。"""
        data = {}
        if os.path.exists(self._fundamental_file):
            with open(self._fundamental_file, encoding="utf-8") as f:
                data = json.load(f)
        entry = data.get(symbol.upper())
        if entry is None:
            return None
        return float(entry.get("eps_ttm", 0)) or None

    def get_shares_outstanding(self, symbol: str) -> Optional[float]:
        """取得流通股數（百萬股）；找不到回傳 None。"""
        data = {}
        if os.path.exists(self._fundamental_file):
            with open(self._fundamental_file, encoding="utf-8") as f:
                data = json.load(f)
        entry = data.get(symbol.upper())
        if entry is None:
            return None
        return float(entry.get("shares_outstanding_M", 0)) or None

    # ── P/E 計算 ──────────────────────────────────────────────────────────────

    def calculate(self, symbol: str, price: float) -> Optional[float]:
        """
        計算 P/E 比率 = price / eps_ttm。
        - eps <= 0 或找不到資料 → 回傳 None
        - 回傳值四捨五入至小數第二位
        """
        eps = self.get_eps(symbol)
        if eps is None or eps <= 0:
            logger.warning("[PECalculator] %s EPS 無效 (%s)，無法計算 P/E", symbol, eps)
            return None
        return round(price / eps, 2)

    def calculate_market_cap(self, symbol: str, price: float) -> Optional[float]:
        """
        計算市值（百萬美元）= price × shares_outstanding_M。
        找不到資料回傳 None。
        """
        shares = self.get_shares_outstanding(symbol)
        if shares is None:
            return None
        return round(price * shares, 2)

    # ── 歷史紀錄 ──────────────────────────────────────────────────────────────

    def save(self, symbol: str, pe: float, date: str = None) -> None:
        """
        將 P/E 值寫入 pe_history.json。
        date 格式：'YYYY-MM-DD'；預設今日。
        """
        if date is None:
            date = datetime.date.today().isoformat()
        symbol = symbol.upper()

        history = {}
        if os.path.exists(self._pe_history_file):
            with open(self._pe_history_file, encoding="utf-8") as f:
                history = json.load(f)

        if symbol not in history:
            history[symbol] = []

        # 若同日已有紀錄則更新
        for entry in history[symbol]:
            if entry["date"] == date:
                entry["pe"] = round(float(pe), 2)
                break
        else:
            history[symbol].append({"date": date, "pe": round(float(pe), 2)})

        # 按日期排序
        history[symbol].sort(key=lambda x: x["date"])

        os.makedirs(os.path.dirname(self._pe_history_file), exist_ok=True)
        with open(self._pe_history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        logger.info("[PECalculator] %s P/E=%.2f 已儲存 (%s)", symbol, pe, date)

    def load(self, symbol: str, date: str) -> Optional[float]:
        """
        讀取指定日期的 P/E；找不到回傳 None。
        """
        if not os.path.exists(self._pe_history_file):
            return None
        with open(self._pe_history_file, encoding="utf-8") as f:
            history = json.load(f)
        for entry in history.get(symbol.upper(), []):
            if entry["date"] == date:
                return float(entry["pe"])
        return None

    def get_history(self, symbol: str, days: int = 30) -> List[Dict]:
        """
        取得最近 N 天的 P/E 歷史（按日期遞增）。
        回傳：[{"date": "YYYY-MM-DD", "pe": float}, ...]
        """
        if not os.path.exists(self._pe_history_file):
            return []
        with open(self._pe_history_file, encoding="utf-8") as f:
            history = json.load(f)
        entries = sorted(history.get(symbol.upper(), []), key=lambda x: x["date"])
        return entries[-days:] if days > 0 else entries
