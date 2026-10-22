"""Agent registry safety, extension and existing CSV workflow integration."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_hub import AgentContext, AgentRegistry, Capability
from agent_modules import build_registry


class AgentHubTests(unittest.TestCase):
    def setUp(self):
        self.context = AgentContext(b'age,target\n20,0\n30,1\n40,0\n50,1\n', 'sample.csv')
        self.registry = build_registry()

    def test_discover_and_extend(self):
        names = [x['name'] for x in self.registry.available()]
        self.assertIn('csv.inspect', names)
        self.assertIn('csv.plan', names)
        self.assertIn('csv.train', names)
        self.registry.register(Capability('future.example', '未來模組', lambda ctx, params: 'ok'))
        self.assertEqual(self.registry.run('future.example', self.context), 'ok')
        with self.assertRaises(ValueError):
            self.registry.register(Capability('future.example', '重複', lambda ctx, params: 'bad'))
        with self.assertRaises(ValueError):
            self.registry.run('shell.run', self.context)

    def test_inspect_and_explicit_target(self):
        overview = self.registry.run('csv.inspect', self.context)
        self.assertEqual(overview['rows'], 4)
        self.assertEqual(overview['columns'], ['age', 'target'])
        missing = self.registry.run('csv.plan', self.context)
        self.assertTrue(missing['target_required'])
        plan = self.registry.run('csv.plan', self.context, {'target': 'target'})
        self.assertEqual(plan['suggested_options']['task'], 'classification')

    def test_training_requires_approval_and_uses_shared_engine(self):
        request = {'target': 'target', 'task': 'classification', 'model': 'auto'}
        with self.assertRaises(PermissionError):
            self.registry.run('csv.train', self.context, request)
        with patch('training_service.run_training_bytes', return_value=(b'zip-content', {'metrics': {}})) as mocked:
            result = self.registry.run('csv.train', self.context, request, approved=True)
            self.assertEqual(result['bundle'], b'zip-content')
            args, _ = mocked.call_args
            self.assertEqual(args[0], self.context.payload)
            self.assertEqual(args[1]['target'], 'target')
            self.assertEqual(args[1]['encoding'], 'auto')

    def test_training_rejects_unknown_parameters(self):
        with self.assertRaises(ValueError):
            self.registry.run('csv.train', self.context,
                              {'target': 'target', 'unsafe_command': 'echo hi'}, approved=True)


if __name__ == '__main__':
    unittest.main()
