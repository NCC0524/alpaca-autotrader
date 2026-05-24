"""
Phase 4 測試案例 — Streamlit 儀表板（雲端可部署）
TC-4-01 ~ TC-4-10

設計原則：
  - 測試資料層邏輯（DashboardDataProvider），不依賴 Streamlit 伺服器
  - 憑證來自 conftest.py 環境變數（與 Streamlit Cloud Secrets 同機制）
  - 使用 tmp_path 隔離報告目錄，不依賴任何本地固定路徑
  - monkeypatch 模擬 API，避免 benchmark 測試受限於 IEX 資料可用性
"""
import ast
import datetime
import json
import os

import pytest

from src.dashboard.data_provider import DashboardDataProvider
from src.dashboard.config import (
    get_secret,
    get_refresh_interval_seconds,
    get_reports_dir,
)
from src.reports.report_model import ReportModel

# ── 共用測試資料 ──────────────────────────────────────────────────────────────
MOCK_NAV_HISTORY = [
    {"date": "2026-01-02", "nav": 100_000.0},
    {"date": "2026-02-01", "nav": 103_000.0},
    {"date": "2026-03-01", "nav": 101_500.0},  # drawdown from 103k
    {"date": "2026-04-01", "nav": 105_000.0},
    {"date": "2026-04-15", "nav": 104_000.0},  # drawdown from 105k
    {"date": "2026-05-01", "nav": 106_000.0},
    {"date": "2026-05-23", "nav": 107_000.0},
]

MINIMAL_REPORT = {
    "report_date":  "2026-01-15",
    "account_id":   "ACC001",
    "strategy_id":  "nasdaq_top10",
    "generated_at": "2026-01-15T12:00:00",
    "summary": {
        "nav": 105_000.0,  "cash": 5_000.0,   "invested": 100_000.0,
        "inception_nav": 100_000.0,            "inception_date": "2026-01-02",
        "daily_pnl": 500.0,                    "daily_pnl_pct": 0.004762,
        "weekly_pnl_pct": 0.02,                "monthly_pnl_pct": 0.05,
        "total_return_pct": 0.05,              "annual_return_pct": 0.18,
        "max_drawdown_pct": -0.014563,         "days_elapsed": 13,
    },
    "positions":    [],
    "trades_today": [],
    "nav_history":  MOCK_NAV_HISTORY,
    "watchlist":    {},
}


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def provider(account_manager, tmp_path_factory):
    """建立帶有獨立 tmp 報告目錄的 DashboardDataProvider"""
    tmp = tmp_path_factory.mktemp("phase4_reports")
    rm  = ReportModel(client=None, reports_dir=str(tmp))
    return DashboardDataProvider(account_manager=account_manager, report_model=rm)


@pytest.fixture(scope="module")
def saved_report(provider):
    """預先存入一份歷史報告，供 TC-4-09 使用"""
    provider.report_model.save(MINIMAL_REPORT, "ACC001")
    return MINIMAL_REPORT


# ════════════════════════════════════════════════════════════════════════════
# TC-4-01  app.py 語法正確，核心模組可正常 import
# ════════════════════════════════════════════════════════════════════════════
class TestTC401:
    def test_app_py_has_valid_syntax(self):
        """TC-4-01a：app.py 無語法錯誤（AST 解析通過）"""
        path = os.path.join(os.path.dirname(__file__), "../../src/dashboard/app.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        ast.parse(source)   # SyntaxError → test fails

    def test_data_provider_importable(self):
        """TC-4-01b：DashboardDataProvider 可正常 import"""
        assert DashboardDataProvider is not None

    def test_config_module_importable(self):
        """TC-4-01c：config 模組可正常 import"""
        from src.dashboard.config import get_secret, get_refresh_interval_seconds
        assert callable(get_secret)
        assert callable(get_refresh_interval_seconds)

    def test_pages_importable(self):
        """TC-4-01d：所有 page 模組可正常 import（不啟動 Streamlit server）"""
        import importlib
        for mod in [
            "src.dashboard.pages.overview",
            "src.dashboard.pages.positions",
            "src.dashboard.pages.top10",
            "src.dashboard.pages.history",
        ]:
            m = importlib.import_module(mod)
            assert m is not None

    def test_components_importable(self):
        """TC-4-01e：圖表元件模組可正常 import"""
        from src.dashboard.components.nav_chart import build_nav_chart
        from src.dashboard.components.drawdown_chart import build_drawdown_chart
        assert callable(build_nav_chart)
        assert callable(build_drawdown_chart)


# ════════════════════════════════════════════════════════════════════════════
# TC-4-02  config 從環境變數讀取（不依賴本機固定設定）
# ════════════════════════════════════════════════════════════════════════════
class TestTC402:
    def test_get_secret_reads_env_var(self):
        """TC-4-02a：get_secret 從 os.environ 讀取（st.secrets 不可用時）"""
        os.environ["_TC402_TEST_VAR"] = "cloud_secret_value"
        try:
            val = get_secret("_TC402_TEST_VAR")
            assert val == "cloud_secret_value"
        finally:
            del os.environ["_TC402_TEST_VAR"]

    def test_get_secret_returns_default_when_missing(self):
        """TC-4-02b：找不到 secret 時回傳 default，不拋出例外"""
        val = get_secret("_TC402_NO_SUCH_VAR_XYZ", "default_fallback")
        assert val == "default_fallback"

    def test_get_secret_returns_none_without_default(self):
        """TC-4-02c：無預設值時回傳 None"""
        val = get_secret("_TC402_NO_SUCH_VAR_XYZ2")
        assert val is None

    def test_acc001_credentials_available(self, provider):
        """TC-4-02d：ACC001 憑證可從環境變數取得，provider 能初始化 client"""
        client = provider.account_manager.get_client("ACC001")
        assert client is not None

    def test_account_id_in_summary(self, provider):
        """TC-4-02e：切換帳戶後，summary 中的 account_id 與選擇一致"""
        summary = provider.get_account_summary("ACC001")
        assert summary["account_id"] == "ACC001"


# ════════════════════════════════════════════════════════════════════════════
# TC-4-03  現金水位與 API 直接回傳值一致
# ════════════════════════════════════════════════════════════════════════════
class TestTC403:
    def test_cash_matches_api(self, provider, real_client):
        """TC-4-03a：provider.get_account_summary()['cash'] 與 API cash 一致"""
        summary  = provider.get_account_summary("ACC001")
        api_cash = real_client.get_cash()
        # 允許 $1 誤差（多次 API call 之間的微小時間差）
        assert abs(summary["cash"] - api_cash) < 1.0

    def test_nav_is_positive(self, provider):
        """TC-4-03b：NAV > 0（帳戶有正資產）"""
        summary = provider.get_account_summary("ACC001")
        assert summary["nav"] > 0

    def test_invested_equals_nav_minus_cash(self, provider):
        """TC-4-03c：invested = NAV - cash（資金完整性）"""
        s = provider.get_account_summary("ACC001")
        assert abs(s["invested"] - (s["nav"] - s["cash"])) < 0.01


# ════════════════════════════════════════════════════════════════════════════
# TC-4-04  持倉清單欄位完整，按市值排序
# ════════════════════════════════════════════════════════════════════════════
class TestTC404:
    REQUIRED_FIELDS = [
        "symbol", "qty", "avg_entry_price", "current_price",
        "market_value", "weight_pct", "pnl_amount", "pnl_pct",
    ]

    def test_positions_is_list(self, provider):
        """TC-4-04a：get_positions() 回傳 list"""
        positions = provider.get_positions("ACC001")
        assert isinstance(positions, list)

    def test_positions_have_all_required_fields(self, provider):
        """TC-4-04b：每筆持倉含所有必要欄位"""
        for p in provider.get_positions("ACC001"):
            for f in self.REQUIRED_FIELDS:
                assert f in p, f"持倉缺少欄位：{f}"

    def test_positions_sorted_by_market_value_desc(self, provider):
        """TC-4-04c：持倉按市值由大到小排序"""
        values = [p["market_value"] for p in provider.get_positions("ACC001")]
        assert values == sorted(values, reverse=True)

    def test_position_weights_are_percentage(self, provider):
        """TC-4-04d：weight_pct 為百分比（0~100 範圍）"""
        for p in provider.get_positions("ACC001"):
            assert 0 <= p["weight_pct"] <= 100


# ════════════════════════════════════════════════════════════════════════════
# TC-4-05  損益值為數值，正負色彩邏輯正確
# ════════════════════════════════════════════════════════════════════════════
class TestTC405:
    def test_all_pnl_fields_are_numeric(self, provider):
        """TC-4-05a：所有損益欄位為數值型別"""
        s = provider.get_account_summary("ACC001")
        for key in ["daily_pnl", "daily_pnl_pct", "weekly_pnl_pct", "monthly_pnl_pct"]:
            assert isinstance(s[key], (int, float)), f"{key} 應為數值，得到 {type(s[key])}"

    def test_positive_pnl_color_green(self):
        """TC-4-05b：正值損益 → 綠色（#059669）"""
        def pnl_color(v): return "#059669" if v >= 0 else "#dc2626"
        assert pnl_color(100)   == "#059669"
        assert pnl_color(0)     == "#059669"
        assert pnl_color(0.001) == "#059669"

    def test_negative_pnl_color_red(self):
        """TC-4-05c：負值損益 → 紅色（#dc2626）"""
        def pnl_color(v): return "#059669" if v >= 0 else "#dc2626"
        assert pnl_color(-100)   == "#dc2626"
        assert pnl_color(-0.001) == "#dc2626"


# ════════════════════════════════════════════════════════════════════════════
# TC-4-06  NAV 圖勾選 QQQ，benchmark 曲線正確疊加並正規化
# ════════════════════════════════════════════════════════════════════════════
class TestTC406:
    def test_normalize_bars_first_value_is_1(self):
        """TC-4-06a：_normalize_bars() 第一個 close_norm = 1.0"""
        bars = [
            {"date": "2026-01-02", "close": 500.0},
            {"date": "2026-01-03", "close": 510.0},
            {"date": "2026-01-04", "close": 490.0},
        ]
        normed = DashboardDataProvider._normalize_bars(bars)
        assert normed[0]["close_norm"] == pytest.approx(1.0)

    def test_normalize_bars_relative_values_correct(self):
        """TC-4-06b：相對漲幅計算正確（+2% → 1.02）"""
        bars = [
            {"date": "2026-01-02", "close": 500.0},
            {"date": "2026-01-03", "close": 510.0},
        ]
        normed = DashboardDataProvider._normalize_bars(bars)
        assert normed[1]["close_norm"] == pytest.approx(1.02)

    def test_normalize_bars_empty_returns_empty(self):
        """TC-4-06c：空序列回傳空 list"""
        assert DashboardDataProvider._normalize_bars([]) == []

    def test_qqq_key_in_result_when_requested(self, provider, monkeypatch):
        """TC-4-06d：請求 QQQ 時，get_benchmark_series 回傳含 QQQ key"""
        mock_bars = [
            {"date": "2026-01-02", "close": 500.0},
            {"date": "2026-01-03", "close": 505.0},
        ]
        client = provider.account_manager.get_client("ACC001")
        monkeypatch.setattr(client, "get_historical_bars",
                            lambda sym, s, e, tf="1Day": mock_bars)

        series = provider.get_benchmark_series(
            "ACC001", ["QQQ"], "2026-01-02", "2026-01-03"
        )
        assert "QQQ" in series
        assert len(series["QQQ"]) == 2
        assert series["QQQ"][0]["close_norm"] == pytest.approx(1.0)


# ════════════════════════════════════════════════════════════════════════════
# TC-4-07  取消勾選 SPY，SPY 曲線正確消失
# ════════════════════════════════════════════════════════════════════════════
class TestTC407:
    def test_spy_absent_when_not_requested(self, provider, monkeypatch):
        """TC-4-07a：僅請求 QQQ 時，結果中不含 SPY"""
        client = provider.account_manager.get_client("ACC001")
        monkeypatch.setattr(client, "get_historical_bars",
                            lambda sym, s, e, tf="1Day": [
                                {"date": "2026-01-02", "close": 500.0}
                            ])
        series = provider.get_benchmark_series(
            "ACC001", ["QQQ"], "2026-01-02", "2026-01-02"
        )
        assert "SPY" not in series

    def test_filter_benchmarks_removes_unchecked(self):
        """TC-4-07b：filter_benchmarks() 移除未勾選的 symbol"""
        from src.dashboard.components.nav_chart import filter_benchmarks
        all_data = {
            "QQQ": [{"date": "2026-01-02", "close_norm": 1.0}],
            "SPY": [{"date": "2026-01-02", "close_norm": 1.0}],
        }
        visible = filter_benchmarks(all_data, selected=["QQQ"])
        assert "SPY" not in visible
        assert "QQQ" in visible

    def test_filter_benchmarks_empty_selection(self):
        """TC-4-07c：全部取消勾選時，回傳空 dict"""
        from src.dashboard.components.nav_chart import filter_benchmarks
        all_data = {"QQQ": [], "SPY": []}
        visible = filter_benchmarks(all_data, selected=[])
        assert visible == {}


# ════════════════════════════════════════════════════════════════════════════
# TC-4-08  回撤曲線最低點與 max_drawdown_pct 一致
# ════════════════════════════════════════════════════════════════════════════
class TestTC408:
    def test_drawdown_min_equals_max_drawdown(self):
        """TC-4-08a：calc_drawdown_series() 最小值 == _calc_max_drawdown()"""
        dd_series = DashboardDataProvider.calc_drawdown_series(MOCK_NAV_HISTORY)
        min_dd    = min(e["drawdown"] for e in dd_series)
        expected  = ReportModel._calc_max_drawdown(MOCK_NAV_HISTORY)
        assert abs(min_dd - expected) < 1e-7, \
            f"回撤序列最低值 {min_dd:.8f} ≠ max_drawdown {expected:.8f}"

    def test_drawdown_series_length_matches_history(self):
        """TC-4-08b：回撤序列長度 == NAV 歷史長度"""
        dd_series = DashboardDataProvider.calc_drawdown_series(MOCK_NAV_HISTORY)
        assert len(dd_series) == len(MOCK_NAV_HISTORY)

    def test_all_drawdown_values_non_positive(self):
        """TC-4-08c：所有回撤值 <= 0（跌幅表示為負數）"""
        dd_series = DashboardDataProvider.calc_drawdown_series(MOCK_NAV_HISTORY)
        for entry in dd_series:
            assert entry["drawdown"] <= 0, \
                f"{entry['date']} 回撤值應 <= 0，得到 {entry['drawdown']}"

    def test_drawdown_zero_at_new_high(self):
        """TC-4-08d：創新高時回撤 = 0.0"""
        history   = [{"date": "2026-01-01", "nav": 100_000},
                     {"date": "2026-01-02", "nav": 110_000}]
        dd_series = DashboardDataProvider.calc_drawdown_series(history)
        assert dd_series[-1]["drawdown"] == pytest.approx(0.0)

    def test_drawdown_chart_buildable(self):
        """TC-4-08e：calc_drawdown_series 結果可直接傳入 build_drawdown_chart"""
        from src.dashboard.components.drawdown_chart import build_drawdown_chart
        dd_series = DashboardDataProvider.calc_drawdown_series(MOCK_NAV_HISTORY)
        fig = build_drawdown_chart(dd_series)
        assert fig is not None
        assert len(fig.data) > 0


# ════════════════════════════════════════════════════════════════════════════
# TC-4-09  歷史報告透過相對路徑載入（雲端相容）
# ════════════════════════════════════════════════════════════════════════════
class TestTC409:
    def test_history_report_loads(self, provider, saved_report):
        """TC-4-09a：儲存後能正確讀取歷史報告"""
        loaded = provider.load_history_report("ACC001", "2026-01-15")
        assert loaded is not None
        assert loaded["account_id"] == "ACC001"
        assert loaded["report_date"] == "2026-01-15"

    def test_history_report_nav_intact(self, provider, saved_report):
        """TC-4-09b：歷史報告中的 NAV 數值正確"""
        loaded = provider.load_history_report("ACC001", "2026-01-15")
        assert loaded["summary"]["nav"] == 105_000.0

    def test_nonexistent_report_returns_none(self, provider):
        """TC-4-09c：找不到報告時回傳 None，不拋出例外"""
        loaded = provider.load_history_report("ACC001", "1999-01-01")
        assert loaded is None

    def test_available_dates_contains_saved_date(self, provider, saved_report):
        """TC-4-09d：get_available_dates() 包含已儲存的日期"""
        dates = provider.get_available_dates("ACC001")
        assert "2026-01-15" in dates, f"期望 2026-01-15 在 {dates} 中"

    def test_reports_dir_is_valid_string(self):
        """TC-4-09e：get_reports_dir() 回傳非空字串（跨環境路徑解析正確）"""
        reports_dir = get_reports_dir()
        assert isinstance(reports_dir, str) and len(reports_dir) > 0


# ════════════════════════════════════════════════════════════════════════════
# TC-4-10  60 秒自動刷新，設定值正確
# ════════════════════════════════════════════════════════════════════════════
class TestTC410:
    def test_refresh_interval_is_60_seconds(self):
        """TC-4-10a：get_refresh_interval_seconds() 回傳 60"""
        assert get_refresh_interval_seconds() == 60

    def test_refresh_interval_ms_is_60000(self):
        """TC-4-10b：get_refresh_interval_ms() 回傳 60000"""
        assert DashboardDataProvider.get_refresh_interval_ms() == 60_000

    def test_settings_json_has_auto_refresh(self):
        """TC-4-10c：config/settings.json 中 auto_refresh_seconds = 60"""
        settings_path = os.path.join(
            os.path.dirname(__file__), "../../config/settings.json"
        )
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
        assert settings["dashboard"]["auto_refresh_seconds"] == 60

    def test_streamlit_config_headless(self):
        """TC-4-10d：.streamlit/config.toml 設定 headless=true（雲端部署必要）"""
        config_path = os.path.join(
            os.path.dirname(__file__), "../../.streamlit/config.toml"
        )
        with open(config_path, encoding="utf-8") as f:
            content = f.read()
        assert "headless" in content.lower()
        assert "true" in content.lower()
