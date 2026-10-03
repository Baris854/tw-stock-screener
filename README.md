# 台股公開資料進階篩選器 (Taiwan Stock Screener)

串接台灣證券交易所（TWSE）官方 OpenAPI，提供全欄位雙向排序（本益比、殖利率、淨值比、年化市銷率、葛拉漢指數）、流動性過濾、經典策略快選、TradingView/Goodinfo 捷徑與自選股儲存功能的台股篩選器。

---

## 🚀 部署到 Render（免費 3 分鐘上線）

### 步驟 1：上傳程式碼到 GitHub
1. 在 [GitHub](https://github.com/) 建立一個新的公開或私有儲存庫（Repository），例如命名為 `tw-stock-screener`。
2. 在本機資料夾執行以下指令將檔案推送到 GitHub：
   ```bash
   git init
   git add .
   git commit -m "feat: initial commit for tw-stock-screener"
   git branch -M main
   git remote add origin https://github.com/<你的GitHub帳號>/tw-stock-screener.git
   git push -u origin main
   ```

### 步驟 2：在 Render 建立 Web Service
1. 前往 [Render.com](https://render.com/) 登入（可直接用 GitHub 帳號登入）。
2. 點擊右上角 **「New +」** -> 選擇 **「Web Service」**。
3. 選擇 **「Build and deploy from a Git repository」**，並連接剛才建立的 `tw-stock-screener` 儲存庫。
4. 設定欄位確認（Render 會自動偵測）：
   - **Name**: `tw-stock-screener`（網址會是 `tw-stock-screener.onrender.com`）
   - **Region**: 建議選擇 `Singapore`（新加坡，對台灣連線最快）
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt || true`
   - **Start Command**: `python server.py`
   - **Instance Type**: 選擇 **Free**（完全免費）
5. 點擊最下方的 **「Deploy Web Service」**。

---

## ⏱️ 大功告成！
等待 1~2 分鐘建置完成後，Render 會分配一個專屬的永久 HTTPS 網址（例如 `https://tw-stock-screener.onrender.com`），點開即可永久使用！
