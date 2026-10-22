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
