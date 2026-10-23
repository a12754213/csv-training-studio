"""Explicitly run a single scheduled-search batch; schedule externally.

Example: python agent_worker.py --db outputs/agent_hub.db --once
This does NOT spawn from Streamlit. Worker never runs model training or opens
any arbitrary search result URL. For ongoing runs configure an OS task/cron.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path

from agent_store import AgentStore
from agent_hub import AgentContext
from agent_modules.research_tools import search


def tick(db_path: Path, *, key: str) -> list[dict]:
    if not key or len(key) < 8:
        raise ValueError("需要 BRAVE_SEARCH_API_KEY 才能執行排程搜尋。")
    store = AgentStore(db_path)
    return store.run_due(lambda query: search(AgentContext(), {
        "query": query, "api_key": key, "count": 5
    }))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("outputs/agent_hub.db"))
    parser.add_argument("--once", action="store_true", required=True,
                        help="Execute one bounded tick; no resident background worker.")
    args = parser.parse_args()
    statuses = tick(args.db, key=os.environ.get("BRAVE_SEARCH_API_KEY", ""))
    for s in statuses:
        print(s["id"], s["status"])


if __name__ == "__main__":
    main()
