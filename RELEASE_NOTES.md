# AI Agent Hub v3.1.0 — 網路研究、多媒體與本機工作排程

新增 Research & Media 獨立頁面及獨立工具註冊：
- Brave 搜尋、明確核准網址後擷取最多三個研究來源、可選 OpenAI 依來源產生有編號的文字報告。
- 選用 Playwright 動態網頁（預設禁用，需網路隔離）；YouTube 影片公開資訊及可用字幕（預設禁用）。
- PDF 文字、圖片尺寸與可選視覺理解、WAV 時長及選用語音轉錄、SRT／VTT 字幕整理。
- 本機 SQLite 明確記憶、任務摘要記錄、每小時／每天／每週搜尋工作定義，以及由 OS Scheduler 單次觸發的 Worker。
- 遠端唯讀 MCP 原型新增公開搜尋工具，沿用認證限制；不會自動連到 ChatGPT 帳號。
- 所有新增需要外部存取／上傳的能力皆須確認，專案原有 CSV／AutoML／Core 2.0／3.0 不刪除。

**尚待外部設定：** 自有 Brave/OpenAI API Key、可用隔離瀏覽器與影片相關依賴、私人 HTTPS 遠端服務和 ChatGPT 客戶端授權、常駐排程 Worker 或通知服務。部分網站沒有公開字幕或禁止擷取。GitHub Actions 測試不能取代這些真實外部帳戶的驗收。

完整指南：docs/AGENT_CAPABILITIES.md

---

# AI Agent Hub v3.0.0 — Adaptive Agent Core

- 新增第七個獨立頁面「Agent Core 3.0」：依上一步的網頁擷取結果，從固定已註冊工具中選擇下個步驟；最多三個來源，每次最多 12 步。
- 任務狀態與工具 trace、至多一次重試（最多兩次失敗）；可選擇使用 OpenAI 逐步提供候選動作，但結果仍經由當前狀態 allow-list 驗證。
- 可選擇將不含原始 CSV、網址 query、金鑰的工作狀態輸出至 JSON Journal。會話內保存當次輸入，斷線後不會自動重播外部存取。
- 新增 opt-in 的唯讀 Streamable HTTP MCP Adapter。預設 localhost 綁定，Bearer Token 驗證，沒有模型訓練和本機檔案存取權限；公網 TLS、反向代理及 ChatGPT 連接需要使用者另外設定與驗收。
- 保留 v2.6.0 全部 CSV、AutoML、網頁擷取與 Core 2.0 功能。

注意：本版尚未提供搜尋引擎、JS 動態網頁／影片、跨 session 自動恢復、無限制自主執行或已綁定至 ChatGPT 網頁版的遠端工具。OpenAI API 獨立計費。

---

# AI Agent Hub v2.6.0 — Agent Core 2.0

新增受控多工具 Agent Core 工作台（pages/5_Agent_Core.py）：使用自然語言規劃，先預覽來源與工具，再分開核准外部讀取和模型訓練。

- 繼承現有的 web.crawl / csv.inspect / csv.plan / text.inspect / csv.train 工具註冊中心。
- 依實際抓取結果把文字送到文字工具，表格送到 CSV 工具；可以上傳 CSV 而不必經過爬蟲。
- 可選 OpenAI API 解析意圖，嚴格限制 JSON 結構與網址來源，不允許 AI 編造網址／任意執行指令。
- 語言模型僅收到使用者文字、已提供的網址與有限 CSV 欄名，不上傳 CSV 儲存格資料。
- 保留兩次人工核准：來源讀取，以及最終選定目標後的模型訓練；顯示工具執行紀錄、分析概況與結果下載。
- 增加獨立後端安全測試、六頁 Streamlit 渲染與本機／雲端導覽驗收。

限制：非全自主瀏覽，尚無搜尋引擎、多頁／JS 網站爬取、影片、記憶體持久化或自動重試。OpenAI API 另外計費；ChatGPT 對話本身不會自動連上 Streamlit 網站。

--- 

# AI Agent Hub v2.5.0 — 多功能智慧工作台

這次以整體使用體驗為中心重新整理網站，讓 CSV Training Studio 不再主導全部頁面的名稱，正式定位為 **AI Agent Hub**。

## 首頁與工作區
- 首頁改為 AI Agent Hub，多模組入口可直接選擇資料分析 Agent、自然語言工作台、公開網頁資料擷取及 Agent 工具分流。
- 原有 CSV／AutoML 流程保留在首頁下方；範例資料、上傳、欄位分析、切分、模型訓練與 ZIP 匯出不變。
- 五個頁面統一標題、版本、小節說明及響應式版面，繁體中文行高和手機安全間距同步調整。
- 自然語言工具仍需要 OpenAI API Key；規則式 Agent 不需要。網站不會替使用者自動付費或執行未核准訓練。

## 向下相容
- 原本的 Python 模組、訓練輸出檔、CSV/時間序列設定、MCP 工具 API 不更動。
- 舊 GitHub 專案名稱 `csv-training-studio` 和既有 Streamlit Cloud 網址先保留，避免分享連結失效。網站可見品牌已變更。
- 更新自動化 UI、桌機／手機與雲端瀏覽器測試，以確認新導覽和舊訓練功能。

## 限制
影片擷取、動態登入網站與任意網頁自主操作仍未實作。跨工具分流仍是規則型；不是已能解決任何任務的完整自主 Agent。

詳細參考：`README.md`、`docs/AI_AGENT.md`。
