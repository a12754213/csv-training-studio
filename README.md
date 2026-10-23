# CSV Training Studio · v2.3.1

把含數值、類別、評論文字與單位的 CSV 整理為可訓練的稀疏特徵，並保留相同規則處理新資料。

**功能：中文／英文斷詞、TF-IDF、自訂詞與停用詞、數字與單位拆分、相容單位換算、處理預覽及詞彙匯出。**

**流程：CSV → 概況與缺值分析 → 選擇目標 → 先切資料 → 訓練集 fit 補值／編碼／縮放 → 匯出 X/y → 基準模型。**

## 🤖 AI Agent 自然語言助手（新增）

- **無 API 版本**：在側邊欄開啟「AI Agent」，上傳 CSV 後確認目標欄與訓練設定。
- **自然語言版本**：在側邊欄開啟「AI Chat」，提供自己的 OpenAI API Key 後，直接輸入「幫我預測是否流失，排除客戶編號並比較模型」。
- 模型只負責提出**可審核的計畫**，必須在網頁按「核准並開始訓練」才會真正執行。所有訓練與評估仍重用原本的 Python 核心。
- ChatGPT Plus 不包含 API 額度；不輸入 API Key 仍可使用原有 AI Agent 工作台，或依 `docs/CHATGPT_LOCAL.md` 設定本機 MCP。
- MCP 新增唯讀功能清單 `list_agent_capabilities` 與 `run_agent_read_tool`，也共用 Agent 註冊中心。**單靠雲端網站不會使目前 ChatGPT 對話自動連線到你的本機程式**。

詳細安全說明、未來新增功能方式：`docs/AI_AGENT.md`。

## v2.2.0 新增

- **明確的欄位排除多選**：編號等欄位可直接選擇不參與訓練；修改後舊結果失效，報告列出實際採用／排除的欄位。
- **時間序列模型**：指定日期、歷史視窗、未來跨度，訓練 Ridge／Random Forest／本機 LSTM，與 Naive 比較並匯出獨立模型。詳見 [時間序列](docs/TIME_SERIES.md)。
- **AutoML 選模**：一般表格與時間序列都能在訓練集內建立驗證區間，比較候選模型後再評估保留測試集。Agent 可用 `suggest_training_plan` 取得可解釋的任務與欄位建議。
- **ChatGPT 本機對話操作**：共用訓練核心的 MCP 與 CLI，支援匯入、背景訓練、結果查詢與下載；本機 Streamlit 顯示工作結果。先執行 `SETUP_CHATGPT.bat`，再做一次本機連接，詳見 [ChatGPT 設定](docs/CHATGPT_LOCAL.md)。

## 雲端部署的依賴清單

為排查 Streamlit Cloud 的 `ModuleNotFoundError: joblib`，本專案將相依套件分成兩份：

- `requirements.txt`：**Streamlit Cloud 專用精簡清單**，直接列出 `joblib==1.5.3` 等七個重要套件，放在 `app.py` 相同目錄。
- `requirements.lock.txt`：Windows 一鍵啟動、Linux、Docker 的**原有完整版本鎖定清單**。一鍵安裝維持隔離，不修改現有 ComfyUI 或 Conda。

GitHub CI 的 `cloud-dependencies` 會在全新 Python 3.12 環境用雲端清單安裝、驗證所有必要 import。若網站仍顯示缺少套件，請到 Streamlit Cloud → Manage app → Logs 檢查實際安裝紀錄，再按 Reboot；GitHub 測試成功不等於 Streamlit Cloud 安裝成功。

## Streamlit 線上網址

- **線上開啟：** https://csv-training-studio-nz7xft3au8v8d6pcrjrnkd.streamlit.app/
- **服務存活檢查：** https://github.com/a12754213/csv-training-studio/actions/workflows/cloud-smoke.yml

使用者已提供上方 Streamlit Community Cloud App 網址。可以透過瀏覽器上傳 CSV；上傳內容會送往雲端處理。請使用本地版處理機密資料。雲端 HTTP health 通過不代表 CSV 操作全流程已實測。

## 下載後直接使用（Windows 11 x64）

1. 將整個 ZIP 解壓縮到固定資料夾，例如 `F:\CSV_Training_Studio`。
2. 雙擊 **`START_WINDOWS.bat`**。
3. 第一次會下載專案自己的 Python 3.12、安裝固定版本套件，完成後自動開啟瀏覽器。
4. 之後仍雙擊同一個檔案。視窗要保持開啟；按 Ctrl+C 停止。

不必先安裝 Python／Conda／Git，也不需要系統管理員。首次安裝需要網路與可寫入的磁碟空間，
這是自動安裝版，不是包含所有套件的離線安裝包。需要連線到 GitHub、Python 發行檔和 PyPI。
Python、套件與快取放在此專案的 `.runtime` / `.venv`，不更改你的 ComfyUI、OneTrainer 或課程環境。
已完成安裝且套件未變更時可以離線啟動。遇到問題請看 [本地部署與排錯](docs/LOCAL.md)。

## GitHub、線上使用與版本回溯

**部署這份程式：** 前往 [Streamlit Community Cloud](https://share.streamlit.io/) → Create app → 選擇已有 GitHub 專案，填入 repository `a12754213/csv-training-studio`、branch `main`、entrypoint `app.py`，並在 Advanced settings 使用 Python 3.12。也可以貼入 [GitHub 上的 app.py](https://github.com/a12754213/csv-training-studio/blob/main/app.py)。Streamlit 帳號授權與初次建立 App 必須由帳號持有人完成；正式網址以 Streamlit 實際提供的網址為準，不預設宣稱已上線。


| 你的需求 | 使用方式 |
|---|---|
| 保存程式與修改紀錄 | GitHub repository；`main` 保存穩定版本 |
| 回到某個版本 | Git tag / Release，例如 `v2.0.0`、`v2.1.4`；步驟見 [版本管理](docs/VERSION_CONTROL.md) |
| 瀏覽器直接使用 | GitHub 接到 Streamlit Community Cloud；見 [線上部署](docs/DEPLOY.md) |
| 本地一鍵使用 | 下載 Release ZIP → 解壓 → `START_WINDOWS.bat` |
| 容器使用 | 已安裝 Docker 時，執行 `docker compose up --build -d` |
| 每次修改自動驗證 | GitHub Actions 執行 Linux / Windows 測試 |
| 發布新版下載包 | 更新版本號並推送 main；CI 通過後自動建立 tag 與 Release ZIP |

GitHub Pages 只能提供靜態網頁，無法直接執行本專案的 Python 訓練後端。
線上版本使用 Streamlit 主機運算，資料會傳到該主機；本地版本則在你的電腦運算。
程式不會把上傳 CSV 自動提交到 GitHub，也不呼叫外部 AI 模型。
下載結果及訓練模型請自行保存；程式版本回溯不會還原未保存的資料或模型。

若此 ZIP 有 `history/CSV_Training_Studio.bundle`，裡面含原始 v2.0.0 與此版的 Git 紀錄。
[第一次發布到 GitHub](docs/GITHUB.md) 有保留完整歷史的操作，也提供 `PUBLISH_GITHUB.bat`。

需要本機 LSTM 時，執行 **`SETUP_LSTM.bat`**（也會準備 MCP），再重新啟動本機網頁／ChatGPT 連接。Windows 原生安裝使用 CPU；NVIDIA GPU 需另設 WSL2。

## 第一次操作

1. 左側先選「使用示範資料」。想試新功能，選「評論與單位｜混合特徵分類」；另外保留客戶流失與房價範例。
2. 「資料概況」查看資料列、缺值比例、重複列與欄位提醒。
3. 「整理與切分」指定你要預測的目標欄位 y，並選擇分類或回歸。
4. 選合適的切分方式，檢查欄位的格式建議與處理預覽。必要時指定「文字斷詞 + TF-IDF」或「數字 + 單位」。
   在對應設定區可修改詞彙上限、自訂詞、停用詞、相鄰雙詞與單位換算。
5. 按「整理成訓練資料」，到第三頁看處理結果。
6. 可按「訓練並查看測試結果」，再按「產生可下載資料包」下載 ZIP。

**必須由你決定目標與任務。** 程式可以判斷欄位格式，但無法從任意 CSV 確定你真正想預測的事。
分類是預測「是否流失／種類」，回歸是預測「價格／數量」等數值。

## 自動處理的內容

| 項目 | 行為 |
|---|---|
| 讀檔 | 支援 UTF-8、UTF-16 BOM、Big5/CP950，並可手動選擇；自動或指定分隔符號 |
| 型態 | 先保留文字與前導零，再只依訓練資料推測數值／類別／日期／文字／數字與單位 |
| 缺值 | 預設空白；你可指定 NULL、N/A、? 等額外標記 |
| 數值 | 中位數（預設）、平均數或固定 0；可加缺值指示及標準化 |
| 類別 | 眾數或獨立缺失類別，One-Hot 編碼，合併低頻類別、處理未見過的類別 |
| 文字 | 中文 jieba 斷詞、英文與數字 token；每欄各自建立 TF-IDF，可加相鄰雙詞、自訂詞及停用詞 |
| 數字與單位 | 僅解析明確的單一數量；可換算相容單位，不同量綱／幣別分欄，保留缺失與解析失敗指示 |
| 型號與代碼 | AB123、RTX4070、00123 保留完整類別；疑似 ID 預設排除，原始資料仍保留 |
| 日期 | 自動接受明確 YYYY-MM-DD / YYYY/MM/DD，可手動指定其他可解析日期；展開年／月／日／星期／小時，統一 UTC |
| 欄位排除 | 疑似 ID、訓練集全空、常數及高缺值率欄；輸出排除理由 |
| 重複列 | 可在切分前移除完全重複列；不會因特徵相似就擅自刪除 |
| 目標缺失 | 隔離到 unlabeled_rows.csv；不補標籤，回歸的非數值標籤直接提示修正 |
| 切分 | 隨機（分類分層）、按群組、按時間；保留原始資料列對照 |
| 評估 | Logistic Regression／Ridge 基準，與 Dummy 對照，分類另有混淆矩陣及各類別指標 |

欄位角色可以手動覆寫。自動模式判錯時，可改成數值、類別、日期、文字或數字與單位；
如果訓練集沒有任何可用值，仍會排除。類型轉換失敗會視為缺值，並在報告中計數。
新資料缺少必要特徵欄會停止並指出欄名，不會默默用全空欄代替。

## 文字與數字怎麼處理

| 原始內容 | 處理方式 |
|---|---|
| 評論：`安裝簡單，低噪音的設計很滿意` | 中文斷詞後轉 TF-IDF；可將「低噪音」加到自訂詞 |
| 評論：`Good quality and easy to use` | 英文預設統一小寫，再建立單詞及相鄰雙詞特徵 |
| 尺寸：`30cm`、`尺寸30cm`、`0.3m` | 開啟換算時都得到長度數值 `0.3`，單位 `m` |
| 重量：`500g`、`0.5kg` | 都得到重量數值 `0.5`，單位 `kg` |
| 比例：`50%` | 得到比例數值 `0.5` |
| 金額：`NT$1,200`、`500美元`、`500元` | 分別保留為 TWD、USD、未指定幣別的元；不換匯 |
| 型號：`RTX4070`、`AB123`、`00123` | 不把字母或數字拆散，保留完整類別 |
| `30×40cm`、`10–20cm`、`$500`、`1,5cm` | 不猜複合尺寸、範圍、幣別或逗號小數；自動模式保留類別，強制單位模式則標記解析失敗 |

**自動建議並不代表所有欄位都要斷詞。** 城市、方案、型號等適合當類別；只有句子／描述才做文字特徵。
文字辨識會參考欄名與句子格式；短句、特殊欄名或混合錯字的單位欄，可能需要手動指定。
單位的自動判斷要求所有非缺失值均可解析，避免把代碼拆錯。正式規則仍只由訓練集決定。

### 文字設定

- 中文使用 jieba 內附字典；繁體中文與專有名詞的品質取決於字典，請用預覽檢查，必要時每行加入一個自訂詞。
- 預設不刪停用詞，避免自動刪掉否定詞。停用詞在斷詞後套用，可自行填寫。
- 預設每個文字欄最多 5,000 個特徵，包含單詞與相鄰雙詞；可設定最低文件出現次數。
- 空白文字使用空字串，不捏造句子；預設另加缺失指示欄。
- 新詞不擴充訓練詞彙表。非空文字若完全沒有命中詞彙，會得到零向量，檢查報告會計數。
- 詞彙被全部篩掉時，保留一個零值佔位特徵並提示調整設定，不會偷用測試集重建。
- 每筆文字預設處理前 20,000 字，可在介面調整；超長筆數有記錄，原始 CSV 仍完整保留。
- TF-IDF 是詞彙統計特徵，不是語意嵌入或大型語言模型；目前 token 規則針對中文、英文與數字。

### 支援的單位與缺值

| 類型 | 常用輸入 | 換算後單位 |
|---|---|---|
| 長度 | mm、cm、m、km、毫米、公分、公尺、公里 | m |
| 重量 | mg、g、kg、毫克、公克、公斤 | kg |
| 容量 | ml、L、毫升、公升 | L |
| 時間 | s、sec、min、h、hr、秒、分鐘、小時 | s |
| 比例 | %、‰ | ratio |
| 溫度 | °C、℃、°F、℉、攝氏度、華氏度 | °C |
| 貨幣 | NT$/TWD、US$/USD、CNY/RMB、EUR/€、JPY、元及明確中文幣名 | 各自幣別；元維持未指定 |

只有已知且相容的單位才換算。關閉換算後，每種單位寫法各用不同數值欄；不會將 cm 的 30 與 m 的 30 混在同一尺度。
同一欄混有長度和重量時，會各自建立數值與出現指示；訓練時未見過的新量綱不新增特徵，會在稽核中標示。
量值缺失、解析失敗或不適用時以 0 搭配指示欄表示，和真實的 0 可區分，不跨單位取平均補值。
這些 0 是標準化前的填充值；若開啟數值標準化，輸出的矩陣值會再依訓練集統計縮放。

第三頁可查看實際處理預覽與詞彙摘要；下載資料包會附 `text_vocabulary.json`（完整詞彙、欄內索引、IDF）
與 `transformation_preview.csv`（訓練集前幾筆）。`feature_names.json` 則記錄合併後完整矩陣的欄位順序。

## 匯出後直接訓練

解壓從介面下載的 `training_data.zip`，進入解壓資料夾：

```powershell
python train.py --data .
python predict.py --model model.joblib --csv 新資料.csv --output predictions.csv
```

如果換電腦或環境，先裝資料包自己的 `requirements.txt`。它會記錄產生該資料包的精確套件版本。
若目前介面已完成基準訓練，資料包直接包含模型，可以跳過 `train.py`。

需要自己換模型，可在訓練資料包中：

```python
import pandas as pd
from scipy.sparse import load_npz
from sklearn.ensemble import RandomForestClassifier

X_train = load_npz("X_train.npz")
X_test = load_npz("X_test.npz")
y_train = pd.read_csv("y_train.csv", dtype=str, keep_default_na=False).iloc[:, 0]
y_test = pd.read_csv("y_test.csv", dtype=str, keep_default_na=False).iloc[:, 0]

model = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)
print(model.score(X_test, y_test))
```

上述例子適用分類；回歸請改用回歸模型與數值 y。X 是 scipy 稀疏矩陣，
不是所有模型都接受。深度學習模型可能需要稠密陣列、float32、標籤編碼及合適的輸出層；
需依目標模型介面調整，並非任何 CSV 都能直接丟給任何模型。

## 為什麼要先 split 再補值？

假設訓練集年齡平均是 30 歲，測試集是 70 歲。如果先對全表算平均再切分，
測試集就影響了訓練規則。這裡先分開，再只用訓練集得到補值、編碼、TF-IDF 詞彙／IDF 與縮放規則；
測試資料及新資料都只做 transform。

**做交叉驗證時，必須在每一折重新 fit 前處理。** 不要直接把已對整個訓練集
整理好的 X_train 用於嚴格 CV。請讀 `raw_train.csv`，使用新的前處理器和 Pipeline：

```python
import json
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.linear_model import LogisticRegression
from preprocessing import TabularPreprocessor

cfg = json.load(open("config.json", encoding="utf-8"))
raw = pd.read_csv("raw_train.csv", dtype=str, keep_default_na=False)
target = cfg["target"]
X, y = raw.drop(columns=target), raw[target]
pipeline = Pipeline([
    ("preprocess", TabularPreprocessor(**cfg["preprocessor"])),
    ("model", LogisticRegression(max_iter=1500, class_weight="balanced")),
])
cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
print(cross_val_score(pipeline, X, y, cv=cv, scoring="f1_macro"))
```

這個 CV 範例僅適用獨立樣本分類且每類至少有 3 筆。群組資料須將分組欄排除於 X，
並以 GroupKFold 傳入 groups；時間資料需排序並使用合適的時間驗證和 gap。
不應用這個隨機範例去驗證時間／群組資料。

## 目前的界線

- 支援表格分類／回歸及單一序列的固定跨度預測；提供有限候選模型的 AutoML 比較及本機 LSTM；未提供 GRU、多序列、遞迴多步或大範圍超參數搜尋。
- 不自動修正資料的業務含義，無法保證識別所有答案洩漏欄位。
- 只有已列明格式的單一數量才解析；裸千分位數字（例如沒有單位的 1,200）、複合尺寸、範圍與含糊單位需先清理。
- 不自動處理異常值、SMOTE 或合成標籤；這些要依資料來源與任務決定。
- 資料先 split、再 fit，不等於所有洩漏都能自動避免；同人多筆、重疊時間窗仍要正確設計。
- 最多 30 MB / 20 萬列 / 500 原始欄；每個類別欄預設最多 50 個編碼欄，每個文字欄預設最多 5,000 個特徵。
- 小型結果另附 X_train.csv / X_test.csv；總矩陣超過 200 萬格只輸出 NPZ，避免稠密展開。
- joblib 請只載入自己產生且信任的檔案；模型與前處理應在相同 sklearn 環境使用。

## 檔案位置與學習順序

| 檔案 | 內容 |
|---|---|
| app.py | Streamlit 介面 |
| preprocessing.py | 讀檔、欄位分析、切分、前處理、基準評估與匯出 |
| text_features.py | 中文／英文 token、TF-IDF、單一數字與單位解析 |
| train.py | 使用訓練資料包建立模型 |
| predict.py | 套用模型與相同規則，預測原始 CSV |
| make_demo.py / samples | 合成示範資料及產生程式 |
| tests/test_pipeline.py | 原有補值、切分、未知類別與匯出往返測試 |
| tests/test_features.py | 詞彙與 IDF 隔離、單位換算、型號保護、混合特徵匯出往返 |
| tests/test_app.py | 三個示範的介面流程與修改文字／單位設定後清除舊結果 |

建議先看 `prepare_data()` 的 split → fit_transform → transform，接著讀
`TabularPreprocessor.fit()` 的數值／類別處理，最後再看 Streamlit 介面。

驗證指令：`python -m unittest discover -s tests -v`。

## 技術參考

- https://scikit-learn.org/stable/common_pitfalls.html
- https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html
- https://scikit-learn.org/stable/modules/compose.html
- https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader
- https://github.com/fxsjy/jieba
- https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html

訓練核心與 MCP 本機連接不需要 OpenAI API key。直接使用網頁時不呼叫 AI；使用 ChatGPT 操作時，工具回傳的欄位、摘要與結果會進入對話，依 ChatGPT 的存取與資料設定處理。
