"""Reproduce a long-lived Streamlit process retaining a previous release."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from release_bootstrap import ensure_current_release

ROOT = Path(__file__).resolve().parents[1]


class ReleaseBootstrapTests(unittest.TestCase):
    def test_stale_router_registry_and_ui_refresh_without_replacing_core_types(self):
        # A separate process models an actual deployment without invalidating
        # class imports held by unrelated tests in the test runner.
        script = '''
import version, agent_hub, agent_modules, agent_supervisor, ui_layout, preprocessing
from release_bootstrap import ensure_current_release, current_source_version
context_type, registry_type = agent_hub.AgentContext, agent_hub.AgentRegistry
version.__version__ = "3.1.0"
preprocessing.__version__ = "3.1.0"
training_type = preprocessing.PrepConfig
agent_supervisor.plan_task = lambda *a, **kw: "stale router"
agent_modules.build_registry = lambda: "stale registry"
ui_layout.__version__ = "3.1.0"
assert ensure_current_release() == current_source_version()
assert agent_supervisor.plan_task("分析台積電股價").symbol == "2330"
assert "market.twse" in {c["name"] for c in agent_modules.build_registry().available()}
assert ui_layout.__version__ == current_source_version()
assert agent_hub.AgentContext is context_type
assert agent_hub.AgentRegistry is registry_type
assert preprocessing.__version__ == current_source_version()
assert preprocessing.PrepConfig is training_type
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_current_release_does_not_reload_during_each_widget_rerun(self):
        ensure_current_release()
        with patch("release_bootstrap.importlib.reload") as reload:
            ensure_current_release()
            reload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
