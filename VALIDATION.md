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
