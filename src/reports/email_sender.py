"""
email_sender.py
Email 發送層 — 支援 SMTP / Gmail
憑證從 config.py 讀取（st.secrets 優先，fallback 至 env var）
設計原則：
  - send() 成功回傳 True；位址全無效回傳 False；SMTP 故障拋 EmailError
  - 無效格式的收件人地址只記錄 warning 並跳過，不影響其他有效地址
  - 所有 HTML 模板包含固定風險提醒
"""
import json
import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Union

logger = logging.getLogger(__name__)

# RFC 5322 簡化版 Email 格式驗證
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

RISK_DISCLAIMER = (
    "⚠️ <b>風險提醒</b>：本通知所有內容（持倉、損益、分析）僅供資訊整理與研究參考，"
    "<b>不構成任何投資建議</b>。投資有風險，請自行評估後審慎決策。"
)


# ── 自訂例外 ──────────────────────────────────────────────────────────────────
class EmailError(Exception):
    """Email 發送相關錯誤（認證失敗、連線逾時等）"""


# ── 主類別 ────────────────────────────────────────────────────────────────────
class EmailSender:
    """
    SMTP Email 發送器（STARTTLS，port 587，相容 Gmail / SendGrid）。
    單一實例可反覆呼叫 send*() 系列方法。
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender_email: str,
        sender_password: str,
        timeout: int = 15,
    ):
        self.smtp_host       = smtp_host
        self.smtp_port       = smtp_port
        self.sender_email    = sender_email
        self.sender_password = sender_password
        self.timeout         = timeout

    # ── 工廠方法 ─────────────────────────────────────────────────────────────
    @classmethod
    def from_config(cls) -> "EmailSender":
        """
        從 config.py 自動建立 EmailSender（雲端 & 本地均適用）。
        必要 secret：EMAIL_SENDER, EMAIL_PASSWORD
        """
        from src.dashboard.config import get_secret, get_settings_path
        try:
            with open(get_settings_path(), encoding="utf-8") as f:
                cfg = json.load(f).get("email", {})
            smtp_host = cfg.get("smtp_host", "smtp.gmail.com")
            smtp_port = int(cfg.get("smtp_port", 587))
        except Exception:
            smtp_host, smtp_port = "smtp.gmail.com", 587

        sender   = get_secret("EMAIL_SENDER", "")
        password = get_secret("EMAIL_PASSWORD", "")
        if not sender or not password:
            raise EmailError(
                "找不到 EMAIL_SENDER / EMAIL_PASSWORD。"
                "請在 .streamlit/secrets.toml 或環境變數中設定。"
            )
        return cls(smtp_host=smtp_host, smtp_port=smtp_port,
                   sender_email=sender, sender_password=password)

    # ── 工具方法 ─────────────────────────────────────────────────────────────
    @staticmethod
    def is_valid_email(address: str) -> bool:
        """回傳 True 表示格式合法的 Email 地址"""
        return bool(_EMAIL_RE.match(address.strip()))

    # ── 核心發送 ─────────────────────────────────────────────────────────────
    def send(
        self,
        to: Union[str, List[str]],
        subject: str,
        html_body: str,
    ) -> bool:
        """
        發送 HTML Email。

        - 無效格式地址：記錄 warning，跳過
        - 所有地址均無效：回傳 False（不拋例外）
        - SMTP 連線 / 認證失敗：拋 EmailError（由 Notifier 捕捉）
        """
        recipients = [to] if isinstance(to, str) else list(to)
        valid   = [r for r in recipients if self.is_valid_email(r)]
        invalid = [r for r in recipients if not self.is_valid_email(r)]

        for addr in invalid:
            logger.warning("收件人格式錯誤，跳過：%r", addr)

        if not valid:
            logger.error("無有效收件人，Email 未發送（主旨：%s）", subject)
            return False

        msg              = MIMEMultipart("alternative")
        msg["From"]      = self.sender_email
        msg["To"]        = ", ".join(valid)
        msg["Subject"]   = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port,
                              timeout=self.timeout) as server:
                server.ehlo()
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, valid, msg.as_string())
            logger.info("Email 已發送 → %s  主旨：%s", valid, subject)
            return True
        except smtplib.SMTPAuthenticationError as e:
            raise EmailError(f"SMTP 認證失敗：{e}") from e
        except Exception as e:
            raise EmailError(f"Email 發送失敗（{type(e).__name__}）：{e}") from e

    # ── 模板方法 ─────────────────────────────────────────────────────────────
    def send_daily_report(self, report: dict, to: Union[str, List[str]]) -> bool:
        """
        發送每日報告 Email。
        HTML 內容由 ReportView.render_html() 產生，確保格式一致。
        """
        from src.reports.report_view import ReportView
        html = ReportView().render_html(report)

        s   = report.get("summary", {})
        nav = s.get("nav", 0)
        pnl = s.get("daily_pnl", 0)
        subject = (
            f"【帳戶日報】{report.get('report_date', '')} | "
            f"NAV ${nav:,.0f} | "
            f"今日損益 {'+' if pnl >= 0 else ''}${pnl:,.0f}"
        )
        return self.send(to, subject, html)

    def send_trade_notification(
        self,
        trade: dict,
        to: Union[str, List[str]],
    ) -> bool:
        """發送單筆交易執行通知（下單後立即呼叫）"""
        html    = self._build_trade_html(trade)
        sym     = trade.get("symbol", "—")
        side    = trade.get("side", "").upper()
        qty     = int(trade.get("qty", 0))
        subject = f"【交易通知】{sym} {side} {qty} 股"
        return self.send(to, subject, html)

    def send_rebalance_notification(
        self,
        orders: dict,
        account_id: str,
        to: Union[str, List[str]],
    ) -> bool:
        """發送再平衡通知，包含完整買賣明細"""
        html       = self._build_rebalance_html(orders, account_id)
        buy_count  = len(orders.get("buy",  []))
        sell_count = len(orders.get("sell", []))
        subject    = (
            f"【再平衡通知】{account_id} — "
            f"賣出 {sell_count} 筆，買入 {buy_count} 筆"
        )
        return self.send(to, subject, html)

    # ── HTML 建構 ─────────────────────────────────────────────────────────────
    @staticmethod
    def _build_trade_html(trade: dict) -> str:
        sym    = trade.get("symbol", "—")
        side   = trade.get("side", "").upper()
        qty    = int(trade.get("qty", 0))
        price  = trade.get("price", 0) or 0
        status = trade.get("status", "—")
        color  = "#059669" if side == "BUY" else "#dc2626"

        return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head><meta charset="UTF-8">
<title>交易通知</title></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;color:#333;padding:24px;max-width:480px;">
  <h2 style="color:#1a56db;margin-bottom:4px;">📈 交易執行通知</h2>
  <table style="border-collapse:collapse;width:100%;margin-bottom:20px;">
    <tr><td style="padding:8px 12px;border:1px solid #e5e7eb;color:#6b7280;">股票</td>
        <td style="padding:8px 12px;border:1px solid #e5e7eb;font-weight:700;">{sym}</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #e5e7eb;color:#6b7280;">方向</td>
        <td style="padding:8px 12px;border:1px solid #e5e7eb;color:{color};font-weight:700;">{side}</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #e5e7eb;color:#6b7280;">股數</td>
        <td style="padding:8px 12px;border:1px solid #e5e7eb;">{qty} 股</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #e5e7eb;color:#6b7280;">成交價</td>
        <td style="padding:8px 12px;border:1px solid #e5e7eb;">${float(price):,.2f}</td></tr>
    <tr><td style="padding:8px 12px;border:1px solid #e5e7eb;color:#6b7280;">狀態</td>
        <td style="padding:8px 12px;border:1px solid #e5e7eb;">{status}</td></tr>
  </table>
  <div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:8px;
              padding:12px 16px;font-size:13px;color:#92400e;">
    {RISK_DISCLAIMER}
  </div>
</body></html>"""

    @staticmethod
    def _build_rebalance_html(orders: dict, account_id: str) -> str:
        sells = orders.get("sell", [])
        buys  = orders.get("buy",  [])

        def _rows(items, color):
            if not items:
                return '<tr><td colspan="2" style="padding:8px;color:#9ca3af;font-style:italic;">（無）</td></tr>'
            return "".join(
                f'<tr>'
                f'<td style="padding:7px 12px;border:1px solid #e5e7eb;font-weight:700;">{sym}</td>'
                f'<td style="padding:7px 12px;border:1px solid #e5e7eb;color:{color};">{qty} 股</td>'
                f'</tr>'
                for sym, qty in items
            )

        return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head><meta charset="UTF-8">
<title>再平衡通知</title></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;color:#333;padding:24px;max-width:560px;">
  <h2 style="color:#1a56db;margin-bottom:4px;">⚖️ 再平衡通知 — {account_id}</h2>
  <h3 style="color:#dc2626;margin-bottom:6px;">賣出（{len(sells)} 筆）</h3>
  <table style="border-collapse:collapse;width:100%;margin-bottom:20px;">
    {_rows(sells, "#dc2626")}
  </table>
  <h3 style="color:#059669;margin-bottom:6px;">買入（{len(buys)} 筆）</h3>
  <table style="border-collapse:collapse;width:100%;">
    {_rows(buys, "#059669")}
  </table>
  <div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:8px;
              padding:12px 16px;font-size:13px;color:#92400e;margin-top:24px;">
    {RISK_DISCLAIMER}
  </div>
</body></html>"""
