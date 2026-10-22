# 線上使用：GitHub + Streamlit Community Cloud

GitHub 保存程式與歷史；Streamlit 主機執行 Python、處理 CSV、提供瀏覽器介面。
GitHub Pages 不支援本專案所需的 Python 後端。

## 雲端套件安裝問題排查

Cloud 偵測根目錄、與 `app.py` 同層的 `requirements.txt`，其中包含 `joblib==1.5.3`；本地安裝則使用 `requirements.lock.txt` 固定完整直接和間接相依。新加的 `cloud-dependencies` GitHub CI 工作會驗證在 Python 3.12 新環境安裝 Cloud 清單後可以匯入 `joblib` 和 `preprocessing`。

若 Cloud 仍顯示 `ModuleNotFoundError`：請確認部署 branch `main` 和入口 `app.py`，到 Streamlit **Manage app → Logs** 找到套件安裝階段，再使用 **Reboot** 重新啟動及重新嘗試。既有 App 的 Python 版本無法在部署後直接修改；若有版本不符，應先保存 App 網址和設定，再依官方流程重建。GitHub 的測試成功不代表 Streamlit Cloud 主機已重建成功。

## 目前已建立的 Streamlit Cloud 網址

使用者提供的 App 網址：https://csv-training-studio-nz7xft3au8v8d6pcrjrnkd.streamlit.app/

健康檢查紀錄：https://github.com/a12754213/csv-training-studio/actions/workflows/cloud-smoke.yml

Cloud 健康檢查現在由 GitHub Runner 的 Chromium 真正載入 App 頁面，確認 Streamlit 標題顯示；即使成功，也不保證 CSV 上傳、補值、訓練和 ZIP 匯出已在雲端驗收。

## 直接部署這個儲存庫（實際填寫值）

- Streamlit 登入與建立入口：https://share.streamlit.io/
- Repository：`a12754213/csv-training-studio`
- Branch：`main`
- Main file path：`app.py`
- Python：`3.12`（Advanced settings）
- 可用於「Paste GitHub URL」的檔案：https://github.com/a12754213/csv-training-studio/blob/main/app.py

**注意：** 上方已列出使用者提供的真實 App 網址。此段的 GitHub 參數可用於日後重新部署或建立另一個 App。

## 首次部署

1. 完成 [GitHub 發布](GITHUB.md)。儲存庫根目錄必須直接看得到 `app.py`、`requirements.txt` 與 `.streamlit`。
2. 登入 https://share.streamlit.io/ ，授權它存取這個 GitHub 儲存庫。
3. 建立 App，選擇對應 repository。
4. Branch 選 `main`，Main file path 填 `app.py`。
5. 在 Advanced settings 選 **Python 3.12**。`.python-version` 供本地工具使用，不代替這個選項。
6. 不需要 API key 或 secrets。確認 App 的觀看權限符合自己的需求，再按 Deploy。
7. 開啟部署後平台實際提供的 `https://…streamlit.app/` 網址，先試三個內建範例。

這些設定已可用於部署，但必須由登入平台的帳號完成 GitHub 授權與 App 建立。
設定檔沒有放假網址，也沒有宣稱尚未完成的平台部署已成功。

## 後續更新與回溯

平台追蹤你指定的 GitHub 分支。將修改提交到 `main` 後，它會依程式與相依設定更新 App。
預設這不是「等待 GitHub CI 成功才部署」的 gate；要讓上線前先測試，請透過分支／PR，
並在 GitHub 的 branch rules/ruleset 設定必須通過 CI 才能合併到 `main`。規則的可用性依帳號與方案而定。
不要把試驗改動直接推到線上使用的 `main`。

需要回復時，在新分支建立回復提交，檢查測試再合併；見 [版本回溯](VERSION_CONTROL.md)。
`git switch --detach v2.1.0` 只切換本機，不會改變線上版本。

## 資料與資源

- 上傳的 CSV 會傳到執行 App 的伺服器。機密資料優先用本地版，或部署在你管理的主機。
- 程式使用每個連線的 Streamlit session state 保存結果，不自行把資料寫入 repository。
- 重新整理、重啟、重新部署或工作階段結束後，結果可能消失；請下載 ZIP 保存。
- 目前沒有帳號系統、共享資料庫、背景工作佇列，也不保存跨連線工作紀錄。
- 程式檢查上限仍是 30 MB／20 萬列／500 欄，這不是任何主機都能處理到上限的效能保證。
- 文字欄位多、詞彙量大或多人同時訓練可能耗用較多 RAM；雲端資源不足時改用本地／自己的主機。
- 本流程是 CPU 的 scikit-learn 工作，不需要 CUDA 或 NVIDIA 顯卡。
- 私人 GitHub repository 與 App 觀看權限是兩項設定，部署時兩者都要確認。

## 官方文件

- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
- https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site
