# CSV Training Studio v2.3.0

新增可以持續擴充的 AI Agent 註冊中心、獨立資料分析工作台，以及**可選的自然語言對話**。

- Streamlit 左側 **AI Agent**：不使用外部 API，直接上傳 CSV，查看概況、確認目標與特徵排除，再沿用既有核心完成訓練。
- Streamlit 左側 **AI Chat**：可自行提供 OpenAI API Key，說明「幫我預測是否流失，排除客戶編號」。語言模型提出工作計畫，**必須由使用者再次核准**才會實際訓練。
- 自然語言請求只傳送使用者指令、欄位名稱、推測型態、缺值率和列數等摘要，不上傳原始 CSV 列資料或模型。請注意欄名本身仍可能敏感。
- Agent 工具註冊採明確白名單；未知工具、目標、切分欄不能直接執行。模型選擇、前處理、評估、訓練 ZIP 仍沿用 v2.2.0 核心。
- 本機 ChatGPT MCP 增加 `list_agent_capabilities`、`run_agent_read_tool`；自然語言 ChatGPT 端仍須另行完成 MCP 連接。
- OpenAI API 單獨計費，不包含在 ChatGPT Plus 方案。**無 API Key**仍可用 AI Agent 工作台與原本全部 CSV 功能。
- 新增安全、結構化輸出與 MCP 整合測試。

教學見 `docs/AI_AGENT.md`、`docs/CHATGPT_LOCAL.md`。本次變更不新增第三方套件。
GitHub CI 通過後自動產生可下載版本；雲端網站能否實際完成對話需用使用者自己的 API Key 另外驗收。
