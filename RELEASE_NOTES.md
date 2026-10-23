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
