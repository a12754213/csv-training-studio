# Agent Core 2.0 · 受控多工具工作流

## 在網站使用

首頁或左側導覽選擇 **Agent Core**（`pages/5_Agent_Core.py`）。

1. 輸入繁體中文指令，並提供公開 HTTP(S) URL、上傳 CSV，或兩者都提供。
2. 點「解析需求並預覽工具計畫」。不提供 API Key 時只做規則分流；若勾選 OpenAI 解析自然語言，必須自行輸入 API Key（獨立計費）。
3. 檢查來源和預計工具，按「核准讀取來源並執行分析」。
4. 讀取公開網頁會呼叫既有 `web.crawl`，完成後依**實際**結果選擇 `text.inspect` 或 `csv.inspect`。當明確的目標欄位存在時再呼叫 `csv.plan`。
5. 若是表格，選擇**真實存在**的預測目標、任務類型與排除欄位，檢查建議選項，另外按「核准並開始模型訓練」。既有 `csv.train` 會回傳實際指標及 ZIP。
6. 變更來源、檔案、指令或規劃模式會清除頁面上一次的計畫與結果，避免沿用錯誤來源。

## 隱私、安全與限制

- 語言模型只看使用者輸入的指令、選定的網址及至多 100 個 CSV 欄名；**不會收到原始 CSV 的列值**。但 URL 本身與欄名可能含敏感資料，請避免在文字指令中放密碼、Token 或機密資訊。
- 使用者提供的網址是唯一允許的來源；模型編造的網址會被拒絕。目標欄位必須與實際欄名相符。
- 外部網頁讀取與訓練是**兩次分開的人工核准**；即使模型說「直接訓練」，也不能跳過。
- 仍沿用爬蟲的 robots.txt、公開 IP、下載容量和單頁限制；網頁與 CSV 都視為不可信資料。無 Python／shell／任意工具執行權限。
- 當前文字模組只有提取文字、字數／段落概況，不是經過 LLM 的文章摘要或事實查核。
- 尚無網路搜尋引擎、多頁遞迴、JavaScript 動態網站、YouTube/影片、跨工作階段記憶與自動重試。
- Streamlit 頁面不是可被此 ChatGPT 對話直接呼叫的 MCP API。原有本機 MCP 功能不受影響；如需本機 ChatGPT 連線，依 `docs/CHATGPT_LOCAL.md` 完成實際配置及驗收。

## 測試

```bash
python -m unittest tests.test_agent_core -v
python -m unittest discover -s tests -v
python scripts/check_local_ui_browser.py
```

後端測試涵蓋虛構 URL 拒絕、未知操作拒絕、CSV 欄名校驗、API 資料最小化、多工具串接與讀取／訓練核准。端對端 UI 測試仍須 GitHub Actions 與 Streamlit Cloud 部署檢查。

## 擴充方向

新的功能一律以 `Capability` 註冊在 `agent_modules`，並提供獨立測試。在擴充跨工具能力時增加明確的 allow-list、輸入檢查與必要核准；不要根據網頁、CSV 或模型輸出的文字動態匯入 Python 模組。
