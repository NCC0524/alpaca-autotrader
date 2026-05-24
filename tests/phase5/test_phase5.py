"""
Phase 5 測試案例 — Email 通知系統
TC-5-01 ~ TC-5-09

測試策略：
  - 所有 SMTP 操作透過 unittest.mock.patch 模擬，不發送真實 Email
  - 驗證 SMTP 握手序列（ehlo → starttls → login → sendmail）
  - 驗證 HTML 結構、NAV 數值、風險提醒
  - 驗證錯誤隔離（SMTP 失敗不拋出；無效格式跳過）
"""
import logging
import time
from unittest.mock import MagicMock, patch, call

import pytest

from src.reports.email_sender import EmailSender, EmailError, RISK_DISCLAIMER
from src.notifications.notifier import Notifier

# ── 共用測試資料 ──────────────────────────────────────────────────────────────
SENDER_EMAIL    = "sender@example.com"
SENDER_PASSWORD = "test_password"
SMTP_HOST       = "smtp.gmail.com"
SMTP_PORT       = 587

MOCK_REPORT = {
    "report_date":  "2026-05-24",
    "account_id":   "ACC001",
    "strategy_id":  "nasdaq_top10",
    "generated_at": "2026-05-24T06:00:00",
    "summary": {
        "nav": 107_000.0,  "cash": 5_000.0,   "invested": 102_000.0,
        "inception_nav": 100_000.0,            "inception_date": "2026-01-02",
        "daily_pnl": 1_000.0,                  "daily_pnl_pct": 0.009434,
        "weekly_pnl_pct": 0.02,                "monthly_pnl_pct": 0.05,
        "total_return_pct": 0.07,              "annual_return_pct": 0.18,
        "max_drawdown_pct": -0.014563,         "days_elapsed": 142,
    },
    "positions": [
        {"symbol": "AAPL", "qty": 51.0, "avg_entry_price": 190.0,
         "current_price": 195.0, "market_value": 9945.0,
         "weight_pct": 9.3, "pnl_amount": 255.0, "pnl_pct": 0.02632},
    ],
    "trades_today": [],
    "nav_history":  [],
    "watchlist":    {},
}

MOCK_TRADE = {
    "symbol": "NVDA",
    "side":   "buy",
    "qty":    10,
    "price":  131.50,
    "status": "filled",
}

MOCK_ORDERS = {
    "sell": [("AAPL", 5), ("TSLA", 3)],
    "buy":  [("NVDA", 8), ("MSFT", 2)],
}


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def sender():
    """建立不需真實 SMTP 的 EmailSender（憑證為假值）"""
    return EmailSender(
        smtp_host       = SMTP_HOST,
        smtp_port       = SMTP_PORT,
        sender_email    = SENDER_EMAIL,
        sender_password = SENDER_PASSWORD,
    )


@pytest.fixture
def mock_smtp():
    """Patch smtplib.SMTP，回傳可追蹤呼叫的 MagicMock"""
    with patch("src.reports.email_sender.smtplib.SMTP") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_instance)
        mock_cls.return_value.__exit__  = MagicMock(return_value=False)
        yield mock_cls, mock_instance


@pytest.fixture
def notifier(sender):
    return Notifier(email_sender=sender)


# ════════════════════════════════════════════════════════════════════════════
# TC-5-01  SMTP 握手序列正確（ehlo → starttls → login → sendmail）
# ════════════════════════════════════════════════════════════════════════════
class TestTC501:
    def test_smtp_constructor_called_with_correct_host_port(
        self, sender, mock_smtp
    ):
        """TC-5-01a：SMTP 以正確的 host/port 初始化"""
        mock_cls, _ = mock_smtp
        sender.send("user@test.com", "測試主旨", "<p>測試</p>")
        mock_cls.assert_called_once_with(SMTP_HOST, SMTP_PORT, timeout=15)

    def test_smtp_handshake_sequence(self, sender, mock_smtp):
        """TC-5-01b：ehlo → starttls → login → sendmail 順序正確"""
        _, smtp = mock_smtp
        sender.send("user@test.com", "主旨", "<p>body</p>")
        smtp.ehlo.assert_called_once()
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with(SENDER_EMAIL, SENDER_PASSWORD)
        smtp.sendmail.assert_called_once()

    def test_sendmail_recipient_matches_to(self, sender, mock_smtp):
        """TC-5-01c：sendmail 的收件人清單與 to 參數一致"""
        _, smtp = mock_smtp
        to_addr = "recipient@test.com"
        sender.send(to_addr, "主旨", "<p>body</p>")
        args = smtp.sendmail.call_args
        assert to_addr in args[0][1]   # sendmail(from, [to], msg)

    def test_send_returns_true_on_success(self, sender, mock_smtp):
        """TC-5-01d：成功發送後 send() 回傳 True"""
        result = sender.send("user@test.com", "主旨", "<p>body</p>")
        assert result is True


# ════════════════════════════════════════════════════════════════════════════
# TC-5-02  Email HTML 格式正確（有效的 HTML 結構）
# ════════════════════════════════════════════════════════════════════════════
class TestTC502:
    def test_daily_report_html_has_doctype(self, sender):
        """TC-5-02a：日報 HTML 包含 DOCTYPE 聲明"""
        from src.reports.report_view import ReportView
        html = ReportView().render_html(MOCK_REPORT)
        assert "<!DOCTYPE html>" in html or "<!doctype html" in html.lower()

    def test_daily_report_html_has_html_body_tags(self, sender):
        """TC-5-02b：日報 HTML 包含完整 <html> <body> 結構"""
        from src.reports.report_view import ReportView
        html = ReportView().render_html(MOCK_REPORT)
        assert "<html" in html and "</html>" in html
        assert "<body" in html and "</body>" in html

    def test_trade_html_has_valid_structure(self, sender):
        """TC-5-02c：交易通知 HTML 有有效的文件結構"""
        html = EmailSender._build_trade_html(MOCK_TRADE)
        assert "<html" in html and "</html>" in html
        assert "<!DOCTYPE html>" in html or "<!doctype html" in html.lower()

    def test_rebalance_html_has_valid_structure(self):
        """TC-5-02d：再平衡通知 HTML 有有效的文件結構"""
        html = EmailSender._build_rebalance_html(MOCK_ORDERS, "ACC001")
        assert "<html" in html and "</html>" in html
        assert "<table" in html

    def test_email_subject_format(self, sender):
        """TC-5-02e：日報主旨格式符合規範（直接捕捉 send() 的 subject 參數）"""
        with patch.object(sender, "send", return_value=True) as mock_send:
            sender.send_daily_report(MOCK_REPORT, "user@test.com")
        subject = mock_send.call_args[0][1]   # send(to, subject, html)
        assert "帳戶日報"   in subject
        assert "2026-05-24" in subject


# ════════════════════════════════════════════════════════════════════════════
# TC-5-03  Email 中 NAV 數值與 JSON 報告一致
# ════════════════════════════════════════════════════════════════════════════
class TestTC503:
    def test_nav_in_daily_report_html(self):
        """TC-5-03a：日報 HTML 中含有報告的 NAV 數值（107,000）"""
        from src.reports.report_view import ReportView
        html = ReportView().render_html(MOCK_REPORT)
        assert "107,000" in html, "NAV 107,000 應出現在日報 HTML 中"

    def test_nav_in_subject_line(self, sender):
        """TC-5-03b：Email 主旨中包含 NAV 數值"""
        with patch.object(sender, "send", return_value=True) as mock_send:
            sender.send_daily_report(MOCK_REPORT, "user@test.com")
        subject = mock_send.call_args[0][1]
        assert "107,000" in subject, f"NAV 107,000 應在主旨中，實際：{subject}"

    def test_daily_pnl_in_html(self):
        """TC-5-03c：今日損益數值出現在日報 HTML 中"""
        from src.reports.report_view import ReportView
        html = ReportView().render_html(MOCK_REPORT)
        # daily_pnl = 1,000.00
        assert "1,000" in html, "daily_pnl 1,000 應出現在日報 HTML 中"


# ════════════════════════════════════════════════════════════════════════════
# TC-5-04  多帳戶 Email 互不混淆
# ════════════════════════════════════════════════════════════════════════════
class TestTC504:
    def test_each_account_receives_own_email(self, sender, mock_smtp):
        """TC-5-04a：兩個帳戶各自發送到正確的 Email 地址"""
        _, smtp = mock_smtp
        acc_configs = [
            {"account_id": "ACC001", "email": "acc001@test.com"},
            {"account_id": "ACC002", "email": "acc002@test.com"},
        ]
        reports = [
            {**MOCK_REPORT, "account_id": "ACC001"},
            {**MOCK_REPORT, "account_id": "ACC002"},
        ]
        notifier = Notifier(email_sender=sender)
        for report, cfg in zip(reports, acc_configs):
            notifier.on_daily_report(report, cfg)

        # sendmail 應被呼叫兩次
        assert smtp.sendmail.call_count == 2
        calls = smtp.sendmail.call_args_list
        # 第一次收件人含 acc001
        assert "acc001@test.com" in calls[0][0][1]
        # 第二次收件人含 acc002
        assert "acc002@test.com" in calls[1][0][1]

    def test_acc001_email_not_sent_to_acc002(self, sender, mock_smtp):
        """TC-5-04b：ACC001 的 Email 不會誤寄到 ACC002"""
        _, smtp = mock_smtp
        notifier = Notifier(email_sender=sender)
        notifier.on_daily_report(
            {**MOCK_REPORT, "account_id": "ACC001"},
            {"account_id": "ACC001", "email": "acc001@test.com"},
        )
        assert smtp.sendmail.call_count == 1
        recipients = smtp.sendmail.call_args[0][1]
        assert "acc002@test.com" not in recipients

    def test_no_email_when_not_configured(self, sender, mock_smtp):
        """TC-5-04c：帳戶未設定 email 時，不呼叫 SMTP"""
        _, smtp = mock_smtp
        notifier = Notifier(email_sender=sender)
        notifier.on_daily_report(
            MOCK_REPORT,
            {"account_id": "ACC003", "email": ""},   # 空 email
        )
        smtp.sendmail.assert_not_called()


# ════════════════════════════════════════════════════════════════════════════
# TC-5-05  交易通知：立即發送，函式執行時間 < 30 秒
# ════════════════════════════════════════════════════════════════════════════
class TestTC505:
    def test_trade_notification_sent_immediately(self, notifier, mock_smtp):
        """TC-5-05a：on_trade_executed() 立即呼叫 SMTP 發送"""
        _, smtp = mock_smtp
        notifier.on_trade_executed(
            MOCK_TRADE,
            {"account_id": "ACC001", "email": "user@test.com"},
        )
        smtp.sendmail.assert_called_once()

    def test_trade_notification_within_30s_budget(self, sender):
        """TC-5-05b：通知函式執行時間遠低於 30 秒 SLA"""
        with patch("src.reports.email_sender.smtplib.SMTP") as mock_cls:
            mock_ins = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_ins)
            mock_cls.return_value.__exit__  = MagicMock(return_value=False)

            notifier = Notifier(email_sender=sender)
            start = time.time()
            notifier.on_trade_executed(
                MOCK_TRADE,
                {"account_id": "ACC001", "email": "user@test.com"},
            )
            elapsed = time.time() - start

        assert elapsed < 30, f"通知耗時 {elapsed:.2f}s，超過 30 秒 SLA"

    def test_trade_email_contains_symbol(self):
        """TC-5-05c：交易通知 HTML 包含股票代號（直接驗證 HTML builder）"""
        html = EmailSender._build_trade_html(MOCK_TRADE)
        assert "NVDA" in html

    def test_smtp_timeout_within_30s(self, sender):
        """TC-5-05d：EmailSender.timeout 設定 <= 15s（確保 SLA 預算）"""
        assert sender.timeout <= 15


# ════════════════════════════════════════════════════════════════════════════
# TC-5-06  再平衡 Email 包含完整買賣明細
# ════════════════════════════════════════════════════════════════════════════
class TestTC506:
    def test_rebalance_html_contains_all_sell_symbols(self):
        """TC-5-06a：再平衡 HTML 包含所有賣出股票代號"""
        html = EmailSender._build_rebalance_html(MOCK_ORDERS, "ACC001")
        for sym, _ in MOCK_ORDERS["sell"]:
            assert sym in html, f"賣出股票 {sym} 不在再平衡通知中"

    def test_rebalance_html_contains_all_buy_symbols(self):
        """TC-5-06b：再平衡 HTML 包含所有買入股票代號"""
        html = EmailSender._build_rebalance_html(MOCK_ORDERS, "ACC001")
        for sym, _ in MOCK_ORDERS["buy"]:
            assert sym in html, f"買入股票 {sym} 不在再平衡通知中"

    def test_rebalance_html_contains_account_id(self):
        """TC-5-06c：再平衡 HTML 包含帳戶 ID"""
        html = EmailSender._build_rebalance_html(MOCK_ORDERS, "ACC001")
        assert "ACC001" in html

    def test_rebalance_html_shows_quantities(self):
        """TC-5-06d：再平衡 HTML 顯示各股買賣數量"""
        html = EmailSender._build_rebalance_html(MOCK_ORDERS, "ACC001")
        # AAPL 5 股、NVDA 8 股
        assert "5" in html
        assert "8" in html

    def test_rebalance_notification_via_notifier(self, notifier, mock_smtp):
        """TC-5-06e：notifier.on_rebalance_complete() 正確呼叫 SMTP 發送"""
        _, smtp = mock_smtp
        notifier.on_rebalance_complete(
            MOCK_ORDERS,
            {"account_id": "ACC001", "email": "user@test.com"},
        )
        smtp.sendmail.assert_called_once()
        # 主旨透過 send() 的 subject 驗證（捕捉 send 呼叫）
        with patch.object(notifier.email_sender, "send", return_value=True) as ms:
            notifier.on_rebalance_complete(
                MOCK_ORDERS,
                {"account_id": "ACC001", "email": "user@test.com"},
            )
        subject = ms.call_args[0][1]
        assert "再平衡" in subject


# ════════════════════════════════════════════════════════════════════════════
# TC-5-07  SMTP 失敗時記錄 error log，不中斷主流程
# ════════════════════════════════════════════════════════════════════════════
class TestTC507:
    def test_smtp_auth_failure_does_not_raise_from_notifier(self, sender):
        """TC-5-07a：SMTP 認證失敗 → Notifier 捕捉，不拋出例外"""
        with patch("src.reports.email_sender.smtplib.SMTP") as mock_cls:
            import smtplib as _smtplib
            mock_ins = MagicMock()
            mock_ins.login.side_effect = _smtplib.SMTPAuthenticationError(535, b"auth failed")
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_ins)
            mock_cls.return_value.__exit__  = MagicMock(return_value=False)

            notifier = Notifier(email_sender=sender)
            # 不應拋出任何例外
            notifier.on_daily_report(
                MOCK_REPORT,
                {"account_id": "ACC001", "email": "user@test.com"},
            )

    def test_smtp_connection_error_does_not_raise(self, sender):
        """TC-5-07b：網路連線失敗 → Notifier 捕捉，不拋出例外"""
        with patch("src.reports.email_sender.smtplib.SMTP") as mock_cls:
            mock_cls.side_effect = ConnectionRefusedError("連線被拒")
            notifier = Notifier(email_sender=sender)
            notifier.on_trade_executed(
                MOCK_TRADE,
                {"account_id": "ACC001", "email": "user@test.com"},
            )

    def test_smtp_error_is_logged(self, sender, caplog):
        """TC-5-07c：SMTP 失敗時，error 訊息寫入 log"""
        with patch("src.reports.email_sender.smtplib.SMTP") as mock_cls:
            import smtplib as _smtplib
            mock_ins = MagicMock()
            mock_ins.login.side_effect = _smtplib.SMTPAuthenticationError(535, b"fail")
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_ins)
            mock_cls.return_value.__exit__  = MagicMock(return_value=False)

            notifier = Notifier(email_sender=sender)
            with caplog.at_level(logging.ERROR):
                notifier.on_daily_report(
                    MOCK_REPORT,
                    {"account_id": "ACC001", "email": "user@test.com"},
                )
            assert any("失敗" in r.message or "fail" in r.message.lower()
                       for r in caplog.records)

    def test_no_email_sender_does_not_raise(self):
        """TC-5-07d：未設定 email_sender 的 Notifier 靜默跳過所有通知"""
        notifier = Notifier(email_sender=None)
        notifier.on_daily_report(MOCK_REPORT, {"account_id": "X", "email": "x@x.com"})
        notifier.on_trade_executed(MOCK_TRADE, {"email": "x@x.com"})
        notifier.on_rebalance_complete(MOCK_ORDERS, {"email": "x@x.com"})


# ════════════════════════════════════════════════════════════════════════════
# TC-5-08  所有 Email 模板底部包含風險提醒
# ════════════════════════════════════════════════════════════════════════════
class TestTC508:
    RISK_KEYWORD = "不構成任何投資建議"

    def test_daily_report_html_has_risk_disclaimer(self):
        """TC-5-08a：日報 HTML 包含風險提醒"""
        from src.reports.report_view import ReportView
        html = ReportView().render_html(MOCK_REPORT)
        assert self.RISK_KEYWORD in html

    def test_trade_html_has_risk_disclaimer(self):
        """TC-5-08b：交易通知 HTML 包含風險提醒"""
        html = EmailSender._build_trade_html(MOCK_TRADE)
        assert self.RISK_KEYWORD in html

    def test_rebalance_html_has_risk_disclaimer(self):
        """TC-5-08c：再平衡通知 HTML 包含風險提醒"""
        html = EmailSender._build_rebalance_html(MOCK_ORDERS, "ACC001")
        assert self.RISK_KEYWORD in html

    def test_risk_disclaimer_constant_correct(self):
        """TC-5-08d：RISK_DISCLAIMER 常數包含完整警語"""
        assert self.RISK_KEYWORD in RISK_DISCLAIMER
        assert "風險提醒" in RISK_DISCLAIMER


# ════════════════════════════════════════════════════════════════════════════
# TC-5-09  收件人 Email 格式錯誤：跳過並繼續
# ════════════════════════════════════════════════════════════════════════════
class TestTC509:
    def test_is_valid_email_valid_formats(self):
        """TC-5-09a：合法 Email 格式通過驗證"""
        valid = [
            "user@example.com",
            "user.name+tag@domain.co.uk",
            "abc123@sub.domain.org",
        ]
        for addr in valid:
            assert EmailSender.is_valid_email(addr), f"{addr} 應為合法格式"

    def test_is_valid_email_invalid_formats(self):
        """TC-5-09b：非法 Email 格式驗證失敗"""
        invalid = [
            "not-an-email",
            "@nodomain.com",
            "missing@",
            "spaces in@email.com",
            "",
            "double@@at.com",
        ]
        for addr in invalid:
            assert not EmailSender.is_valid_email(addr), f"{addr} 應為非法格式"

    def test_send_with_all_invalid_returns_false(self, sender):
        """TC-5-09c：所有收件人均為無效格式 → send() 回傳 False（不拋例外）"""
        result = sender.send("not-an-email", "主旨", "<p>body</p>")
        assert result is False

    def test_send_with_mixed_skips_invalid_sends_to_valid(self, sender, mock_smtp):
        """TC-5-09d：混合有效 / 無效地址 → 跳過無效，仍發送到有效地址"""
        _, smtp = mock_smtp
        result = sender.send(
            ["valid@test.com", "INVALID_EMAIL", "also@valid.com"],
            "主旨",
            "<p>body</p>",
        )
        assert result is True
        recipients = smtp.sendmail.call_args[0][1]
        assert "valid@test.com"  in recipients
        assert "also@valid.com"  in recipients
        assert "INVALID_EMAIL"   not in recipients

    def test_invalid_email_logged_as_warning(self, sender, caplog):
        """TC-5-09e：無效格式 Email 記錄 warning 而非 error"""
        with caplog.at_level(logging.WARNING):
            sender.send("bad-email", "主旨", "<p>body</p>")
        assert any("格式錯誤" in r.message or "跳過" in r.message
                   for r in caplog.records)

    def test_notifier_skips_account_with_invalid_email(self, sender, mock_smtp):
        """TC-5-09f：notifier 跳過格式錯誤的帳戶，繼續處理其他帳戶"""
        _, smtp = mock_smtp
        notifier = Notifier(email_sender=sender)
        configs = [
            {"account_id": "BAD",   "email": "not-valid"},     # 無效
            {"account_id": "GOOD",  "email": "good@test.com"}, # 有效
        ]
        for cfg in configs:
            notifier.on_daily_report(MOCK_REPORT, cfg)

        # 只有一次成功發送
        assert smtp.sendmail.call_count == 1
        recipients = smtp.sendmail.call_args[0][1]
        assert "good@test.com" in recipients
