# 🦆 波波鴨選股系統

每天早上 08:30 自動分析台股，推播結果到 **Telegram** 和 **LINE**。

## 設定步驟（照順序做）

### 第一步：Fork 這個 Repo
右上角點 **Fork** → 建立到你自己的帳號

### 第二步：設定 Telegram Bot
1. Telegram 搜尋 `@BotFather`
2. 輸入 `/newbot`，依指示建立機器人，取得 **Token**
3. 先傳一則訊息給你的機器人
4. 瀏覽器開啟：`https://api.telegram.org/bot<你的TOKEN>/getUpdates`
5. 找到 `"chat":{"id": 數字}`，記下這個數字（**Chat ID**）

### 第三步：設定 LINE Notify
1. 開啟 https://notify-bot.line.me/
2. 右上角登入 LINE 帳號
3. 點「個人頁面」→「發行權杖」
4. 輸入服務名稱（如：波波鴨選股），選擇接收的聊天室
5. 點「發行」→ 複製 **Token**

### 第四步：填入 GitHub Secrets
在你 Fork 的 Repo：
1. 點 **Settings** → **Secrets and variables** → **Actions**
2. 點 **New repository secret**，依序新增：
   - `TELEGRAM_TOKEN` → 你的 Telegram Bot Token
   - `TELEGRAM_CHAT_ID` → 你的 Telegram Chat ID
   - `LINE_TOKEN` → 你的 LINE Notify Token

### 第五步：啟用 Actions
1. 點 **Actions** 頁籤
2. 點「I understand my workflows, go ahead and enable them」
3. 點左側「🦆 波波鴨每日選股」→「Run workflow」立即測試

## 自動執行時間
每天週一到週五 **08:30（台灣時間）** 自動執行

## 手動執行
Actions → 🦆 波波鴨每日選股 → Run workflow

## 查看 HTML 報告
每次執行後，點 Actions → 選最新的執行紀錄 → Artifacts → 下載「波波鴨選股報告」

---
⚠️ 資料來源：台灣證券交易所公開資料。僅供學習參考，不構成投資建議。
