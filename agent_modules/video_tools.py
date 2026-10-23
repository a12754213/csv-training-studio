"""Restricted YouTube metadata, caption discovery, and transcript inspection.

Metadata extraction is opt-in. Video/audio downloading and DRM bypass are absent.
Only a known public YouTube video URL is accepted.
"""
from __future__ import annotations
import os
import re
from urllib.parse import urlsplit, parse_qs
from agent_hub import AgentContext, AgentRegistry, Capability


class VideoError(ValueError):
    pass


def youtube_id(value: str) -> str:
    if not isinstance(value, str) or len(value) > 400:
        raise VideoError("請提供 YouTube 公開影片網址。")
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        raise VideoError("僅支援 HTTPS YouTube 網址。")
    host = (parts.hostname or "").lower()
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        vid = parse_qs(parts.query).get("v", [""])[0] if parts.path == "/watch" else (
            parts.path.split("/")[2] if parts.path.startswith(("/shorts/", "/live/")) and
            len(parts.path.split("/")) > 2 else "")
    elif host == "youtu.be":
        vid = parts.path.lstrip("/")
    else:
        raise VideoError("只支援 YouTube 或 youtu.be 影片網址。")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        raise VideoError("無法辨識影片 ID。")
    return vid


def video_info(ctx: AgentContext, params: dict) -> dict:
    if set(params) != {"url"}:
        raise VideoError("只接受 url 參數。")
    vid = youtube_id(params["url"])
    if os.environ.get("AI_AGENT_YOUTUBE_ENABLED") != "1":
        raise VideoError("YouTube 遠端讀取預設停用，需由本機管理員啟用。")
    try:
        import yt_dlp
    except ImportError:
        raise VideoError("需安裝選用的 yt-dlp 套件。") from None
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": False, "noplaylist": True, "ignoreerrors": False,
            "socket_timeout": 10, "retries": 0, "extractor_args": {"youtube": {"player_client": ["web"]}}}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            doc = ydl.extract_info("https://www.youtube.com/watch?v=" + vid, download=False)
    except Exception:
        raise VideoError("YouTube 無法提供影片資訊，可能受限於權限或網站限制。") from None
    if not isinstance(doc, dict) or doc.get("id") != vid:
        raise VideoError("影片資料不符合原始網址。")
    def languages(key):
        captions = doc.get(key) or {}
        return sorted(str(lang)[:15] for lang in captions if isinstance(lang, str))[:60]
    return {
        "id": vid, "url": "https://www.youtube.com/watch?v=" + vid,
        "title": str(doc.get("title") or "")[:300], "channel": str(doc.get("channel") or "")[:150],
        "duration_seconds": doc.get("duration") if isinstance(doc.get("duration"), (int, float)) else None,
        "description": str(doc.get("description") or "")[:3500],
        "subtitles_languages": languages("subtitles"),
        "automatic_captions_languages": languages("automatic_captions"),
        "note": "僅擷取公開影片資訊及可用字幕語言，不下載影片、音訊或字幕內容。"
    }



def youtube_transcript(ctx: AgentContext, params: dict) -> dict:
    if set(params) - {"url", "languages"}:
        raise VideoError("只接受 url 和 languages。")
    vid = youtube_id(params.get("url", ""))
    if os.environ.get("AI_AGENT_YOUTUBE_ENABLED") != "1":
        raise VideoError("YouTube 字幕讀取預設停用，請在本機受控環境啟用。")
    languages = params.get("languages", ["zh-Hant", "zh", "en"])
    if (not isinstance(languages, list) or not 1 <= len(languages) <= 4 or
            any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z-]{2,12}", v) for v in languages)):
        raise VideoError("字幕語言格式錯誤。")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        raise VideoError("請安裝選用的 youtube-transcript-api 套件。") from None
    try:
        fetched = YouTubeTranscriptApi().fetch(vid, languages=languages)
        snippets = []
        for item in fetched:
            snippets.append({"start": round(float(item.start), 2),
                             "text": str(item.text)[:300]})
            if len(snippets) >= 300:
                break
    except Exception:
        raise VideoError("這支影片目前無法透過公開字幕 API 取得字幕。") from None
    return {"id": vid, "segments": snippets, "language": getattr(fetched, "language_code", ""),
            "text": "\\n".join(x["text"] for x in snippets)[:28000],
            "note": "這是公開字幕而非視覺畫面辨識；不能保證影片內容完全等於字幕。"}

def register(registry: AgentRegistry) -> None:
    registry.register(Capability("video.youtube_info", "YouTube 公開影片資訊與字幕語言（選用）",
                                 video_info, requires_approval=True))
    registry.register(Capability("video.youtube_transcript", "YouTube 公開字幕轉文字（選用）",
                                 youtube_transcript, requires_approval=True))
