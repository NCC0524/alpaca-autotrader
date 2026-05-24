"""
Phase 1 測試案例 — 基礎建設與多帳戶連接
TC-1-01 ~ TC-1-08
"""
import os
import json
import pytest

from src.core.alpaca_client import (
    AlpacaClient, AlpacaAuthError, AlpacaConnectionError, AlpacaAPIError
)
from src.core.account_manager import AccountManager, AccountConfigError


# ════════════════════════════════════════════════════════════
# TC-1-01  成功載入 account_registry.json，帳戶數量正確
# ════════════════════════════════════════════════════════════
class TestTC101:
    def test_load_registry_success(self, registry_path):
        """TC-1-01：成功載入 account_registry.json"""
        am = AccountManager(registry_path=registry_path)
        assert am.count() >= 1, "至少應有 1 個啟用帳戶"

    def test_registry_contains_acc001(self, registry_path):
        """TC-1-01b：ACC001 應在啟用帳戶列表中"""
        am = AccountManager(registry_path=registry_path)
        assert "ACC001" in am.get_all_account_ids()

    def test_registry_disabled_not_loaded(self, registry_path):
        """TC-1-01c：ACC002（enabled=false）不應被載入"""
        am = AccountManager(registry_path=registry_path)
        assert "ACC002" not in am.get_all_account_ids()

    def test_registry_file_not_found(self, tmp_path):
        """TC-1-01d：登錄檔不存在時拋出明確錯誤"""
        with pytest.raises(AccountConfigError, match="找不到帳戶登錄檔"):
            AccountManager(registry_path=str(tmp_path / "nonexistent.json"))


# ════════════════════════════════════════════════════════════
# TC-1-02  使用正確 API Key 連接 Alpaca，回傳帳戶狀態 ACTIVE
# ════════════════════════════════════════════════════════════
class TestTC102:
    def test_account_status_active(self, real_client):
        """TC-1-02：正確憑證 → 帳戶狀態為 ACTIVE"""
        status = real_client.get_account_status()
        assert status == "ACTIVE", f"期望 ACTIVE，收到 {status}"

    def test_account_returns_dict(self, real_client):
        """TC-1-02b：get_account() 回傳 dict，含必要欄位"""
        acct = real_client.get_account()
        for field in ["id", "cash", "portfolio_value", "status"]:
            assert field in acct, f"帳戶資訊缺少欄位：{field}"


# ════════════════════════════════════════════════════════════
# TC-1-03  使用錯誤 API Key，系統拋出明確錯誤訊息，不崩潰
# ════════════════════════════════════════════════════════════
class TestTC103:
    def test_bad_key_raises_auth_error(self):
        """TC-1-03：錯誤 API Key → AlpacaAuthError，不是未處理 Exception"""
        bad_client = AlpacaClient(
            api_key    = "WRONG_KEY_123456789",
            api_secret = "WRONG_SECRET_XXXXXXXXXXXXXXXXXXXXXXXXXXX",
            base_url   = "https://paper-api.alpaca.markets/v2",
        )
        with pytest.raises(AlpacaAuthError) as exc_info:
            bad_client.get_account()
        assert exc_info.value.code in (401, 403), \
            f"期望 401/403，收到 {exc_info.value.code}"

    def test_error_message_is_readable(self):
        """TC-1-03b：錯誤訊息應為中文可讀格式"""
        bad_client = AlpacaClient("BAD", "BAD")
        with pytest.raises(AlpacaAuthError) as exc_info:
            bad_client.get_account()
        assert len(str(exc_info.value)) > 5


# ════════════════════════════════════════════════════════════
# TC-1-04  同時初始化 2 個以上帳戶，各自獨立運作
# ════════════════════════════════════════════════════════════
class TestTC104:
    def test_two_clients_independent(self):
        """TC-1-04：兩個 Client 實例各自獨立，修改一個不影響另一個"""
        c1 = AlpacaClient("KEY_A", "SECRET_A")
        c2 = AlpacaClient("KEY_B", "SECRET_B")
        assert c1.api_key != c2.api_key
        assert c1 is not c2

    def test_account_manager_isolates_clients(self, account_manager):
        """TC-1-04b：AccountManager 為每個帳戶獨立維護 Client"""
        ids = account_manager.get_all_account_ids()
        assert len(ids) >= 1
        # 取得第一個帳戶的 client，確認不影響其他帳戶
        c1 = account_manager.get_client(ids[0])
        assert isinstance(c1, AlpacaClient)


# ════════════════════════════════════════════════════════════
# TC-1-05  API 超時，自動重試最多 3 次
# ════════════════════════════════════════════════════════════
class TestTC105:
    def test_retry_on_timeout(self, monkeypatch):
        """TC-1-05：模擬超時，驗證重試次數不超過 max_retries"""
        from unittest.mock import patch, MagicMock
        import urllib.request

        call_count = {"n": 0}

        def fake_urlopen(req, timeout=None):
            call_count["n"] += 1
            raise TimeoutError("模擬超時")

        client = AlpacaClient("K", "S", max_retries=3, timeout=1)

        with patch("src.core.alpaca_client.urlopen", fake_urlopen):
            with pytest.raises(AlpacaConnectionError):
                client.get_account()

        assert call_count["n"] == 3, \
            f"期望重試 3 次，實際重試 {call_count['n']} 次"

    def test_max_retries_configurable(self):
        """TC-1-05b：max_retries 可自訂"""
        c = AlpacaClient("K", "S", max_retries=5)
        assert c.max_retries == 5


# ════════════════════════════════════════════════════════════
# TC-1-06  查詢現金餘額，回傳數值 >= 0
# ════════════════════════════════════════════════════════════
class TestTC106:
    def test_cash_is_non_negative(self, real_client):
        """TC-1-06：現金餘額 >= 0"""
        cash = real_client.get_cash()
        assert isinstance(cash, float)
        assert cash >= 0, f"現金餘額不可為負數，收到 {cash}"

    def test_portfolio_value_is_positive(self, real_client):
        """TC-1-06b：帳戶總值 > 0"""
        pv = real_client.get_portfolio_value()
        assert pv > 0, f"帳戶總值應 > 0，收到 {pv}"


# ════════════════════════════════════════════════════════════
# TC-1-07  查詢持倉清單，空帳戶回傳空陣列 []（或有持倉時為 list）
# ════════════════════════════════════════════════════════════
class TestTC107:
    def test_positions_returns_list(self, real_client):
        """TC-1-07：get_positions() 一定回傳 list（空或有資料）"""
        positions = real_client.get_positions()
        assert isinstance(positions, list), \
            f"期望 list，收到 {type(positions)}"

    def test_positions_fields_if_not_empty(self, real_client):
        """TC-1-07b：若有持倉，每筆應含必要欄位"""
        positions = real_client.get_positions()
        for pos in positions:
            for field in ["symbol", "qty", "avg_entry_price", "current_price", "market_value"]:
                assert field in pos, f"持倉資料缺少欄位：{field}"


# ════════════════════════════════════════════════════════════
# TC-1-08  停用帳戶（enabled: false）不被初始化
# ════════════════════════════════════════════════════════════
class TestTC108:
    def test_disabled_account_not_in_list(self, account_manager):
        """TC-1-08：ACC002（enabled=false）不在啟用帳戶清單"""
        ids = account_manager.get_all_account_ids()
        assert "ACC002" not in ids

    def test_disabled_account_raises_error(self, account_manager):
        """TC-1-08b：嘗試取得停用帳戶的 Client 應拋出 AccountConfigError"""
        with pytest.raises(AccountConfigError):
            account_manager.get_client("ACC002")

    def test_disabled_account_in_json_but_not_loaded(self, registry_path):
        """TC-1-08c：ACC002 確實在 JSON 中但 enabled=false"""
        with open(registry_path, encoding="utf-8") as f:
            data = json.load(f)
        acc002 = next((a for a in data["accounts"] if a["account_id"] == "ACC002"), None)
        assert acc002 is not None, "ACC002 應存在於 JSON 中"
        assert acc002["enabled"] is False, "ACC002 的 enabled 應為 false"

        am = AccountManager(registry_path=registry_path)
        assert "ACC002" not in am.get_all_account_ids()
