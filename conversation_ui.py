"""Conversational multi-source UI, sharing the Hub's existing tools and CSV page."""
from __future__ import annotations
import json
import pandas as pd
import streamlit as st
from agent_workspace import (Attachment, Workspace, WorkspaceError, run_agent_turn,
                             collect_turn, snapshot, markdown_report, safe_markdown)

LABELS = {'model.plan': '模型正在規劃下一步', 'outline_task': '安排工作計畫',
          'search_web': '搜尋公開來源', 'read_web': '讀取並檢查來源',
          'inspect_file': '分析附檔', 'analyze_stock': '取得台股資料與統計',
          'propose_training': '準備訓練建議', 'finish_report': '整理跨來源報告',
          'ask_user': '確認缺少的條件'}


def render_conversation(*, openai_key='', brave_key=''):
    if 'conversation_workspace' not in st.session_state:
        st.session_state['conversation_workspace'] = Workspace()
    workspace = st.session_state['conversation_workspace']
    epoch = st.session_state.get('conversation_epoch', 0)
    left, right = st.columns([4, 1])
    left.subheader('對話與多來源工作區')
    if right.button('另開任務', key='conversation_new'):
        st.session_state['conversation_epoch'] = epoch + 1
        st.session_state['conversation_workspace'] = Workspace()
        st.session_state.pop('conversation_result', None)
        st.rerun()
    st.caption('將檔案與網址放在同一個任務；完成後可接著說「加入另一份資料」「換成聯發科」或「比較差異」。')
    goal = st.text_area('這次要完成的目標', key=f'conversation_goal_{epoch}',
                        placeholder='例如：比較這兩份 CSV 與 PDF 的結果，找出差異並列出依據。')
    files = st.file_uploader('加入檔案（最多六份，合計 30 MB）', accept_multiple_files=True,
                             type=['csv','tsv','pdf','png','jpg','jpeg','webp','gif',
                                   'wav','mp3','mp4','m4a','webm','srt','vtt'],
                             key=f'conversation_files_{epoch}')
    use_ai = st.checkbox('使用 AI 自主規劃與整合（需要 OpenAI Key）',
                         value=bool(openai_key), key='conversation_use_ai')
    allow_web = st.checkbox('允許本輪查詢公開網站與行情', value=True, key='conversation_allow_web')
    allow_content = st.checkbox('允許 AI 讀取附檔文字摘錄、表格前五列；圖片／音訊可傳給 OpenAI',
                                value=False, key='conversation_allow_content')
    if use_ai:
        st.caption('會將目標、對話脈絡、檔名與欄位概況送往 OpenAI；附檔內文依上方選項處理。'
                   '每輪最多八步，搜尋另需 Brave Key；模型呼叫依帳戶用量計費。')
    else:
        st.caption('目前為「整理來源」模式：讀取檔案、公開網址及台股資料，保留來源與表格；不做模型生成的跨來源解讀。')
    st.caption('檔案會留在本次任務，可在後續對話重用；「另開任務」會清除本項任務的資料。重新整理可能使工作階段消失。')
    start = st.button('開始任務', type='primary', key='conversation_start')
    prompt = st.chat_input('接續這項任務，例如：再加入這份資料比較', key=f'conversation_followup_{epoch}') if workspace.messages else None
    if start or prompt:
        try:
            if use_ai and not openai_key:
                raise WorkspaceError('請在左側連線設定填入 OpenAI Key，或關閉 AI 自主規劃先整理來源。')
            workspace.add_files([Attachment(file.name, file.getvalue()) for file in files])
            with st.status('正在處理任務…', expanded=True) as status:
                runner = run_agent_turn if use_ai else collect_turn
                result = runner(workspace, prompt or goal, openai_key=openai_key, brave_key=brave_key,
                                allow_file_ai=allow_content,
                                allow_web=allow_web,
                                progress=lambda name: st.write(LABELS.get(name, name)))
                st.session_state['conversation_result'] = result
                status.update(label='本輪已完成' if result['status']=='completed' else '請查看結果與缺口',
                              state='complete', expanded=False)
            st.rerun()
        except (ValueError, RuntimeError, OSError, PermissionError) as exc:
            st.error(str(exc))

    if not workspace.messages:
        st.info('可先用兩份示範 CSV 或字幕檔測試整理來源；啟用自主規劃後，Agent 才會自行決定後續工具。')
        return
    dialogue, sources, datasets, trace = st.tabs(['對話與報告', '來源與缺口', '資料與訓練', '計畫與紀錄'])
    with dialogue:
        for message in workspace.messages:
            with st.chat_message(message['role']):
                if message['role'] == 'user':
                    st.text(message['content'])
                else:
                    st.markdown(message['content'])
                    if message.get('status') not in ('completed', None):
                        st.caption('本輪狀態：' + message['status'])
        if workspace.plan:
            st.caption('本輪工作計畫：' + ' → '.join(workspace.plan))
        st.download_button('下載研究報告 Markdown', markdown_report(workspace), 'agent_report.md', 'text/markdown')
    with sources:
        if not workspace.sources:
            st.info('尚未取得來源；請補上檔案／網址，或設定搜尋金鑰。')
        for source in workspace.sources:
            with st.expander(f"[{source['id']}] {safe_markdown(source.get('title') or source.get('url') or source['key'])}", expanded=True):
                retrieved = pd.Timestamp(source['retrieved_at']).tz_convert('Asia/Taipei').strftime('%Y-%m-%d %H:%M')
                st.caption('狀態：' + source.get('status','unknown') + ' · 取得時間（台灣）：' + retrieved)
                if source.get('url'):
                    st.link_button('開啟來源 ' + source['id'], source['url'])
                    st.caption(source.get('source_class','公開來源'))
                    st.caption('來源標示的發表日期：' + safe_markdown(source.get('published_at') or '未提供'))
                for url in source.get('source_urls', []):
                    st.write(url)
                if source.get('status') == 'unavailable':
                    st.warning('未能讀取原文，不納入已完成的來源。')
                if source.get('text_preview'):
                    st.text(source['text_preview'])
                if source.get('local_data'):
                    data = source['local_data']
                    if 'rows' in data:
                        st.write(f"{data['rows']:,} 列 · {len(data['columns'])} 欄")
                    if data.get('text'):
                        st.text(data['text'][:4000])
                    st.caption('附檔摘錄可送給 AI：' + ('已允許本次讀取' if source.get('content_shared') else '僅本地顯示／概況'))
                if source.get('statistics'):
                    st.json(source['statistics'])
                for warning in source.get('warnings', []):
                    st.warning(warning)
        st.caption('來源編號只標示資料從哪裡來；官方網域、來源數量或模型報告都不代表已完成獨立事實查核。')
    with datasets:
        choices = {}
        for record in workspace.records:
            if record['kind'] == 'csv':
                choices[record['file_id']] = record
        if choices:
            pick = st.selectbox('選擇接續訓練的資料', list(choices), format_func=lambda value: choices[value]['name'])
            record = choices[pick]
            data = record['csv_text'].encode('utf-8-sig')
            st.download_button('下載這份 CSV', data, record['name'], 'text/csv')
            plan = next((r['plan'] for r in reversed(workspace.records)
                         if r['kind']=='training_plan' and r['file_id']==pick), {})
            if plan:
                st.write('Agent 訓練建議：')
                st.json(plan)
            st.caption('接續會帶入資料與建議；請在訓練頁確認目標欄位和設定後再執行。')
            if st.button('接續 CSV 訓練', type='primary', key='conversation_train'):
                st.session_state['workspace_dataset'] = {'name': record['name'], 'payload': data,
                                                        'plan': plan.get('suggested_options', {})}
                st.switch_page('pages/8_CSV_Workspace.py')
        else:
            st.caption('目前沒有可供訓練的表格。')
    with trace:
        for number, step in enumerate(workspace.plan, 1):
            st.write(f'{number}. {step}')
        if workspace.trace:
            st.dataframe(pd.DataFrame(workspace.trace), hide_index=True, width='stretch')
        st.download_button('下載任務紀錄 JSON', json.dumps(snapshot(workspace), ensure_ascii=False, indent=2),
                           'agent_conversation.json', 'application/json')
        st.caption('本次工作階段保留最近十二則對話、最多六份檔案及二十四個來源；尚未跨裝置持久保存。')
