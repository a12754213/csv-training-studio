"""Independent Streamlit Agent workspace. Existing app.py remains unchanged."""
from __future__ import annotations

import hashlib

import streamlit as st
from agent_hub import AgentContext
from agent_modules import build_registry
from preprocessing import DataPreparationError
from ui_layout import apply_page_layout, render_page_header, AGENT_HEADING

st.set_page_config(page_title="資料分析 Agent · AI Agent Hub", page_icon='🤖', layout='wide')
apply_page_layout()
render_page_header(
    title=AGENT_HEADING,
    category="CSV ANALYSIS",
    description="上傳資料 → 檢查資料品質 → 建議模型 → 人工確認後訓練並下載。這個模組採規則型規劃，不需要 AI API Key。",
)
st.info('這是可解釋規則的自動工作流程，不是內建語言模型聊天。要透過 ChatGPT 對話控制本機訓練，請使用專案既有的 MCP 連接器。')

registry = build_registry()
with st.expander('已安裝功能模組／未來擴充點'):
    st.dataframe(registry.available(), hide_index=True, width='stretch')

upload = st.file_uploader('上傳 CSV／TSV', type=['csv', 'tsv', 'txt'])
if upload is None:
    st.stop()

context = AgentContext(payload=upload.getvalue(), filename=upload.name)
digest = hashlib.sha256(context.payload).hexdigest()
if st.session_state.get('agent_digest') != digest:
    st.session_state['agent_digest'] = digest
    st.session_state.pop('agent_result', None)

try:
    overview = registry.run('csv.inspect', context)
except (DataPreparationError, ValueError, UnicodeError) as exc:
    st.error(f'資料讀取失敗：{exc}')
    st.stop()

left, right = st.columns(2)
left.metric('資料筆數', f"{overview['rows']:,}")
right.metric('欄位數', len(overview['columns']))
with st.expander('資料品質與欄位分析', expanded=True):
    import pandas as pd
    st.dataframe(pd.DataFrame(overview['profile']), width='stretch', hide_index=True)

columns = overview['columns']
target = st.selectbox('你想預測哪一欄？（必須由你確認）', ['（請選擇）'] + columns)
forecast_intent = st.checkbox('我要預測未來數值（時間序列）', value=False)
if target == '（請選擇）':
    st.info('先指定目標欄位，Agent 才會提供模型與切分建議。')
    st.stop()

# Detect candidate date columns, but do not infer business intent.
initial = registry.run('csv.plan', context, {'target': target})
time_column = None
if forecast_intent:
    candidates = [c for c in columns if c != target]
    dates = [c for c in initial.get('date_candidates', []) if c in candidates]
    if not candidates:
        st.error('沒有可用的時間欄位。')
        st.stop()
    time_column = st.selectbox('確認時間欄位', candidates,
                               index=candidates.index(dates[0]) if dates else 0)

plan = registry.run('csv.plan', context, {'target': target, 'forecast_intent': forecast_intent,
                                           'time_column': time_column})
st.subheader('Agent 分析建議')
for note in plan.get('notes', []):
    st.caption('• ' + note)
options = plan.get('suggested_options')
if not options:
    st.warning('目前資料不適合直接啟動訓練。請先依建議修正欄位或資料。')
    st.stop()

with st.form('agent_training_form'):
    suggested_task = options['task']
    if forecast_intent:
        task = 'time_series'
        st.write('任務：時間序列預測')
        model = st.selectbox('模型', ['auto', 'ridge', 'random_forest'])
        lookback = st.number_input('歷史視窗（列）', min_value=1, max_value=365, value=int(options['lookback']))
        horizon = st.number_input('預測後面第幾筆', min_value=1, max_value=90, value=1)
    else:
        task = st.selectbox('任務類型（請依業務目的確認）', ['classification', 'regression'],
                            index=0 if suggested_task == 'classification' else 1,
                            format_func=lambda x: {'classification': '分類', 'regression': '回歸'}[x])
        model = st.selectbox('模型', ['auto', 'baseline', 'random_forest'])
    excluded = st.multiselect('不參與訓練的欄位',
                              [c for c in columns if c not in {target, time_column}],
                              default=[c for c in options.get('excluded_columns', []) if c not in {target, time_column}])
    st.caption('排除 ID 是建議；是否有資訊洩漏、同一人多筆或需要群組切分，仍須你確認。')
    approved = st.form_submit_button('確認設定並執行訓練', type='primary')

request = {'target': target, 'task': task, 'model': model, 'excluded_columns': excluded}
if task == 'time_series':
    request.update(time_column=time_column, lookback=int(lookback), horizon=int(horizon),
                   feature_columns=[])

if approved:
    try:
        with st.spinner('執行AI Agent Hub 的訓練與評估流程…'):
            result = registry.run('csv.train', context, request, approved=True)
        st.session_state['agent_result'] = {'digest': digest, 'options': request, 'output': result}
        st.success('模型訓練完成。')
    except (DataPreparationError, ValueError, RuntimeError, TypeError, OverflowError) as exc:
        st.session_state.pop('agent_result', None)
        st.error(f'訓練失敗：{exc}')

saved = st.session_state.get('agent_result')
if saved and saved['digest'] == digest and saved['options'] == request:
    st.subheader('執行結果')
    st.write('實際設定：')
    st.json(saved['options'])
    st.write('模型評估：')
    st.json(saved['output']['summary']['metrics'])
    st.download_button('下載 training_data.zip（含模型及評估）', saved['output']['bundle'],
                       file_name='training_data.zip', mime='application/zip', type='primary')
    st.caption('請檢查測試分數與是否存在資料洩漏；模型準確度不保證未來預測成效。')
