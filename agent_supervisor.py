"""Constrained natural-language task selector across registered skills.

A free-form instruction determines which *known* module receives bounded inputs.
Execution is synchronous and explicitly scoped; no code execution, hidden URLs,
automatic model training, or privilege escalation. Every external action needs
the relevant approval flags before the first tool runs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit
from agent_core import _provided_urls
from agent_hub import AgentContext, AgentRegistry
from agent_modules.video_tools import youtube_id, VideoError


class SupervisorError(ValueError):
    pass


@dataclass(frozen=True)
class TaskPlan:
    kind: str
    instruction: str
    tools: tuple[str, ...]
    urls: tuple[str, ...] = ()
    filename: str = ""
    requires_external: bool = False


def plan_task(instruction: str, *, filename: str = "", upload_present: bool = False) -> TaskPlan:
    if not isinstance(instruction, str) or not 2 <= len(instruction.strip()) <= 2000:
        raise SupervisorError("自然語言要求須為 2～2,000 字。")
    urls = _provided_urls(instruction)
    if len(urls) > 3:
        raise SupervisorError("明確網址每次最多 3 個。")
    name = filename.lower()
    if upload_present:
        if name.endswith((".csv", ".tsv")):
            kind, tools = "csv", ("csv.inspect",)
        elif name.endswith(".pdf"):
            kind, tools = "pdf", ("document.pdf",)
        elif name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            semantic = any(w in instruction.lower() for w in ("辨識", "描述", "內容", "vision", "describe"))
            kind, tools = "image", (("image.describe",) if semantic and not name.endswith(".gif")
                                    else ("image.inspect",))
        elif name.endswith((".srt", ".vtt")):
            kind, tools = "subtitles", ("video.subtitles",)
        elif name.endswith((".wav", ".mp3", ".mp4", ".m4a", ".webm")):
            kind, tools = "audio", ("audio.transcribe",)
        else:
            raise SupervisorError("檔案格式目前沒有可用的處理工具。")
        return TaskPlan(kind, instruction, tools, filename=filename,
                        requires_external=tools[0] in ("image.describe", "audio.transcribe"))
    if urls:
        if len(urls) == 1:
            try:
                youtube_id(urls[0])
                wants_subtitle = any(k in instruction.lower() for k in
                                     ("字幕", "逐字", "transcript", "captions"))
                return TaskPlan("youtube", instruction,
                                ("video.youtube_transcript",) if wants_subtitle else
                                ("video.youtube_info",), urls=(urls[0],))
            except VideoError:
                pass
        if any(urlsplit(u).scheme not in ("http", "https") for u in urls):
            raise SupervisorError("只接受 HTTP(S) 網址。")
        return TaskPlan("web", instruction, ("web.research_selected",), urls=tuple(urls))
    if len(instruction.strip()) > 300:
        raise SupervisorError("搜尋任務請縮短至 300 字以內。")
    return TaskPlan("search", instruction, ("web.search", "web.research_selected"))


def run_task(plan: TaskPlan, registry: AgentRegistry, *,
             upload: bytes | None = None, filename: str = "",
             brave_key: str = "", openai_key: str = "",
             approved_read=False, approved_follow=False,
             approved_external_upload=False, approved_report=False) -> dict:
    """Execute a pre-reviewed plan; only bounded registered skill handlers."""
    if not isinstance(plan, TaskPlan):
        raise SupervisorError("必須先建立任務計畫。")
    if not approved_read:
        raise PermissionError("必須先核准讀取上傳檔案或外部網路。")
    ctx = AgentContext(payload=upload or b"", filename=filename or plan.filename)
    audit = []
    data = None
    if plan.kind == "search":
        if not isinstance(brave_key, str) or len(brave_key) < 8:
            raise SupervisorError("網路搜尋需要 Brave Search API Key。")
        audit.append("web.search")
        found = registry.run("web.search", AgentContext(), {
            "query": plan.instruction, "api_key": brave_key, "count": 5}, approved=True)
        data = {"search": found}
        if approved_follow:
            urls = [x["url"] for x in found.get("results", [])[:3]]
            if urls:
                audit.append("web.research_selected")
                data["research"] = registry.run("web.research_selected", AgentContext(),
                                                {"urls": urls}, approved=True)
    elif plan.kind == "web":
        audit.append("web.research_selected")
        data = registry.run("web.research_selected", AgentContext(),
                            {"urls": list(plan.urls)}, approved=True)
    elif plan.kind == "youtube":
        audit.append(plan.tools[0])
        data = registry.run(plan.tools[0], AgentContext(),
                            {"url": plan.urls[0]}, approved=True)
    else:
        if upload is None or not upload:
            raise SupervisorError("任務預期的檔案不存在。")
        tool = plan.tools[0]
        if tool in ("audio.transcribe", "image.describe") and not approved_external_upload:
            raise PermissionError("外部視覺／音訊模型必須另行核准將檔案傳給 OpenAI。")
        params = {"api_key": openai_key} if tool in ("audio.transcribe", "image.describe") else {}
        audit.append(tool)
        data = registry.run(tool, ctx, params, approved=approved_external_upload)
    if approved_report and openai_key:
        sources = (data.get("research") or data).get("sources") if isinstance(data, dict) else None
        if isinstance(sources, list):
            audit.append("web.synthesize")
            report = registry.run("web.synthesize", AgentContext(), {
                "api_key": openai_key, "query": plan.instruction, "sources": sources}, approved=True)
            data = {"data": data, "report": report}
    if len(audit) > 4:
        raise SupervisorError("任務執行超過工具數量上限。")
    return {"status": "completed", "kind": plan.kind, "trace": audit, "result": data}
