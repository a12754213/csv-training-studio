# AI Agent Hub v3.2.1

統一首頁：自然語言任務 → 自動搜尋／讀取 → 圖表、來源與分析 → 接續 CSV 訓練。
新增證交所上市股票日成交分析、Ridge／Random Forest 回測、Naive 對照與模型下載。
既有 CSV、時間序列、爬蟲、多媒體、Core 與 MCP 工具保留。

自動搜尋需 Brave Search Key，AI 彙整／圖片理解／語音需 OpenAI Key。台股日成交與 CSV 不需 Key。
動態瀏覽器、YouTube、持久排程和 ChatGPT 連接仍需依文件配置環境；不代表已替帳號啟用。

詳見 docs/QUICKSTART_AGENT.md 與 VALIDATION.md。

修正 Streamlit Cloud 更新原始碼後保留舊 Python 模組的問題；入口會刷新本次變更模組，並清除舊任務狀態。
