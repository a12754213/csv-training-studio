# v2.5.0 · 2026-10-23

- 正式品牌改為 **AI Agent Hub · 多功能智慧工作台**；CSV Training Studio 成為 Hub 中保留的資料訓練模組，不再是整站標題。
- 新首頁：四個可直接開啟的獨立工具模組卡片、清楚標示能力／限制，CSV／AutoML 工作區保留在首頁下方。
- 五頁統一標題、版本資訊、RWD 排版、頁面說明與介面視覺語言；保留原有功能、頁面路徑及既有下載格式。
- 更新瀏覽器版面測試、線上冒煙測試與 CSV 訓練端到端測試，確保改版沒有影響流程。
- GitHub repo 與 Streamlit Cloud 的舊 URL 不在這次改名，以保留向下相容性。

# v2.4.0 · 2026-10-23

- 把獨立網路爬蟲、文字分析與 Agent URL 工具分流加入同一套擴充式能力註冊中心。
- 提供網頁文字和表格擷取、 CSV 訓練目標確認、GitHub/MCP 新工具與安全測試。
- 保留 v2.3.1 的資料清理、模型訓練、下載以及 AI Chat。
- 網址變更時清除舊結果；未支援影片及遞迴爬取，不能稱作完全自主瀏覽。

# v2.3.1 · 2026-10-23

- 修正首頁、AI Agent、AI Chat 固定工具列擋住第一個標題的版面問題；統一響應式 CSS 與行動裝置 safe-area。
- 在 Cloud smoke 加入本地真實 Chromium 桌面／手機版面及 Agent 頁面測試。
- Cloud 部署檢查明確辨識舊版與缺少的 Agent 導覽，避免誤判成應用程式無法使用。
- 訓練核心、模型結果與 API/MCP 的既有行為維持不變。

# v2.3.0 · 2026-10-23

- 新增可擴充 AgentRegistry、CSV 工作模組、Streamlit AI Agent 工作台。
- 新增可選 OpenAI API 自然語言對話頁、僅傳欄位摘要的結構化意圖規劃、使用者審核訓練門檻。
- ChatGPT 本機 MCP 提供註冊能力清單與受控唯讀工具；保留原本訓練工作佇列。
- 新增 Agent、MCP 與安全測試，不修改模型訓練核心或依賴。

# v2.2.0 · 2026-10-22

- 加入 AutoML 內層驗證選模、Agent 任務建議、本機 TensorFlow LSTM 與 .keras 匯出。
- 加入明確的 excluded_columns 設定、UI 多選、結果失效與實際欄位紀錄。
- 加入單一時間序列的歷史視窗、固定未來跨度、交界隔離、Ridge／Random Forest、Naive 評估、獨立預測與重訓匯出包。
- 加入 ChatGPT 本機 STDIO MCP、背景工作與原始檔校驗、Streamlit 工作下載區、CLI 與 Windows 設定入口。
- 增加因果時間對齊、未來資料不影響訓練、匯出重載、欄位排除及真實 MCP 協定測試。
- 保留 Streamlit Cloud 原有最小依賴，MCP 僅作為本機選用安裝。

# v2.1.4 — 2026-10-22

- 調整 Streamlit Cloud 相依清單，只列出必要的七個直接依賴套件（包含 joblib），減少與雲端安裝環境的衝突。
- 將原有直接／間接版本完全鎖定清單保存在 `requirements.lock.txt`，Windows 一鍵啟動、Linux、Docker 與本地驗證使用原有版本。
- GitHub CI 加入全新 Python 3.12 環境安裝 Cloud 清單、實際 import 所有主要程式依賴的回歸測試。
- 雲端建置狀態仍須從 Streamlit Cloud Logs 確認，無法由 GitHub CI 判定完成修復。

# v2.1.3

- 更新部署指南，填入實際 GitHub 儲存庫、main 分支及 app.py 入口，減少首次部署手動查找。
- 校正 README 與啟動說明的目前版本資訊，補充已通過的 GitHub Windows / Linux CI 驗證紀錄。
- 保留 v2.1.2 已驗證的前處理、模型與本地啟動行為，不變更依賴或運算邏輯。

# v2.1.2

- 修正 CI 打包時 detached HEAD 導致攜帶的 Git history 缺少 main 分支。
- 發布前驗證可從 bundle 還原 main 分支。

# Changelog

## 2.1.1 — 2026-10-21

- 修正 Windows 重新導向輸出時，中文訓練／預測訊息遇到預設編碼而失敗。
- 匯出往返測試明確使用 UTF-8 讀取 JSON 與子程序輸出。

## 2.1.0 — 2026-10-21

- Windows x64 雙擊啟動，自動下載隔離的 Python 3.12 與套件，支援 PowerShell 5.1 / 7。
- 固定相依版本、啟動前檢查環境，首次安裝後可在環境未變更時離線啟動。
- 本地 loopback 啟動、埠占用處理、服務就緒後開啟瀏覽器。
- 新增 Git 忽略規則、版本標籤、回溯說明與可攜 Git 歷史。
- 新增 Linux / Windows CI、標籤觸發 Release ZIP、SHA-256 校驗檔。
- 新增 Streamlit Community Cloud 部署說明及可選 Docker 設定。
- 介面顯示版本與本地／線上資料處理位置，訓練包包含相同版本模組。
- 保留既有分析、補值、文字／單位特徵、訓練與匯出流程。

## 2.0.0 — 原始上傳版本

保留使用者提供的完整專案，含中文／英文斷詞、TF-IDF、單位拆分與訓練流程。


## Unreleased · Modular Web Agent

- Independent web crawler and text inspection modules registered in Agent Hub.
- Standalone Streamlit crawler and tool router pages with explicit training approval.
- Public URL and robots.txt checks, size limits and MCP table import.
- Dedicated unit tests.
