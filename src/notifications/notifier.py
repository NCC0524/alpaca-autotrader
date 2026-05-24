"""
notifier.py
通知分發器 — 將系統事件路由到各通知渠道（目前支援 Email）
設計原則：
  - 任何通知失敗只記錄 error log，絕不拋出例外（不中斷主交易流程）
  - 帳戶未設定 Email 則靜默跳過
  - 帳戶 Email 格式錯誤則記錄 warning，繼續處理其他帳戶
"""
import logging
from typing import Optional

from src.reports.email_sender import EmailSender, EmailError

logger = logging.getLogger(__name__)


class Notifier:
    """
    統一通知入口。
    所有 on_* 方法均保證不拋出例外。
    """

    def __init__(self, email_sender: Optional[EmailSender] = None):
        self.email_sender = email_sender

    # ── 每日報告 ─────────────────────────────────────────────────────────────
    def on_daily_report(self, report: dict, account_config: dict) -> None:
        """
        每日報告產生後呼叫此方法。
        帳戶設定中 email 欄位決定收件人。
        """
        if not self.email_sender:
            return
        to          = account_config.get("email", "")
        account_id  = account_config.get("account_id", "UNKNOWN")
        if not to:
            logger.warning("帳戶 %s 未設定 email，跳過日報通知。", account_id)
            return
        try:
            self.email_sender.send_daily_report(report, to)
        except EmailError as e:
            logger.error("日報 Email 發送失敗（%s）：%s", account_id, e)
        except Exception as e:
            logger.error("日報 Email 未知錯誤（%s）：%s", account_id, e)

    # ── 交易通知 ─────────────────────────────────────────────────────────────
    def on_trade_executed(self, trade: dict, account_config: dict) -> None:
        """
        下單成功後立即呼叫此方法。
        通知延遲 = SMTP 連線時間（max timeout=15s），遠低於 30 秒 SLA。
        """
        if not self.email_sender:
            return
        to         = account_config.get("email", "")
        account_id = account_config.get("account_id", "UNKNOWN")
        if not to:
            return
        try:
            self.email_sender.send_trade_notification(trade, to)
        except EmailError as e:
            logger.error("交易通知 Email 失敗（%s）：%s", account_id, e)
        except Exception as e:
            logger.error("交易通知未知錯誤（%s）：%s", account_id, e)

    # ── 再平衡通知 ───────────────────────────────────────────────────────────
    def on_rebalance_complete(self, orders: dict, account_config: dict) -> None:
        """再平衡完成後呼叫，Email 包含完整買賣明細"""
        if not self.email_sender:
            return
        to         = account_config.get("email", "")
        account_id = account_config.get("account_id", "UNKNOWN")
        if not to:
            return
        try:
            self.email_sender.send_rebalance_notification(orders, account_id, to)
        except EmailError as e:
            logger.error("再平衡 Email 失敗（%s）：%s", account_id, e)
        except Exception as e:
            logger.error("再平衡通知未知錯誤（%s）：%s", account_id, e)
