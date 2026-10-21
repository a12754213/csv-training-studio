# CSV Training Studio · v2

把含數值、類別、評論文字與單位的 CSV 整理為可訓練的稀疏特徵，並保留相同規則處理新資料。

**v2 新增：中文／英文斷詞、TF-IDF、自訂詞與停用詞、數字與單位拆分、相容單位換算、處理預覽及詞彙匯出。**

**流程：CSV → 概況與缺值分析 → 選擇目標 → 先切資料 → 訓練集 fit 補值／編碼／縮放 → 匯出 X/y → 基準模型。**

## Windows / Anaconda 啟動

建議建立獨立環境，避免改動既有課程、ComfyUI 或 OneTrainer 的套件：

```powershell
conda create -n csvprep python=3.12 -y
conda activate csvprep
cd "C:\你解壓縮的位置\CSV_Training_Studio"
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

支援的程式語法為 Python 3.10+；已用 Python 3.12 驗證。若你要沿用 `py310_env`，
可先 `conda activate py310_env` 再安裝套件；pip 會選擇支援 Python 3.10 的版本。
請注意安裝可能調整該環境既有套件，因此優先建議新的 `csvprep` 環境。

啟動後在瀏覽器開啟 http://127.0.0.1:8501 。再次啟動只需要啟用環境、進入資料夾，
執行 `python -m streamlit run app.py`。PowerShell 允許執行腳本時，也可用 `./start.ps1`。

從第一版升級：解壓本版到新的資料夾，在該資料夾重新執行 `python -m pip install -r requirements.txt`，
這會安裝新增的 jieba 相依套件。請用原始 CSV 重新整理與訓練；既有資料包應保留其原本的程式與環境。

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

| 項目 | v2 行為 |
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

- 針對含文字特徵的表格分類／回歸；不是完整 AutoML、語意理解、影像或多步時間序列系統。
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

本專案不需要 API key，不會將 CSV 傳給第三方 AI 模型。
