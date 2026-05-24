"""
Phase 7 Advanced Analytics — 測試套件
TC-7-01  PECalculator — calculate() 正確計算 P/E 比率
TC-7-02  PECalculator — save() / load() / get_history() 讀寫一致
TC-7-03  MomentumScorer — score() 上漲趨勢 > 0.5，下跌趨勢 < 0.5
TC-7-04  MomentumScorer — 資料不足時回傳中性 0.5
TC-7-05  Predictor — 強烈上漲動量 → direction="up"，disclaimer 存在
TC-7-06  Predictor — 資料不足 → direction="neutral"
TC-7-07  Top10Analyzer — get_top10_snapshot() 回傳結構正確
"""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# ── project root ──────────────────────────────────────────────────────────────
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── 受測模組 ──────────────────────────────────────────────────────────────────
from src.analytics.pe_calculator   import PECalculator
from src.analytics.momentum_scorer import MomentumScorer
from src.analytics.predictor       import Predictor, PREDICTION_DISCLAIMER
from src.analytics.top10_analyzer  import Top10Analyzer

# ════════════════════════════════════════════════════════════════════════════
# Fixtures / helpers
# ════════════════════════════════════════════════════════════════════════════

def _make_bars(closes: list, start_date: str = "2026-01-01") -> list:
    """建立 bars list：[{"date": ..., "close": ...}, ...]"""
    import datetime
    base = datetime.date.fromisoformat(start_date)
    result = []
    for i, c in enumerate(closes):
        d = (base + datetime.timedelta(days=i)).isoformat()
        result.append({"date": d, "close": float(c)})
    return result


# 持續上漲 21 天（+1% /天）
RISING_BARS  = _make_bars([100 * (1.01 ** i) for i in range(21)])
# 持續下跌 21 天（-1% /天）
FALLING_BARS = _make_bars([100 * (0.99 ** i) for i in range(21)])
# 只有 2 筆資料（不足）
SHORT_BARS   = _make_bars([100, 101])

# Mock fundamental_data.json 內容
MOCK_FUNDAMENTAL = {
    "AAPL": {"eps_ttm": 6.75, "shares_outstanding_M": 15448, "name": "Apple Inc.", "sector": "Technology"},
    "NVDA": {"eps_ttm": 1.92, "shares_outstanding_M": 24430, "name": "NVIDIA Corp.", "sector": "Semiconductors"},
    "MSFT": {"eps_ttm": 12.05, "shares_outstanding_M": 7431, "name": "Microsoft Corp.", "sector": "Technology"},
}


# ════════════════════════════════════════════════════════════════════════════
# TC-7-01  PECalculator.calculate()
# ════════════════════════════════════════════════════════════════════════════
class TestTC701:
    """TC-7-01：P/E 比率計算正確性"""

    @pytest.fixture
    def calc(self, tmp_path):
        """使用臨時目錄的 PECalculator，fundamental 資料用 mock"""
        fund_file = tmp_path / "fundamental_data.json"
        fund_file.write_text(json.dumps(MOCK_FUNDAMENTAL), encoding="utf-8")
        return PECalculator(
            fundamental_file=str(fund_file),
            pe_history_file=str(tmp_path / "pe_history.json"),
        )

    def test_pe_formula_correct(self, calc):
        """TC-7-01a：P/E = price / eps_ttm（AAPL: 192.5 / 6.75 ≈ 28.52）"""
        pe = calc.calculate("AAPL", 192.5)
        assert pe is not None
        assert abs(pe - (192.5 / 6.75)) < 0.01, f"PE={pe}"

    def test_pe_rounded_to_2_decimals(self, calc):
        """TC-7-01b：P/E 四捨五入至小數第二位"""
        pe = calc.calculate("AAPL", 192.5)
        assert pe == round(pe, 2)

    def test_unknown_symbol_returns_none(self, calc):
        """TC-7-01c：未知股票代號回傳 None"""
        pe = calc.calculate("UNKNOWN_XYZ", 100.0)
        assert pe is None

    def test_market_cap_formula(self, calc):
        """TC-7-01d：市值 = price × shares_outstanding_M"""
        cap = calc.calculate_market_cap("AAPL", 192.5)
        expected = round(192.5 * 15448, 2)
        assert cap == expected

    def test_zero_eps_returns_none(self, tmp_path):
        """TC-7-01e：EPS=0 時回傳 None（避免除零）"""
        fund_file = tmp_path / "fundamental_data.json"
        fund_file.write_text(json.dumps({"BAD": {"eps_ttm": 0, "shares_outstanding_M": 1000}}), encoding="utf-8")
        calc = PECalculator(
            fundamental_file=str(fund_file),
            pe_history_file=str(tmp_path / "pe_history.json"),
        )
        pe = calc.calculate("BAD", 100.0)
        assert pe is None


# ════════════════════════════════════════════════════════════════════════════
# TC-7-02  PECalculator save / load / get_history
# ════════════════════════════════════════════════════════════════════════════
class TestTC702:
    """TC-7-02：P/E 歷史讀寫一致"""

    @pytest.fixture
    def calc(self, tmp_path):
        fund_file = tmp_path / "fundamental_data.json"
        fund_file.write_text(json.dumps(MOCK_FUNDAMENTAL), encoding="utf-8")
        return PECalculator(
            fundamental_file=str(fund_file),
            pe_history_file=str(tmp_path / "pe_history.json"),
        )

    def test_save_and_load_roundtrip(self, calc):
        """TC-7-02a：save → load 讀回相同值"""
        calc.save("AAPL", 28.52, "2026-05-24")
        val = calc.load("AAPL", "2026-05-24")
        assert val == 28.52

    def test_load_nonexistent_returns_none(self, calc):
        """TC-7-02b：load 不存在的日期回傳 None"""
        val = calc.load("AAPL", "2000-01-01")
        assert val is None

    def test_get_history_returns_list(self, calc):
        """TC-7-02c：get_history 回傳 list"""
        calc.save("NVDA", 45.0, "2026-05-22")
        calc.save("NVDA", 46.5, "2026-05-23")
        calc.save("NVDA", 47.0, "2026-05-24")
        history = calc.get_history("NVDA", days=30)
        assert isinstance(history, list)
        assert len(history) == 3

    def test_get_history_sorted_ascending(self, calc):
        """TC-7-02d：get_history 按日期遞增排序"""
        calc.save("MSFT", 30.0, "2026-05-24")
        calc.save("MSFT", 29.5, "2026-05-22")
        calc.save("MSFT", 29.8, "2026-05-23")
        history = calc.get_history("MSFT")
        dates = [h["date"] for h in history]
        assert dates == sorted(dates)

    def test_same_date_overwrite(self, calc):
        """TC-7-02e：同日儲存兩次，以後者為準"""
        calc.save("AAPL", 28.0, "2026-05-24")
        calc.save("AAPL", 29.0, "2026-05-24")
        val = calc.load("AAPL", "2026-05-24")
        assert val == 29.0

    def test_get_history_days_limit(self, calc):
        """TC-7-02f：get_history(days=2) 只回傳最近 2 筆"""
        for d in ["2026-05-20", "2026-05-21", "2026-05-22", "2026-05-23"]:
            calc.save("AAPL", 28.0, d)
        history = calc.get_history("AAPL", days=2)
        assert len(history) == 2
        assert history[-1]["date"] == "2026-05-23"


# ════════════════════════════════════════════════════════════════════════════
# TC-7-03  MomentumScorer 趨勢分數
# ════════════════════════════════════════════════════════════════════════════
class TestTC703:
    """TC-7-03：動量評分器方向性"""

    def test_rising_trend_score_above_half(self):
        """TC-7-03a：持續上漲 → score > 0.5"""
        scorer = MomentumScorer()
        score  = scorer.score(RISING_BARS)
        assert score > 0.5, f"上漲動量 score={score}"

    def test_falling_trend_score_below_half(self):
        """TC-7-03b：持續下跌 → score < 0.5"""
        scorer = MomentumScorer()
        score  = scorer.score(FALLING_BARS)
        assert score < 0.5, f"下跌動量 score={score}"

    def test_score_range_0_to_1(self):
        """TC-7-03c：score 永遠在 [0, 1] 範圍"""
        scorer = MomentumScorer()
        for bars in [RISING_BARS, FALLING_BARS, SHORT_BARS]:
            s = scorer.score(bars)
            assert 0.0 <= s <= 1.0, f"score 超出範圍：{s}"

    def test_score_detail_has_all_fields(self):
        """TC-7-03d：score_detail 包含所有必要欄位"""
        scorer = MomentumScorer()
        detail = scorer.score_detail(RISING_BARS)
        for key in ["score", "1d", "5d", "20d", "weighted_return", "data_points"]:
            assert key in detail, f"缺少欄位：{key}"

    def test_rising_bars_positive_returns(self):
        """TC-7-03e：上漲趨勢的 1D/5D/20D 報酬率均為正"""
        scorer = MomentumScorer()
        detail = scorer.score_detail(RISING_BARS)
        for key in ["1d", "5d", "20d"]:
            assert detail[key] > 0, f"{key} 報酬率 = {detail[key]}"

    def test_invalid_weights_raises(self):
        """TC-7-03f：weights 合計不等於 1.0 時拋出 ValueError"""
        with pytest.raises(ValueError):
            MomentumScorer(weights={"1d": 0.5, "5d": 0.5, "20d": 0.5})


# ════════════════════════════════════════════════════════════════════════════
# TC-7-04  MomentumScorer 資料不足
# ════════════════════════════════════════════════════════════════════════════
class TestTC704:
    """TC-7-04：資料不足時回傳中性"""

    def test_single_bar_returns_neutral(self):
        """TC-7-04a：只有 1 筆資料 → score = 0.5"""
        scorer = MomentumScorer()
        bars   = [{"date": "2026-05-24", "close": 100.0}]
        assert scorer.score(bars) == 0.5

    def test_empty_bars_returns_neutral(self):
        """TC-7-04b：空 bars → score = 0.5"""
        scorer = MomentumScorer()
        assert scorer.score([]) == 0.5

    def test_two_bars_uses_1d_only(self):
        """TC-7-04c：2 筆資料時只計算 1D，5D/20D=None，score 仍非中性（有方向）"""
        scorer = MomentumScorer()
        bars   = [
            {"date": "2026-05-23", "close": 100.0},
            {"date": "2026-05-24", "close": 110.0},  # +10%
        ]
        detail = scorer.score_detail(bars)
        assert detail["5d"]  is None
        assert detail["20d"] is None
        assert detail["score"] > 0.5  # 上漲應 > 0.5

    def test_data_points_counted_correctly(self):
        """TC-7-04d：data_points 與輸入 bars 數量一致"""
        scorer = MomentumScorer()
        bars   = _make_bars([100, 101, 102, 103, 104])
        detail = scorer.score_detail(bars)
        assert detail["data_points"] == 5


# ════════════════════════════════════════════════════════════════════════════
# TC-7-05  Predictor 強烈動量
# ════════════════════════════════════════════════════════════════════════════
class TestTC705:
    """TC-7-05：強烈趨勢下的預測方向"""

    def test_strong_rising_gives_up(self):
        """TC-7-05a：強烈上漲動量 → direction = 'up'"""
        pred   = Predictor()
        result = pred.predict(RISING_BARS)
        assert result["direction"] == "up", f"direction={result['direction']}"

    def test_strong_falling_gives_down(self):
        """TC-7-05b：強烈下跌動量 → direction = 'down'"""
        pred   = Predictor()
        result = pred.predict(FALLING_BARS)
        assert result["direction"] == "down", f"direction={result['direction']}"

    def test_disclaimer_always_present(self):
        """TC-7-05c：所有預測結果均包含 disclaimer"""
        pred = Predictor()
        for bars in [RISING_BARS, FALLING_BARS, SHORT_BARS]:
            result = pred.predict(bars)
            assert "disclaimer" in result
            assert len(result["disclaimer"]) > 10

    def test_disclaimer_contains_warning(self):
        """TC-7-05d：disclaimer 包含風險警示關鍵詞"""
        pred   = Predictor()
        result = pred.predict(RISING_BARS)
        disc   = result["disclaimer"]
        assert any(kw in disc for kw in ["⚠️", "投資建議", "風險", "不構成"]), \
            f"disclaimer 缺少風險警示：{disc}"

    def test_confidence_in_range(self):
        """TC-7-05e：confidence 在 [0, 1] 範圍"""
        pred = Predictor()
        for bars in [RISING_BARS, FALLING_BARS]:
            result = pred.predict(bars)
            assert 0.0 <= result["confidence"] <= 1.0

    def test_result_has_all_required_fields(self):
        """TC-7-05f：預測結果包含所有必要欄位"""
        pred   = Predictor()
        result = pred.predict(RISING_BARS)
        for field in ["direction", "confidence", "momentum_score", "volatility", "data_points", "disclaimer"]:
            assert field in result, f"缺少欄位：{field}"


# ════════════════════════════════════════════════════════════════════════════
# TC-7-06  Predictor 資料不足
# ════════════════════════════════════════════════════════════════════════════
class TestTC706:
    """TC-7-06：資料不足時輸出 neutral"""

    def test_less_than_5_bars_returns_neutral(self):
        """TC-7-06a：少於 5 筆資料 → direction = 'neutral'"""
        pred  = Predictor()
        bars  = _make_bars([100, 102, 101, 103])  # 4 筆
        result = pred.predict(bars)
        assert result["direction"] == "neutral"

    def test_empty_bars_returns_neutral(self):
        """TC-7-06b：空 bars → direction = 'neutral'"""
        pred   = Predictor()
        result = pred.predict([])
        assert result["direction"] == "neutral"

    def test_low_confidence_returns_neutral(self):
        """TC-7-06c：低信心度（震盪盤）→ direction = 'neutral'"""
        pred = Predictor(neutral_threshold=0.99)  # 極高門檻，強制 neutral
        result = pred.predict(RISING_BARS)
        assert result["direction"] == "neutral"

    def test_neutral_still_has_disclaimer(self):
        """TC-7-06d：neutral 預測仍有 disclaimer"""
        pred   = Predictor()
        result = pred.predict([])
        assert "disclaimer" in result
        assert result["disclaimer"] == PREDICTION_DISCLAIMER


# ════════════════════════════════════════════════════════════════════════════
# TC-7-07  Top10Analyzer.get_top10_snapshot()
# ════════════════════════════════════════════════════════════════════════════
class TestTC707:
    """TC-7-07：Top10Analyzer 快照結構驗證"""

    @pytest.fixture
    def analyzer(self, tmp_path):
        """建立帶有 mock 依賴的 Top10Analyzer"""
        # Mock client
        mock_client = MagicMock()
        mock_client.get_latest_prices.return_value = {
            "AAPL": 192.5,
            "NVDA": 120.0,
            "MSFT": 420.0,
        }
        mock_client.get_bars.return_value = RISING_BARS

        # Mock strategy engine
        mock_se = MagicMock()
        mock_se.load.return_value = {
            "universe": {"symbols": ["AAPL", "NVDA", "MSFT"]}
        }

        # PECalculator 使用 mock fundamental 資料
        fund_file = tmp_path / "fundamental_data.json"
        fund_file.write_text(json.dumps(MOCK_FUNDAMENTAL), encoding="utf-8")
        pe_calc = PECalculator(
            fundamental_file=str(fund_file),
            pe_history_file=str(tmp_path / "pe_history.json"),
        )

        return Top10Analyzer(
            client=mock_client,
            strategy_engine=mock_se,
            pe_calculator=pe_calc,
        )

    def test_returns_list(self, analyzer):
        """TC-7-07a：回傳 list 型別"""
        result = analyzer.get_top10_snapshot("tech_top10")
        assert isinstance(result, list)

    def test_returns_correct_count(self, analyzer):
        """TC-7-07b：回傳條目數 = 策略股票數（≤ 10）"""
        result = analyzer.get_top10_snapshot("tech_top10")
        assert len(result) == 3  # mock 有 3 支股票

    def test_item_has_required_fields(self, analyzer):
        """TC-7-07c：每個條目包含必要欄位"""
        result = analyzer.get_top10_snapshot("tech_top10")
        required = ["symbol", "name", "price", "market_cap_M", "pe_ratio",
                    "momentum", "direction", "confidence"]
        for item in result:
            for field in required:
                assert field in item, f"條目 {item.get('symbol')} 缺少欄位：{field}"

    def test_prices_match_input(self, analyzer):
        """TC-7-07d：price 與 client.get_latest_prices 一致"""
        result = analyzer.get_top10_snapshot("tech_top10")
        price_map = {item["symbol"]: item["price"] for item in result}
        assert price_map["AAPL"] == 192.5
        assert price_map["NVDA"] == 120.0

    def test_sorted_by_market_cap_desc(self, analyzer):
        """TC-7-07e：結果按市值由大到小排序"""
        result = analyzer.get_top10_snapshot("tech_top10")
        caps   = [item["market_cap_M"] for item in result if item["market_cap_M"] is not None]
        assert caps == sorted(caps, reverse=True), f"排序不正確：{caps}"

    def test_pe_ratio_calculated(self, analyzer):
        """TC-7-07f：P/E 比率正確計算（AAPL: 192.5 / 6.75 ≈ 28.52）"""
        result   = analyzer.get_top10_snapshot("tech_top10")
        aapl     = next(i for i in result if i["symbol"] == "AAPL")
        expected = round(192.5 / 6.75, 2)
        assert aapl["pe_ratio"] == expected

    def test_direction_field_valid_value(self, analyzer):
        """TC-7-07g：direction 只能是 up / down / neutral"""
        result = analyzer.get_top10_snapshot("tech_top10")
        valid  = {"up", "down", "neutral"}
        for item in result:
            assert item["direction"] in valid, \
                f"{item['symbol']} direction={item['direction']!r} 不合法"

    def test_missing_price_skipped(self, tmp_path):
        """TC-7-07h：無法取得價格的股票被跳過"""
        mock_client = MagicMock()
        mock_client.get_latest_prices.return_value = {"AAPL": 192.5}  # NVDA 缺
        mock_client.get_bars.return_value = RISING_BARS

        mock_se = MagicMock()
        mock_se.load.return_value = {
            "universe": {"symbols": ["AAPL", "NVDA"]}
        }

        fund_file = tmp_path / "fundamental_data.json"
        fund_file.write_text(json.dumps(MOCK_FUNDAMENTAL), encoding="utf-8")
        pe_calc = PECalculator(
            fundamental_file=str(fund_file),
            pe_history_file=str(tmp_path / "pe_history.json"),
        )

        analyzer = Top10Analyzer(
            client=mock_client,
            strategy_engine=mock_se,
            pe_calculator=pe_calc,
        )
        result = analyzer.get_top10_snapshot("tech_top10")
        symbols = [i["symbol"] for i in result]
        assert "AAPL" in symbols
        assert "NVDA" not in symbols
