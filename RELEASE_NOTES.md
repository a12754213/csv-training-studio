# AI Agent Hub · CSV Training Studio v2.4.0

此版本延續 v2.3.1 的 CSV/AutoML/AI Chat/MCP 系統，加入**獨立網路工具**，而不是把所有功能塞進 CSV。

## 本次新增
- **網路爬蟲**獨立頁面：人工確認後擷取單頁公開 HTML/CSV，顯示文章文字、表格資料並支援匯出 CSV。
- **AI Agent 自動工具分流**獨立頁面：讀到表格時交由 `csv.inspect`，指定目標後可 `csv.plan`，經使用者再次同意才能 `csv.train`；文章則送至 `text.inspect`。
- **MCP 新工具**：`inspect_public_web` 與 `import_public_web_table`，供有連接的 ChatGPT Agent 使用。
- **安全邊界**：公開 HTTP(S)、DNS/IP 檢查與連線目標鎖定、尊重 robots.txt、拒絕登入/內網/自訂連接埠、限制轉址與擷取容量，不執行網頁中的指令。
- **測試覆蓋**：增加獨立爬蟲及路由測試；保留 CSV 上傳→訓練→ZIP 的端到端測試。修改網址會清除舊結果，避免錯認來源。

## 暫不支援
這次的「Agent 自動分流」是**規則型**，尚不是能自行搜尋全網的 LLM Agent。
目前沒有多頁遞迴爬取、JavaScript 動態頁面、YouTube 字幕、影片下載、無字幕音訊轉錄、影像辨識、登入及反爬繞過。這些應以**獨立模組**逐步開發、驗收。
ChatGPT Plus 並不包含網站內額外 OpenAI API 使用額度；本機 MCP 客戶端也必須由使用者實際連接。

若你的正式網站還是舊版，請檢查 Streamlit Cloud 指向 `main`／`app.py`，並從 Manage app 查看 Logs、重新啟動。

詳細說明請見 `docs/AI_AGENT.md`。
