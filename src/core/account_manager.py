"""
account_manager.py
多帳戶管理 — 從 account_registry.json 載入帳戶，並統一管理 AlpacaClient 實例
"""

import json
import os
from typing import Dict, List, Optional

from .alpaca_client import AlpacaClient, AlpacaAuthError, AlpacaError


class AccountConfigError(Exception):
    """帳戶設定錯誤"""
    pass


class AccountManager:
    """
    多帳戶管理器。
    - 從 account_registry.json 載入帳戶清單
    - 自動略過 enabled=false 的帳戶
    - 每個帳戶的 API Key/Secret 從環境變數讀取（不硬寫入程式）
    - 每個帳戶同時只能使用一個策略
    """

    REQUIRED_FIELDS = [
        "account_id", "name", "api_key_env",
        "api_secret_env", "base_url", "enabled",
    ]

    def __init__(self, registry_path: str = "accounts/account_registry.json"):
        self.registry_path = registry_path
        self._accounts: Dict[str, dict] = {}   # account_id → config
        self._clients:  Dict[str, AlpacaClient] = {}  # 惰性初始化
        self._load_registry()

    # ── 載入登錄檔 ─────────────────────────────────────────────────────────
    def _load_registry(self):
        if not os.path.exists(self.registry_path):
            raise AccountConfigError(
                f"找不到帳戶登錄檔：{self.registry_path}\n"
                "請確認路徑正確，或複製 accounts/account_template.json 建立設定"
            )

        with open(self.registry_path, encoding="utf-8") as f:
            data = json.load(f)

        accounts_raw = data.get("accounts", [])
        if not accounts_raw:
            raise AccountConfigError("account_registry.json 中沒有任何帳戶設定")

        loaded = 0
        for acc in accounts_raw:
            # 驗證必要欄位
            self._validate_account_config(acc)
            # 略過停用帳戶
            if not acc.get("enabled", True):
                continue
            acc_id = acc["account_id"]
            self._accounts[acc_id] = acc
            loaded += 1

        if loaded == 0:
            raise AccountConfigError("所有帳戶均已停用（enabled: false），至少需要一個啟用帳戶")

    def _validate_account_config(self, acc: dict):
        """驗證帳戶設定完整性"""
        acc_id = acc.get("account_id", "（未知）")
        for field in self.REQUIRED_FIELDS:
            if field not in acc:
                raise AccountConfigError(
                    f"帳戶 {acc_id} 缺少必要欄位：{field}"
                )

    # ── 取得 Client ─────────────────────────────────────────────────────────
    def get_client(self, account_id: str) -> AlpacaClient:
        """
        取得指定帳戶的 AlpacaClient（惰性初始化）
        API Key/Secret 從環境變數讀取
        """
        if account_id not in self._accounts:
            raise AccountConfigError(
                f"帳戶 {account_id} 不存在或已停用"
            )

        if account_id not in self._clients:
            acc = self._accounts[account_id]
            api_key    = os.environ.get(acc["api_key_env"], "")
            api_secret = os.environ.get(acc["api_secret_env"], "")

            if not api_key:
                raise AccountConfigError(
                    f"帳戶 {account_id}：環境變數 {acc['api_key_env']} 未設定"
                )
            if not api_secret:
                raise AccountConfigError(
                    f"帳戶 {account_id}：環境變數 {acc['api_secret_env']} 未設定"
                )

            self._clients[account_id] = AlpacaClient(
                api_key    = api_key,
                api_secret = api_secret,
                base_url   = acc.get("base_url", AlpacaClient.PAPER_BASE_URL),
                data_url   = acc.get("data_url", AlpacaClient.DATA_URL),
            )

        return self._clients[account_id]

    # ── 帳戶查詢 ────────────────────────────────────────────────────────────
    def get_all_account_ids(self) -> List[str]:
        """取得所有啟用帳戶的 ID 列表"""
        return list(self._accounts.keys())

    def get_account_config(self, account_id: str) -> dict:
        """取得帳戶設定（完整 dict）"""
        if account_id not in self._accounts:
            raise AccountConfigError(f"帳戶 {account_id} 不存在")
        return self._accounts[account_id].copy()

    def get_active_strategy(self, account_id: str) -> Optional[str]:
        """取得帳戶目前啟用的策略 ID（無策略時回傳 None）"""
        return self._accounts.get(account_id, {}).get("active_strategy")

    def get_email(self, account_id: str) -> str:
        """取得帳戶的 Email 地址"""
        return self._accounts.get(account_id, {}).get("email", "")

    def is_enabled(self, account_id: str) -> bool:
        """帳戶是否啟用"""
        return account_id in self._accounts

    def count(self) -> int:
        """啟用帳戶數量"""
        return len(self._accounts)

    # ── 策略管理 ────────────────────────────────────────────────────────────
    def set_active_strategy(self, account_id: str, strategy_id: str):
        """
        切換帳戶的啟用策略。
        規則：每帳戶同時只能有一個啟用策略。
        異動後立即寫回 account_registry.json。
        """
        if account_id not in self._accounts:
            raise AccountConfigError(f"帳戶 {account_id} 不存在")

        self._accounts[account_id]["active_strategy"] = strategy_id
        self._save_registry()

    def _save_registry(self):
        """將修改後的策略設定寫回 JSON 檔"""
        with open(self.registry_path, encoding="utf-8") as f:
            data = json.load(f)

        for acc in data["accounts"]:
            acc_id = acc.get("account_id")
            if acc_id in self._accounts:
                acc["active_strategy"] = self._accounts[acc_id].get("active_strategy")

        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 批次操作 ────────────────────────────────────────────────────────────
    def iter_enabled_accounts(self):
        """
        逐一迭代所有啟用帳戶，回傳 (account_id, client, config) tuple
        適合 GitHub Actions 走過所有帳戶
        """
        for acc_id in self.get_all_account_ids():
            try:
                client = self.get_client(acc_id)
                config = self.get_account_config(acc_id)
                yield acc_id, client, config
            except (AccountConfigError, AlpacaAuthError) as e:
                print(f"  ⚠ 帳戶 {acc_id} 初始化失敗，跳過：{e}")
                continue

    def __repr__(self):
        return f"AccountManager(accounts={self.get_all_account_ids()})"
