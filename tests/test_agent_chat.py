"""Offline tests for optional LLM planner (no actual network or API key)."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_chat import (AgentChatError, SCHEMA, metadata_for_model, propose_with_openai,
                        validate_proposal)


OVERVIEW = {
    'rows': 150, 'columns': ['客戶編號', '是否流失', '年齡', '註冊時間'],
    'profile': [
        {'欄位': '客戶編號', '推測類型': 'identifier', '缺值率 (%)': 0.0,
         '常見值': 'do-not-send-this-personal-value'},
        {'欄位': '是否流失', '推測類型': 'categorical', '缺值率 (%)': 0.0},
    ],
    'suggested_excluded_columns': ['客戶編號'],
}


class FakeResponse:
    def __init__(self, payload):
        self.content = io.BytesIO(json.dumps(payload).encode('utf-8'))
    def __enter__(self):
        return self.content
    def __exit__(self, *args):
        return False


class AgentChatTests(unittest.TestCase):
    def test_only_metadata_goes_to_llm(self):
        summary = metadata_for_model(OVERVIEW)
        self.assertNotIn('do-not-send-this-personal-value', json.dumps(summary))
        self.assertNotIn('常見值', str(summary))
        self.assertEqual(summary['provided_columns'][1], '是否流失')

    def test_unknown_target_must_be_clarified(self):
        raw = {'action': 'plan', 'target': '不存在', 'task': 'classification',
               'excluded_columns': ['不存在', '客戶編號'], 'message': 'OK'}
        checked = validate_proposal(raw, OVERVIEW)
        self.assertEqual(checked['action'], 'clarify')
        self.assertIsNone(checked['target'])
        self.assertEqual(checked['excluded_columns'], ['客戶編號'])

    def test_training_requires_date_for_forecasting(self):
        raw = {'action': 'plan', 'target': '是否流失', 'task': 'time_series',
               'time_column': '不存在', 'message': '開始', 'excluded_columns': []}
        checked = validate_proposal(raw, OVERVIEW)
        self.assertEqual(checked['action'], 'clarify')

    def test_group_split_needs_group_column(self):
        raw = {'action': 'plan', 'target': '是否流失', 'task': 'classification',
               'split_mode': 'group', 'split_column': None, 'excluded_columns': []}
        self.assertEqual(validate_proposal(raw, OVERVIEW)['action'], 'clarify')

    def test_no_direct_side_effects_and_no_row_transfer(self):
        raw = {'action': 'plan', 'target': '是否流失', 'task': 'classification',
               'time_column': None, 'split_mode': 'random', 'split_column': None,
               'model': 'auto', 'excluded_columns': ['客戶編號'],
               'lookback': None, 'horizon': None, 'message': '建議分類'}
        server_payload = {'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps(raw, ensure_ascii=False)}
        ]}]}
        seen = {}
        def fake_urlopen(req, timeout):
            seen['data'] = json.loads(req.data)
            seen['headers'] = req.headers
            return FakeResponse(server_payload)
        with patch('agent_chat.request.urlopen', side_effect=fake_urlopen):
            result = propose_with_openai('請預測是否流失', OVERVIEW, 'test-secret')
        self.assertEqual(result['action'], 'plan')
        self.assertEqual(result['target'], '是否流失')
        self.assertEqual(result['model'], 'auto')
        self.assertEqual(seen['data']['text']['format']['type'], 'json_schema')
        self.assertTrue(seen['data']['text']['format']['strict'])
        self.assertEqual(set(SCHEMA['properties']), set(SCHEMA['required']))
        self.assertFalse(seen['data']['store'])
        serialized = json.dumps(seen['data'], ensure_ascii=False)
        self.assertNotIn('do-not-send-this-personal-value', serialized)
        self.assertNotIn('test-secret', serialized)
        self.assertEqual(seen['data']['input'].count('請預測是否流失'), 1)

    def test_no_key_and_invalid_action_are_rejected(self):
        with self.assertRaises(AgentChatError):
            propose_with_openai('請預測', OVERVIEW, '')
        with self.assertRaises(AgentChatError):
            validate_proposal({'action': 'shell', 'message': 'run'}, OVERVIEW)


if __name__ == '__main__':
    unittest.main()
