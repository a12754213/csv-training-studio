"""Agent Core 2.0 contract tests: multi-step routing, privacy and approval."""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core import (
    AgentCoreError, SCHEMA, execute_approved_training, execute_read_plan,
    prepare_training, propose_with_openai, suggest_without_api, validate_intent,
)
from agent_hub import AgentRegistry, Capability

URL = "https://example.org/data.csv"
CSV = b"id,label\n1,0\n2,1\n"


class FakeResponse:
    def __init__(self, body):
        self.body = io.BytesIO(json.dumps(body).encode())
    def __enter__(self):
        return self.body
    def __exit__(self, *args):
        return False


def make_registry(kind="table"):
    registry = AgentRegistry()
    calls = []
    def add(name, handler, approval=False):
        def logged(ctx, params):
            calls.append((name, ctx.payload, params))
            return handler(ctx, params)
        registry.register(Capability(name, name, logged, requires_approval=approval))
    add("web.crawl", lambda ctx, params: {
        "kind": kind, "url": params["url"],
        "csv_bytes": CSV if kind == "table" else b"",
        "text": "An example article." if kind == "text" else "",
    }, approval=True)
    add("csv.inspect", lambda ctx, params: {
        "rows": 2, "columns": ["id", "label"], "profile": [],
    })
    add("csv.plan", lambda ctx, params: {
        "suggested_options": {"target": params["target"], "task": "classification", "model": "auto"},
        "notes": [],
    })
    add("text.inspect", lambda ctx, params: {"characters": 19, "preview": "An example article.", "note": "test"})
    add("csv.train", lambda ctx, params: {"bundle": b"zip", "summary": {"metrics": {"accuracy": 1}}},
        approval=True)
    return registry, calls


def intent(source="web", target="label", goal="prepare_training"):
    return validate_intent({
        "source": source, "goal": goal,
        "url": URL if source == "web" else None,
        "target": target, "message": "Inspect then plan.",
    }, instruction=f"分析 {URL}", has_upload=source == "upload",
        upload_columns=["id", "label"])


class AgentCoreTests(unittest.TestCase):
    def test_preview_does_not_trigger_network(self):
        with patch("agent_core.request.urlopen") as opened:
            planned = suggest_without_api("幫我分析 " + URL, has_upload=False)
        self.assertEqual(planned["source"], "web")
        self.assertIn("web.crawl", planned["tools_preview"])
        opened.assert_not_called()

    def test_hallucinated_url_and_unknown_action_rejected(self):
        raw = {"source": "web", "goal": "inspect",
               "url": "https://evil.example/secret", "target": None, "message": "ok"}
        with self.assertRaises(AgentCoreError):
            validate_intent(raw, instruction=f"分析 {URL}", has_upload=False)
        with self.assertRaises(AgentCoreError):
            validate_intent(dict(raw, goal="run_shell"), instruction=URL, has_upload=False)
        with self.assertRaises(AgentCoreError):
            validate_intent(dict(raw, arbitrary_command="whoami"), instruction=URL, has_upload=False)

    def test_upload_target_must_be_real_column(self):
        proposed = validate_intent({"source": "upload", "goal": "prepare_training",
                                    "url": None, "target": "not-real", "message": ""},
                                   instruction="train", has_upload=True, upload_columns=["label"])
        self.assertIsNone(proposed["target"])

    def test_chained_web_table_tool_order_and_separate_training_approval(self):
        registry, calls = make_registry()
        outcome = execute_read_plan(intent(), registry, user_approved=True)
        self.assertEqual([step["tool"] for step in outcome["trace"]],
                         ["web.crawl", "csv.inspect", "csv.plan"])
        self.assertEqual([name for name, _, _ in calls],
                         ["web.crawl", "csv.inspect", "csv.plan"])
        self.assertNotIn("csv.train", [name for name, _, _ in calls])
        with self.assertRaises(PermissionError):
            execute_approved_training(registry, outcome, {"target": "label"})
        self.assertEqual(prepare_training(registry, outcome, "label")["suggested_options"]["target"], "label")
        result = execute_approved_training(registry, outcome,
                                           {"target": "label", "task": "classification"}, user_approved=True)
        self.assertEqual(result["bundle"], b"zip")

    def test_text_cannot_train_or_become_fake_csv(self):
        registry, calls = make_registry(kind="text")
        outcome = execute_read_plan(intent(target=None, goal="inspect"), registry, user_approved=True)
        self.assertEqual([step["tool"] for step in outcome["trace"]],
                         ["web.crawl", "text.inspect"])
        with self.assertRaises(AgentCoreError):
            prepare_training(registry, outcome, "label")
        with self.assertRaises(AgentCoreError):
            execute_approved_training(registry, outcome, {"target": "label"}, user_approved=True)

    def test_direct_csv_upload_and_unknown_target_fail_closed(self):
        registry, calls = make_registry()
        result = execute_read_plan(intent(source="upload"), registry, upload=CSV, user_approved=True)
        self.assertEqual([s["tool"] for s in result["trace"]], ["csv.inspect", "csv.plan"])
        self.assertEqual(calls[0][1], CSV)
        with self.assertRaises(AgentCoreError):
            execute_approved_training(registry, result, {"target": "fake"}, user_approved=True)

    def test_llm_receives_only_instruction_and_header_names(self):
        raw = {"source": "upload", "goal": "prepare_training", "url": None,
               "target": "label", "message": "plan"}
        response = {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(raw)}
        ]}]}
        seen = {}
        def fake_open(req, timeout):
            seen["body"] = json.loads(req.data)
            return FakeResponse(response)
        with patch("agent_core.request.urlopen", side_effect=fake_open):
            out = propose_with_openai("預測 label", "secret-api-key", has_upload=True,
                                      upload_columns=["id", "label"])
        self.assertEqual(out["target"], "label")
        self.assertEqual(set(SCHEMA["properties"]), set(SCHEMA["required"]))
        self.assertTrue(seen["body"]["text"]["format"]["strict"])
        self.assertFalse(seen["body"]["store"])
        request_content = json.dumps(seen["body"])
        self.assertNotIn("secret-api-key", request_content)
        self.assertNotIn("CSV_PRIVATE_ROW", request_content)
        self.assertEqual(json.loads(seen["body"]["input"])["uploaded_column_names_only"], ["id", "label"])

    def test_cannot_use_tool_without_valid_source(self):
        registry, _ = make_registry()
        with self.assertRaises(AgentCoreError):
            execute_read_plan({"source": "none"}, registry, user_approved=True)
        with self.assertRaises(AgentCoreError):
            execute_read_plan({"source": "upload"}, registry, user_approved=True)


if __name__ == "__main__":
    unittest.main()
