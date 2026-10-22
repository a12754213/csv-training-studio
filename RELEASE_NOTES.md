# CSV Training Studio v2.2.0

新增可見的訓練特徵排除、真正的時間序列預測及 ChatGPT 本機訓練介面。

- 表格：多選不參與訓練的欄位，輸出採用／排除紀錄；排除欄不再是模型輸入。
- 時間序列：歷史視窗 + Ridge／Random Forest，嚴格時間交界、Naive 比較、模型與預測匯出。提供本機選用 LSTM 與 .keras 匯出；尚未提供 GRU。
- ChatGPT：SETUP_CHATGPT.bat 安裝本機 MCP 依賴並產生設定；需在支援本機工具的客戶端完成一次連接。雲端對話無法自動讀取 Windows Python 或本機路徑。
- 本機網頁可以查看並下載 ChatGPT 工作結果；自動化與網頁共用訓練核心。

使用 START_WINDOWS.bat 開啟本機網頁；時間序列見 docs/TIME_SERIES.md，對話流程見 docs/CHATGPT_LOCAL.md。
完整測試說明見 VALIDATION.md。GitHub Release 由 CI 通過後自動產生；雲端站台操作和使用者本機 ChatGPT 連線需分別驗收。

- AutoML：比較有限候選模型，使用內層驗證挑選，測試集最後才評估。MCP 提供任務與特徵建議工具。
- 本機 LSTM：執行 SETUP_LSTM.bat；時間驗證 EarlyStopping、最佳輪數重訓、獨立模型重載。Windows 原生安裝預設 CPU，GPU 需 WSL2。
