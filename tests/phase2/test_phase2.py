"""
Phase 2 測試案例 — 策略引擎（JSON 驅動）
TC-2-01 ~ TC-2-10
"""
import json
import os
import pytest

from src.core.strategy_engine import (
    StrategyEngine, StrategyValidationError, StrategyNotFoundError
)
from src.trading.executor import TradeExecutor


STRATEGIES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "strategies"
)

@pytest.fixture(scope="module")
def engine():
    return StrategyEngine(strategies_dir=STRATEGIES_DIR)

@pytest.fixture(scope="module")
def nasdaq_strategy(engine):
    return engine.load("nasdaq_top10")

# 模擬股價
MOCK_PRICES = {
    "AAPL":  195.0,  "NVDA":  130.0,  "MSFT":  420.0,
    "AMZN":  185.0,  "AVGO":  160.0,  "META":  540.0,
    "TSLA":  175.0,  "GOOGL": 175.0,  "GOOG":  173.0,
    "COST":  900.0,
}
PORTFOLIO_VALUE = 100_000.0


# ════════════════════════════════════════════════════════════
# TC-2-01  載入 nasdaq_top10.json，所有欄位驗證通過
# ════════════════════════════════════════════════════════════
class TestTC201:
    def test_load_strategy_success(self, engine):
        """TC-2-01：nasdaq_top10 策略載入不拋出例外"""
        s = engine.load("nasdaq_top10")
        assert s is not None

    def test_required_fields_present(self, nasdaq_strategy):
        """TC-2-01b：必要欄位均存在"""
        for field in ["strategy_id", "strategy_name", "universe", "allocation", "execution"]:
            assert field in nasdaq_strategy, f"缺少欄位：{field}"

    def test_strategy_id_matches(self, nasdaq_strategy):
        """TC-2-01c：strategy_id 正確"""
        assert nasdaq_strategy["strategy_id"] == "nasdaq_top10"

    def test_per_stock_pct_is_10(self, nasdaq_strategy):
        """TC-2-01d：每股配置 10%"""
        assert nasdaq_strategy["allocation"]["per_stock_pct"] == 10

    def test_integer_shares_only(self, nasdaq_strategy):
        """TC-2-01e：integer_shares_only = true"""
        assert nasdaq_strategy["allocation"]["integer_shares_only"] is True


# ════════════════════════════════════════════════════════════
# TC-2-02  載入格式錯誤的策略 JSON，回傳明確錯誤
# ════════════════════════════════════════════════════════════
class TestTC202:
    def test_missing_required_field_raises(self, tmp_path):
        """TC-2-02：缺少 strategy_id → StrategyValidationError"""
        bad = {"strategy_name": "壞策略", "universe": {"symbols": ["AAPL"]},
               "allocation": {"method": "equal_weight", "per_stock_pct": 10, "integer_shares_only": True},
               "execution": {"order_type": "market", "time_in_force": "day"}}
        p = tmp_path / "bad_strategy.json"
        p.write_text(json.dumps(bad))
        engine = StrategyEngine(strategies_dir=str(tmp_path))
        with pytest.raises(StrategyValidationError, match="格式驗證失敗"):
            engine.load("bad_strategy")

    def test_invalid_json_raises(self, tmp_path):
        """TC-2-02b：非法 JSON 格式"""
        p = tmp_path / "broken.json"
        p.write_text("{this is not json}")
        engine = StrategyEngine(strategies_dir=str(tmp_path))
        with pytest.raises(StrategyValidationError, match="JSON 格式錯誤"):
            engine.load("broken")

    def test_not_found_raises(self, engine):
        """TC-2-02c：找不到策略檔案 → StrategyNotFoundError"""
        with pytest.raises(StrategyNotFoundError):
            engine.load("nonexistent_strategy_xyz")


# ════════════════════════════════════════════════════════════
# TC-2-03  取得 Nasdaq Top 10 清單，回傳恰好 10 檔股票
# ════════════════════════════════════════════════════════════
class TestTC203:
    def test_exactly_10_symbols(self, nasdaq_strategy):
        """TC-2-03：universe.symbols 恰好 10 檔"""
        symbols = nasdaq_strategy["universe"]["symbols"]
        assert len(symbols) == 10, f"期望 10 檔，收到 {len(symbols)}"

    def test_symbols_are_strings(self, nasdaq_strategy):
        """TC-2-03b：所有 symbol 為非空字串"""
        for sym in nasdaq_strategy["universe"]["symbols"]:
            assert isinstance(sym, str) and len(sym) > 0


# ════════════════════════════════════════════════════════════
# TC-2-04  $100,000 帳戶、每股 10%，計算出正確整數股數
# ════════════════════════════════════════════════════════════
class TestTC204:
    def test_target_positions_correct(self, engine, nasdaq_strategy):
        """TC-2-04：AAPL @ $195 → 10% of $100k = $10k → 51 股"""
        targets = engine.calc_target_positions(nasdaq_strategy, PORTFOLIO_VALUE, MOCK_PRICES)
        # AAPL: $10,000 / $195 = 51.28 → int = 51
        assert targets["AAPL"] == 51, f"AAPL 期望 51 股，收到 {targets['AAPL']}"

    def test_all_symbols_in_result(self, engine, nasdaq_strategy):
        """TC-2-04b：所有 10 個 symbol 均在結果中"""
        targets = engine.calc_target_positions(nasdaq_strategy, PORTFOLIO_VALUE, MOCK_PRICES)
        for sym in nasdaq_strategy["universe"]["symbols"]:
            assert sym in targets

    def test_all_quantities_non_negative(self, engine, nasdaq_strategy):
        """TC-2-04c：所有目標股數 >= 0"""
        targets = engine.calc_target_positions(nasdaq_strategy, PORTFOLIO_VALUE, MOCK_PRICES)
        for sym, qty in targets.items():
            assert qty >= 0, f"{sym} 股數為負：{qty}"

    def test_all_quantities_are_integers(self, engine, nasdaq_strategy):
        """TC-2-04d：integer_shares_only=true 時，所有股數為整數"""
        targets = engine.calc_target_positions(nasdaq_strategy, PORTFOLIO_VALUE, MOCK_PRICES)
        for sym, qty in targets.items():
            assert isinstance(qty, int), f"{sym} 應為整數，收到 {type(qty)}"


# ════════════════════════════════════════════════════════════
# TC-2-05  高價股（如 COST @ $900）計算整數股數 >= 1
# ════════════════════════════════════════════════════════════
class TestTC205:
    def test_high_price_stock_gets_at_least_1_share(self, engine, nasdaq_strategy):
        """TC-2-05：COST @ $900 → $10k / $900 = 11 股 >= 1"""
        targets = engine.calc_target_positions(nasdaq_strategy, PORTFOLIO_VALUE, MOCK_PRICES)
        assert targets["COST"] >= 1, f"COST 期望 >= 1 股，收到 {targets['COST']}"


# ════════════════════════════════════════════════════════════
# TC-2-06  先賣出超額持倉，再買入不足持倉
# ════════════════════════════════════════════════════════════
class TestTC206:
    def test_sell_before_buy_ordering(self, engine):
        """TC-2-06：calc_rebalance_orders 正確分類買賣"""
        target  = {"AAPL": 50, "NVDA": 80, "MSFT": 20}
        current = {"AAPL": 60, "NVDA": 70, "MSFT": 20}  # AAPL 多、NVDA 少、MSFT 不變
        orders = engine.calc_rebalance_orders(target, current)
        sell_syms = [s for s, _ in orders["sell"]]
        buy_syms  = [s for s, _ in orders["buy"]]
        assert "AAPL" in sell_syms
        assert "NVDA" in buy_syms
        assert "MSFT" not in sell_syms
        assert "MSFT" not in buy_syms

    def test_sell_qty_correct(self, engine):
        """TC-2-06b：賣出數量正確"""
        target  = {"AAPL": 40}
        current = {"AAPL": 50}
        orders = engine.calc_rebalance_orders(target, current)
        assert orders["sell"] == [("AAPL", 10)]

    def test_buy_qty_correct(self, engine):
        """TC-2-06c：買入數量正確"""
        target  = {"NVDA": 100}
        current = {"NVDA": 80}
        orders = engine.calc_rebalance_orders(target, current)
        assert orders["buy"] == [("NVDA", 20)]


# ════════════════════════════════════════════════════════════
# TC-2-07  dry_run 模式：不實際下單，回傳 status=dry_run
# ════════════════════════════════════════════════════════════
class TestTC207:
    def test_dry_run_no_real_orders(self, real_client):
        """TC-2-07：dry_run=True 不呼叫 Alpaca 下單 API"""
        executor = TradeExecutor(client=real_client)
        orders = {"buy": [("AAPL", 1)], "sell": []}
        results = executor.execute(orders, dry_run=True)
        assert results[0]["status"] == "dry_run"
        assert results[0]["symbol"] == "AAPL"


# ════════════════════════════════════════════════════════════
# TC-2-08  帳戶切換策略後，strategy_id 正確更新
# ════════════════════════════════════════════════════════════
class TestTC208:
    def test_set_active_strategy(self, account_manager):
        """TC-2-08：切換策略後 get_active_strategy 回傳新策略"""
        original = account_manager.get_active_strategy("ACC001")
        account_manager.set_active_strategy("ACC001", "nasdaq_top10")
        assert account_manager.get_active_strategy("ACC001") == "nasdaq_top10"
        # 還原
        account_manager.set_active_strategy("ACC001", original or "nasdaq_top10")


# ════════════════════════════════════════════════════════════
# TC-2-09  新增全新 JSON 策略（不修改 Python），系統正常載入
# ════════════════════════════════════════════════════════════
class TestTC209:
    def test_new_json_strategy_loads_without_code_change(self, tmp_path):
        """TC-2-09：純新增 JSON → StrategyEngine 可載入，無需改 Python"""
        new_strategy = {
            "strategy_id":   "test_new_strategy",
            "strategy_name": "測試新策略",
            "version":       "1.0.0",
            "universe":      {"source": "static", "symbols": ["AAPL", "MSFT"], "top_n": 2},
            "allocation":    {"method": "equal_weight", "per_stock_pct": 50, "integer_shares_only": True},
            "rebalance":     {},
            "risk":          {},
            "execution":     {"order_type": "market", "time_in_force": "day", "sell_before_buy": True},
        }
        path = tmp_path / "test_new_strategy.json"
        path.write_text(json.dumps(new_strategy, ensure_ascii=False), encoding="utf-8")

        engine = StrategyEngine(strategies_dir=str(tmp_path))
        loaded = engine.load("test_new_strategy")
        assert loaded["strategy_id"] == "test_new_strategy"
        assert loaded["universe"]["symbols"] == ["AAPL", "MSFT"]


# ════════════════════════════════════════════════════════════
# TC-2-10  同帳戶不允許同時有兩個啟用策略
# ════════════════════════════════════════════════════════════
class TestTC210:
    def test_one_strategy_per_account(self, account_manager):
        """TC-2-10：每帳戶只有一個 active_strategy"""
        strategy = account_manager.get_active_strategy("ACC001")
        # active_strategy 是單一字串或 None，不可能是 list
        assert strategy is None or isinstance(strategy, str), \
            f"active_strategy 應為字串或 None，收到 {type(strategy)}"

    def test_switch_strategy_replaces_old(self, account_manager):
        """TC-2-10b：切換策略後，舊策略消失，只剩新策略"""
        account_manager.set_active_strategy("ACC001", "nasdaq_top10")
        assert account_manager.get_active_strategy("ACC001") == "nasdaq_top10"
        account_manager.set_active_strategy("ACC001", "sp500_growth")
        assert account_manager.get_active_strategy("ACC001") == "sp500_growth"
        # 不是同時有兩個
        config = account_manager.get_account_config("ACC001")
        assert config["active_strategy"] == "sp500_growth"
        # 還原
        account_manager.set_active_strategy("ACC001", "nasdaq_top10")
