# 本地部署

本地 Windows、Linux 與 Docker 使用 `requirements.lock.txt` 鎖定直接與間接套件；Streamlit Community Cloud 另使用精簡 `requirements.txt`。不要拿雲端清單覆蓋本地鎖定檔。


## Windows 11 x64：雙擊啟動

把整個專案解壓到固定位置，雙擊 `START_WINDOWS.bat`。不要直接在 ZIP 預覽中執行。
支援 PowerShell 7，也能使用 Windows 內建的 PowerShell 5.1；啟動器只為此次程序設定腳本執行方式。
第一次下載 uv 0.13.4，驗證固定 SHA-256 後解壓，再下載 Python 3.12 並建立 `.venv`。
程式不要求系統管理員，也不調整系統 PATH、Conda 或 Windows Python 登錄。

首次準備需要網路；已完成安裝後，套件與設定未變更時可離線啟動。
軟體下載與安裝可能需要數分鐘及數 GB 可用空間，依網路與磁碟而異。
預設開啟 `http://127.0.0.1:8501`；該埠被占用會選用 8502～8520，請看啟動視窗顯示的網址。
本地啟動只監聽此電腦的 loopback 位址。

| 本地項目 | 用途 |
|---|---|
| `.runtime/uv` | 安裝工具 |
| `.runtime/python` | 專案專用 Python |
| `.runtime/cache` | 下載快取 |
| `.venv` | 此專案的套件環境 |
| `data` / `outputs` / `models` | 可自行放資料、結果與模型，Git 預設忽略 |

你的 CSV 不會因啟動器而被搬移或刪除。下載資料包請選擇自己的保存位置。
移動整個資料夾後，虛擬環境的路徑可能失效；先將 `.venv` 改名為 `.venv-backup` 再啟動重建，
確認新版正常後再自行決定是否刪掉備份。原始資料與模型不要放在 `.venv` 或 `.runtime`。

## 可選命令（PowerShell 7）

```powershell
# 只準備環境，不開啟介面
.\start.ps1 -SetupOnly

# 指定埠、不自動開瀏覽器
.\start.ps1 -Port 8601 -NoBrowser

# 檢查版本與套件
.\.venv\Scripts\python.exe scripts/check_environment.py

# 執行測試
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 常見狀況

- **防毒／組織政策阻擋**：依畫面的實際錯誤處理；不要停用防毒或組織控管。
- **下載失敗**：檢查網路能否存取 GitHub、GitHub release assets、PyPI；恢復後再雙擊。
- **uv checksum mismatch**：下載內容不符已鎖定發行檔，不會執行；重新下載專案或回報。
- **現有環境版本錯誤／啟動路徑失效**：將 `.venv` 改名保存，再重跑。不要拿 ComfyUI 的環境來覆蓋。
- **瀏覽器沒跳出**：手動開啟終端機印出的 `http://127.0.0.1:埠號`。
- **中文／空格路徑**：腳本使用完整且引號包覆的路徑；Windows CI 另有此情境。
- **Windows ARM**：本次一鍵安裝器限定 x64；可改用下列 Python 3.12 手動流程，套件平台相容性另行確認。

## 手動使用自己的獨立 Python 3.12 環境

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe scripts/serve.py
```

若用 Conda，建立新的 Python 3.12 環境後安裝 `requirements.lock.txt`，再執行 `python scripts/serve.py`。
本發行版的部署與相依套件統一以 Python 3.12 為準，不能再沿用舊 README 的 3.10 支援宣告。

## Linux / macOS

先安裝 Python 3.12，在專案內執行 `bash start.sh`；腳本會建立獨立 `.venv`、安裝套件並啟動。
再次執行時會核對套件版本，未變更便不重新下載。
也可設定 `CSV_STUDIO_PYTHON` 為 Python 3.12 的完整路徑。
本次 Linux 已驗證，macOS 未實機驗證。

## Docker（可選）

先安裝並啟動 Docker / Docker Desktop，然後在專案資料夾執行：

```powershell
docker compose up --build -d
# 瀏覽 http://127.0.0.1:8501

docker compose logs -f
# 停止
docker compose down
```

Compose 預設只把 8501 提供給本機；容器內的服務監聽 `0.0.0.0`。
此設定沒有登入管理，也不是對外公開的正式服務設定。
Docker 使用 Python 3.12 的基底映像標籤；若需要位元級固定映像，另將 FROM 鎖到經驗證的 digest。
