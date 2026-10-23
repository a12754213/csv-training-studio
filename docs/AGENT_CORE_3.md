# Agent Core 3.0（v3.0.0）

這是可擴充、結果導向的多步驟 Agent **第一階段**。目前不是可執行任意任務的自主電腦，也不能自行登入網站。

## 在 Streamlit 使用

1. 進入 **Agent Core 3.0** 獨立頁面（`pages/6_Agent_Core_3.py`）。
2. 輸入中文需求（可包含公開 HTTP(S) URL），也可在網址欄逐行貼上另外的公開網址，或上傳一份 CSV。所有來源合計最多三個。
3. 可以輸入 CSV 的目標欄位。未知欄位不會觸發訓練，也不會當成已找到的欄位。
4. 按「建立與預覽任務」；此時還不會連上任何外部網站。
5. 要爬網站，先核准**本任務明確列出的網址**。按「開始／繼續執行工具」後，程式在當次請求中串接工具、看到真實結果後決定下一個工具。
6. 工具流程：`source.load`（上傳資料）或 `web.crawl` → 依實際格式呼叫 `csv.inspect`／`text.inspect` → 若有效目標欄存在則呼叫 `csv.plan` → 下一個來源 → 完成。
7. 出錯最多允許一次手動重試；連續兩次失敗或達到 12 步上限便停止。失敗不會悄悄改變資料來源。
8. 想訓練時，仍需要回到原有 CSV／AutoML 或 Core 2.0 的人工核准步驟；**Core 3.0 不提供訓練操作**。

## LLM Agent

在設定區啟用 OpenAI 並輸入自己 API Key，模型可以看各步的**最小化工具輸出摘要**（包含現有 CSV 欄名、筆數、執行狀態），從 **目前已允許的動作**中選擇下一步。引擎最終審核每個選擇，永遠不執行任意模型給的 Python、shell、SQL、新網址或未知工具。沒有 API Key 則使用可檢查的 deterministic planner。

這不是全面的自由研究 Agent。工具 registry 目前只有 CSV、公開單頁網頁及基本文字概況；要加入搜尋、文章語意摘要、影片或 PDF 需另行註冊與測試。**目前不會把 CSV 原始列資料送給模型**，但欄名可能有敏感資訊。

## 記憶與任務狀態

`AgentTask` 在目前 Streamlit 工作階段保存原始來源、目前狀態、工具執行紀錄和結果。頁面刷新、檔案改變或重開工作階段可能失去來源內容。

`TaskJournal` 是獨立的**選用**本機稽核記錄，可在自己的 Python 服務中呼叫 `run_until_gate(..., journal=TaskJournal(Path("outputs/agent-jobs")))`。只把工作代碼、工具名稱、狀態、步數、站點主機等資訊保存成 JSON；不保存金鑰、CSV 檔案內容或完整 URL。Journal 上的進行中工作重新讀入時會標示為 `interrupted`，**不能在缺少原始資料及授權的情況下自動恢復**。公開 Streamlit 頁面目前未開啟此本機紀錄。

## 選用的遠端 MCP 介面（開發者部署）

`agent_remote_mcp.py` 是與 Streamlit 分開啟動的**唯讀 Streamable HTTP MCP** 原型，預設僅監聽 `127.0.0.1:8765`，不會由 Streamlit Cloud 自動啟動。包含：

- `list_public_agent_tools`：列出公開唯讀工具。
- `preview_public_agent_task`：不連網站，預覽指定 URL 工作。
- `inspect_public_agent_task`：在支援工具核准的客戶端中，使用明確提供的公開 URL 進行有上限的實際擷取與分析。
- 服務**不提供** CSV 上傳、任意檔案存取、模型訓練、shell、部署程式寫入等能力。

安裝專案本機 Python 和可選 MCP 依賴後，使用 PowerShell：

```powershell
# 產生高熵臨時測試用權杖；請勿提交到 GitHub
$env:AI_AGENT_REMOTE_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(48))"
python agent_remote_mcp.py --host 127.0.0.1 --port 8765
```

HTTP MCP 入口為 `http://127.0.0.1:8765/mcp`，要求 `Authorization: Bearer <token>`。本機測試之外請**不要**用未加密 HTTP 傳送權杖。瀏覽器來源若帶 `Origin` header，必須設定 `AI_AGENT_ALLOWED_ORIGINS` 允許，否則拒絕。權杖不得共用或寫入 Git。

要讓雲端 ChatGPT 呼叫，還需要自行部署**公開 HTTPS** 反向代理、設定身分驗證與流量限制，確保不暴露本機/內網或使用者檔案；ChatGPT 端需依該帳號與連接器實際支援的授權方式完成連接。這裡的 Bearer 權杖驗證 **不是 OAuth**，不能保證能直接加入 ChatGPT 自訂 MCP。此版**未**替你開通網域、憑證或連接服務，也不應直接把開發用服務綁在公網。

## 驗收與限制

```bash
python -m unittest tests.test_agent_engine tests.test_agent_remote_mcp -v
python -m unittest discover -s tests -v
python scripts/check_local_ui_browser.py
```

仍待開發：可授權的全網搜尋、瀏覽器 JavaScript 網頁、多頁推進、文章內容交叉查核、影片/PDF/語音、用戶級持久化資料倉、可靠任務排程以及雲端 ChatGPT 端到端授權連接。
