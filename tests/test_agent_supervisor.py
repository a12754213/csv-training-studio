"""Natural-language supervisor routes to registered tools without hidden privileges."""
import unittest

from agent_hub import AgentContext, AgentRegistry, Capability
from agent_supervisor import plan_task, run_task, SupervisorError


class SupervisorTests(unittest.TestCase):
    def registry(self):
        reg = AgentRegistry()
        calls = []
        def add(name, reply, needs=False):
            def handler(ctx, params):
                calls.append((name, ctx.payload, params.copy()))
                return reply
            reg.register(Capability(name, "test", handler, requires_approval=needs))
        add("web.search", {"results": [
            {"url": "https://example.org/a"}, {"url": "https://example.org/b"}],
            "count": 2}, True)
        add("web.research_selected", {"sources": [{
            "url": "https://example.org/a", "status": "completed",
            "text_preview": "sample source", "title": "A", "kind": "text"
        }]}, True)
        add("web.synthesize", {"report": "source [1]", "sources": []}, True)
        add("document.pdf", {"pages": 1}, False)
        add("image.inspect", {"width": 2}, False)
        add("image.describe", {"description": "a cat"}, True)
        add("audio.transcribe", {"text": "hello"}, True)
        add("csv.inspect", {"rows": 2, "columns": ["y"]}, False)
        add("video.youtube_info", {"title": "title"}, True)
        add("video.youtube_transcript", {"text": "subs"}, True)
        return reg, calls

    def test_query_automatically_plans_search_and_follows_opt_in(self):
        task = plan_task("幫我找台灣科技新聞")
        self.assertEqual(task.kind, "search")
        reg, calls = self.registry()
        with self.assertRaises(PermissionError):
            run_task(task, reg, brave_key="private-brave")
        output = run_task(task, reg, brave_key="private-brave", approved_read=True)
        self.assertEqual(output["trace"], ["web.search"])
        calls.clear()
        output = run_task(task, reg, brave_key="private-brave", approved_read=True,
                          approved_follow=True, approved_report=True, openai_key="openai-secret")
        self.assertEqual(output["trace"], ["web.search", "web.research_selected", "web.synthesize"])
        self.assertEqual(calls[1][2]["urls"], ["https://example.org/a", "https://example.org/b"])

    def test_uploaded_document_image_and_audio_are_routed_safely(self):
        reg, calls = self.registry()
        pdf = plan_task("幫我檢查文件", filename="demo.pdf", upload_present=True)
        out = run_task(pdf, reg, upload=b"%PDF-1.7", approved_read=True)
        self.assertEqual(out["trace"], ["document.pdf"])
        image = plan_task("請描述圖片內容", filename="photo.png", upload_present=True)
        self.assertEqual(image.tools, ("image.describe",))
        with self.assertRaises(PermissionError):
            run_task(image, reg, upload=b"png", approved_read=True)
        out = run_task(image, reg, upload=b"png", approved_read=True,
                       approved_external_upload=True, openai_key="openai-secret")
        self.assertEqual(out["trace"], ["image.describe"])
        audio = plan_task("請幫我轉錄", filename="speech.mp3", upload_present=True)
        self.assertTrue(audio.requires_external)
        self.assertEqual(audio.tools, ("audio.transcribe",))

    def test_youtube_subtitle_and_explicit_web_url(self):
        yt = plan_task("幫我找字幕 https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(yt.tools, ("video.youtube_transcript",))
        another = plan_task("讀取 https://example.org/data.csv")
        self.assertEqual(another.kind, "web")
        self.assertEqual(another.urls, ("https://example.org/data.csv",))

    def test_unknown_extension_and_overlong_search_fail(self):
        with self.assertRaises(SupervisorError):
            plan_task("read document", filename="secret.exe", upload_present=True)
        with self.assertRaises(SupervisorError):
            plan_task("n" * 310)
        with self.assertRaises(SupervisorError):
            plan_task("a" * 2001)


if __name__ == "__main__":
    unittest.main()
