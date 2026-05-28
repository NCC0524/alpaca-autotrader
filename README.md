# 📈 Alpaca AutoTrader

一個完全自動化的股票交易系統，整合 **Alpaca Paper Trading API**、**GitHub Actions CI/CD** 和 **Streamlit Cloud Dashboard**。

## ✨ 核心功能

### 🤖 自動交易引擎
- **每日自動交易** (UTC 13:31 / EST 09:31) — 自動執行買賣訂單
- **每月重新平衡** (每月第一個週一) — 維持目標資產配置
- **多帳戶管理** — 支援多個 Alpaca 紙質交易帳戶
- **乾運行模式** — 測試訂單邏輯而不實際執行

### 📊 實時儀表板
- **Streamlit Cloud 部署** — 零設置、自動託管
- **4 個頁面**:
  - 📋 持倉明細 — 完整持倉表格 + 資產配置圓餅圖
  - 📈 帳戶總覽 — NAV、現金、未實現損益、績效指標
  - 🏆 每日 TOP 10 — 根據策略篩選的股票排名
  - 📅 交易歷史 — 過去 30 天的日淨資產曲線圖
- **60 秒自動重整** — 實時數據更新

### 🔍 智能分析模組
- **動量評分器** (MomentumScorer)
  - 加權 1D (20%) + 5D (35%) + 20D (45%) 動量
  - Sigmoid 正規化，K=10.0
  
- **P/E 計算器** (PECalculator)
  - 基於 EPS TTM 計算市盈率
  - 自動數據快取與歷史追蹤
  
- **趨勢預測器** (Predictor)
  - 方向預測 (向上/向下/中立)
  - 信心度評估 (0.0 ~ 1.0)
  - 波動度衰減調整
  - ⚠️ 免責聲明：僅供參考，不構成投資建議

### 📧 日報告 & 電郵通知
- **自動生成 JSON 報告** — 每日 UTC 11:00 (EST 06:00)
- **Git Commit** — 報告自動提交回 repo
- **電郵通知** (可選) — Gmail SMTP 支援
- **NAV 歷史追蹤** — 長期績效分析

---

## 🏗️ 系統架構

```
alpaca-autotrader/
├── src/
│   ├── dashboard/              # Streamlit 儀表板
│   │   ├── app.py              # 主應用入口
│   │   ├── data_provider.py     # API 數據供應者
│   │   ├── config.py            # 配置管理（秘密讀取）
│   │   ├── pages/
│   │   │   ├── overview.py      # 帳戶總覽頁
│   │   │   ├── positions.py     # 持倉明細頁
│   │   │   ├── top10.py         # TOP 10 分析頁
│   │   │   └── history.py       # 歷史曲線頁
│   │
│   ├── runner/                  # GitHub Actions 入口
│   │   ├── daily_trader.py      # 每日交易執行
│   │   ├── daily_reporter.py    # 日報告生成
│   │   └── monthly_rebalancer.py # 月度重新平衡
│   │
│   ├── analytics/               # 分析引擎
│   │   ├── momentum_scorer.py   # 動量評分
│   │   ├── pe_calculator.py     # P/E 計算
│   │   └── predictor.py         # 趨勢預測
│   │
│   ├── broker/                  # Alpaca API 封裝
│   │   ├── alpaca_client.py     # API 客戶端
│   │   └── account_manager.py   # 帳戶管理
│   │
│   └── utils/                   # 工具函數
│       └── logger.py            # 日誌管理
│
├── strategies/                  # 交易策略配置
│   └── tech_top10.json          # Top 10 科技股策略
│
├── config/                      # 靜態配置
│   └── accounts_registry.json   # 帳戶註冊表
│
├── .github/workflows/           # GitHub Actions 工作流
│   ├── daily_trading.yml        # 每日交易工作流
│   ├── daily_report.yml         # 日報告工作流
│   └── monthly_rebalance.yml    # 月度重新平衡工作流
│
├── reports/                     # 生成的交易報告
│   └── *.json                   # 日期格式的報告文件
│
├── logs/                        # GitHub Actions 日誌
│   └── .gitkeep
│
├── streamlit_app.py             # Streamlit Cloud 入口
├── GITHUB_ACTIONS_SETUP.md      # 詳細設置指南
└── README.md                    # 本文件
```

---

## 🚀 快速開始

### 前置需求
- Python 3.12+
- Git & GitHub 帳號
- Alpaca 紙質交易帳號 ([alpaca.markets](https://alpaca.markets))
- Streamlit Cloud 帳號 (免費)

### 第 1 步：複製並設置本地環境

```bash
git clone https://github.com/NCC0524/alpaca-autotrader.git
cd alpaca-autotrader

# 安裝依賴
pip install -r requirements.txt

# 設置本地秘密（開發用）
mkdir -p .streamlit
cat > .streamlit/secrets.toml << EOF
ALPACA_KEY_ACC001 = "YOUR_API_KEY"
ALPACA_SECRET_ACC001 = "YOUR_API_SECRET"
ALPACA_BASE_URL = "https://paper-api.alpaca.markets/v2"
ALPACA_DATA_URL = "https://data.alpaca.markets/v1"
EOF
```

### 第 2 步：設置 GitHub Secrets (自動交易)

詳見 [GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md)

**快速檢查清單：**
```bash
# 驗證所有 4 個 Alpaca 秘密已設置
gh secret list | grep ALPACA

# 應該看到：
# ALPACA_BASE_URL
# ALPACA_DATA_URL
# ALPACA_KEY_ACC001
# ALPACA_SECRET_ACC001
```

### 第 3 步：部署 Streamlit Cloud 儀表板

1. Fork 此 repo 到你的 GitHub 帳號
2. 登入 [streamlit.io](https://streamlit.io)
3. 點擊 **New app** → **From existing repo**
4. 選擇：
   - Repository: `your-username/alpaca-autotrader`
   - Branch: `master`
   - Main file path: `streamlit_app.py`
5. 點擊 **Deploy**
6. 在 Streamlit 應用設置中添加秘密：
   ```toml
   ALPACA_KEY_ACC001 = "YOUR_API_KEY"
   ALPACA_SECRET_ACC001 = "YOUR_API_SECRET"
   ALPACA_BASE_URL = "https://paper-api.alpaca.markets/v2"
   ALPACA_DATA_URL = "https://data.alpaca.markets/v1"
   ```
7. 點擊 **Save** 並等待 30 秒自動重載

✅ 儀表板現在應該在線並顯示實時帳戶數據！

### 第 4 步：啟用 GitHub Actions 自動交易

1. 確保 repo Settings → Actions → **Workflow permissions** 設置為 **Read and write**
2. 手動觸發測試：
   ```bash
   gh workflow run daily_trading.yml
   ```
3. 監控執行：
   ```bash
   gh run list --workflow=daily_trading.yml
   ```

---

## 📅 自動執行排程

設置完畢後，GitHub Actions 將自動執行（市場時間，週一～週五）：

| 工作流 | 時間 (UTC) | 時間 (EST) | 功能 |
|--------|-----------|-----------|------|
| **Daily Auto Trading** | 13:31 | 09:31 | 執行每日交易訂單 |
| **Daily Report & Email** | 11:00 | 06:00 | 生成報告並發送郵件 |
| **Monthly Rebalance** | 13:35 (月初週一) | 09:35 | 強制重新平衡持倉 |

---

## ⚙️ 配置選項

### 帳戶管理 (`config/accounts_registry.json`)

```json
{
  "accounts": [
    {
      "account_id": "ACC001",
      "enabled": true,
      "api_key_env": "ALPACA_KEY_ACC001",
      "api_secret_env": "ALPACA_SECRET_ACC001",
      "active_strategy": "tech_top10",
      "email": "your-email@gmail.com"
    }
  ]
}
```

**添加新帳戶：**
1. 在此 JSON 中新增帳戶
2. 為每個帳戶在 GitHub Secrets 添加 `ALPACA_KEY_ACC00X` 和 `ALPACA_SECRET_ACC00X`
3. Commit & Push

### 交易策略 (`strategies/tech_top10.json`)

```json
{
  "strategy_id": "tech_top10",
  "description": "每日前 10 大科技股配置",
  "universe": [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "NFLX", "ADBE", "CRM"
  ],
  "allocation": {
    "top_1": 0.20,
    "top_2_5": 0.15,
    "top_6_10": 0.10,
    "cash_buffer": 0.15
  }
}
```

**修改策略：**
編輯此檔案，commit & push。工作流將自動使用新配置。

---

## 🔧 故障排查

### GitHub Actions 執行失敗

**檢查日誌：**
```bash
# 查看最近失敗的執行
gh run list --status failed --workflow=daily_trading.yml

# 查看詳細錯誤
gh run view <run-id> --log-failed
```

**常見問題：**

| 錯誤 | 解決方案 |
|------|--------|
| `AlpacaAuthError` | 驗證 `ALPACA_KEY_ACC001` / `ALPACA_SECRET_ACC001` 是否正確 |
| `FileNotFoundError: logs/` | 確認 `logs/.gitkeep` 存在 |
| `pandas.applymap() AttributeError` | 升級到 pandas 2.1+: `pip install --upgrade pandas` |
| `SMTP Authentication failed` | 驗證 Gmail 應用密碼（非登入密碼） |

### Streamlit 儀表板無法連線到 Alpaca

**檢查清單：**
1. ✅ `ALPACA_KEY_ACC001` 和 `ALPACA_SECRET_ACC001` 在 Streamlit Secrets 中設置
2. ✅ 帳號啟用標誌為 `true` (config/accounts_registry.json)
3. ✅ Alpaca API 在線狀態 (status.alpaca.markets)
4. ✅ 清除瀏覽器快取 (Ctrl+Shift+Delete)
5. ✅ 在 Streamlit 應用設置中點擊 **Reboot app**

### 未收到郵件通知

**檢查清單：**
1. ✅ `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` 已設置
2. ✅ config/accounts_registry.json 中的 `email` 欄位正確
3. ✅ Gmail 應用密碼已生成 (myaccount.google.com/apppasswords)
4. ✅ 檢查垃圾郵件文件夾
5. ✅ 查看 workflow 日誌中 "Send email" step

---

## 📊 績效監控

### 查看交易報告

```bash
# 列出所有報告
ls -la reports/

# 查看最新報告
cat reports/$(date +%Y-%m-%d)_ACC001_report.json | jq .
```

**報告結構：**
```json
{
  "account_id": "ACC001",
  "date": "2026-05-29",
  "nav": 1050000.00,
  "nav_change": 50000.00,
  "trades": [
    {
      "symbol": "AAPL",
      "action": "buy",
      "qty": 100,
      "price": 195.50,
      "status": "filled"
    }
  ],
  "positions": [...],
  "summary": "..."
}
```

### 監控 NAV 歷史

儀表板 **交易歷史** 頁面顯示過去 30 天的 NAV 曲線圖，自動從 `reports/` 目錄加載數據。

---

## 🔐 安全最佳實踐

✅ **該做的事：**
- 使用 GitHub Secrets 管理 API 金鑰（絕不 hardcode）
- 使用 Alpaca 紙質交易帳號（零真實資金風險）
- 定期檢查 workflow 日誌
- 啟用 GitHub 兩步驟驗證

❌ **不該做的事：**
- 將 API Key/Secret 提交到代碼
- 在郵件或聊天中分享 GitHub Secrets
- 在 public repo 中使用真實交易帳號
- 依賴本系統作為唯一投資決策來源

---

## 📚 進階主題

### 本地開發與測試

```bash
# 運行儀表板本地版本
streamlit run streamlit_app.py

# 運行單元測試
pytest tests/ -v

# 執行交易模擬（乾運行）
python -m src.runner.daily_trader --dry-run
```

### 添加自訂分析指標

1. 在 `src/analytics/` 中創建新模組
2. 在 `top10_analyzer.py` 中整合
3. 在儀表板頁面中使用新數據

### 使用私有數據源

修改 `data_provider.py` 以支援其他 API：
```python
def get_custom_metric(self, symbol: str) -> dict:
    # 自訂 API 呼叫
    pass
```

---

## 🤝 貢獻指南

歡迎 Pull Requests！請確保：
1. 代碼遵循 PEP 8 風格
2. 新功能包含單元測試
3. 更新相關文檔
4. 提交信息清晰明瞭

---

## 📄 許可證

MIT License — 詳見 [LICENSE](LICENSE)

---

## 📞 支援與反饋

- 📖 **文檔**：[GITHUB_ACTIONS_SETUP.md](GITHUB_ACTIONS_SETUP.md)
- 🐛 **報告問題**：GitHub Issues
- 💬 **討論**：GitHub Discussions

---

## ⚠️ 免責聲明

本項目提供的所有分析和預測**僅供參考，不構成任何投資建議**。股票市場具有高度不確定性，使用本系統進行投資決策存在風險。**請自行承擔所有投資風險**，並在做出任何交易決策前諮詢專業財務顧問。

紙質交易不涉及真實資金，但其結果可能不能準確反映真實市場條件下的實際交易績效。

---

**最後更新：2026-05-29** | [查看提交歷史](https://github.com/NCC0524/alpaca-autotrader/commits/master)
