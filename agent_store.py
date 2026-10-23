"""Local, opt-in SQLite task log, explicit user notes and recurring public searches.

No API keys, uploaded file bytes, authentication tokens or private browser state
are ever persisted. The scheduler runs ONLY when the operator runs the worker.
Do not use as a multi-tenant unauthenticated cloud service.
"""
from __future__ import annotations
from contextlib import contextmanager
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


class StoreError(ValueError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


class AgentStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.setup()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=10000")
            with conn:
                yield conn
        finally:
            conn.close()

    def setup(self):
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, query TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL, next_run TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1, last_status TEXT NOT NULL DEFAULT 'scheduled',
                last_run TEXT, result_json TEXT NOT NULL DEFAULT '{}'
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY, content TEXT NOT NULL, created_at TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS task_history (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                status TEXT NOT NULL, snapshot_json TEXT NOT NULL
            )""")

    def remember(self, text: str, *, consent=False) -> str:
        if not consent:
            raise PermissionError("記憶內容必須由使用者明確同意儲存。")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
            raise StoreError("記憶內容須為 1～500 字。")
        ident = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO notes VALUES (?, ?, ?)",
                       (ident, text.strip(), utc_now().isoformat()))
        return ident

    def recall(self, keyword: str = "") -> list[dict]:
        if not isinstance(keyword, str) or len(keyword) > 100:
            raise StoreError("搜尋內容過長。")
        with self.connect() as db:
            rows = db.execute("SELECT * FROM notes ORDER BY created_at DESC LIMIT 50").fetchall()
        return [dict(r) for r in rows if keyword.casefold() in r["content"].casefold()][:20]

    def forget(self, note_id: str) -> bool:
        if not re.fullmatch(r"[0-9a-f]{32}", note_id):
            raise StoreError("無效的記憶 ID。")
        with self.connect() as db:
            cur = db.execute("DELETE FROM notes WHERE id=?", (note_id,))
            return cur.rowcount > 0

    def record_snapshot(self, snapshot: dict) -> None:
        """Accept the redacted AgentTask.snapshot() schema only."""
        ident = snapshot.get("id")
        if not isinstance(ident, str) or not re.fullmatch(r"[0-9a-f]{32}", ident):
            raise StoreError("工作 ID 格式錯誤。")
        safe = {k: snapshot.get(k) for k in
                ("id", "status", "phase", "steps", "position", "events", "result_types", "recoverable")}
        events = safe.get("events") or []
        if not isinstance(events, list) or len(events) > 20:
            raise StoreError("工作執行紀錄格式不正確。")
        safe["events"] = [
            {"tool": str(x.get("tool", ""))[:80],
             "status": str(x.get("status", ""))[:30],
             "attempt": x.get("attempt", 0)} for x in events if isinstance(x, dict)
        ]
        payload = json.dumps(safe, ensure_ascii=False)[:7000]
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO task_history VALUES (?, ?, ?, ?)",
                       (ident, utc_now().isoformat(), str(safe["status"])[:32], payload))

    def history(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM task_history ORDER BY created_at DESC LIMIT 50").fetchall()
        return [{"id": x["id"], "status": x["status"],
                 "created_at": x["created_at"]} for x in rows]

    def schedule_search(self, query: str, interval_minutes: int, *, consent=False) -> str:
        if not consent:
            raise PermissionError("需要明確核准排程與未來的外部搜尋。")
        if (not isinstance(query, str) or not 2 <= len(query.strip()) <= 200
                or type(interval_minutes) is not int or
                interval_minutes < 60 or interval_minutes > 10080):
            raise StoreError("查詢需 2～200 字；排程間隔為 60～10080 分鐘。")
        ident = uuid4().hex
        due = (utc_now() + timedelta(minutes=interval_minutes)).isoformat()
        with self.connect() as db:
            db.execute("INSERT INTO jobs (id,query,interval_minutes,next_run) VALUES (?,?,?,?)",
                       (ident, query.strip(), interval_minutes, due))
        return ident

    def list_schedules(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY next_run LIMIT 50").fetchall()
        return [dict(x) for x in rows]

    def stop_schedule(self, job_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise StoreError("無效的排程 ID。")
        with self.connect() as db:
            db.execute("UPDATE jobs SET enabled=0 WHERE id=?", (job_id,))

    def run_due(self, search_fn, *, now=None, limit=3) -> list[dict]:
        """One scheduler tick. Each durable job is claimed before external I/O."""
        now = now or utc_now()
        if limit < 1 or limit > 10:
            raise StoreError("單次排程上限為 1～10。")
        selected = []
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM jobs WHERE enabled=1 AND next_run<=? ORDER BY next_run LIMIT ?",
                (now.isoformat(), limit)).fetchall()
            for row in rows:
                next_run = (now + timedelta(minutes=row["interval_minutes"])).isoformat()
                db.execute("UPDATE jobs SET next_run=?,last_status='running' WHERE id=?",
                           (next_run, row["id"]))
                selected.append(dict(row))
        outcomes = []
        for job in selected:
            try:
                result = search_fn(job["query"])
                compact = json.dumps({
                    "count": result.get("count", 0),
                    "results": [{"title": str(r.get("title", ""))[:180],
                                 "url": str(r.get("url", ""))[:800]}
                                for r in result.get("results", [])[:10]]
                }, ensure_ascii=False)
                state = "completed"
            except Exception:
                state, compact = "failed", "{}"
            with self.connect() as db:
                db.execute("UPDATE jobs SET last_run=?,last_status=?,result_json=? WHERE id=?",
                           (now.isoformat(), state, compact, job["id"]))
            outcomes.append({"id": job["id"], "status": state})
        return outcomes
