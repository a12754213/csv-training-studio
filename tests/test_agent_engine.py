"""Agent Core 3.0 offline tests with fake registered capabilities."""
import json
import tempfile
import unittest
from pathlib import Path

from agent_engine import (
    AgentEngineError, TaskJournal, choose_next, make_task, next_actions,
    perform_next, run_until_gate,
)
from agent_hub import AgentRegistry, Capability

WEB = "https://example.org/sample"
CSV = b"id,target\n1,0\n2,1\n3,0\n4,1\n"


def fake_registry(kind="table", fail_first=False):
    registry = AgentRegistry()
    history = []
    failures = {"remaining": 1 if fail_first else 0}
    def crawl(ctx, params):
        history.append("web.crawl")
        if failures["remaining"]:
            failures["remaining"] -= 1
            raise OSError("transient connection")
        return {"url": params["url"], "kind": kind, "csv_bytes": CSV if kind == "table" else b"",
                "text": "This is a public sample article." if kind == "text" else ""}
    def inspect(ctx, params):
        history.append("csv.inspect")
        return {"rows": 4, "columns": ["id", "target"], "profile": [],
                "suggested_excluded_columns": ["id"]}
    def plan(ctx, params):
        history.append("csv.plan")
        return {"notes": [], "suggested_options": {"target": params["target"],
                "task": "classification", "model": "auto"}}
    def text(ctx, params):
        history.append("text.inspect")
        return {"characters": 32, "preview": "This is a public sample article.",
                "note": "no LLM summary"}
    def train(ctx, params):
        raise AssertionError("Training must never run from adaptive read-only agent")
    registry.register(Capability("web.crawl", "web", crawl, requires_approval=True))
    registry.register(Capability("csv.inspect", "inspect", inspect))
    registry.register(Capability("csv.plan", "plan", plan))
    registry.register(Capability("text.inspect", "text", text))
    registry.register(Capability("csv.train", "train", train, requires_approval=True))
    return registry, history


class AgentEngineTests(unittest.TestCase):
    def test_source_must_be_user_provided_and_bounded(self):
        with self.assertRaises(AgentEngineError):
            make_task("hello", urls=[WEB])
        with self.assertRaises(AgentEngineError):
            make_task(" ".join([WEB]), upload=b"")
        with self.assertRaises(AgentEngineError):
            make_task("hi " + " ".join("https://example.org/" + str(i) for i in range(4)))
        with self.assertRaises(AgentEngineError):
            make_task("https://example.org", urls=["http://169.254.169.254"])
        self.assertEqual(len(make_task(WEB).sources), 1)

    def test_web_requires_preapproval_and_routes_after_observation(self):
        task = make_task(WEB, target="target")
        registry, called = fake_registry()
        self.assertEqual(run_until_gate(task, registry), "needs_approval")
        self.assertEqual(called, [])
        result = run_until_gate(task, registry, approved_urls={WEB})
        self.assertEqual(task.status, "completed")
        self.assertEqual(result, "next.source")
        self.assertEqual(called, ["web.crawl", "csv.inspect", "csv.plan"])
        self.assertEqual([x["tool"] for x in task.events],
                         ["web.crawl", "csv.inspect", "csv.plan", "next.source"])
        self.assertEqual(task.results[0]["plan"]["suggested_options"]["target"], "target")

    def test_text_route_uses_text_tool_not_fake_csv(self):
        task = make_task(WEB, target="target")
        registry, called = fake_registry(kind="text")
        run_until_gate(task, registry, approved_urls={WEB})
        self.assertEqual(task.status, "completed")
        self.assertEqual(called, ["web.crawl", "text.inspect"])
        self.assertEqual(task.results[0]["kind"], "text")

    def test_two_web_sources_and_uploaded_csv_in_one_job(self):
        other = "https://example.org/second"
        task = make_task(WEB + " " + other, upload=CSV, target="target")
        registry, called = fake_registry()
        run_until_gate(task, registry, approved_urls={WEB, other})
        self.assertEqual(task.status, "completed")
        self.assertEqual(len(task.results), 3)
        self.assertEqual(called.count("web.crawl"), 2)
        self.assertEqual(called.count("csv.inspect"), 3)
        self.assertEqual(called.count("csv.plan"), 3)
        self.assertLessEqual(task.steps, 12)

    def test_retries_stop_after_two_failures(self):
        registry, called = fake_registry(fail_first=True)
        task = make_task(WEB)
        outcome = run_until_gate(task, registry, approved_urls={WEB})
        self.assertEqual(outcome, "retryable")
        self.assertEqual(task.position, 0)
        self.assertEqual(task.steps, 0)
        outcome = run_until_gate(task, registry, approved_urls={WEB})
        self.assertEqual(task.status, "completed")
        self.assertEqual(outcome, "next.source")
        self.assertEqual(called.count("web.crawl"), 2)

        task2 = make_task(WEB)
        registry2, _ = fake_registry()
        def always_fail(ctx, params):
            raise OSError("no connection")
        # A new registry proves two successive failures stop the job.
        fail_reg = AgentRegistry()
        fail_reg.register(Capability("web.crawl", "web", always_fail, True))
        self.assertEqual(run_until_gate(task2, fail_reg, approved_urls={WEB}), "retryable")
        self.assertEqual(run_until_gate(task2, fail_reg, approved_urls={WEB}), "failed")
        self.assertEqual(task2.status, "failed")

    def test_model_must_choose_registered_legal_state_action(self):
        task = make_task(WEB)
        with self.assertRaises(AgentEngineError):
            choose_next(task, adviser=lambda snapshot: "shell.run")
        with self.assertRaises(AgentEngineError):
            choose_next(task, adviser=lambda snapshot: "csv.train")
        self.assertEqual(task.steps, 0)
        self.assertEqual(choose_next(task, adviser=lambda x: x["allowed_actions"][0]), "web.crawl")

    def test_journal_redacts_payload_and_disallows_traversal(self):
        task = make_task(WEB + "?access_token=secret-123", upload=CSV)
        registry, _ = fake_registry()
        with tempfile.TemporaryDirectory() as tmp:
            log = TaskJournal(Path(tmp))
            run_until_gate(task, registry, approved_urls={WEB + "?access_token=secret-123"}, journal=log)
            p = Path(tmp, task.id + ".json")
            saved = p.read_text(encoding="utf-8")
            self.assertNotIn("secret-123", saved)
            self.assertNotIn("id,target", saved)
            self.assertNotIn("uploaded.csv", saved)
            data = log.read(task.id)
            self.assertEqual(data["status"], "completed")
            with self.assertRaises(AgentEngineError):
                log.read("../secret")
            # No raw payload persisted, therefore interrupted runs cannot be resumed blindly.
            task.status = "retryable"
            log.write(task)
            self.assertEqual(log.read(task.id)["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
