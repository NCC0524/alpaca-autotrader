"""
predictor.py
趨勢預測器 — 整合動量分數、近期波動度，輸出方向性預測與信心度。

⚠️ 重要免責聲明：
  本模組輸出為統計模型估算結果，僅供參考，不構成任何投資建議。
  股票市場受多重因素影響，任何預測均存在不確定性。
  請勿單獨依據本系統進行投資決策，並請自行承擔投資風險。

設計原則：
  - 整合 MomentumScorer 分數 + 近期波動度（ATR-like）
  - 輸出：direction ("up" / "down" / "neutral") + confidence (0.0~1.0)
  - confidence < NEUTRAL_THRESHOLD → 強制輸出 "neutral"
  - 永遠在輸出中攜帶 disclaimer
"""
import logging
from typing import List

from .momentum_scorer import MomentumScorer

logger = logging.getLogger(__name__)

# 信心度門檻：低於此值視為中性（0.45 對應動量分數 ≈ 0.72+ 才給方向信號）
NEUTRAL_THRESHOLD = 0.45

# 免責聲明（所有預測輸出均須包含）
PREDICTION_DISCLAIMER = (
    "⚠️ 本預測為統計模型估算，僅供參考，不構成任何投資建議。"
    "股票市場具有高度不確定性，請自行承擔投資風險，切勿單獨依賴本系統進行投資決策。"
)


class Predictor:
    """
    趨勢預測器。

    使用範例：
        p = Predictor()
        result = p.predict(bars)
        # {
        #   "direction":  "up",
        #   "confidence": 0.72,
        #   "momentum_score": 0.73,
        #   "volatility":     0.018,
        #   "data_points":    21,
        #   "disclaimer":     "⚠️ ...",
        # }
    """

    def __init__(
        self,
        scorer: MomentumScorer = None,
        neutral_threshold: float = NEUTRAL_THRESHOLD,
    ):
        self._scorer    = scorer or MomentumScorer()
        self._threshold = neutral_threshold

    # ── 波動度估算 ────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_volatility(bars: List[dict], window: int = 10) -> float:
        """
        計算近 window 個交易日的日報酬率標準差（作為波動度估算）。
        bars 不足時使用全部資料。
        """
        sorted_bars = sorted(bars, key=lambda b: b.get("date", ""))
        closes = [float(b["close"]) for b in sorted_bars if "close" in b]
        if len(closes) < 2:
            return 0.0

        subset = closes[-(window + 1):]
        daily_returns = [
            (subset[i] - subset[i - 1]) / subset[i - 1]
            for i in range(1, len(subset))
            if subset[i - 1] != 0
        ]
        if not daily_returns:
            return 0.0

        mean = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean) ** 2 for r in daily_returns) / len(daily_returns)
        import math
        return round(math.sqrt(variance), 6)

    # ── 信心度計算 ────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_confidence(momentum_score: float, volatility: float) -> float:
        """
        信心度 = |momentum_score - 0.5| × 2，再依波動度衰減。
        高波動 → 信心度下降（不確定性上升）。

        回傳範圍：0.0 ~ 1.0
        """
        raw_conf = abs(momentum_score - 0.5) * 2.0  # 0.0 ~ 1.0
        # 波動度衰減：每 1% 波動削減 5% 信心度
        decay = min(1.0, volatility * 5.0)
        conf  = raw_conf * (1.0 - decay * 0.5)
        return round(max(0.0, min(1.0, conf)), 4)

    # ── 主預測 ────────────────────────────────────────────────────────────────

    def predict(self, bars: List[dict]) -> dict:
        """
        對一組 K 線資料進行方向性預測。

        參數：
            bars：[{"date": "YYYY-MM-DD", "close": float}, ...]，按日期排序

        回傳：
            {
              "direction":      "up" | "down" | "neutral",
              "confidence":     float,   # 0.0 ~ 1.0
              "momentum_score": float,
              "volatility":     float,
              "data_points":    int,
              "disclaimer":     str,
            }
        """
        detail     = self._scorer.score_detail(bars)
        mom_score  = detail["score"]
        volatility = self._calc_volatility(bars)
        confidence = self._calc_confidence(mom_score, volatility)
        data_pts   = detail["data_points"]

        # 資料不足 or 信心度不足 → neutral
        if data_pts < 5 or confidence < self._threshold:
            direction = "neutral"
        elif mom_score > 0.5:
            direction = "up"
        else:
            direction = "down"

        result = {
            "direction":      direction,
            "confidence":     confidence,
            "momentum_score": mom_score,
            "volatility":     volatility,
            "data_points":    data_pts,
            "disclaimer":     PREDICTION_DISCLAIMER,
        }
        logger.info(
            "[Predictor] direction=%s confidence=%.2f momentum=%.4f vol=%.4f",
            direction, confidence, mom_score, volatility,
        )
        return result
