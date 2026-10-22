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
