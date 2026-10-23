"""Offline tests for research, safe optional media, SQLite and scheduling."""
import io
import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta

from agent_hub import AgentContext
from agent_modules import build_registry
from agent_modules.research_tools import ResearchError, search
from agent_modules.video_tools import VideoError, youtube_id
from agent_modules.document_media import DocumentError
from agent_modules.browser_tools import BrowserError
from agent_store import AgentStore, utc_now

CSV = b"col,y\n1,0\n2,1\n"


class Response:
    def __init__(self, data):
        self.data = io.BytesIO(json.dumps(data).encode("utf-8"))
    def __enter__(self):
        return self.data
    def __exit__(self, *args):
        return False
    def read(self, size=-1):
        return self.data.read(size)


class Opener:
    def __init__(self, callback):
        self.callback = callback
    def open(self, req, timeout):
        return self.callback(req, timeout)


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.r = build_registry()

    def test_all_modules_registered_and_private_tools_require_approval(self):
        names = {x["name"] for x in self.r.available()}
        self.assertTrue({"web.search", "web.render", "document.pdf",
                         "image.inspect", "image.describe", "audio.transcribe",
                         "video.youtube_info", "video.youtube_transcript",
                         "video.subtitles", "web.research_selected"} <= names)
        with self.assertRaises(PermissionError):
            self.r.run("image.describe", AgentContext(b"no", "a.png"), {})
        with self.assertRaises(PermissionError):
            self.r.run("web.search", AgentContext(), {"query": "nvidia"})
        with self.assertRaises(PermissionError):
            self.r.run("web.render", AgentContext(), {"url": "https://example.org/"})

    def test_brave_search_url_dedup_and_no_redirect_key(self):
        data = {"web": {"results": [
            {"url": "https://example.com/one", "title": "one", "description": "<b>brief</b>"},
            {"url": "https://example.com/one", "title": "duplicate"},
            {"url": "http://example.com/two", "title": "insecure"},
            {"url": "https://example.org/three", "title": "three"}
        ]}}
        seen = {}
        def answer(req, timeout):
            seen["url"] = req.full_url
            seen["token"] = req.headers.get("X-subscription-token")
            return Response(data)
        with patch("agent_modules.research_tools.request.build_opener", return_value=Opener(answer)):
            out = search(AgentContext(), {"query": "pricing", "api_key": "test-private-key", "count": 5})
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["results"][0]["snippet"], "brief")
        self.assertNotIn("test-private-key", seen["url"])
        self.assertEqual(seen["token"], "test-private-key")

    def test_bad_search_query_and_no_explicit_crawl_consent(self):
        with self.assertRaises(ResearchError):
            search(AgentContext(), {"query": "a", "api_key": "x" * 20})
        with self.assertRaises(PermissionError):
            self.r.run("web.research_selected", AgentContext(), {"urls": ["https://example.com"]})
        with self.assertRaises(ResearchError):
            self.r.run("web.research_selected", AgentContext(),
                       {"urls": ["https://example.com"] * 4}, approved=True)

    def test_youtube_url_allowlist_and_disabled_by_default(self):
        self.assertEqual(youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        with self.assertRaises(VideoError):
            youtube_id("https://www.youtube.com.attacker.net/watch?v=dQw4w9WgXcQ")
        with patch.dict(os.environ, {"AI_AGENT_YOUTUBE_ENABLED": "0"}):
            with self.assertRaises(VideoError):
                self.r.run("video.youtube_info", AgentContext(),
                           {"url": "https://youtu.be/dQw4w9WgXcQ"}, approved=True)
            with self.assertRaises(VideoError):
                self.r.run("video.youtube_transcript", AgentContext(),
                           {"url": "https://youtu.be/dQw4w9WgXcQ"}, approved=True)

    def test_pdf_and_image_and_subtitle_tools(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        stream = io.BytesIO()
        writer.write(stream)
        result = self.r.run("document.pdf", AgentContext(stream.getvalue(), "demo.pdf"))
        self.assertEqual(result["pages"], 1)

        from PIL import Image
        buff = io.BytesIO()
        Image.new("RGB", (24, 12)).save(buff, format="PNG")
        image_info = self.r.run("image.inspect", AgentContext(buff.getvalue(), "img.png"))
        self.assertEqual((image_info["width"], image_info["height"]), (24, 12))
        with self.assertRaises(DocumentError):
            self.r.run("document.pdf", AgentContext(b"not pdf", "fake.pdf"))
        subtitles = b"WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello world\n\n"
        out = self.r.run("video.subtitles", AgentContext(subtitles, "demo.vtt"))
        self.assertIn("Hello world", out["text"])

    def test_wav_info_and_no_transcribe_without_consent(self):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
            wav.writeframes(b"\x00\x00" * 8000)
        info = self.r.run("audio.inspect", AgentContext(buf.getvalue(), "voice.wav"))
        self.assertAlmostEqual(info["duration_seconds"], 1.0)
        with self.assertRaises(PermissionError):
            self.r.run("audio.transcribe", AgentContext(buf.getvalue(), "voice.wav"),
                       {"api_key": "not-shared"})

    def test_playwright_restricted_by_environment(self):
        with patch.dict(os.environ, {"AI_AGENT_ISOLATED_BROWSER": "0"}):
            with self.assertRaises(BrowserError):
                self.r.run("web.render", AgentContext(),
                           {"url": "https://example.com"}, approved=True)


class SQLiteTests(unittest.TestCase):
    def test_local_memory_requires_consent_and_forget(self):
        with tempfile.TemporaryDirectory() as temp:
            store = AgentStore(Path(temp, "agent.db"))
            with self.assertRaises(PermissionError):
                store.remember("save this")
            ident = store.remember("prefer CSV charts", consent=True)
            self.assertEqual(len(store.recall("CSV")), 1)
            self.assertTrue(store.forget(ident))
            self.assertEqual(store.recall(), [])

    def test_scheduler_requires_approval_runs_due_and_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            store = AgentStore(Path(temp, "agent.db"))
            with self.assertRaises(PermissionError):
                store.schedule_search("NVIDIA GPU news", 60)
            with self.assertRaises(ValueError):
                store.schedule_search("NVIDIA GPU news", 5, consent=True)
            ident = store.schedule_search("NVIDIA GPU news", 60, consent=True)
            self.assertEqual(store.run_due(lambda q: {"count": 0}), [])
            now = utc_now() + timedelta(hours=2)
            calls = []
            result = store.run_due(lambda q: (calls.append(q) or {
                "count": 1, "results": [{"title": "News", "url": "https://example.com"}]}), now=now)
            self.assertEqual(result[0]["status"], "completed")
            self.assertEqual(calls, ["NVIDIA GPU news"])
            self.assertEqual(store.run_due(lambda q: {}, now=now), [])
            store.stop_schedule(ident)
            self.assertEqual(store.run_due(lambda q: {}, now=now + timedelta(days=1)), [])

    def test_redacted_history_and_invalid_id(self):
        with tempfile.TemporaryDirectory() as temp:
            store = AgentStore(Path(temp, "agent.db"))
            ident = "a" * 32
            store.record_snapshot({"id": ident, "status": "completed", "steps": 1,
                                   "events": [{"tool": "csv.inspect", "status": "completed",
                                               "attempt": 1}], "secret": "do-not-store"})
            stored = Path(temp, "agent.db").read_bytes()
            self.assertNotIn(b"do-not-store", stored)
            self.assertEqual(store.history()[0]["id"], ident)


if __name__ == "__main__":
    unittest.main()
