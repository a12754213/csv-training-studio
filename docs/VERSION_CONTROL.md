# 版本管理與回溯

## 這次的版本

- `v2.0.0`：你提供的原始專案，保留完整內容。
- `v2.1.0`：加入一鍵啟動、固定相依版本、雲端部署準備、自動測試與 Release 打包。
- `v2.1.1`：修正 Windows UTF-8 測試／匯出往返。
- `v2.1.2`：確保 Release 歷史包含可還原的 main 分支。
- `v2.1.3`：補充經驗證的 CI 狀態，對齊部署說明與版本資訊。

`main` 放可用版本；`feature/功能名稱` 放進行中的修改；tag 為已發布的固定版本。
`CHANGELOG.md` 說明差異；`version.py`、tag 和 Release 版本要一致。
標籤不應搬移覆蓋；發現問題請發布新的修正版。

目前 GitHub 已保留 `versions/v2.0.0`、`versions/v2.1.0` 分支作為原始快照。
下載包內的歷史可能另含相同名稱的 tag；在 GitHub 尚未建立舊版 tag 時，
可用 `origin/versions/v2.0.0` 或 `origin/versions/v2.1.0` 查看。

## 日常修改（已安裝 Git）

先設定你自己的 Git 提交名稱與 email（可使用 GitHub 提供的 noreply email）。

```powershell
git switch main
git pull --ff-only
git switch -c feature/new-report
# 編輯、檢查、測試
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
git status
# 只加入此次修改的程式，不要直接加入私人資料
git add app.py
git commit -m "Add new report view"
git push -u origin feature/new-report
```

在 GitHub 建立 Pull Request，通過 CI 並檢查後合併。要強制這個流程，另設定 main 分支保護規則。

## 回溯有三種不同目的

### 只想下載某個舊版使用

到 GitHub → Releases → 選版本 → 下載 ZIP，解壓到另一個資料夾。
v2.1.0 起的 Release 含 `START_WINDOWS.bat`；原始 v2.0.0 尚未提供一鍵安裝。
保留新版資料夾，方便比對。不要把舊版檔案直接覆蓋進正在跑的環境。

### 想在本機查看／測試指定版本

在 Git clone 中：

```powershell
git fetch origin --tags
git status
# 先提交或自行備份未提交的修改，再切換
git switch --detach v2.1.0
.\START_WINDOWS.bat
# 回到主要分支
git switch main
```

一鍵啟動會核對該版本的 `requirements.lock.txt`（v2.1.3 以前為 `requirements.txt`）。原始 v2.0.0 需依它自己的 README 手動啟動。
也可以在乾淨工作目錄執行 `git worktree add --detach ../studio-v2.1.0 v2.1.0`，獨立試用舊版本。

### 想讓線上版本撤銷某次改動

先找出該筆一般提交（非 merge commit）：

```powershell
git switch main
git pull --ff-only
git log --oneline -10
git switch -c fix/revert-change
git revert 提交SHA
# 安裝相依與測試，接著推送並開 PR
git push -u origin fix/revert-change
```

`git revert` 新增一筆反向提交，保留原本歷史；合併 PR 到部署分支後，線上版本才會更新。
若要撤銷 merge commit，需要另外選擇正確 parent，不要直接套用上面的單筆示例。
本文件不使用 `reset --hard` 或 force push 覆寫共享歷史。

## 發布下一版

`main` 的 CI 通過後，Publish tested version 會為尚未發布的 `version.py` 版本
建立 tag 與 Release ZIP。已發布版本不會被覆蓋；每次要發布新版請先增加版本號。
此流程只處理同一儲存庫 main 分支的 push 測試，不處理外部分支或 Pull Request 的程式碼。

以下 tag 流程仍可手動使用：

1. 從 feature 分支修改程式，更新 `version.py`（例如 `2.1.1`）、`CHANGELOG.md` 和 `RELEASE_NOTES.md`。
2. 若更新套件，先改 `requirements.in`，更新 Cloud 的 `requirements.txt`、重新產生 `requirements.lock.txt`，再跑全套測試。
3. PR 合併到 main 後：

```powershell
git switch main
git pull --ff-only
git tag v2.1.1
git push origin v2.1.1
```

Release workflow 會先跑 Linux / Windows 測試，再核對版本、建立 ZIP 與 SHA256SUMS.txt、發布 Release。
它不會替你把 Streamlit App 初次建立好。測試失敗時不發布該版，先修正再決定下一個版本。
GitHub 的 Actions 政策、額度及權限仍需允許 workflow 執行。

## 資料和模型的版本

Git 追蹤程式，不會自動記錄你上傳過的 CSV、訓練結果或下載檔。
`data/`、`outputs/`、`models/` 與模型／資料副檔名預設忽略；三個合成 demo CSV 會追蹤。
已被 Git 追蹤的檔案不會因後來加入 `.gitignore` 自動停止追蹤。
請用獨立備份保存原始 CSV 和每次訓練包；每個包包含版本、設定、套件版本和處理規則。
舊模型使用原本的資料包／環境；程式回溯不保證 sklearn 模型跨版本相容。

## 相依套件更新

維護者可安裝 uv 後執行：

```powershell
uv pip compile requirements.in --universal --python-version 3.12 --no-emit-index-url --output-file requirements.lock.txt
```

`requirements.lock.txt` 鎖定直接及間接相依；Windows / Linux 依環境 marker 安裝對應項目。Cloud 的 `requirements.txt` 是直接相依清單，需要與 `requirements.in` 中的指定版本同步。
Python 固定 3.12 小版本系列，下載的修補版可能不同；這不是作業系統或二進位映像的完整快照。
