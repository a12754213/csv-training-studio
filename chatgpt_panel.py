"""Read local MCP job results inside the Streamlit UI; enabled only by the local launcher."""
import json
import os
from pathlib import Path
import streamlit as st
from training_service import DEFAULT_WORKSPACE


def render_chatgpt_panel():
    with st.expander('ChatGPT 本機訓練工作與下載'):
        st.caption('ChatGPT 與本機網頁使用同一套訓練核心。首次請執行 SETUP_CHATGPT.bat，連接 MCP 後即可用對話操作。')
        st.button('重新整理 ChatGPT 工作', key='refresh_chatgpt_jobs')
        root = Path(os.environ.get('CSV_STUDIO_WORKSPACE', DEFAULT_WORKSPACE)).resolve()
        paths = sorted((root / 'jobs').glob('*/status.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
        if not paths:
            st.info('尚無 ChatGPT 工作。完成連接後，上傳檔案並說明預測目標與排除欄位。')
        for path in paths:
            record = json.loads(path.read_text(encoding='utf-8'))
            job_id = record['job_id']
            st.write(f"{record['created_at']} · {record['options'].get('target', '')} · {record['status']}")
            if record.get('error'):
                st.error(record['error'])
            if record['status'] == 'completed':
                summary = json.loads((path.parent / 'summary.json').read_text(encoding='utf-8'))
                st.json({'metrics': summary['metrics'], 'used_columns': summary['used_columns'],
                         'excluded_columns': summary['excluded_columns']}, expanded=False)
                st.download_button('下載這次訓練結果', (path.parent / 'training_data.zip').read_bytes(),
                                   file_name=f'training_{job_id[:8]}.zip', mime='application/zip', key=f'job_{job_id}')
