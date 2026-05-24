"""
config.py
統一配置載入器 — 支援 Streamlit Cloud Secrets 與本地環境變數
讓 Dashboard 在任何環境均可部署，零本地依賴
優先順序：st.secrets → os.environ → 預設值
"""
import json
import os
from typing import Optional


# ── 路徑解析 ─────────────────────────────────────────────────────────────────
def _project_root() -> str:
    """動態計算專案根目錄（config.py 位於 src/dashboard/ 下兩層）"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", ".."))


# ── Secret 讀取 ──────────────────────────────────────────────────────────────
def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    按優先順序讀取 secret：
    1. Streamlit st.secrets（Streamlit Cloud 部署時）
    2. os.environ（本地開發 / GitHub Actions）
    3. default
    """
    try:
        import streamlit as st          # noqa: F401
        val = st.secrets.get(key)
        if val is not None:
            return str(val)
    except Exception:
        pass
    return os.environ.get(key, default)


# ── Alpaca 憑證 ───────────────────────────────────────────────────────────────
def get_alpaca_key(account_id: str) -> str:
    key = get_secret(f"ALPACA_KEY_{account_id}")
    if not key:
        raise EnvironmentError(
            f"找不到 ALPACA_KEY_{account_id}。"
            f"請在 .streamlit/secrets.toml 或環境變數中設定。"
        )
    return key


def get_alpaca_secret(account_id: str) -> str:
    secret = get_secret(f"ALPACA_SECRET_{account_id}")
    if not secret:
        raise EnvironmentError(
            f"找不到 ALPACA_SECRET_{account_id}。"
            f"請在 .streamlit/secrets.toml 或環境變數中設定。"
        )
    return secret


def get_base_url() -> str:
    return get_secret("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2")


def get_data_url() -> str:
    return get_secret("ALPACA_DATA_URL", "https://data.alpaca.markets/v2")


# ── 路徑設定 ─────────────────────────────────────────────────────────────────
def get_reports_dir() -> str:
    """
    報告目錄（相對於專案根目錄），可被環境變數 REPORTS_BASE_DIR 覆蓋。
    Streamlit Cloud：報告由 GitHub Actions 提交到 repo，dashboard 讀取。
    """
    override = os.environ.get("REPORTS_BASE_DIR")
    if override:
        return override
    return os.path.join(_project_root(), "reports", "model")


def get_accounts_registry_path() -> str:
    return os.path.join(_project_root(), "accounts", "account_registry.json")


def get_settings_path() -> str:
    return os.path.join(_project_root(), "config", "settings.json")


# ── 儀表板設定 ───────────────────────────────────────────────────────────────
def get_refresh_interval_seconds() -> int:
    """自動刷新間隔（秒），來源：config/settings.json"""
    try:
        with open(get_settings_path(), encoding="utf-8") as f:
            settings = json.load(f)
        return int(settings.get("dashboard", {}).get("auto_refresh_seconds", 60))
    except Exception:
        return 60


def get_benchmark_symbols() -> list:
    """benchmark 比較指數（如 QQQ, SPY）"""
    try:
        with open(get_settings_path(), encoding="utf-8") as f:
            settings = json.load(f)
        return settings.get("market", {}).get("benchmark_symbols", ["QQQ", "SPY"])
    except Exception:
        return ["QQQ", "SPY"]
