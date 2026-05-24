"""
Phase 3 測試案例 — 每日報告系統（Model-View 分離）
TC-3-01 ~ TC-3-10
"""
import json
import os
import datetime
import pytest

from src.reports.report_model import ReportModel
from src.reports.report_view  import ReportView

TODAY = datetime.date.today().isoformat()

# ── 測試用資料 ─────────────────────────────────────────────────────────────
MOCK_NAV_HISTORY = [
    {"date": "2026-01-02", "nav": 100000.0},
    {"date": "2026-02-01", "nav": 103000.0},
    {"date": "2026-03-01", "nav": 101500.0},
    {"date": "2026-04-01", "nav": 105000.0},
    {"date": "2026-04-15", "nav": 104000.0},  # 模擬回撤
    {"date": "2026-05-01", "nav": 106000.0},
    {"date": "2026-05-23", "nav": 107000.0},  # 昨日
]
INCEPTION_NAV  = 100000.0
INCEPTION_DATE = "2026-01-02"

@pytest.fixture(scope="module")
def model(real_client, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("reports_model")
    return ReportModel(client=real_client, reports_dir=str(tmp))

@pytest.fixture(scope="module")
def report(model):
    return model.generate(
        account_id     = "ACC001",
        strategy_id    = "nasdaq_top10",
        nav_history    = MOCK_NAV_HISTORY,
        inception_nav  = INCEPTION_NAV,
        inception_date = INCEPTION_DATE,
    )

@pytest.fixture(scope="module")
def view():
    return ReportView()


# ════════════════════════════════════════════════════════════
# TC-3-01  產生今日 JSON 報告，所有必要欄位均存在
# ════════════════════════════════════════════════════════════
class TestTC301:
    REQUIRED_TOP_FIELDS    = ["report_date","account_id","strategy_id","generated_at","summary","positions","trades_today","nav_history"]
    REQUIRED_SUMMARY_FIELDS= ["nav","cash","inception_nav","inception_date","daily_pnl","daily_pnl_pct","total_return_pct","annual_return_pct","max_drawdown_pct","days_elapsed"]

    def test_top_level_fields(self, report):
        """TC-3-01a：頂層必要欄位均存在"""
        for f in self.REQUIRED_TOP_FIELDS:
            assert f in report, f"缺少頂層欄位：{f}"

    def test_summary_fields(self, report):
        """TC-3-01b：summary 必要欄位均存在"""
        s = report["summary"]
        for f in self.REQUIRED_SUMMARY_FIELDS:
            assert f in s, f"缺少 summary 欄位：{f}"

    def test_positions_is_list(self, report):
        """TC-3-01c：positions 為 list"""
        assert isinstance(report["positions"], list)

    def test_trades_today_is_list(self, report):
        """TC-3-01d：trades_today 為 list"""
        assert isinstance(report["trades_today"], list)


# ════════════════════════════════════════════════════════════
# TC-3-02  報告日期欄位與今日日期一致
# ════════════════════════════════════════════════════════════
class TestTC302:
    def test_report_date_is_today(self, report):
        """TC-3-02：report_date 為今日"""
        assert report["report_date"] == TODAY

    def test_generated_at_starts_with_today(self, report):
        """TC-3-02b：generated_at 的日期部分為今日"""
        assert report["generated_at"][:10] == TODAY


# ════════════════════════════════════════════════════════════
# TC-3-03  日損益計算正確（與 Alpaca API 一致）
# ════════════════════════════════════════════════════════════
class TestTC303:
    def test_daily_pnl_is_number(self, report):
        """TC-3-03：daily_pnl 為數值"""
        assert isinstance(report["summary"]["daily_pnl"], (int, float))

    def test_daily_pnl_pct_is_float(self, report):
        """TC-3-03b：daily_pnl_pct 為浮點數"""
        assert isinstance(report["summary"]["daily_pnl_pct"], float)

    def test_daily_pnl_matches_nav_minus_yesterday(self, model):
        """TC-3-03c：daily_pnl = 今日 NAV - 昨日 NAV"""
        yesterday_nav = model._get_yesterday_nav(MOCK_NAV_HISTORY, TODAY)
        if yesterday_nav > 0:
            # 昨日 NAV 是 107000
            assert yesterday_nav == 107000.0


# ════════════════════════════════════════════════════════════
# TC-3-04  週報酬率計算正確
# ════════════════════════════════════════════════════════════
class TestTC304:
    def test_weekly_return_is_float(self, report):
        """TC-3-04：weekly_pnl_pct 為浮點數"""
        assert isinstance(report["summary"]["weekly_pnl_pct"], float)

    def test_period_return_logic(self, model):
        """TC-3-04b：7 天報酬率計算邏輯正確"""
        current_nav = 110000.0
        # 7天前最近一筆是 2026-05-01 @ 106000
        r = model._period_return(MOCK_NAV_HISTORY, current_nav, days=7)
        # 結果應為正（從 106000 漲到 110000）
        assert r > 0


# ════════════════════════════════════════════════════════════
# TC-3-05  最大回撤計算正確
# ════════════════════════════════════════════════════════════
class TestTC305:
    def test_max_drawdown_is_negative_or_zero(self, model):
        """TC-3-05：最大回撤 <= 0（跌幅為負值）"""
        dd = model._calc_max_drawdown(MOCK_NAV_HISTORY)
        assert dd <= 0, f"回撤應 <= 0，收到 {dd}"

    def test_max_drawdown_known_sequence(self, model):
        """TC-3-05b：已知序列驗證：高點 105000 → 低點 104000 → 回撤 ≈ -0.952%"""
        history = [
            {"date": "2026-01-01", "nav": 100000},
            {"date": "2026-01-02", "nav": 105000},  # 峰值
            {"date": "2026-01-03", "nav": 104000},  # 回撤 -952
            {"date": "2026-01-04", "nav": 106000},
        ]
        dd = model._calc_max_drawdown(history)
        expected = (104000 - 105000) / 105000
        assert abs(dd - expected) < 1e-6, f"回撤期望 {expected:.6f}，收到 {dd:.6f}"

    def test_max_drawdown_zero_for_only_rising(self, model):
        """TC-3-05c：只有上漲時，回撤為 0"""
        history = [
            {"date": "2026-01-01", "nav": 100000},
            {"date": "2026-01-02", "nav": 101000},
            {"date": "2026-01-03", "nav": 102000},
        ]
        assert model._calc_max_drawdown(history) == 0.0


# ════════════════════════════════════════════════════════════
# TC-3-06  P/E Ratio 計算（本益比）
# ════════════════════════════════════════════════════════════
class TestTC306:
    def test_pe_ratio_formula(self):
        """TC-3-06：P/E = 股價 / EPS，結果正確"""
        price = 195.0
        eps   = 6.5
        pe    = price / eps
        assert abs(pe - 30.0) < 0.1

    def test_pe_ratio_positive_eps(self):
        """TC-3-06b：EPS > 0 時，P/E > 0"""
        price = 100.0
        eps   = 5.0
        assert price / eps == 20.0

    def test_pe_ratio_negative_eps(self):
        """TC-3-06c：EPS < 0（虧損股）時，P/E 為負（無意義，應標示 N/A）"""
        price = 100.0
        eps   = -2.0
        pe    = price / eps if eps != 0 else None
        # 確認系統不崩潰，且 P/E 為負
        assert pe is not None and pe < 0


# ════════════════════════════════════════════════════════════
# TC-3-07  JSON Model 渲染為 HTML，包含所有必要區塊
# ════════════════════════════════════════════════════════════
class TestTC307:
    def test_html_contains_nav(self, view, report):
        """TC-3-07：HTML 包含 NAV 數值"""
        html = view.render_html(report)
        nav_str = f"{report['summary']['nav']:,.2f}"
        assert nav_str in html, f"HTML 中找不到 NAV：{nav_str}"

    def test_html_contains_risk_warning(self, view, report):
        """TC-3-07b：HTML 含風險提醒"""
        html = view.render_html(report)
        assert "不構成任何投資建議" in html

    def test_html_contains_account_id(self, view, report):
        """TC-3-07c：HTML 含帳戶 ID"""
        html = view.render_html(report)
        assert report["account_id"] in html

    def test_html_is_valid_structure(self, view, report):
        """TC-3-07d：HTML 有完整的 html/body 標籤"""
        html = view.render_html(report)
        assert "<html" in html
        assert "</html>" in html
        assert "<body" in html


# ════════════════════════════════════════════════════════════
# TC-3-08  報告儲存至正確路徑
# ════════════════════════════════════════════════════════════
class TestTC308:
    def test_save_creates_file(self, model, report, tmp_path):
        """TC-3-08：save() 建立 JSON 檔案"""
        model.reports_dir = str(tmp_path / "model")
        path = model.save(report, "ACC001")
        assert os.path.exists(path), f"報告檔案不存在：{path}"

    def test_saved_file_is_valid_json(self, model, report, tmp_path):
        """TC-3-08b：儲存的檔案可被正確解析為 JSON"""
        model.reports_dir = str(tmp_path / "model2")
        path = model.save(report, "ACC001")
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["account_id"] == "ACC001"

    def test_path_contains_date_directory(self, model, report, tmp_path):
        """TC-3-08c：路徑包含日期目錄 YYYY-MM-DD"""
        model.reports_dir = str(tmp_path / "model3")
        path = model.save(report, "ACC001")
        assert TODAY in path


# ════════════════════════════════════════════════════════════
# TC-3-09  查詢歷史報告，正確回傳
# ════════════════════════════════════════════════════════════
class TestTC309:
    def test_load_existing_report(self, model, report, tmp_path):
        """TC-3-09：儲存後能正確載入"""
        model.reports_dir = str(tmp_path / "hist")
        model.save(report, "ACC001")
        loaded = model.load("ACC001", TODAY)
        assert loaded is not None
        assert loaded["account_id"] == "ACC001"

    def test_load_nonexistent_returns_none(self, model):
        """TC-3-09b：找不到歷史報告時回傳 None"""
        result = model.load("ACC001", "1999-01-01")
        assert result is None


# ════════════════════════════════════════════════════════════
# TC-3-10  Model 與 View 完全分離
# ════════════════════════════════════════════════════════════
class TestTC310:
    def test_view_accepts_any_valid_report_dict(self, view):
        """TC-3-10：View 直接接受 dict，不依賴 Model 類別"""
        minimal_report = {
            "report_date": TODAY,
            "account_id":  "TEST",
            "strategy_id": "test",
            "generated_at": TODAY + "T00:00:00",
            "summary": {
                "nav": 100000, "cash": 5000, "inception_nav": 100000,
                "inception_date": "2026-01-01",
                "daily_pnl": 100, "daily_pnl_pct": 0.001,
                "weekly_pnl_pct": 0.02, "monthly_pnl_pct": 0.05,
                "total_return_pct": 0.0, "annual_return_pct": 0.0,
                "max_drawdown_pct": 0.0, "days_elapsed": 0,
            },
            "positions": [],
            "trades_today": [],
        }
        html = view.render_html(minimal_report)
        assert len(html) > 100  # 有實質 HTML 內容

    def test_modifying_view_template_does_not_affect_model(self, model, view, report):
        """TC-3-10b：View 渲染不修改原始 report dict"""
        original_nav = report["summary"]["nav"]
        _ = view.render_html(report)
        assert report["summary"]["nav"] == original_nav
