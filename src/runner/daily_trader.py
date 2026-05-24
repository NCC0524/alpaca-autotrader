"""
daily_trader.py
每日交易執行腳本 — 由 GitHub Actions daily_trading.yml 呼叫
設計原則：
  - 單帳戶執行失敗只記錄 error，其他帳戶繼續執行
  - API Key / Secret 絕不出現在任何 log 輸出中
  - 支援 dry_run=True 模式，不實際下單
  - 執行後輸出 Markdown Summary 至 $GITHUB_STEP_SUMMARY
"""
import argparse
import datetime
import logging
import os
import sys
import time
from typing import Callable, Dict, Optional

# ── 確保 project root 在 path ─────────────────────────────────────────────────
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.core.account_manager import AccountManager
from src.core.strategy_engine import StrategyEngine, StrategyNotFoundError
from src.trading.executor import TradeExecutor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(_ROOT, "logs", f"trade_{datetime.date.today()}.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("runner.daily_trader")


# ── 月份第一個交易日判斷 ──────────────────────────────────────────────────────
def is_first_trading_day_of_month(
    date: str = None,
    calendar: list = None,
) -> bool:
    """
    判斷 date 是否為當月第一個交易日。
    calendar : [{"date": "2026-05-01"}, ...] (由 AlpacaClient.get_calendar() 提供)
    """
    if date is None:
        date = datetime.date.today().isoformat()
    year_month = date[:7]
    month_days = sorted(
        e["date"] for e in (calendar or [])
        if e["date"].startswith(year_month)
    )
    return bool(month_days) and month_days[0] == date


# ── 單帳戶執行 ────────────────────────────────────────────────────────────────
def _run_single_account(
    account_id: str,
    client,
    config: dict,
    strategy_engine: StrategyEngine,
    executor_factory: Optional[Callable] = None,
    notifier=None,
    dry_run: bool = False,
) -> dict:
    """
    執行單一帳戶的交易策略。
    回傳 {"orders": {...}, "trades": [...], "nav": float}
    """
    strategy_id = config.get("active_strategy")
    if not strategy_id:
        logger.info("[%s] 未設定 active_strategy，跳過。", account_id)
        return {"orders": {"buy": [], "sell": []}, "trades": [], "nav": 0}

    account = client.get_account()
    nav     = float(account.get("portfolio_value", 0))

    strategy = strategy_engine.load(strategy_id)
    symbols  = strategy["universe"]["symbols"]
    prices   = client.get_latest_prices(symbols)

    positions_raw = client.get_positions()
    current = {
        p["symbol"]: int(float(p.get("qty", 0)))
        for p in positions_raw
    }

    targets = strategy_engine.calc_target_positions(strategy, nav, prices)
    orders  = strategy_engine.calc_rebalance_orders(targets, current)

    executor     = executor_factory(client) if executor_factory else TradeExecutor(client=client)
    trade_results = executor.execute(orders, dry_run=dry_run)

    if notifier:
        for t in trade_results:
            if t.get("status") in ("filled", "accepted", "dry_run"):
                notifier.on_trade_executed(t, config)

    logger.info(
        "[%s] NAV=$%.0f  買入=%d筆  賣出=%d筆  dry_run=%s",
        account_id, nav,
        len(orders.get("buy", [])),
        len(orders.get("sell", [])),
        dry_run,
    )
    return {"orders": orders, "trades": trade_results, "nav": nav}


# ── 主執行（所有帳戶）────────────────────────────────────────────────────────
def run_all_accounts(
    account_manager: AccountManager,
    strategy_engine: StrategyEngine,
    executor_factory: Optional[Callable] = None,
    notifier=None,
    dry_run: bool = False,
) -> Dict[str, dict]:
    """
    依序執行所有啟用帳戶。
    單帳戶失敗只記錄 error，其他帳戶繼續執行（不中斷整體流程）。

    回傳：
        {
          "ACC001": {"status": "success", "orders": {...}, "trades": [...], "nav": 107000},
          "ACC002": {"status": "failed",  "error":  "..."},
        }
    """
    results: Dict[str, dict] = {}
    start   = time.time()
    logger.info("=== Daily Trading 開始 (%s) ===", datetime.datetime.now().isoformat())

    for account_id, client, config in account_manager.iter_enabled_accounts():
        try:
            result = _run_single_account(
                account_id, client, config,
                strategy_engine, executor_factory, notifier, dry_run,
            )
            results[account_id] = {"status": "success", **result}
        except Exception as exc:
            logger.error("[%s] 執行失敗：%s", account_id, exc, exc_info=True)
            results[account_id] = {"status": "failed", "error": str(exc)}

    elapsed = time.time() - start
    logger.info("=== Daily Trading 完成  耗時 %.1fs ===", elapsed)
    return results


# ── GitHub Actions Summary ────────────────────────────────────────────────────
def build_summary_markdown(results: Dict[str, dict]) -> str:
    """
    產生 GitHub Actions Step Summary Markdown。
    每個帳戶的執行狀態一目了然。
    """
    lines = [
        "## 🏦 每日交易執行摘要",
        f"**執行時間**：{datetime.datetime.now().isoformat()[:19]}",
        "",
        "| 帳戶 | 狀態 | 買入 | 賣出 | NAV |",
        "| ---- | ---- | ---- | ---- | --- |",
    ]
    for acc_id, res in results.items():
        status = res["status"]
        if status == "success":
            orders = res.get("orders", {})
            buy    = len(orders.get("buy",  []))
            sell   = len(orders.get("sell", []))
            nav    = f"${res.get('nav', 0):,.0f}"
            icon   = "✅"
        elif status == "skipped":
            buy, sell, nav, icon = "—", "—", "—", "⏭️"
        else:
            buy  = "—"
            sell = "—"
            nav  = "—"
            icon = "❌"
        lines.append(f"| {acc_id} | {icon} {status} | {buy} | {sell} | {nav} |")

    if any(r["status"] == "failed" for r in results.values()):
        lines += ["", "⚠️ 部分帳戶執行失敗，請檢查 logs/。"]
    return "\n".join(lines)


def _write_step_summary(markdown: str) -> None:
    """寫入 GitHub Actions Step Summary（$GITHUB_STEP_SUMMARY 環境變數）"""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")


# ── CLI 入口 ──────────────────────────────────────────────────────────────────
def main(argv=None):
    parser = argparse.ArgumentParser(description="Alpaca 每日交易執行器")
    parser.add_argument("--dry-run",    action="store_true", help="不實際下單")
    parser.add_argument("--rebalance",  action="store_true", help="強制再平衡模式")
    args = parser.parse_args(argv)

    dry_run = args.dry_run or os.environ.get("DRY_RUN", "").lower() == "true"

    from src.dashboard.config import get_accounts_registry_path, _project_root
    am = AccountManager(registry_path=get_accounts_registry_path())
    se = StrategyEngine(strategies_dir=os.path.join(_project_root(), "strategies"))

    results  = run_all_accounts(am, se, dry_run=dry_run)
    summary  = build_summary_markdown(results)
    print(summary)
    _write_step_summary(summary)

    failed = [a for a, r in results.items() if r["status"] == "failed"]
    if failed:
        logger.error("失敗帳戶：%s", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
