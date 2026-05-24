"""
conftest.py — pytest 全域設定
設定測試用環境變數（從真實 Alpaca Paper 帳號）
"""
import os
import pytest

# ── 測試用 API 憑證（Paper Trading，不影響真實資金）──────────────────────
REAL_KEY    = "PKL6ZHN5BMJWRVHAQPC3N63PJI"
REAL_SECRET = "BmoeU1bH5HTJs6XJDaLCsUtZDqAH8q8SAmZPisPX9awg"
BAD_KEY     = "INVALID_KEY_XXXXXXXXXXXXXXXX"
BAD_SECRET  = "INVALID_SECRET_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

@pytest.fixture(autouse=True, scope="session")
def set_env_vars():
    """Session 級別：設定所有測試用環境變數"""
    os.environ["ALPACA_KEY_ACC001"]    = REAL_KEY
    os.environ["ALPACA_SECRET_ACC001"] = REAL_SECRET
    os.environ["ALPACA_KEY_ACC002"]    = BAD_KEY
    os.environ["ALPACA_SECRET_ACC002"] = BAD_SECRET
    yield
    # teardown：清除環境變數
    for key in ["ALPACA_KEY_ACC001", "ALPACA_SECRET_ACC001",
                "ALPACA_KEY_ACC002", "ALPACA_SECRET_ACC002"]:
        os.environ.pop(key, None)

@pytest.fixture(scope="session")
def real_client():
    """提供已驗證的 AlpacaClient（複用同一實例）"""
    from src.core.alpaca_client import AlpacaClient
    return AlpacaClient(
        api_key    = REAL_KEY,
        api_secret = REAL_SECRET,
        base_url   = "https://paper-api.alpaca.markets/v2",
    )

@pytest.fixture(scope="session")
def registry_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "accounts", "account_registry.json"
    )

@pytest.fixture(scope="session")
def account_manager(registry_path):
    from src.core.account_manager import AccountManager
    return AccountManager(registry_path=registry_path)
