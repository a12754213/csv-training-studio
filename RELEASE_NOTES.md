# CSV Training Studio v2.3.1

這次是 v2.3.0 AI Agent 的介面與部署維護更新，原始 CSV 訓練核心保持不變。

- **修正頁首遮擋**：首頁與「AI Agent / AI Chat」全面共用安全間距 CSS，支援狹窄螢幕及 iOS safe-area；放大中文字標題行高，避免頂端被 Streamlit 固定工具列蓋住。
- **完善驗收**：Cloud GitHub Actions 在 Chromium 啟動本地 Streamlit，檢查桌機／手機寬度的大標題位置、兩個 Agent 頁面導覽，接著檢查實際公網版本。
- **辨識過期部署**：若 Cloud 公網仍為 v2.2.x 或 v2.3.0，明確回報「STALE DEPLOYMENT」，不再誤稱整個 UI 無法開啟。
- **補齊測試**：包含各頁可渲染與版面 CSS 迴歸測試。
- **保留全部功能**：原本的 CSV 分析、TF-IDF、AutoML、時間序列、可選自然語言 AI Chat、本機 MCP 均保留。

**雲端注意事項：** GitHub CI／本地瀏覽器通過不表示 Streamlit Cloud 已自動部署。若雲端網站仍顯示舊版，
需由 Streamlit Cloud 帳號在 Manage app 確認分支 `main`、入口 `app.py` 並查看 Logs／Reboot。詳細操作請見 `docs/DEPLOY.md`。

本機 MCP 的自動化測試不等於使用者自己的 ChatGPT 客戶端已連接。連接步驟仍在 `docs/CHATGPT_LOCAL.md`。
