# GitHub Actions 自動交易設定指南

## 📋 目錄
1. [添加 GitHub Secrets](#添加-github-secrets)
2. [驗證 Workflows](#驗證-workflows)
3. [監控執行狀態](#監控執行狀態)
4. [故障排查](#故障排查)

---

## 🔐 添加 GitHub Secrets

### 步驟 1：進入 Settings

1. 打開 GitHub repo: https://github.com/NCC0524/alpaca-autotrader
2. 點擊 **Settings** (頂部導航)
3. 左側菜單 → **Secrets and variables** → **Actions**

### 步驟 2：添加 Alpaca 交易憑證

點擊 **New repository secret** 並依次添加以下 4 個：

#### Secret #1: ALPACA_KEY_ACC001
```
Name: ALPACA_KEY_ACC001
Value: PKL6ZHN5BMJWRVHAQPC3N63PJI
```
✅ 點擊 **Add secret**

#### Secret #2: ALPACA_SECRET_ACC001
```
Name: ALPACA_SECRET_ACC001
Value: BmoeU1bH5HTJs6XJDaLCsUtZDqAH8q8SAmZPisPX9awg
```
✅ 點擊 **Add secret**

#### Secret #3: ALPACA_BASE_URL
```
Name: ALPACA_BASE_URL
Value: https://paper-api.alpaca.markets/v2
```
✅ 點擊 **Add secret**

#### Secret #4: ALPACA_DATA_URL
```
Name: ALPACA_DATA_URL
Value: https://data.alpaca.markets/v1
```
✅ 點擊 **Add secret**

### 步驟 3：添加電郵通知憑證（可選）

如果想要每日報告電郵通知，再添加以下 3 個：

#### Secret #5: SMTP_HOST
```
Name: SMTP_HOST
Value: smtp.gmail.com  (或你的郵件服務商)
```

#### Secret #6: SMTP_USER
```
Name: SMTP_USER
Value: your-email@gmail.com
```

#### Secret #7: SMTP_PASSWORD
```
Name: SMTP_PASSWORD
Value: your-app-password  (Google 應用密碼，非登入密碼)
```

**Google Gmail 步驟：**
1. 訪問 https://myaccount.google.com/security
2. 啟用「兩步驟驗證」
3. 產生「應用密碼」(選擇 Mail → Windows Computer)
4. 複製密碼，貼入 SMTP_PASSWORD

---

## ✅ 驗證 Secrets 已正確添加

回到 **Secrets and variables → Actions**，應該看到：

```
✓ ALPACA_KEY_ACC001
✓ ALPACA_SECRET_ACC001
✓ ALPACA_BASE_URL
✓ ALPACA_DATA_URL
✓ SMTP_HOST         (可選)
✓ SMTP_USER         (可選)
✓ SMTP_PASSWORD     (可選)
```

---

## 🔄 驗證 Workflows

### 步驟 1：檢查 Workflows 是否存在

1. 進入 repo → **Actions** (頂部導航)
2. 應該看到 3 個 Workflows：
   - ✅ Daily Auto Trading
   - ✅ Daily Report & Email
   - ✅ Monthly Rebalance

### 步驟 2：手動觸發測試（選擇性）

#### 測試 Daily Trading Workflow

1. 點擊 **Daily Auto Trading** workflow
2. 右側點擊 **Run workflow** → **Run workflow**
3. 等待 30-60 秒，應該看到：
   - 🟢 Checkout repository
   - 🟢 Set up Python 3.12
   - 🟢 Install dependencies
   - 🟢 Execute trading
   - 🟢 Upload logs

#### 測試 Daily Report Workflow

1. 點擊 **Daily Report & Email** workflow
2. 右側點擊 **Run workflow** → **Run workflow**
3. 等待，應該看到：
   - 🟢 Checkout repository
   - 🟢 Generate reports
   - 🟢 Commit and push reports
   - 🟢 Send email (若已配置 SMTP)

---

## 📊 監控執行狀態

### 檢查 Workflow 執行日誌

1. 進入 **Actions** tab
2. 選擇任一 workflow run
3. 點擊 **Execute trading** step 查看詳細日誌

**預期輸出：**
```
=== Daily Trading 開始 (2026-05-24T13:31:00) ===
[ACC001] NAV=$107,000  買入=2筆  賣出=1筆  dry_run=False
=== Daily Trading 完成  耗時 12.3s ===
```

### 檢查生成的報告

1. 進入 repo → **Code** tab
2. 打開 `reports/` 文件夾
3. 應該看到日期格式的 JSON 報告：
   ```
   reports/
   ├── 2026-05-24_ACC001_report.json
   ├── 2026-05-23_ACC001_report.json
   └── ...
   ```

4. 點擊任一報告 → **Raw** → 查看 JSON 內容

---

## ⏰ 自動執行排程

設置完畢後，GitHub Actions 會自動執行：

### Daily Auto Trading
```
時間：每日 13:31 UTC (09:31 EST)
日期：週一～週五 (weekdays only)
動作：
  1. 計算每支股票目標持倉
  2. 執行買賣訂單
  3. 上傳 logs artifact
```

### Daily Report & Email
```
時間：每日 11:00 UTC (06:00 EST)
日期：週一～週五
動作：
  1. 生成今日 JSON 報告
  2. Commit 回 repo
  3. 發送電郵通知 (若配置)
```

### Monthly Rebalance
```
時間：每月第一個 Monday 的 13:35 UTC (09:35 EST)
動作：
  1. 強制再平衡所有帳戶
  2. 記錄重新配置的訂單
```

---

## 🐛 故障排查

### 問題 1：Workflow 執行失敗 (❌ 紅燈)

**檢查日誌：**
1. Actions tab → 失敗的 run
2. 展開 **Execute trading** step
3. 查看錯誤信息

**常見原因：**

| 錯誤 | 解決方案 |
|------|--------|
| `AlpacaAuthError` | 檢查 ALPACA_KEY_ACC001 / ALPACA_SECRET_ACC001 是否正確 |
| `SMTP Authentication failed` | 檢查 SMTP_USER / SMTP_PASSWORD 是否正確；確認 Google 應用密碼 |
| `requests.exceptions.Timeout` | Alpaca API 暫時無法連線，GitHub Actions 會自動重試 |
| `reports/ directory not found` | 確認 `reports/` 文件夾已建立 (手動建立一次) |

### 問題 2：郵件未收到

**檢查清單：**
1. ✅ SMTP_HOST / SMTP_USER / SMTP_PASSWORD 已設定
2. ✅ config/accounts_registry.json 中的 `email` 欄位正確
3. ✅ 檢查垃圾郵件文件夾
4. ✅ 查看 workflow 日誌中的 "Send email" step

### 問題 3：報告未 Commit 到 Repo

**原因：** GitHub Actions 預設無 push 權限

**解決方案：**
1. Settings → Actions → General
2. 向下滾到 **Workflow permissions**
3. 選擇 **Read and write permissions**
4. ✅ Save

---

## 🔍 高級監控

### 方案 A：Slack 通知（可選）

在 workflow 失敗時獲得 Slack 通知：

```yaml
- name: Notify Slack on Failure
  if: failure()
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK }}
    payload: |
      {
        "text": "❌ Daily Trading Failed",
        "blocks": [...]
      }
```

需先添加 Secret: `SLACK_WEBHOOK`

### 方案 B：使用 GitHub Issues 作為日誌

每次交易完畢自動開 issue：

```yaml
- name: Create Daily Report Issue
  uses: actions/github-script@v6
  with:
    script: |
      github.rest.issues.create({
        owner: context.repo.owner,
        repo: context.repo.repo,
        title: `Trading Report - ${new Date().toISOString().split('T')[0]}`,
        body: '...'
      })
```

---

## ✨ 設定完成！

完成以上步驟後：

✅ **每天 09:31 EST** — 自動執行交易  
✅ **每天 06:00 EST** — 生成報告並電郵通知  
✅ **每月第一個 Monday** — 自動再平衡  
✅ **24/7 監控** — GitHub Actions 日誌可查看  

**無須本地電腦運行，完全自動化！** 🤖

---

## 📞 支援

| 問題 | 檢查 |
|------|------|
| 不知道 Alpaca 金鑰在哪 | Alpaca Dashboard → Settings → API Keys |
| 不知道 Google 應用密碼 | myaccount.google.com/apppasswords |
| Workflow 不運行 | 確認 repo Settings → Actions → 已啟用 |
| 看不到 Secrets | 檢查帳號是否有 repo admin 權限 |

