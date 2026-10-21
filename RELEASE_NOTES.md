CSV Training Studio 現在可透過 GitHub 管理版本，並部署到 Streamlit Community Cloud。

本地使用：下載 `CSV_Training_Studio-v2.1.1.zip`，完整解壓後雙擊 `START_WINDOWS.bat`。
首次需網路，自動準備專案自己的 Python 3.12 與套件。Windows 一鍵版支援 x64。

包含 CSV 分析／補值、中文英文斷詞、TF-IDF、單位換算、基準訓練、資料包匯出，
以及版本回溯指南、可攜 Git 歷史、Linux／Windows 自動測試與 Release 打包。

線上部署入口為 `app.py`、Python 選 3.12，請依 `docs/DEPLOY.md` 設定平台。
本地啟動不需要 NVIDIA 顯卡、API key 或既有 Conda 環境。
請參考 `VALIDATION.md` 查看實際已驗證項目與尚未驗證的平台。
