"""Streamlit controls for direct-horizon forecasting."""
import hashlib
import importlib.util
import os
import pandas as pd
import streamlit as st
from forecasting import ForecastConfig, make_forecast_bundle, prepare_forecast, train_forecast
from preprocessing import DataPreparationError, _identifier_name, profile_frame


def render_forecast_ui(frame, digest, missing_tokens, settings_tab, output_tab, initial_options=None):
    initial_options = initial_options or {}
    profile = profile_frame(frame, missing_tokens)
    guessed = profile.set_index('欄位')['推測類型'].to_dict()
    with settings_tab:
        st.subheader('用過去的資料，預測未來第幾筆？')
        st.info('支援單一時間序列的數值預測：Ridge、Random Forest 與本機選用 LSTM。AutoML 使用獨立時間驗證區間比較模型。')
        columns = list(frame.columns)
        time_options = ['（請選擇時間欄位）'] + columns
        default_time = next((c for c in columns if guessed[c] == 'datetime'), time_options[0])
        if initial_options.get('time_column') in columns:
            default_time = initial_options['time_column']
        time_col = st.selectbox('時間欄位', time_options, index=time_options.index(default_time), key=f'fc_time_{digest}')
        target_options = ['（請選擇預測目標）'] + [c for c in columns if c != time_col]
        target = st.selectbox('未來要預測的數值欄', target_options,
                              index=target_options.index(initial_options['target']) if initial_options.get('target') in target_options else 0,
                              key=f'fc_target_{digest}_{time_col}')
        available = [c for c in columns if c not in [time_col, target]]
        excluded = st.multiselect('不參與訓練的欄位', available,
                                  default=[c for c in available if _identifier_name(c)],
                                  key=f'fc_exclude_{digest}_{time_col}_{target}')
        extras = st.multiselect('另外使用的歷史數值欄（可不選）', [c for c in available if c not in excluded],
                               key=f'fc_features_{digest}_{time_col}_{target}_{tuple(excluded)}')
        st.caption('目標欄過去的數值一定會使用；其他欄只有在上方選取後才會參與。所有欄位都只讀取預測起點以前已知的值。')
        a, b, c = st.columns(3)
        initial_lookback = initial_options.get('lookback', 14)
        initial_horizon = initial_options.get('horizon', 1)
        lookback = int(a.number_input('歷史視窗（筆）', 1, 365, max(1, min(365, int(initial_lookback))), key=f'fc_lookback_{digest}'))
        horizon = int(b.number_input('預測未來第幾筆', 1, 90, max(1, min(90, int(initial_horizon))), key=f'fc_horizon_{digest}'))
        ratio = c.slider('最後多少 % 當測試資料', 10, 40, 20, step=5, key='fc_ratio') / 100
        model_options = {'Ridge｜線性基準': 'ridge', 'Random Forest｜非線性': 'random_forest', 'AutoML｜比較後選擇': 'auto'}
        local_lstm = os.environ.get('CSV_STUDIO_LOCAL') == '1' and importlib.util.find_spec('tensorflow') is not None
        if local_lstm:
            model_options['LSTM｜本機神經網路'] = 'lstm'
        model_name = st.selectbox('時間序列模型', list(model_options))
        model_choice = model_options[model_name]
        include_lstm = local_lstm and model_choice == 'auto' and st.checkbox('AutoML 也比較 LSTM（訓練較久）')
        epochs, units = 30, 32
        if model_choice == 'lstm' or include_lstm:
            epochs = int(st.number_input('LSTM 最多 epochs', 1, 100, 30))
            units = int(st.number_input('LSTM 單元數', 8, 128, 32, step=8))
            st.caption('使用時間驗證集決定 early stopping，再用最佳 epoch 數重訓外層訓練集。Windows 原生安裝預設使用 CPU。')
        elif not local_lstm:
            st.caption('需要 LSTM：在本機執行 SETUP_LSTM.bat 後，用 START_WINDOWS.bat 啟動；雲端版保留輕量模型。')
        config = ForecastConfig(target=target, time_column=time_col, lookback=lookback, horizon=horizon,
                                test_size=ratio, model=model_choice, include_lstm=include_lstm, lstm_epochs=epochs, lstm_units=units,
                                feature_columns=tuple(extras), excluded_columns=tuple(excluded), missing_tokens=missing_tokens)
        signature = hashlib.sha256((digest + repr(config)).encode()).hexdigest()
        if st.session_state.get('forecast_signature') != signature:
            for name in ('forecast_data', 'forecast_trained', 'forecast_zip'):
                st.session_state.pop(name, None)
        st.write(f'例如：使用最近 {lookback} 筆已知資料，預測起點之後第 {horizon} 筆的數值。')
        st.caption('按日期排序且不打亂；自動隔離交界樣本。重複時間請先選單一股票／商品或彙總。不規則日期的「筆」不等於「天」。')
        if st.button('建立時間序列資料', type='primary', disabled=target not in frame or time_col not in frame):
            try:
                with st.spinner('建立歷史視窗並檢查時間交界…'):
                    data = prepare_forecast(frame, config)
                st.session_state['forecast_data'] = data
                st.session_state['forecast_signature'] = signature
                st.session_state.pop('forecast_trained', None)
                st.session_state.pop('forecast_zip', None)
                st.success('已建立，請到「3 · 訓練與下載」。')
            except (DataPreparationError, ValueError) as exc:
                st.error(str(exc))
    with output_tab:
        data = st.session_state.get('forecast_data')
        if data is None:
            st.info('先選擇時間、目標與歷史視窗，再建立時間序列資料。')
            return
        a, b, c = st.columns(3)
        a.metric('訓練視窗', len(data.train_positions))
        b.metric('測試視窗', len(data.test_positions))
        c.metric('交界隔離', data.report['rows']['purged'])
        st.write('實際使用的歷史欄：', '、'.join(data.report['history_columns']))
        st.caption('手動排除：' + ('、'.join(data.report['excluded_columns']) or '無'))
        with st.expander('時間範圍與處理紀錄'):
            st.json(data.report)
            st.dataframe(data.manifest.tail(15), hide_index=True, width='stretch')
        st.caption('逐次往前預測：每個起點可使用當時已發生的歷史值，模型固定。這不是一次預測整段未知未來。')
        if st.button('訓練時間序列模型', type='primary'):
            try:
                with st.spinner('只從訓練視窗學習，並與 Naive 比較…'):
                    st.session_state['forecast_trained'] = train_forecast(data)
                    st.session_state.pop('forecast_zip', None)
            except (DataPreparationError, ValueError) as exc:
                st.error(str(exc))
        trained = st.session_state.get('forecast_trained')
        if trained is not None:
            model, metrics, predictions = trained
            if 'model_comparison' in metrics:
                st.write('驗證集模型比較（不使用測試分數選模型）')
                st.dataframe(pd.json_normalize(metrics['model_comparison']), hide_index=True, width='stretch')
            st.caption('這次模型：' + metrics['model'])
            st.dataframe(pd.DataFrame({'模型': metrics['test_scores'], 'Naive 最近一次真值': metrics['naive_scores']}), width='stretch')
            if metrics['beats_naive_mae']:
                st.success('這次測試的 MAE 優於 Naive；仍需其他時間區段驗證。')
            else:
                st.warning('這次測試的 MAE 沒有優於 Naive，不能因曲線接近就判定模型有效。')
            plot = predictions.set_index('target_time')[['actual', 'prediction', 'naive_prediction']]
            st.line_chart(plot)
            try:
                st.write('根據最後已知歷史，預測未來：')
                st.dataframe(pd.DataFrame([model.forecast(frame)]), hide_index=True, width='stretch')
                st.caption('這一筆未來預測尚無真實答案，不包含在測試分數內。時間戳留空表示未推定固定時間間隔。')
            except DataPreparationError as exc:
                st.info(str(exc))
            if st.button('產生時間序列模型包'):
                st.session_state['forecast_zip'] = make_forecast_bundle(data, trained)
            if 'forecast_zip' in st.session_state:
                st.download_button('下載 forecast_training.zip', st.session_state['forecast_zip'],
                                   file_name='forecast_training.zip', mime='application/zip', type='primary')
