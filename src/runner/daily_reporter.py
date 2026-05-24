"""
daily_reporter.py
每日報告產生腳本 — 由 GitHub Actions daily_report.yml 呼叫
流程：取得帳戶資料 → 產生 JSON 報告 → 儲存至 reports/ → 發送 Email
"""
import datetime
import logging
import os
import sys

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(_ROOT, "logs", f"report_{datetime.date.today()}.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("runner.daily_reporter")


def _load_nav_history(report_model, account_id: str) -> list:
    """
    從昨日報告載入 nav_history，找不到則回傳空 list。
    GitHub Actions 每日提交報告 JSON，讓歷史資料可累積。
    """
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    prev      = report_model.load(account_id, yesterday)
    if prev:
        history = list(prev.get("nav_history", []))
        # append yesterday's nav if not already last entry
        prev_nav = prev["summary"].get("nav", 0)
        if not history or history[-1]["date"] != yesterday:
            history.append({"date": yesterday, "nav": prev_nav})
        return history
    return []


def generate_for_account(
    account_id: str,
    client,
    config: dict,
    report_model,
    notifier=None,
    inception_nav: float = None,
    inception_date: str = None,
) -> str:
    """
    為單一帳戶產生並儲存今日 JSON 報告。
    回傳：報告 JSON 檔案路徑
    """
    strategy_id = config.get("active_strategy", "unknown")

    nav_history = _load_nav_history(report_model, account_id)

    # 若無起始資料，以今日 NAV 作為起始值
    account   = client.get_account()
    nav       = float(account.get("portfolio_value", 0))
    today     = datetime.date.today().isoformat()

    if inception_nav is None:
        inception_nav  = nav_history[0]["nav"] if nav_history else nav
    if inception_date is None:
        inception_date = nav_history[0]["date"] if nav_history else today

    # 將今日加入歷史（給 generate 用）
    full_history = nav_history + [{"date": today, "nav": nav}]

    report = report_model.generate(
        account_id     = account_id,
        strategy_id    = strategy_id,
        nav_history    = full_history,
        inception_nav  = inception_nav,
        inception_date = inception_date,
    )

    path = report_model.save(report, account_id)
    logger.info("[%s] 報告儲存完成：%s", account_id, path)

    if notifier:
        notifier.on_daily_report(report, config)

    return path


def run_all_reporters(
    account_manager,
    report_model_factory,
    notifier=None,
):
    """
    為所有啟用帳戶產生報告。
    單帳戶失敗只記錄 error，繼續處理其他帳戶。
    """
    results = {}
    logger.info("=== Daily Report 開始 (%s) ===", datetime.datetime.now().isoformat())

    for account_id, client, config in account_manager.iter_enabled_accounts():
        try:
            rm   = report_model_factory(client)
            path = generate_for_account(
                account_id, client, config, rm, notifier
            )
            results[account_id] = {"status": "success", "path": path}
        except Exception as exc:
            logger.error("[%s] 報告產生失敗：%s", account_id, exc, exc_info=True)
            results[account_id] = {"status": "failed", "error": str(exc)}

    logger.info("=== Daily Report 完成 ===")
    return results


def main():
    from src.dashboard.config import get_accounts_registry_path, get_reports_dir
    from src.core.account_manager import AccountManager
    from src.reports.report_model import ReportModel

    am = AccountManager(registry_path=get_accounts_registry_path())

    def rm_factory(client):
        return ReportModel(client=client, reports_dir=get_reports_dir())

    try:
        from src.dashboard.config import get_secret
        from src.reports.email_sender import EmailSender
        from src.notifications.notifier import Notifier
        sender   = EmailSender.from_config()
        notifier = Notifier(email_sender=sender)
    except Exception as e:
        logger.warning("Email 未設定，跳過通知：%s", e)
        notifier = None

    run_all_reporters(am, rm_factory, notifier)


if __name__ == "__main__":
    main()
