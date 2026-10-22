"""Actual STDIO handshake, upload, train, polling and artifact resource roundtrip."""
import asyncio
import base64
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'optional MCP dependency not installed')
class MCPChecks(unittest.TestCase):
    def test_real_stdio_training_and_resource(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def workflow(root):
            inbox = root / 'inbox'; inbox.mkdir()
            payload = (ROOT / 'samples/demo_timeseries.csv').read_bytes()
            (inbox / 'daily.csv').write_bytes(payload)
            parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'chatgpt_server.py'),
                                                '--workspace', str(root / 'work'), '--inbox', str(inbox)])
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    self.assertIn('start_training', [t.name for t in tools.tools])
                    uploaded = await session.call_tool('import_csv', {'path': 'daily.csv'})
                    self.assertFalse(uploaded.isError, uploaded)
                    dataset = uploaded.structuredContent
                    plan = await session.call_tool('suggest_training_plan', {'dataset_id': dataset['dataset_id'],
                                                   'target': '銷量', 'forecast_intent': True})
                    self.assertFalse(plan.isError, plan)
                    self.assertEqual(plan.structuredContent['suggested_options']['task'], 'time_series')
                    response = await session.call_tool('start_training', {'dataset_id': dataset['dataset_id'],
                            'target': '銷量', 'task': 'time_series', 'time_column': '日期',
                            'excluded_columns': ['流水號'], 'lookback': 14, 'horizon': 2})
                    self.assertFalse(response.isError, response)
                    job_id = response.structuredContent['job_id']
                    for _ in range(120):
                        result = await session.call_tool('get_training_result', {'job_id': job_id})
                        self.assertFalse(result.isError, result)
                        job = result.structuredContent
                        if job['status'] not in {'queued', 'running'}:
                            break
                        await asyncio.sleep(.1)
                    self.assertEqual(job['status'], 'completed', job)
                    resource = await session.read_resource(job['artifact_uri'])
                    binary = base64.b64decode(resource.contents[0].blob)
                    with zipfile.ZipFile(io.BytesIO(binary)) as z:
                        self.assertIn('model.joblib', z.namelist())
                        self.assertIn('test_predictions.csv', z.namelist())
                    denied = await session.call_tool('import_csv', {'path': '../outside.csv'})
                    self.assertTrue(denied.isError)
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(asyncio.wait_for(workflow(Path(tmp)), timeout=45))


if __name__ == '__main__':
    unittest.main()
