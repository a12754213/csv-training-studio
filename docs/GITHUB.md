# 第一次放到 GitHub

建議名稱 `csv-training-studio`，預設私人儲存庫。公開程式是另一個決定，可以日後自行修改。
這份專案只有三份合成範例資料；自己的 CSV、模型及 secrets 不應上傳。

## 方式 A：本機發布助手（保留原始歷史）

本地使用本程式不需要 Git；只有要發布到 GitHub 才需要 Git 和 GitHub CLI。
若尚未安裝，可從官方網站安裝，或在 Windows 終端機執行：

```powershell
winget install --id Git.Git -e
winget install --id GitHub.cli -e
```

安裝完成後重新開啟終端機／檔案總管，再雙擊 **`PUBLISH_GITHUB.bat`**。
首次會用 GitHub CLI 的瀏覽器登入流程，請核對登入帳號並完成授權。不要將 token 貼到聊天或程式碼。

助手會：

1. 若還沒有 Git 儲存庫，從 ZIP 裡的 `history/CSV_Training_Studio.bundle` 還原 Git 歷史。
2. 核對工作目錄乾淨、位於 `main`；不自動提交你另外加入的檔案。
3. 在當前 GitHub CLI 登入帳號下建立 **私人** `csv-training-studio` 儲存庫。
4. 推送 `main` 與版本標籤；GitHub Actions 接著測試，通過才建立 Release。
5. 印出真實儲存庫網址。依 [線上部署](DEPLOY.md) 建立 Streamlit App。

同名儲存庫已存在或 origin 指向別處時會停止；不覆寫舊儲存庫、不 force push。
如需不同名稱：

```powershell
.\scripts\publish_github.ps1 -RepoName 'my-csv-studio'
```

若原先登入的 GitHub CLI 權限不足以推送 `.github/workflows`，依 GitHub 的提示補足 workflow 權限，
再重新執行。公開／私人設定不會因重跑助手而被更改。
如果原始 ZIP 沒有 bundle（例如 GitHub 自動產生的 Source code ZIP），請改用 Release ZIP 或 git clone。

## 方式 B：GitHub Desktop

1. 安裝 Git / GitHub Desktop，登入自己的 GitHub 帳號。
2. 想保留本次完整歷史，先在解壓資料夾執行：

```powershell
git clone .\history\CSV_Training_Studio.bundle ..\CSV_Training_Studio_git
cd ..\CSV_Training_Studio_git
git remote remove origin
```

3. GitHub Desktop → File → Add local repository，選剛建立的 `CSV_Training_Studio_git`。
4. 按 Publish repository，名稱填 `csv-training-studio`，保留 **Keep this code private**。
5. 推送標籤：在該資料夾執行 `git push origin --tags`。

Desktop 新建 repo 也能開始版本控制，但若只上傳檔案而沒有匯入 bundle，就不包含之前的 v2.0.0 提交。
GitHub 網頁的 Upload files 只能上傳檔案，無法匯入 Git bundle 內的歷史。

## 之後換電腦

從 GitHub clone 儲存庫，或下載 Releases 的指定版 ZIP。
直接下載 ZIP 適合使用；要修改、提交與回溯則建議 Git clone。

```powershell
# 將下面占位字換成 GitHub 畫面上的真實帳號及儲存庫
git clone https://github.com/YOUR_ACCOUNT/csv-training-studio.git
```

Git 不會下載 Python 環境，換電腦後雙擊 `START_WINDOWS.bat` 即可重新準備。

## 本次尚未代做的帳號動作

檔案內的 workflow 和發布助手不等於已在你的帳號建立 repository 或線上 App。
請以 GitHub 實際出現的 repository、Actions 結果、Release，以及 Streamlit 提供的網址為準。
