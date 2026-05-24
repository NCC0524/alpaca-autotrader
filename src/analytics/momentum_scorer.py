"""
momentum_scorer.py
動量評分器 — 依據 1D / 5D / 20D 報酬率計算加權動量，再透過 sigmoid 函數正規化為 0~1 分數。

設計原則：
  - 分數 0.5 = 無明確動量
  - 分數 > 0.5 → 正動量（偏多）
  - 分數 < 0.5 → 負動量（偏空）
  - 接受「K 線 bars」list：[{"date": "YYYY-MM-DD", "close": float}, ...]，按日期遞增排序
  - 若 bars 不足所需天數，以可用資料計算，不足的權重分配至較短周期
"""
import logging
import math
from typing import List, Optional

logger = logging.getLogger(__name__)

# 預設 1D / 5D / 20D 加權（合計 1.0）
DEFAULT_WEIGHTS = {
    "1d":  0.20,
    "5d":  0.35,
    "20d": 0.45,
}

# sigmoid 縮放係數（控制靈敏度）
_SIGMOID_K = 10.0


def _sigmoid(x: float) -> float:
    """標準 sigmoid：f(x) = 1 / (1 + e^-x)"""
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _period_return(closes: list, period: int) -> Optional[float]:
    """
    計算最近 period 個交易日的報酬率（小數）。
    closes：收盤價 list（已排序，最舊在前）
    period：回顧天數（1 = 昨日 vs 今日）
    回傳 None 若資料不足。
    """
    if len(closes) < period + 1:
        return None
    base = closes[-(period + 1)]
    last = closes[-1]
    if base == 0:
        return None
    return (last - base) / base


class MomentumScorer:
    """
    多周期動量評分器。

    使用範例：
        scorer = MomentumScorer()
        bars = [{"date": "2026-05-01", "close": 180.0}, ...]
        score = scorer.score(bars)   # 0.0 ~ 1.0
        detail = scorer.score_detail(bars)
        # {"score": 0.73, "1d": 0.012, "5d": 0.035, "20d": 0.087,
        #  "weighted_return": 0.052, "data_points": 21}
    """

    def __init__(self, weights: dict = None, sigmoid_k: float = _SIGMOID_K):
        self.weights   = weights or DEFAULT_WEIGHTS
        self.sigmoid_k = sigmoid_k

        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights 合計應為 1.0，目前為 {total:.4f}")

    def _extract_closes(self, bars: list) -> list:
        """從 bars 提取 close 價格 list（遞增排序）。"""
        sorted_bars = sorted(bars, key=lambda b: b.get("date", ""))
        return [float(b["close"]) for b in sorted_bars if "close" in b]

    def score(self, bars: List[dict]) -> float:
        """
        計算動量分數（0.0 ~ 1.0）。
        bars 不足 2 筆時回傳 0.5（中性）。
        """
        return self.score_detail(bars)["score"]

    def score_detail(self, bars: List[dict]) -> dict:
        """
        計算動量分數並回傳完整細節。
        回傳：
            {
              "score": float,          # 0.0 ~ 1.0
              "1d":    float or None,  # 1 日報酬率
              "5d":    float or None,  # 5 日報酬率
              "20d":   float or None,  # 20 日報酬率
              "weighted_return": float,
              "data_points": int,
            }
        """
        closes = self._extract_closes(bars)
        data_points = len(closes)

        if data_points < 2:
            return {
                "score": 0.5, "1d": None, "5d": None, "20d": None,
                "weighted_return": 0.0, "data_points": data_points,
            }

        periods   = {"1d": 1, "5d": 5, "20d": 20}
        returns   = {}
        available = {}

        for key, p in periods.items():
            r = _period_return(closes, p)
            returns[key]   = r
            available[key] = r is not None

        # 重新分配權重（不足天數的周期被排除）
        total_w = sum(self.weights[k] for k in periods if available[k])
        if total_w == 0:
            return {
                "score": 0.5, **{k: returns[k] for k in periods},
                "weighted_return": 0.0, "data_points": data_points,
            }

        weighted_return = sum(
            returns[k] * (self.weights[k] / total_w)
            for k in periods
            if available[k]
        )

        score = round(_sigmoid(self.sigmoid_k * weighted_return), 6)
        score = max(0.0, min(1.0, score))

        return {
            "score":           round(score, 4),
            "1d":              returns["1d"],
            "5d":              returns["5d"],
            "20d":             returns["20d"],
            "weighted_return": round(weighted_return, 6),
            "data_points":     data_points,
        }
