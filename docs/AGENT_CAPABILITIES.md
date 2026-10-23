# AI Agent Hub v3.1.0 — Research / Media / Memory / Scheduling

此版以 **獨立工具、最小權限、明確核准** 方式擴充 v3.0.0。不是「AI 能不受限制地操作任何網站」，也不是 ChatGPT 帳號已自動完成連接。

## 能用的功能

| 模組 | 註冊工具 | 實際可做的事 | 需要的條件 |
| --- | --- | --- | --- |
| 網路搜尋 | `web.search` | Brave Web Search 公開網路索引、最多 10 筆 | 自有 Brave Search API Key |
| 多來源研究 | `web.research_selected` | 在已核准網址上以既有安全爬蟲取公開表格與文字 | 選擇 1–3 個網址，遵守 robots.txt |
| 研究報告 | `web.synthesize` | 把擷取來源片段交給 OpenAI 整理並標註來源編號 | 使用者明確同意外傳片段、自有 OpenAI API Key |
| 動態網頁 | `web.render` | Playwright 載入指定網址與同站 JS 的文字畫面 | 本機隔離容器、已安裝 Playwright+Chromium、`AI_AGENT_ISOLATED_BROWSER=1` |
| YouTube | `video.youtube_info`、`video.youtube_transcript` | 公開影片標題、簡介、字幕語言；可用時擷取公開字幕 | 選用 yt-dlp、youtube-transcript-api、`AI_AGENT_YOUTUBE_ENABLED=1` |
| PDF | `document.pdf` | 擷取文字型 PDF 頁數、文字 | 已安裝 pypdf；掃描型 PDF 尚無 OCR |
| 圖片 | `image.inspect`、`image.describe` | 讀取圖片格式尺寸；可選外部視覺模型做圖片內容描述 | 上傳圖片；理解內容需 OpenAI API Key／明確外傳核准 |
| 音訊 | `audio.inspect`、`audio.transcribe` | WAV 時長；可選 OpenAI `gpt-transcribe` 語音轉文字 | 音訊上傳；轉錄需 API Key／明確外傳核准 |
| 字幕 | `video.subtitles` | SRT/VTT 字幕文字提取 | 上傳字幕檔 |
| 本機記憶 | `AgentStore` | 以 SQLite 保存、檢索、刪除明確同意的筆記與安全狀態摘要 | 單機私有資料夾，`AI_AGENT_LOCAL_WORKSPACE=1` |
| 排程 | `AgentStore`、`agent_worker.py` | 依使用者核准的頻率定期查詢公開搜尋索引、保存最近回報 | SQLite、Brave 金鑰、Windows Task Scheduler／cron 主動執行 Worker |

**自然語言跨工具分派器**：Research & Media 上方可輸入中文要求，`agent_supervisor.plan_task` 會依明確網址、上傳副檔名及請求文字選擇 `web.search`、`web.research_selected`、`document.pdf`、`image.inspect`／`image.describe`、`audio.transcribe`、`csv.inspect`、YouTube 資訊／字幕等既有工具。使用者可一次核准搜尋並明確選擇允許自動讀取前三個搜尋結果；外部傳送檔案／文字另外核准。這是**受控的有限任務分派器**，不是能自由執行任意程式或自行登入各個網站的 Agent。

首頁會出現第八個模組頁面「Research & Media」。其他原有 CSV／AutoML／Core 2.0／Core 3.0 不變。

## 選用依賴

預設雲端只安裝 **pypdf**（純文字 PDF）。要使用額外的本機影片／瀏覽器功能，請在獨立的本機 Python 工作環境安裝：

```bash
python -m pip install -r requirements-agent-extras.txt
python -m playwright install chromium
```

Playwright 不是放上網公開的網頁自動操作 API。只有在**限制網路出口的隔離容器／VM** 配好時，才允許設定 `AI_AGENT_ISOLATED_BROWSER=1`。瀏覽器網頁的主機與子資源都受相同主機、robots、URL、大小與次數限制，但若部署平台不具備網路隔離，不建議啟用。不能保證每個需要跨站 JS 的網頁正常顯示。

YouTube 不繞過登入、付費、DRM、平台限制；部分影片沒有公開字幕，或會因地區／防機器人措施而失敗。影片資訊不是完整影片影像辨識。SRT/VTT 字幕可直接上傳解析。

## 啟動本機資料庫與排程

僅在本機、個人工作區：

```powershell
$env:AI_AGENT_LOCAL_WORKSPACE = "1"
$env:BRAVE_SEARCH_API_KEY = "在此本機工作階段輸入金鑰"
python -m streamlit run app.py
```

進入「Research & Media」→「本機記憶與排程」。建立排程只寫入 SQLite，**不會自己開啟背景監控**。在 Windows 工作排程器建立一個每小時觸發的動作，執行：

```powershell
python agent_worker.py --db outputs/agent_hub.db --once
```

工作排程器必須自行指定專案工作目錄、Python 絕對路徑與安全的 `BRAVE_SEARCH_API_KEY` 環境來源。每次 Worker 最多執行 3 筆到期工作；失敗會記錄狀態，下一週期重新執行。不能比每小時更頻繁。這不會自動寄信或推播；要通知還需另外配置通知管道。

請勿在公開 Streamlit Cloud 啟用本機共享 SQLite：此範例沒有多用戶隔離與登入；雲端容器的磁碟也不保證持久。

## 與 ChatGPT 直接連接

`agent_remote_mcp.py` 新增 `search_public_web`（伺服器端另需 Brave Key），與既有唯讀公開網址工具共用 Bearer Token 閘道。該 API **不**提供任意 shell、訓練、個人資料庫或本機檔案讀寫。

**只有程式碼已就緒，沒有自動替 ChatGPT Plus 帳號註冊遠端服務。** 目前還缺：
- 獨立公開 HTTPS 主機及服務管理、身份驗證（ChatGPT 客戶端需支援其授權方式；Bearer Token 不等於 OAuth）、部署網域。
- 各服務自有 API Key、實際帳號授權及連線端到端驗收。
- 若希望 ChatGPT 發起持久性的自動任務，還需要部署通過權限檢查的資料持久化 Worker／通知服務。

不得把這個開發服務直接綁定公網。任何第三方服務將依用量與自己的 API 帳戶獨立計費，ChatGPT Plus 不包含這些 API 的免費額度。

## 驗收

```bash
python -m unittest tests.test_agent_extensions -v
python -m unittest discover -s tests -v
python scripts/check_local_ui_browser.py
```

以上有自動測試的部分：工具註冊、搜尋資料契約、API 權杖防轉址、私有 IP 爬蟲限制（沿用原有測試）、PDF/圖片/音訊資訊與字幕、YouTube 網址驗證、隔離瀏覽器預設停用、SQLite 記憶、排程核准與單次執行。

仍非完成品：搜尋後由 LLM 自動決定整個任務的任意多輪自由研究、複雜網頁交互操作、任意格式影片逐幀視覺分析、掃描 PDF OCR、跨裝置加密使用者資料庫、自動推播及 ChatGPT 帳號遠端連線。這些需要額外的授權、硬體、模型或服務環境，不能將程式介面視為成功啟用。
