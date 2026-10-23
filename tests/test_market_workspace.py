"""Provider contracts, isolated financial evaluation, and unified user flows."""
from datetime import date
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from agent_hub import AgentContext
from agent_modules import build_registry
from agent_modules.market_tools import (MarketError, resolve_symbol, parse_month,
                                        fetch_prices, analyze_prices, backtest_prices)
from agent_modules.research_tools import research_selected, ResearchError
from agent_supervisor import plan_task, run_task

ROOT = Path(__file__).resolve().parents[1]


def prices():
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0, 1, 180))
    frame = pd.DataFrame({'Date': pd.bdate_range('2025-01-01', periods=180).strftime('%Y-%m-%d'),
                          'Open': close, 'High': close+1, 'Low': close-1,
                          'Close': close, 'Volume': np.repeat(10000., 180)})
    return {'symbol': '2330', 'as_of': frame.Date.iloc[-1], 'rows': frame.to_dict('records'),
            'missing_months': [], 'invalid_rows': 0, 'warnings': [], 'sources': [], 'status': 'completed'}


class MarketTests(unittest.TestCase):
    def test_resolves_taiwan_not_adr_or_ambiguous_symbols(self):
        for query in ('台積電股價', '臺積電趨勢', '2330.TW 股價', '2026年台積電股價會到3000元嗎'):
            self.assertEqual(plan_task(query).symbol, '2330')
        for query in ('TSM ADR price', '台積電美股', '比較2330與2317股價'):
            self.assertIsNone(resolve_symbol(query))
            self.assertEqual(plan_task(query).kind, 'search')

    def test_natural_media_and_dynamic_routes_keep_environment_gate(self):
        task = plan_task('讀取動態網頁 https://example.org')
        self.assertEqual(task.kind, 'browser')
        with patch.dict('os.environ', {'AI_AGENT_ISOLATED_BROWSER': '0'}):
            with self.assertRaises(ValueError):
                run_task(task, build_registry(), approved_read=True)
        self.assertEqual(plan_task('分析影片 https://youtu.be/dQw4w9WgXcQ').tools,
                         ('video.youtube_transcript',))
        self.assertTrue(plan_task('分析圖片', filename='a.png', upload_present=True).requires_external)

    def test_month_parse_rejects_future_wrong_month_and_bad_ohlc(self):
        fields = ['日期', '成交股數', '開盤價', '最高價', '最低價', '收盤價']
        doc = {'stat': 'OK', 'fields': fields, 'data': [
            ['115/09/01','1,000','100','102','98','101'],
            ['115/10/01','1000','100','102','98','101'],
            ['115/09/30','1000','100','102','98','101'],
            ['115/09/02','1000','100','90','98','101'],
            ['115/09/03','1000','100','102','98','NaN']]}
        rows, skipped = parse_month(doc, '20260901', today=date(2026,9,20))
        self.assertEqual(len(rows), 1)
        self.assertEqual(skipped, 4)
        self.assertEqual(rows[0]['Volume'], 1000)
        with self.assertRaises(MarketError):
            parse_month({'stat':'OK','fields':[]}, '20260901')

    def test_fetch_bounds_and_no_approval_no_network(self):
        reg = build_registry()
        with patch('agent_modules.market_tools.request.build_opener') as network:
            with self.assertRaises(PermissionError):
                reg.run('market.twse', AgentContext(), {'symbol':'2330'})
            for params in ({'symbol':'http://127.0.0.1'}, {'months':99}, {'months':True}, {'url':'http://example.com'}):
                with self.assertRaises(MarketError):
                    fetch_prices(AgentContext(), params)
            network.assert_not_called()

    def test_analysis_arithmetic_and_json_export(self):
        data = prices()
        report = analyze_prices(data)
        frame = pd.DataFrame(data['rows'])
        self.assertAlmostEqual(report['statistics']['ma20'], frame.Close.tail(20).mean())
        self.assertAlmostEqual(report['statistics']['change_20_sessions_pct'],
                               (frame.Close.iloc[-1]/frame.Close.iloc[-21]-1)*100)
        json.dumps(report, allow_nan=False)

    def test_backtest_time_isolation_naive_and_export_reload(self):
        import joblib
        data = prices()
        report, bundle = backtest_prices(data, 5)
        self.assertEqual(report['metrics']['selection_data'], 'inner_validation_only')
        p = pd.DataFrame(report['predictions'])
        expected = (p.actual-p.naive_prediction).abs().mean()
        self.assertAlmostEqual(expected, report['metrics']['naive_scores']['mae'])
        with zipfile.ZipFile(io.BytesIO(bundle)) as z:
            meta = json.loads(z.read('report.json'))
            self.assertLess(pd.Timestamp(meta['train_last_target_time']), pd.Timestamp(meta['test_first_origin_time']))
            model = joblib.load(io.BytesIO(z.read('model.joblib')))
            self.assertAlmostEqual(model.forecast(pd.DataFrame(data['rows']))['prediction'], report['future']['prediction'])
        data['missing_months'] = ['202502']
        with self.assertRaises(MarketError):
            backtest_prices(data)

    def test_market_retains_prices_on_bad_news_key(self):
        with patch('agent_modules.market_tools.fetch_prices', return_value=prices()):
            out = run_task(plan_task('分析台積電股價未來趨勢'), build_registry(),
                           brave_key='bad', approved_read=True, approved_follow=True)
        self.assertIn('prices', out['result'])
        self.assertEqual(out['status'], 'partial')
        self.assertNotIn('bad', json.dumps(out))

    def test_one_unreachable_source_does_not_drop_others(self):
        doc = {'url':'https://example.org/good', 'kind':'table', 'title':'Table', 'text':'',
               'csv_bytes':b'x,y\n1,2\n2,3\n', 'rows':2, 'columns':2}
        with patch('agent_modules.research_tools._destination', side_effect=[ValueError('DNS failed'), None]), \
             patch('agent_modules.web_crawler.crawl', return_value=doc):
            result = research_selected(AgentContext(), {'urls':['https://invalid.example/a','https://example.org/good']})
        self.assertEqual(result['sources'][0]['status'], 'unavailable')
        self.assertEqual(result['sources'][1]['status'], 'completed')
        self.assertIn('table_csv', result['sources'][1])
        self.assertTrue(result['sources'][1]['numeric_summary'])

    def test_report_failure_and_empty_sources_have_honest_status(self):
        with patch('agent_modules.research_tools.research_selected', return_value={'sources':[]}):
            out = run_task(plan_task('讀 https://example.org'), build_registry(), approved_read=True)
            self.assertEqual(out['status'], 'no_sources')
        source = {'url':'https://example.org', 'status':'completed','text_preview':'hello'}
        with patch('agent_modules.research_tools.research_selected', return_value={'sources':[source]}), \
             patch('agent_modules.research_tools.synthesize', side_effect=ResearchError('failed')):
            out = run_task(plan_task('讀 https://example.org'), build_registry(), approved_read=True,
                           approved_report=True, openai_key='test-private-key')
            self.assertEqual(out['status'], 'partial')
            self.assertEqual(out['result']['sources'], [source])
            self.assertNotIn('test-private-key', json.dumps(out))


class WorkspaceTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(ROOT/'pages/0_AI_Workspace.py'), default_timeout=30).run()

    def test_empty_query_and_missing_search_key(self):
        app = self.app()
        self.assertTrue(next(b for b in app.button if b.label == '開始分析').disabled)
        app.text_area(key='workspace_query').set_value('搜尋半導體新聞').run()
        next(b for b in app.button if b.label == '開始分析').click().run()
        self.assertFalse(app.exception)
        self.assertIn('Brave', app.error[0].value)

    def test_stock_result_backtest_and_input_invalidation(self):
        app = self.app()
        app.text_area(key='workspace_query').set_value('分析台積電股價').run()
        with patch('agent_modules.market_tools.fetch_prices', return_value=prices()):
            next(b for b in app.button if b.label == '開始分析').click().run()
        self.assertFalse(app.exception)
        self.assertIn('workspace_result', app.session_state)
        next(b for b in app.button if b.label == '訓練並回測股價模型').click().run()
        self.assertFalse(app.exception)
        self.assertIn('workspace_backtest', app.session_state)
        app.selectbox[0].select(20).run()
        self.assertNotIn('workspace_backtest', app.session_state)
        app.text_area(key='workspace_query').set_value('搜尋其他資料').run()
        self.assertNotIn('workspace_result', app.session_state)

    def test_csv_handoff_is_available_without_upload_again(self):
        app = AppTest.from_file(str(ROOT/'pages/8_CSV_Workspace.py'), default_timeout=30)
        app.session_state['workspace_dataset'] = {'name':'test.csv','payload':(ROOT/'samples/demo_churn.csv').read_bytes()}
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(next(r for r in app.radio if r.label=='資料來源').value,'使用 AI 任務資料')


if __name__ == '__main__':
    unittest.main()
