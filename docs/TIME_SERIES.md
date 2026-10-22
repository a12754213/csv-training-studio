# 時間序列訓練

v2.2.0 新增真正的歷史視窗與未來目標；原先「按時間切分」仍是一般表格的切分方式。

1. 上傳 CSV，或選「每日銷量｜時間序列」範例。
2. 選「時間序列｜預測未來數值」，指定時間欄、目標數值欄。
3. 選「不參與訓練的欄位」。另外要用的歷史數值欄需明確選入，預設僅使用目標的歷史值。
4. 設定 lookback、horizon、最後測試比例與模型，按「建立時間序列資料」。
5. 第三頁訓練，檢查模型與 Naive 的 MAE／RMSE，再下載時間序列模型包。

模型提供 Ridge、Random Forest、**本機 LSTM** 與 AutoML 比較。LSTM 需先執行 `SETUP_LSTM.bat`，再透過本機啟動器開啟；Streamlit Cloud 不安裝 TensorFlow。用最近 L 筆觀測預測起點之後第 h 筆，輸出一個未來端點，不是連續 h 筆未來。單位為資料筆數；交易日、缺日期不能直接視為日曆天。

## 時間對齊

對未來目標位置 t，輸入是 `[t-h-L+1, ..., t-h]`，標籤是 y[t]；所有額外特徵也使用同一段過去視窗。每個目標時間嚴格晚於輸入視窗結束。

以較早標籤訓練、較晚標籤測試；並移除交界處標籤晚於或等於第一筆測試起點的訓練樣本。允許使用先前已發生的歷史做輸入，不允許模型訓練時看見未來標籤。補值、常數處理和標準化只 fit 訓練視窗。

測試是 **rolling-origin fixed-model**：固定同一個已訓練模型，依序於各測試起點預測。較晚起點可使用已經發生的較早測試期真實值。這不是從第一個測試起點一次預測完整測試區間，也不是測試期逐步重新訓練。

Naive 預測是每個起點的最後一次真值 y[t-h]，與模型使用相同目標區間。`beats_naive_mae=false` 表示模型在此測試沒有打敗此簡單基準；股價或強趨勢曲線看起來接近，不代表模型有用。

## 支援範圍

- 單一序列；時間缺失、解析失敗或重複時間會要求先修正。不自動混合不同股票、商品、機台。
- 目標和額外歷史欄僅支援數值；不要求先做標準化。目標不可補答案。
- 歷史目標缺失不刪除原始時間列，因此不會偷偷縮短跨度。缺標籤或缺起點 Naive 的視窗不參與評估。
- lookback 1～365、horizon 1～90；視窗矩陣最多 500 萬格，超過需減少資料／視窗／欄位。
- 無法辨識不規則交易日的下一個實際日期；沒有一致頻率時 `forecast_time` 留空。
- 尚未提供多序列、遞迴多步、GRU、季節模型或大範圍自動調參；目前沒有再用全資料重訓部署模型。

## AutoML 與 LSTM

AutoML 會在外層訓練資料內再建立時間驗證區間，交界也會隔離，依驗證 MAE 比較 Ridge 與 Random Forest。本機可勾選 LSTM；測試集不參與選模。

LSTM 使用 Input → LSTM → Dense(16, relu) → Dense(1)，預設 32 單元、最多 30 epochs。補值／縮放只 fit 內層訓練視窗，以內層時間驗證的 val_loss 進行 EarlyStopping（patience=5，恢復最佳權重），取得最佳 epoch 後，以該輪數重新 fit 完整外層訓練資料。最後只用選中的設定評估測試集。

Windows 原生 TensorFlow 2.21 使用 CPU；RTX GPU 需要另外設定 WSL2。程式會顯示實際偵測到的 GPU，不保證已使用顯卡。安裝依賴與模型執行都在本專案環境，無須更動 ComfyUI。

## 匯出

`model.joblib` 含前處理與模型；`history.csv` 保留原始資料供重訓；`config.json`、`report.json`、`metrics.json`、`window_manifest.csv` 和 `test_predictions.csv` 記錄設定與評估。排除訓練不會刪除原始 history.csv 中的欄位。

解壓後可用 `forecast.py` 讀原始歷史資料預測，也能以 `--retrain` 重跑同一設定；完整指令見資料包內 README。不要用一般表格的 predict.py 載入時間序列模型。

技術參考：[scikit-learn 歷史特徵預測範例](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html)。

LSTM 另附 `model.keras`、`preprocessor.joblib` 與 `lstm_scaling.json`。Keras 模型本身需要經前處理且排成 `(樣本, lookback, 欄數)` 的資料，輸出需反縮放；`forecast.py` 配合 `model.joblib` 已整合這些步驟，可直接讀原始歷史 CSV。

官方依據：[TensorFlow Windows／WSL2 安裝](https://www.tensorflow.org/install/pip)、[EarlyStopping](https://keras.io/api/callbacks/early_stopping/)、[Keras 儲存格式](https://keras.io/guides/serialization_and_saving/)。
