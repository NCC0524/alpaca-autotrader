"""
report_view.py
報告顯示層（View） — 將 JSON 報告 Model 渲染為 HTML
與 Model 完全分離：修改 HTML 模板不影響資料層
"""
import os
import datetime


class ReportView:
    """將 report_model.py 產生的 JSON 渲染成 HTML"""

    VIEW_DIR = "reports/views"

    def render_html(self, report: dict) -> str:
        """將報告 dict 渲染為完整 HTML 字串"""
        s = report.get("summary", {})
        positions = report.get("positions", [])
        trades    = report.get("trades_today", [])

        def pct(v): return f"{v*100:+.2f}%"
        def usd(v): return f"${v:,.2f}"
        def cls(v): return "pos" if v >= 0 else "neg"

        # ── 持倉列 ────────────────────────────────────────────────────
        pos_rows = ""
        for p in positions:
            c = cls(p["pnl_amount"])
            pos_rows += f"""
            <tr>
              <td><b>{p['symbol']}</b></td>
              <td>{usd(p['current_price'])}</td>
              <td>{usd(p['avg_entry_price'])}</td>
              <td>{int(p['qty'])}</td>
              <td>{usd(p['market_value'])}</td>
              <td>{p['weight_pct']:.1f}%</td>
              <td class="{c}">{pct(p['pnl_pct'])}</td>
              <td class="{c}">{usd(p['pnl_amount'])}</td>
            </tr>"""

        # ── 交易紀錄列 ────────────────────────────────────────────────
        trade_rows = ""
        for t in trades:
            sc = "buy-tag" if t["side"] == "buy" else "sell-tag"
            trade_rows += f"""
            <tr>
              <td>{t['time']}</td>
              <td><b>{t['symbol']}</b></td>
              <td><span class="{sc}">{t['side'].upper()}</span></td>
              <td>{int(t['qty'])}</td>
              <td>{usd(t['price']) if t['price'] else '—'}</td>
              <td>{t['status']}</td>
            </tr>"""

        if not trade_rows:
            trade_rows = '<tr><td colspan="6" style="color:#888;text-align:center">今日無交易</td></tr>'

        daily_cls   = cls(s.get("daily_pnl", 0))
        total_cls   = cls(s.get("total_return_pct", 0))
        annual_cls  = cls(s.get("annual_return_pct", 0))

        html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>每日報告 {report['report_date']} — {report['account_id']}</title>
<style>
  body  {{ font-family:'Segoe UI',Arial,sans-serif; background:#f5f7fa; color:#333; margin:0; padding:1.5rem; }}
  h1   {{ font-size:1.4rem; color:#1a56db; margin-bottom:0.3rem; }}
  .sub {{ color:#6b7280; font-size:0.82rem; margin-bottom:1.5rem; }}
  .cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:1rem; margin-bottom:1.5rem; }}
  .card {{ background:#fff; border-radius:10px; padding:1rem 1.2rem; box-shadow:0 1px 4px rgba(0,0,0,.08); }}
  .card .label {{ font-size:0.72rem; color:#6b7280; text-transform:uppercase; letter-spacing:.05em; margin-bottom:.3rem; }}
  .card .value {{ font-size:1.6rem; font-weight:700; }}
  .card .hint  {{ font-size:0.73rem; color:#9ca3af; margin-top:.2rem; }}
  .pos {{ color:#059669; }} .neg {{ color:#dc2626; }}
  .section {{ background:#fff; border-radius:10px; padding:1.2rem; box-shadow:0 1px 4px rgba(0,0,0,.08); margin-bottom:1.2rem; }}
  .section h2 {{ font-size:0.95rem; margin-bottom:.8rem; color:#374151; border-bottom:1px solid #e5e7eb; padding-bottom:.4rem; }}
  table {{ width:100%; border-collapse:collapse; font-size:.82rem; }}
  th {{ background:#f9fafb; padding:7px 10px; text-align:right; color:#6b7280; font-weight:600; font-size:.72rem; }}
  th:first-child {{ text-align:left; }}
  td {{ padding:7px 10px; border-bottom:1px solid #f3f4f6; text-align:right; }}
  td:first-child {{ text-align:left; }}
  .buy-tag  {{ background:#d1fae5; color:#059669; padding:2px 8px; border-radius:999px; font-size:.7rem; font-weight:700; }}
  .sell-tag {{ background:#fee2e2; color:#dc2626; padding:2px 8px; border-radius:999px; font-size:.7rem; font-weight:700; }}
  .risk {{ background:#fef3c7; border:1px solid #fbbf24; border-radius:8px; padding:.8rem 1rem; font-size:.78rem; color:#92400e; margin-top:1.5rem; }}
  @media(max-width:700px){{ .cards{{ grid-template-columns:repeat(2,1fr); }} }}
</style>
</head>
<body>
  <h1>🏦 每日投資組合報告</h1>
  <div class="sub">
    {report['account_id']} ｜ 策略：{report['strategy_id']} ｜
    報告日期：{report['report_date']} ｜ 產生時間：{report['generated_at'][:19]}
  </div>

  <div class="cards">
    <div class="card">
      <div class="label">💰 NAV 淨值</div>
      <div class="value">{usd(s.get('nav',0))}</div>
      <div class="hint">起始 {usd(s.get('inception_nav',0))}</div>
    </div>
    <div class="card">
      <div class="label">📅 今日損益</div>
      <div class="value {daily_cls}">{usd(s.get('daily_pnl',0))}</div>
      <div class="hint {daily_cls}">{pct(s.get('daily_pnl_pct',0))}</div>
    </div>
    <div class="card">
      <div class="label">📈 總報酬率</div>
      <div class="value {total_cls}">{pct(s.get('total_return_pct',0))}</div>
      <div class="hint">投資 {s.get('days_elapsed',0)} 天</div>
    </div>
    <div class="card">
      <div class="label">🗓 年化收益率</div>
      <div class="value {annual_cls}">{pct(s.get('annual_return_pct',0))}</div>
      <div class="hint">最大回撤 {pct(s.get('max_drawdown_pct',0))}</div>
    </div>
  </div>

  <div class="section">
    <h2>📋 持倉明細（{len(positions)} 檔）</h2>
    <table>
      <tr>
        <th>股票</th><th>現價</th><th>均價</th><th>股數</th>
        <th>市值</th><th>權重</th><th>損益%</th><th>損益金額</th>
      </tr>
      {pos_rows if pos_rows else '<tr><td colspan="8" style="text-align:center;color:#888">尚無持倉</td></tr>'}
    </table>
  </div>

  <div class="section">
    <h2>📜 今日交易紀錄</h2>
    <table>
      <tr><th style="text-align:left">時間</th><th style="text-align:left">股票</th>
          <th style="text-align:left">方向</th><th>數量</th><th>成交價</th><th>狀態</th></tr>
      {trade_rows}
    </table>
  </div>

  <div class="risk">
    ⚠️ <b>風險提醒</b>：本報告所有內容（持倉、損益、分析）僅供資訊整理與研究參考，
    <b>不構成任何投資建議</b>。投資有風險，請自行評估後審慎決策。
  </div>

</body>
</html>"""
        return html

    def save_html(self, report: dict, account_id: str) -> str:
        """儲存 HTML 報告，回傳路徑"""
        date_dir = os.path.join(self.VIEW_DIR, report["report_date"])
        os.makedirs(date_dir, exist_ok=True)
        path = os.path.join(date_dir, f"{account_id}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.render_html(report))
        return path
