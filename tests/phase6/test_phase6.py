"""
Phase 6 測試案例 — GitHub Actions 自動化
TC-6-01 ~ TC-6-08

測試策略：
  - Workflow YAML 驗證（cron、trigger、secrets 注入）
  - Runner 邏輯測試（run_all_accounts、generate_for_account）
  - 錯誤隔離（單帳戶失敗不中斷整體流程）
  - 安全驗證（API Key 不出現在 log 輸出中）
  - Summary Markdown 格式驗證
"""
import datetime
import json
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from src.runner.daily_trader import (
    run_all_accounts,
    build_summary_markdown,
    is_first_trading_day_of_month,
    _run_single_account,
)
from src.runner.daily_reporter import generate_for_account

REAL_KEY    = "PKL6ZHN5BMJWRVHAQPC3N63PJI"
REAL_SECRET = "BmoeU1bH5HTJs6XJDaLCsUtZDqAH8q8SAmZPisPX9awg"


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def strategy_engine():
    from src.core.strategy_engine import StrategyEngine
    from src.dashboard.config import _project_root
    return StrategyEngine(strategies_dir=os.path.join(_project_root(), "strategies"))


# ════════════════════════════════════════════════════════════════════════════
# TC-6-01  手動觸發 / 排程觸發：所有啟用帳戶依序執行
# ════════════════════════════════════════════════════════════════════════════
class TestTC601:
    def test_run_all_accounts_returns_result_for_each_enabled(
        self, account_manager, strategy_engine
    ):
        """TC-6-01a：run_all_accounts 為每個啟用帳戶回傳結果"""
        results = run_all_accounts(
            account_manager=account_manager,
            strategy_engine=strategy_engine,
            dry_run=True,
        )
        # ACC001 是唯一啟用帳戶
        assert "ACC001" in results

    def test_acc001_result_has_status(self, account_manager, strategy_engine):
        """TC-6-01b：ACC001 結果包含 status 欄位"""
        results = run_all_accounts(
            account_manager=account_manager,
            strategy_engine=strategy_engine,
            dry_run=True,
        )
        assert "status" in results["ACC001"]

    def test_dry_run_does_not_place_real_orders(
        self, account_manager, strategy_engine
    ):
        """TC-6-01c：dry_run=True 時所有交易狀態為 dry_run"""
        results = run_all_accounts(
            account_manager=account_manager,
            strategy_engine=strategy_engine,
            dry_run=True,
        )
        r = results.get("ACC001", {})
        if r.get("status") == "success":
            for trade in r.get("trades", []):
                assert trade.get("status") == "dry_run"

    def test_disabled_account_not_in_results(
        self, account_manager, strategy_engine
    ):
        """TC-6-01d：停用帳戶（ACC002）不出現在結果中"""
        results = run_all_accounts(
            account_manager=account_manager,
            strategy_engine=strategy_engine,
            dry_run=True,
        )
        assert "ACC002" not in results


# ════════════════════════════════════════════════════════════════════════════
# TC-6-02  帳戶 A 失敗，帳戶 B 繼續執行（錯誤隔離）
# ════════════════════════════════════════════════════════════════════════════
class TestTC602:
    def test_failed_account_does_not_stop_others(self):
        """TC-6-02a：第一個帳戶失敗，第二個帳戶仍執行"""
        mock_am = MagicMock()
        mock_am.iter_enabled_accounts.return_value = [
            ("ACC_FAIL", MagicMock(), {"account_id": "ACC_FAIL", "active_strategy": "x"}),
            ("ACC_OK",   MagicMock(), {"account_id": "ACC_OK",   "active_strategy": "x"}),
        ]

        call_log = []

        def mock_single(account_id, client, config, se, ef, notifier, dry_run):
            call_log.append(account_id)
            if account_id == "ACC_FAIL":
                raise RuntimeError("模擬帳戶失敗")
            return {"orders": {}, "trades": [], "nav": 0}

        with patch("src.runner.daily_trader._run_single_account", side_effect=mock_single):
            results = run_all_accounts(
                account_manager   = mock_am,
                strategy_engine   = MagicMock(),
                dry_run           = True,
            )

        assert results["ACC_FAIL"]["status"] == "failed"
        assert results["ACC_OK"]["status"]   == "success"
        assert "ACC_OK" in call_log

    def test_failed_account_has_error_message(self):
        """TC-6-02b：失敗帳戶的結果包含 error 描述"""
        mock_am = MagicMock()
        mock_am.iter_enabled_accounts.return_value = [
            ("BAD", MagicMock(), {"account_id": "BAD", "active_strategy": "x"}),
        ]

        def mock_single(*args, **kwargs):
            raise ValueError("策略不存在")

        with patch("src.runner.daily_trader._run_single_account", side_effect=mock_single):
            results = run_all_accounts(
                account_manager=mock_am, strategy_engine=MagicMock(), dry_run=True
            )

        assert "error" in results["BAD"]
        assert "策略" in results["BAD"]["error"] or "exist" in results["BAD"]["error"].lower()

    def test_empty_accounts_returns_empty_dict(self):
        """TC-6-02c：無啟用帳戶時回傳空 dict（不拋例外）"""
        mock_am = MagicMock()
        mock_am.iter_enabled_accounts.return_value = []
        results = run_all_accounts(
            account_manager=mock_am, strategy_engine=MagicMock(), dry_run=True
        )
        assert results == {}


# ════════════════════════════════════════════════════════════════════════════
# TC-6-03  日報產生並儲存至 repo（JSON 檔存在）
# ════════════════════════════════════════════════════════════════════════════
class TestTC603:
    def test_report_json_created(self, account_manager, tmp_path):
        """TC-6-03a：generate_for_account() 在指定目錄產生 JSON 報告"""
        from src.reports.report_model import ReportModel
        client = account_manager.get_client("ACC001")
        rm     = ReportModel(client=client, reports_dir=str(tmp_path))

        path = generate_for_account(
            account_id  = "ACC001",
            client      = client,
            config      = {"account_id": "ACC001", "active_strategy": "nasdaq_top10"},
            report_model= rm,
        )
        assert os.path.exists(path), f"報告 JSON 不存在：{path}"

    def test_report_json_parseable(self, account_manager, tmp_path):
        """TC-6-03b：儲存的 JSON 可被正確解析"""
        from src.reports.report_model import ReportModel
        client = account_manager.get_client("ACC001")
        rm     = ReportModel(client=client, reports_dir=str(tmp_path / "p603b"))

        path = generate_for_account(
            account_id  = "ACC001",
            client      = client,
            config      = {"account_id": "ACC001", "active_strategy": "nasdaq_top10"},
            report_model= rm,
        )
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["account_id"] == "ACC001"
        assert "summary" in data

    def test_report_path_contains_today(self, account_manager, tmp_path):
        """TC-6-03c：報告路徑包含今日日期目錄"""
        from src.reports.report_model import ReportModel
        today  = datetime.date.today().isoformat()
        client = account_manager.get_client("ACC001")
        rm     = ReportModel(client=client, reports_dir=str(tmp_path / "p603c"))

        path = generate_for_account(
            account_id  = "ACC001",
            client      = client,
            config      = {"account_id": "ACC001", "active_strategy": "nasdaq_top10"},
            report_model= rm,
        )
        assert today in path


# ════════════════════════════════════════════════════════════════════════════
# TC-6-04  monthly_rebalance.yml 正確識別每月第一個交易日
# ════════════════════════════════════════════════════════════════════════════
class TestTC604:
    MOCK_CALENDAR = [
        {"date": "2026-05-01"},
        {"date": "2026-05-04"},
        {"date": "2026-05-05"},
        {"date": "2026-05-06"},
    ]

    def test_first_trading_day_correct(self):
        """TC-6-04a：2026-05-01 是五月第一個交易日"""
        assert is_first_trading_day_of_month("2026-05-01", self.MOCK_CALENDAR) is True

    def test_non_first_day_is_false(self):
        """TC-6-04b：2026-05-04 不是五月第一個交易日"""
        assert is_first_trading_day_of_month("2026-05-04", self.MOCK_CALENDAR) is False

    def test_empty_calendar_returns_false(self):
        """TC-6-04c：空日曆回傳 False（不拋例外）"""
        assert is_first_trading_day_of_month("2026-05-01", []) is False

    def test_different_month_not_detected(self):
        """TC-6-04d：六月資料不影響五月判斷"""
        calendar = [{"date": "2026-06-01"}] + self.MOCK_CALENDAR
        assert is_first_trading_day_of_month("2026-05-01", calendar) is True
        assert is_first_trading_day_of_month("2026-06-01", calendar) is True


# ════════════════════════════════════════════════════════════════════════════
# TC-6-05  執行時間記錄到日誌
# ════════════════════════════════════════════════════════════════════════════
class TestTC605:
    def test_run_logs_start_and_completion(self, caplog):
        """TC-6-05a：run_all_accounts 記錄開始與完成訊息"""
        mock_am = MagicMock()
        mock_am.iter_enabled_accounts.return_value = []
        with caplog.at_level(logging.INFO, logger="runner.daily_trader"):
            run_all_accounts(
                account_manager=mock_am,
                strategy_engine=MagicMock(),
                dry_run=True,
            )
        messages = " ".join(r.message for r in caplog.records)
        assert "開始" in messages or "start" in messages.lower()
        assert "完成" in messages or "finish" in messages.lower() or "complete" in messages.lower()

    def test_run_logs_timing(self, caplog):
        """TC-6-05b：log 中包含耗時資訊（秒數）"""
        mock_am = MagicMock()
        mock_am.iter_enabled_accounts.return_value = []
        with caplog.at_level(logging.INFO, logger="runner.daily_trader"):
            run_all_accounts(
                account_manager=mock_am,
                strategy_engine=MagicMock(),
                dry_run=True,
            )
        messages = " ".join(r.message for r in caplog.records)
        # 耗時格式：Xs 或「耗時」
        assert "s" in messages or "耗時" in messages or "elapsed" in messages.lower()


# ════════════════════════════════════════════════════════════════════════════
# TC-6-06  API Key / Secret 不出現在任何 log 輸出中
# ════════════════════════════════════════════════════════════════════════════
class TestTC606:
    def test_api_key_not_in_logs(self, account_manager, strategy_engine, caplog):
        """TC-6-06a：整個 run_all_accounts 執行過程中，API Key 不出現在 log"""
        with caplog.at_level(logging.DEBUG):
            run_all_accounts(
                account_manager=account_manager,
                strategy_engine=strategy_engine,
                dry_run=True,
            )
        all_logs = " ".join(r.message for r in caplog.records)
        assert REAL_KEY    not in all_logs, "API Key 不應出現在日誌中"
        assert REAL_SECRET not in all_logs, "API Secret 不應出現在日誌中"

    def test_client_repr_masks_key(self, real_client):
        """TC-6-06b：AlpacaClient repr 遮蔽完整 Key（只顯示末 4 碼）"""
        r = repr(real_client)
        assert REAL_KEY    not in r
        assert REAL_SECRET not in r
        assert "***" in r or "key=***" in r.lower()


# ════════════════════════════════════════════════════════════════════════════
# TC-6-07  GitHub Actions Summary 顯示各帳戶執行狀態
# ════════════════════════════════════════════════════════════════════════════
class TestTC607:
    MOCK_RESULTS = {
        "ACC001": {"status": "success", "orders": {"buy": [("AAPL", 5)], "sell": []}, "nav": 107_000},
        "ACC002": {"status": "failed",  "error": "連線逾時"},
    }

    def test_summary_contains_all_accounts(self):
        """TC-6-07a：Summary 包含所有帳戶 ID"""
        md = build_summary_markdown(self.MOCK_RESULTS)
        assert "ACC001" in md
        assert "ACC002" in md

    def test_summary_shows_success_icon(self):
        """TC-6-07b：成功帳戶顯示成功標示"""
        md = build_summary_markdown(self.MOCK_RESULTS)
        assert "✅" in md or "success" in md

    def test_summary_shows_failure_icon(self):
        """TC-6-07c：失敗帳戶顯示失敗標示"""
        md = build_summary_markdown(self.MOCK_RESULTS)
        assert "❌" in md or "failed" in md

    def test_summary_is_markdown_table(self):
        """TC-6-07d：Summary 包含 Markdown 表格格式（| 符號）"""
        md = build_summary_markdown(self.MOCK_RESULTS)
        assert "|" in md
        assert "---" in md

    def test_summary_includes_nav(self):
        """TC-6-07e：Summary 顯示 NAV 數值"""
        md = build_summary_markdown(self.MOCK_RESULTS)
        assert "107,000" in md


# ════════════════════════════════════════════════════════════════════════════
# TC-6-08  週末不觸發 Trading Workflow（cron 限定 1-5）
# ════════════════════════════════════════════════════════════════════════════
class TestTC608:
    def _load_cron(self, workflow_file: str) -> str:
        """從 YAML 文字中擷取 cron 字串（不依賴 pyyaml）"""
        path = os.path.join(
            os.path.dirname(__file__),
            "../../.github/workflows",
            workflow_file,
        )
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # 找到 cron: '...' 的那一行；去除行內 # 註解後再回傳
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("- cron:"):
                raw = stripped.split(":", 1)[1].strip().strip("'\"")
                # 去除 # 之後的行內注釋（先按空格分割）
                cron_expr = raw.split("#")[0].strip().strip("'\"")
                return cron_expr
        return ""

    def test_daily_trading_cron_weekdays_only(self):
        """TC-6-08a：daily_trading.yml cron 僅限工作日 (dow = 1-5)"""
        cron = self._load_cron("daily_trading.yml")
        dow  = cron.split()[-1]
        assert "1-5" in dow, f"daily_trading cron dow={dow!r}，應包含 1-5"

    def test_daily_report_cron_weekdays_only(self):
        """TC-6-08b：daily_report.yml cron 僅限工作日"""
        cron = self._load_cron("daily_report.yml")
        dow  = cron.split()[-1]
        assert "1-5" in dow, f"daily_report cron dow={dow!r}，應包含 1-5"

    def test_daily_trading_cron_correct_hour(self):
        """TC-6-08c：daily_trading.yml cron 在 UTC 13:31（EST 09:31）"""
        cron = self._load_cron("daily_trading.yml")
        parts  = cron.split()
        minute = parts[0]
        hour   = parts[1]
        assert minute == "31" and hour == "13", \
            f"期望 UTC 13:31，cron={cron!r}"

    def test_workflow_files_exist(self):
        """TC-6-08d：三個 workflow YAML 檔案均存在"""
        base = os.path.join(
            os.path.dirname(__file__), "../../.github/workflows"
        )
        for fname in ["daily_trading.yml", "daily_report.yml", "monthly_rebalance.yml"]:
            assert os.path.exists(os.path.join(base, fname)), f"找不到 {fname}"
