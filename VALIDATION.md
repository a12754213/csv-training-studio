# v3.2.0 整合驗收（2026-10-24 台北時間）

- 已在本次工作環境安裝 requirements.txt 與 MCP，執行完整單元／Streamlit AppTest：115 項，113 通過、2 項 TensorFlow 選用測試略過。其後新增的 MCP 工具註冊與自然語言動態／影片路由，連同相關回歸測試共 19 項通過。
- Chromium 桌面 1280px、手機 390px，首頁及全部進階／CSV 模組導覽與標題檢查通過。
- Chromium 真實 CSV 流程通過：示範資料整理／訓練／下載含 model.joblib 的 ZIP；上傳 CSV；資料分析 Agent 訓練／下載；AI Chat 無 Key 的明確提示。
- 實際向 TWSE 取得 2330 最近六個月份：119 筆有效成交列，截至 2026-10-22，沒有缺月份或無效列。趨勢統計、五筆跨度時間回測、139,935-byte 模型 ZIP 產生成功。這是本次取得資料的驗收快照，不保證將來有相同資料或分數。
- 本次實際回測模型 MAE 約 101.46、Naive MAE 約 74.47，模型未勝過基準。UI 正確顯示此限制；此項不作為投資績效主張。
- 新測試覆蓋未來日期／異常價格排除、私有網址與未知參數拒絕、缺月份不回測、訓練時間隔離、匯出重載、搜尋失敗保留價格、來源失敗隔離、摘要失敗保留原文、空來源狀態、變更任務／跨度清除舊結果及 CSV 跨頁交接。
- 未持有使用者 Brave／OpenAI Key，因此真實付費搜尋與 AI 報告未完成帳戶層級驗收；整合控制流程以測試替身驗證。
- 尚未完成使用者的 ChatGPT 客戶端連線、隔離瀏覽器部署、YouTube 帳戶環境驗收與常駐排程。程式接口存在不代表這些服務已啟用。

以下保留舊版驗收歷史：

# v2.2.0 驗收紀錄（2026-10-22）

本次開發環境 Python 3.12，完整 unittest 55 項通過；實際 Streamlit HTTP 啟動通過。

新增涵蓋：

- AutoML 在獨立驗證集挑模型；更改保留測試答案不影響選模結果。
- TensorFlow 2.21 實際 LSTM 訓練、最佳 epoch 重訓、.keras 與 joblib 匯出、新程序重載推論；也測試納入 AutoML。

- 排除欄位即使被指定為數值，也不會進入模型；省略排除欄仍可對新資料預測。
- 修改 UI 排除／歷史跨度設定會使舊訓練與下載結果失效。
- 單一序列的視窗對齊、交界標籤隔離、缺目標不壓縮時間軸、Naive 對齊。
- 修改測試期未來數值不會改變訓練前處理統計或模型參數。
- 時間序列 ZIP 解壓後，在新的 Python 子程序成功重新載入 model.joblib、預測並重訓。
- 原有中英文文字／單位模型匯出後的新程序重載測試保持通過（jieba 已安裝）。
- 真實 MCP STDIO：握手 → 列工具 → 匯入原始 CSV → 背景訓練 → 輪詢 → 讀取 ZIP resource。
- 上傳原始檔及 ZIP 的 SHA256、一個工作資料夾僅一個服務、路徑越界拒絕、中斷／失敗狀態。

GitHub CI 另在 Linux 固定依賴、Windows 中文及空白路徑安裝／MCP 設定、Cloud 最小依賴執行驗證。各次執行結果以 GitHub Actions 紀錄為準。

仍需在使用者環境驗收：ChatGPT 桌面帳號新增連接、附件從對話轉入 Windows inbox、結果附回對話；本次雲端工作環境沒有這台 Windows 的存取權。Streamlit Community Cloud 的線上狀態也須獨立檢查，不以單元測試代替。

---

# Cloud 依賴安裝診斷與調整（2026-10-22）

使用者回報 Streamlit Cloud 的 `preprocessing.py` 在 `import joblib` 時出現 `ModuleNotFoundError`。原 `requirements.txt` 確實宣告了 `joblib==1.5.3`，因此不能把缺少宣告當作根因。

改為 Cloud 直接依賴 `requirements.txt` 與本地完整鎖定 `requirements.lock.txt` 兩套用途。GitHub Actions 另外執行 `cloud-dependencies`，從乾淨 Python 3.12 Linux 環境使用 Cloud 清單安裝並 import `joblib`、`sklearn`、`pandas`、`numpy`、`scipy`、`streamlit`、`jieba`、`preprocessing`；此工作已成功。Cloud 真正部署需另檢查 Streamlit Logs 與網站瀏覽器結果，不能因 CI 成功便稱網站已修好。

---

# GitHub 遠端驗證紀錄（v2.1.2；2026-10-22 查核）

- [GitHub CI](https://github.com/a12754213/csv-training-studio/actions/runs/39633174924) 完成：Linux 與 Windows jobs 皆 success。
- Windows job：在含中文及空格路徑完成第一次獨立 Python 安裝、重複 setup、unittest 與實際 HTTP 啟動檢查。
- Linux job：安裝 requirements、環境檢查、unittest 與 HTTP 啟動檢查全數通過。
- [GitHub 自動發布](https://github.com/a12754213/csv-training-studio/actions/runs/39633377952) success，已產生 v2.1.2 ZIP 與 SHA256SUMS.txt。
- 以上是 GitHub Hosted Runner 的驗證；尚未直接操控使用者電腦，亦不代表 Streamlit Community Cloud 已建立 App。更新後各版仍以該版 Actions / Release 結果為準。

---

# v2.1.1 Windows 編碼修正

首次 GitHub CI：Linux 全部通過；Windows 完成獨立環境安裝和介面測試，
但兩個匯出往返測試碰到系統預設編碼問題。
此版將命令列輸出、測試 JSON 讀取及子程序解碼明確設為 UTF-8。
本地 33 項測試已通過；最新 Windows / Linux 遠端結果請看儲存庫的 Actions。

新增 main 的 CI 成功後自動發布新版本，已發布版本不覆蓋。
GitHub 原始版及部署版快照在 versions/v2.0.0、versions/v2.1.0 分支。

---

# v2.1.0 驗證紀錄

日期：2026-10-21。基於使用者上傳的 v2.0.0，使用合成資料驗證。

已在 Linux / Python 3.12.14 的獨立環境安裝鎖定依賴並通過 **33 項 unittest**：
原有 31 項（包含 2 項 Streamlit AppTest）及新增 2 項部署回歸測試。
三個內建範例均完成整理 → 基準訓練 → 下載；匯出包在獨立程序中重新訓練／預測也通過。
新增測試確認埠已占用時停止，以及訓練包包含自己的 version.py。

另已通過：全部鎖定依賴版本檢查；從不同工作目錄啟動真實本地 launcher，
HTTP `/_stcore/health` 回傳 200；結束後清除測試伺服器。

PowerShell 7.6.7 parser 已驗證兩份 PowerShell 腳本語法；Windows uv 發行檔的
SHA-256 與壓縮包內 `uv.exe` 位置已核對。Python、Bash、TOML 與 workflow YAML
已做語法／解析檢查。語法檢查不等於已完成 Windows 實機安裝驗證。

驗證命令：

```sh
python scripts/check_environment.py
python -m unittest discover -s tests -v
python scripts/smoke_start.py
```

限制：Windows 下載／雙擊流程、Docker 容器與真實 Streamlit Cloud 尚未在對應平台實測。
GitHub CI 已設定 Windows PowerShell 5.1 首次安裝、PowerShell 7 再次啟動、
含中文與空格路徑、完整測試與 HTTP 啟動檢查；需推送到 GitHub 後才能得到遠端結果。
此處不把「已寫好 CI」記為「遠端 CI 已通過」。

以下保留原始 v2 的檢查紀錄供參考。

---

# v2 驗證紀錄

日期：2026-10-21。使用合成資料驗證，尚未針對你的實際 CSV 驗收。

執行環境：Python 3.12.14、pandas 2.2.3、NumPy 2.3.5、SciPy 1.17.0、
scikit-learn 1.8.0、joblib 1.5.3、Streamlit 1.66.0、jieba 0.42.1。

29 項後端測試已通過（原有 16 項、新增 13 項），包含：

- Big5／分隔符號讀取，前導零及有效 NA 標記保存。
- 重複欄名、欄位數不一致、非法回歸標籤、罕見類別切分錯誤。
- 缺失目標隔離、完全重複列移除。
- 補值統計只來自訓練集，測試集非空不影響訓練集空欄處理。
- 分組無重疊、同一時間點不跨集合。
- 新類別、轉數值失敗、必要欄位缺失。
- 稀疏輸出與類別欄維度限制。
- sklearn clone 及 Pipeline 交叉驗證。
- 分類／回歸訓練與預測。
- 匯出 ZIP → 解壓 → train.py → model.joblib → predict.py 的完整往返。
- 評論／數值／單位的類型辨識，以及型號、前導零代碼保護。
- 自訂中文詞、停用詞、英文大小寫與字典實例隔離。
- TF-IDF 詞彙及 IDF 僅取自訓練文件；測試集的新詞不擴充字典。
- 按時間切分時，測試集的新詞與新量綱均不影響訓練特徵。
- 空詞彙、低頻篩選後無詞彙、缺失文字、長度截斷與特徵數上限。
- 長度、重量、容量、時間、比例、溫度換算，以及幣別隔離。
- 拒絕猜測複合尺寸、範圍、裸 $、逗號小數與型號。
- 解析失敗、未知量綱、缺失指示與關閉單位換算的獨立欄位。
- 混合文字／單位特徵支援 sklearn clone 與 Pipeline 交叉驗證。
- 混合範例匯出詞彙、IDF、預覽及新模組後，在獨立程序重新訓練、載入與預測，結果一致。

另有 2 項 Streamlit AppTest 介面測試通過，合計 31 項：
三個範例（客戶流失、房價、評論與單位）的啟動 → 整理 → 基準模型 → 打包，
以及修改自訂詞／單位換算設定後清除舊結果並重新整理。
這是介面自動化檢查，不是使用者 Windows 電腦上的實測。

測試指令：`python -m unittest discover -s tests -v`。
AppTest 在未啟動 Streamlit 伺服器的測試環境可能顯示 `missing ScriptRunContext` 提醒；
上述測試已檢查介面沒有程式例外或錯誤訊息。

Python 3.10 為程式語法與相依版本的相容設計；此處實際執行驗證使用 Python 3.12。
繁體中文的斷詞品質、單位欄的業務含義與模型準確率，仍需用實際資料及預覽驗收。
