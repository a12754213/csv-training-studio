# Portable Git history

當 Release ZIP 附有 `CSV_Training_Studio.bundle` 時，它包含提交、分支與標籤，並非 Python 環境或使用者資料。

```powershell
# 在專案根目錄執行，還原到旁邊的新資料夾
git clone .\history\CSV_Training_Studio.bundle ..\CSV_Training_Studio_git
```

原始 v2.0.0 與部署版 v2.1.0 均可從此歷史查看。連接 GitHub 前，依 `docs/GITHUB.md` 移除 bundle 的本地 origin。
自動產生的 GitHub Source code ZIP 不包含 bundle；Release workflow 另產生含 bundle 的下載包。
