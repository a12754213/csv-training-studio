# CSV Training Studio · 可擴充 AI Agent 工作台

## 目前能做什麼

Streamlit 側邊欄開啟 **AI Agent**，上傳 CSV 後會自動做概況分析，並依你選定的目標欄位建議分類、回歸或時間序列、需排除的 ID 欄。確認後才開始訓練，輸出含模型與報告的 `training_data.zip`。

工作台不複製訓練邏輯：它呼叫 `agent_hub` 的受控工具註冊中心，再呼叫 `agent_modules/csv_workflow.py`，最後沿用 `training_service.run_training_bytes` 與既有 `preprocessing`、`automl`、`forecasting`。沒有 OpenAI API Key 也能使用。

> **重要：** 這是有規則、可檢查決策的自動化工作流程，並非在 Streamlit 內建一個自由對話的 LLM。若想直接用 ChatGPT 下自然語言指令，請依 `docs/CHATGPT_LOCAL.md` 連接現有本機 MCP。ChatGPT 網頁／手機版不會因為這個頁面就自動連上本機服務。

## 如何新增未來功能

1. 新增檔案，例如 `agent_modules/chart_tool.py`，實作 `register(registry)`。
2. 使用 `registry.register(Capability('chart.summary', '產生圖表摘要', handler))` 註冊。
3. 在 `agent_modules/__init__.py` 明確匯入並呼叫 `chart_tool.register(registry)`。
4. 若工具會寫入資料、執行訓練或外部操作，設為 `requires_approval=True`，UI 必須明確取得同意才能傳 `approved=True`。
5. 在工作台或本機 MCP 增加呼叫入口，並撰寫測試。

簡單範例：

```python
from agent_hub import Capability

def summary(context, params):
    return {'message': f'收到 {context.filename}'}

def register(registry):
    registry.register(Capability('extra.summary', '示範新功能', summary))
```

**只允許明確匯入的內部模組**；不要讓上傳 CSV 指定 Python 模組／shell 指令，也不要把 CSV 內容當成 AI 指令。上傳檔案會在 Streamlit 部署主機上處理。

## 現有能力與限制

| 模組 | 能力 | 必須確認 |
|---|---|---|
| `csv.inspect` | 讀取資料、欄位型態、品質與疑似 ID | 否 |
| `csv.plan` | 建議分類／回歸／時間欄與排除欄位 | 否；目標需明確 |
| `csv.train` | 訓練引擎、AutoML 選模、評估、ZIP | **是** |

ID、任務類型與模型選擇只是建議；業務目的、資料洩漏與預測時實際可得欄位仍須確認。第一版工作台的一般表格訓練使用隨機切分，群組／時間切分及進階預處理請在原本的整理頁操作。時間序列需要單一可解析、無缺失且無重複的時間欄。

自動測試：`python -m unittest discover -s tests -v`。


## 第二階段：自然語言對話入口（可選）

新的 Streamlit 左側頁面 **「AI Chat」**（檔案 `pages/2_AI_Chat.py`）可以用繁體中文直接提出分析需求，例如：

> 幫我預測「是否流失」，排除「客戶編號」，自動比較模型。

> 用「日期」和「銷量」，看最近 30 筆來預測下一筆。

流程為：

1. 上傳 CSV；在伺服器本地使用 `csv.inspect` 產生欄位概況。
2. **可選**：輸入自己的 OpenAI API Key，透過 Responses API 的 JSON Schema 結構化輸出解析自然語言。預設模型為 `gpt-4.1-mini`。
3. 只有使用者指令、欄位名稱、型態、缺值比例、行數及排除欄位建議送往 API；**不送原始 CSV 列、範例值、資料檔、模型檔或 API Key 作為模型輸入**。欄名可能含敏感資訊，使用前請自行斟酌。
4. `agent_chat.validate_proposal` 只接受已知的任務、欄位和參數。不認識的目標會要求澄清，沒有時間欄不能建立時間序列計畫。CSV 欄位、LLM 輸出皆屬不可信內容。
5. 只有在介面上再次審核模型、目標、時間／群組切分、排除欄位並按下「核准並開始訓練」後，才會呼叫 `registry.run('csv.train', ..., approved=True)`。
6. 當次訓練結束後顯示**原本訓練核心產出的真實指標**，並提供 `training_data.zip` 下載。

`gpt-4.1-mini` 的 API 存取、帳單與可用性受 API 帳戶狀態影響。**ChatGPT Plus 方案不包含 API 免費額度**。這個功能不會替你申請或保存 API Key 到 GitHub。若不使用額外 API，仍可使用原始 AI Agent 工作台或本機 ChatGPT MCP。

### 與 ChatGPT MCP 共用模組

`chatgpt_server.py` 新增兩個唯讀工具：

- `list_agent_capabilities()`：列出程式已註冊的功能名稱與是否需要核准。
- `run_agent_read_tool(dataset_id, capability, ...)`：只允許 `csv.inspect` 或 `csv.plan`，並直接重用 `agent_hub` 註冊中心。

**開始訓練仍使用原本的 `start_training`**，由本機排程服務管理工作；讀取結果使用 `get_training_result`。不可從唯讀工具繞過訓練限制。若你希望在 ChatGPT 網頁或手機上的這段對話直接控制本機程式，仍須先建立可被該客戶端使用且已授權的 MCP 連線。GitHub、Streamlit Cloud 站點**不會因為新增上述程式碼就自動連接到本對話**。

### 安全及部署說明

- API Key 透過密碼欄位輸入，保留於目前 Streamlit 工作階段，不寫入磁碟、原始 CSV 或版控。**部署公開網站時請不要硬編個人金鑰**。
- AI 不能執行任意命令或 Python 程式；模組需明確註冊，且要求核准的功能仍受程式限制。
- 自然語言助手不保證理解所有模糊業務需求；資料洩漏、訓練／測試資料重疊仍須人工核對。
- 此版本只會呼叫外部 API 來理解意圖，**訓練、補值、斷詞、分割與評估仍在 Streamlit 主機上執行**。
- 本機測試：`python -m unittest tests.test_agent_chat` 或 `python -m unittest discover -s tests -v`。網路/API 真實使用需另外提供你自己的 API Key 驗收。
