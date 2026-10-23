"""Composable Agent router: an auditable decision about which registered tool to call.

The initial routing rules operate without an LLM/API key. The page fetch is
explicitly approved by the caller; model training is never silently started.
"""
from __future__ import annotations

from agent_hub import AgentContext, AgentRegistry


def run_web_workflow(registry: AgentRegistry, url: str, *, target: str = "") -> dict:
    """web.crawl -> csv.inspect/csv.plan OR text.inspect; no automatic training."""
    fetched = registry.run("web.crawl", AgentContext(), {"url": url}, approved=True)
    steps = ["web.crawl"]
    if fetched["kind"] == "table":
        ctx = AgentContext(payload=fetched["csv_bytes"], filename="web_extract.csv")
        overview = registry.run("csv.inspect", ctx)
        steps.append("csv.inspect")
        plan = None
        if target and target in overview["columns"]:
            plan = registry.run("csv.plan", ctx, {"target": target})
            steps.append("csv.plan")
        return {
            "route": "csv_training",
            "reason": "來源包含結構化表格，因此先交給 CSV 資料分析工具；訓練仍需指定目標與核准。",
            "steps": steps, "fetched": fetched, "overview": overview,
            "plan": plan, "target_valid": bool(target and target in overview["columns"]),
            "next_tool": "csv.train" if plan and plan.get("suggested_options") else "csv.plan",
        }
    ctx = AgentContext(payload=fetched["text"].encode("utf-8"), filename="web_article.txt")
    text_info = registry.run("text.inspect", ctx)
    steps.append("text.inspect")
    return {
        "route": "text_analysis",
        "reason": "來源主要是文章文字，沒有可供表格訓練的資料；交給文字分析，不硬轉成 CSV。",
        "steps": steps, "fetched": fetched, "text_info": text_info,
        "next_tool": "text.inspect",
    }
