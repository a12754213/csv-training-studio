"""Natural-language Agent review page. The user approves all training operations."""
from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from agent_chat import AgentChatError, DEFAULT_MODEL, propose_with_openai
from agent_hub import AgentContext
from agent_modules import build_registry
from preprocessing import DataPreparationError
from ui_layout import apply_page_layout
from version import __version__

st.set_page_config(page_title='AI Agent 對話 · CSV Training Studio', page_icon='💬', layout='wide')
apply_page_layout()
st.caption(f'CSV Training Studio · v{__version__}')
st.title('💬 AI Agent · 自然語言助手')
st.caption('上傳 CSV → 直接說明需求 → AI 提出建議 → 你審核 → 由既有訓練引擎執行。')
st.info('這個網頁中的 AI 對話屬於可選的 OpenAI API 功能，API 獨立計費，不包含在 ChatGPT Plus 訂閱中。'
        ' 若不使用 API，可切換「AI Agent」工作台手動設定，或在本機使用既有 MCP 連接器讓 ChatGPT 操作。')

registry = build_registry()
with st.expander('模型連接與隱私設定'):
    api_key = st.text_input('OpenAI API Key（僅在這次工作階段使用）', type='password',
                            help='請勿將 API Key 寫入 GitHub 或 CSV。')
    st.caption('只有你輸入的指令、欄位名稱、推測型態、缺值率及資料筆數會送到 OpenAI API。'
               '原始 CSV 列資料、檔案內容及產出的模型不會傳給語言模型。')
    st.caption(f'目前使用：{DEFAULT_MODEL}。AI 僅提議操作，不能直接執行訓練或任意 Python 指令。')

upload = st.file_uploader('選擇要處理的 CSV／TSV', type=['csv', 'tsv', 'txt'], key='chat_csv')
if upload is None:
    st.stop()
context = AgentContext(payload=upload.getvalue(), filename=upload.name)
digest = hashlib.sha256(context.payload).hexdigest()
if st.session_state.get('chat_file_digest') != digest:
    st.session_state['chat_file_digest'] = digest
    st.session_state['chat_messages'] = []
    st.session_state['chat_pending'] = None
    st.session_state['chat_result'] = None
    st.session_state['chat_history_user'] = []

try:
    overview = registry.run('csv.inspect', context)
except (DataPreparationError, ValueError, UnicodeError) as exc:
    st.error(f'無法讀取 CSV：{exc}')
    st.stop()

a, b = st.columns(2)
a.metric('資料列數', f"{overview['rows']:,}")
b.metric('欄位數量', len(overview['columns']))
with st.expander('本機分析結果（這些不需呼叫 API）'):
    st.dataframe(pd.DataFrame(overview['profile']), width='stretch', hide_index=True)
    st.caption('疑似 ID 欄位：' + ('、'.join(overview['suggested_excluded_columns']) or '無'))

st.subheader('與 Agent 對話')
for message in st.session_state['chat_messages']:
    with st.chat_message(message['role']):
        st.markdown(message['content'])

text = st.chat_input('例如：幫我預測「是否流失」，排除客戶編號並自動比較模型')
if text:
    st.session_state['chat_messages'].append({'role': 'user', 'content': text})
    previous = list(st.session_state['chat_history_user'])
    st.session_state['chat_history_user'] = (previous + [text])[-4:]
    st.session_state['chat_pending'] = None
    # Keep the previous training artifact available while the user asks follow-up questions.
    if not api_key:
        reply = '要使用網站內的自然語言 AI，請先在「模型連接與隱私設定」填入自己的 OpenAI API Key。也可使用無 API 的 AI Agent 工作台。'
    else:
        try:
            with st.spinner('分析你的要求並準備安全的工作計畫…'):
                suggestion = propose_with_openai(text, overview, api_key, history=previous)
            reply = suggestion['message'] or '已解析需求。'
            if suggestion['action'] == 'inspect':
                reply += (f"\n\n這份檔案共有 **{overview['rows']:,} 筆**、"
                          f"**{len(overview['columns'])} 欄**；詳細資料品質見上方報告。")
            elif suggestion['action'] == 'plan':
                plan = registry.run('csv.plan', context, {
                    'target': suggestion['target'],
                    'time_column': suggestion['time_column'] if suggestion['task'] == 'time_series' else None,
                    'forecast_intent': suggestion['task'] == 'time_series',
                })
                if 'suggested_options' not in plan:
                    reply += '\n\n' + '\n'.join(plan.get('notes', []))
                else:
                    st.session_state['chat_pending'] = {
                        'proposal': suggestion, 'plan': plan,
                        'digest': digest, 'request_id': len(st.session_state['chat_messages']),
                    }
                    reply += '\n\n**請在下方檢查並確認訓練設定；我尚未開始訓練。**'
            elif suggestion['action'] == 'clarify':
                reply += '\n\n請在下一句明確告訴我目標欄位；時間序列也需要時間欄。'
        except (AgentChatError, DataPreparationError, ValueError) as exc:
            reply = f'無法產生訓練計畫：{exc} 尚未執行訓練。'
    st.session_state['chat_messages'].append({'role': 'assistant', 'content': reply})
    st.rerun()

pending = st.session_state.get('chat_pending')
if pending and pending['digest'] == digest:
    proposal = pending['proposal']
    recommended = pending['plan']['suggested_options']
    st.divider()
    st.subheader('📋 執行前確認')
    for note in pending['plan'].get('notes', []):
        st.caption('• ' + note)
    candidate_columns = overview['columns']
    with st.form(f"review_{pending['request_id']}"):
        target = st.selectbox('目標欄位（確認預測意義）', candidate_columns,
                              index=candidate_columns.index(proposal['target']))
        task_values = ['classification', 'regression', 'time_series']
        task = st.selectbox('任務類型', task_values, index=task_values.index(
            proposal['task'] or recommended['task']),
            format_func=lambda s: {'classification': '分類', 'regression': '回歸',
                                   'time_series': '時間序列預測'}[s])
        time_column = None
        if task == 'time_series':
            available_dates = [c for c in candidate_columns if c != target]
            if not available_dates:
                st.error('時間序列需要時間欄位。')
                st.stop()
            preferred = (proposal['time_column'] if proposal['time_column'] in available_dates
                         else (pending['plan'].get('date_candidates') or [None])[0])
            time_column = st.selectbox('時間欄位', available_dates,
                                       index=available_dates.index(preferred) if preferred in available_dates else 0)
            model_options = ['auto', 'ridge', 'random_forest']
            default_model = proposal['model'] if proposal['model'] in model_options else 'auto'
            model = st.selectbox('訓練模型', model_options, index=model_options.index(default_model))
            lookback = st.number_input('歷史視窗（筆）', min_value=1, max_value=365, value=proposal['lookback'])
            horizon = st.number_input('預測跨度（筆）', min_value=1, max_value=90, value=proposal['horizon'])
            split_mode = 'time'
            split_column = None
        else:
            model_options = ['auto', 'baseline', 'random_forest']
            default_model = proposal['model'] if proposal['model'] in model_options else 'auto'
            model = st.selectbox('訓練模型', model_options, index=model_options.index(default_model))
            split_options = ['random', 'group', 'time']
            split_default = proposal['split_mode'] if proposal['split_mode'] in split_options else 'random'
            split_mode = st.selectbox('資料切分方式', split_options,
                                      index=split_options.index(split_default),
                                      format_func=lambda s: {'random': '隨機（獨立樣本）',
                                                             'group': '群組（例如同客戶）',
                                                             'time': '時間（避免未來資料洩漏）'}[s])
            split_column = None
            if split_mode != 'random':
                split_candidates = [c for c in candidate_columns if c != target]
                if not split_candidates:
                    st.error('沒有可用的切分欄位。')
                    st.stop()
                preferred = proposal['split_column']
                split_column = st.selectbox('切分欄位', split_candidates,
                    index=split_candidates.index(preferred) if preferred in split_candidates else 0)
            lookback = horizon = None
        blocked = {target, time_column, split_column}
        excluded_choices = [c for c in candidate_columns if c not in blocked]
        defaults = list(dict.fromkeys(
            [*overview['suggested_excluded_columns'], *proposal['excluded_columns']]))
        excluded = st.multiselect('排除欄位（請確認預測當下能否取得）', excluded_choices,
                                  default=[c for c in defaults if c in excluded_choices])
        st.warning('按下確認才會開始訓練。請檢查目標是否合理，以及同一人、多時間點等資訊洩漏風險。')
        confirmed = st.form_submit_button('✅ 核准並開始訓練', type='primary')

    if confirmed:
        request_options = {'target': target, 'task': task, 'model': model,
                           'excluded_columns': excluded}
        if task == 'time_series':
            request_options.update(time_column=time_column, lookback=int(lookback),
                                   horizon=int(horizon), feature_columns=[])
        else:
            request_options.update(split_mode=split_mode, split_column=split_column)
        try:
            with st.spinner('使用 CSV Training Studio 原有訓練核心執行…'):
                trained = registry.run('csv.train', context, request_options, approved=True)
            st.session_state['chat_result'] = {
                'digest': digest, 'request': request_options, 'output': trained}
            st.session_state['chat_pending'] = None
            st.session_state['chat_messages'].append({
                'role': 'assistant',
                'content': '模型訓練完成！下面可以查看真實的評估指標並下載完整結果。'})
            st.rerun()
        except (DataPreparationError, ValueError, TypeError, RuntimeError, OverflowError) as exc:
            st.error(f'訓練失敗，請調整設定：{exc}')

trained = st.session_state.get('chat_result')
if trained and trained['digest'] == digest:
    st.divider()
    st.subheader('訓練完成')
    st.write('實際使用設定')
    st.json(trained['request'])
    st.write('測試結果及模型比較')
    st.json(trained['output']['summary']['metrics'])
    st.download_button('下載模型、資料與報告 ZIP',
                       trained['output']['bundle'], 'training_data.zip',
                       mime='application/zip', type='primary')
    st.caption('模型指標只反映目前資料切分的結果，不能保證真實部署表現。')
