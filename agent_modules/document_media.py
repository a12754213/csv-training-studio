"""Explicit-file document, image, speech and subtitle skills.

No implicit uploads to third-party APIs. API-based vision and audio transcription
require separate credentials and user approval. Files stay in memory in this module.
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import re
import wave
from urllib import error, request
from xml.etree import ElementTree

from agent_hub import AgentContext, AgentRegistry, Capability


class DocumentError(ValueError):
    pass


def _assert_payload(ctx: AgentContext, limit=25_000_000):
    if not ctx.payload or len(ctx.payload) > limit:
        raise DocumentError("請提供非空檔案，大小不超過限制。")


def pdf_inspect(ctx: AgentContext, params: dict) -> dict:
    if params:
        raise DocumentError("PDF 分析不接受其他參數。")
    _assert_payload(ctx, 15_000_000)
    if not ctx.payload.startswith(b"%PDF-"):
        raise DocumentError("檔案不是 PDF。")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise DocumentError("缺少 pypdf，請先安裝可選的文件依賴。") from None
    try:
        reader = PdfReader(io.BytesIO(ctx.payload), strict=True)
        if reader.is_encrypted or len(reader.pages) > 100:
            raise DocumentError("不支援加密 PDF 或超過 100 頁的文件。")
        texts = []
        for pg in reader.pages:
            texts.append((pg.extract_text() or "")[:6000])
        full = "\n".join(texts)[:20000]
    except DocumentError:
        raise
    except Exception:
        raise DocumentError("無法解析 PDF；掃描型文件可能需要 OCR。") from None
    return {"type": "pdf", "pages": len(reader.pages),
            "characters": len(full), "text": full,
            "note": "文字型 PDF 已擷取。掃描或圖片中的文字不會自動辨識。"}


def image_inspect(ctx: AgentContext, params: dict) -> dict:
    if params:
        raise DocumentError("圖片概況不接受其他參數。")
    _assert_payload(ctx, 8_000_000)
    try:
        from PIL import Image
        with Image.open(io.BytesIO(ctx.payload)) as img:
            if img.format not in ("PNG", "JPEG", "WEBP", "GIF"):
                raise DocumentError("只支援 PNG、JPEG、WEBP、GIF。")
            if img.width * img.height > 35_000_000:
                raise DocumentError("圖片解析度超過安全上限。")
            return {"type": "image", "format": img.format,
                    "width": img.width, "height": img.height,
                    "note": "這是圖片檔案資訊；若要辨識內容需額外呼叫視覺模型。"}
    except DocumentError:
        raise
    except Exception:
        raise DocumentError("無法解析圖片。") from None


def image_describe(ctx: AgentContext, params: dict) -> dict:
    if set(params) != {"api_key"}:
        raise DocumentError("圖片語意分析只接受 api_key。")
    info = image_inspect(ctx, {})
    if info["format"] == "GIF":
        raise DocumentError("目前視覺模型只接受 PNG/JPEG/WEBP。")
    key = params["api_key"]
    if not isinstance(key, str) or len(key) < 8:
        raise DocumentError("請提供 OpenAI API Key。")
    mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[info["format"]]
    body = {"model": "gpt-4.1-mini", "store": False, "max_output_tokens": 450,
            "instructions": "請以繁體中文客觀描述圖片中可見的元素；不要猜測人物身分或不確定的細節。",
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": "分析這張使用者授權送出的圖片，描述可見內容。"},
                {"type": "input_image", "image_url": "data:" + mime + ";base64," +
                 base64.b64encode(ctx.payload).decode("ascii"), "detail": "low"},
            ]}]}
    req = request.Request("https://api.openai.com/v1/responses",
                          data=json.dumps(body).encode("utf-8"), method="POST",
                          headers={"Authorization": "Bearer " + key,
                                   "Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=45) as response:
            result = json.load(response)
        texts = [c["text"] for msg in result.get("output", []) if msg.get("type") == "message"
                 for c in msg.get("content", []) if c.get("type") == "output_text"]
        if not texts:
            raise ValueError("empty")
        return {"type": "vision", "description": "".join(texts)[:2200], "image": info}
    except error.HTTPError as exc:
        raise DocumentError(f"視覺分析 API 無法完成（HTTP {exc.code}）。") from None
    except (ValueError, OSError):
        raise DocumentError("視覺模型沒有產生有效回覆。") from None


def audio_inspect(ctx: AgentContext, params: dict) -> dict:
    if params:
        raise DocumentError("音訊概況不接受其他參數。")
    _assert_payload(ctx)
    try:
        with wave.open(io.BytesIO(ctx.payload), "rb") as audio:
            count, rate = audio.getnframes(), audio.getframerate()
            return {"type": "audio", "format": "wav",
                    "duration_seconds": round(count / rate, 2),
                    "channels": audio.getnchannels(), "sample_rate": rate}
    except (wave.Error, EOFError, ValueError, ZeroDivisionError):
        raise DocumentError("本機音訊概況目前需要 WAV；其他格式可使用轉錄服務。") from None


def audio_transcribe(ctx: AgentContext, params: dict) -> dict:
    if set(params) != {"api_key"}:
        raise DocumentError("音訊轉錄只接受 api_key。")
    _assert_payload(ctx, 24_000_000)
    key = params["api_key"]
    if not isinstance(key, str) or len(key) < 8:
        raise DocumentError("請提供 OpenAI API Key。")
    ext = ctx.filename.rsplit(".", 1)[-1].lower() if "." in ctx.filename else ""
    if ext not in {"wav", "mp3", "mp4", "mpeg", "mpga", "m4a", "webm"}:
        raise DocumentError("轉錄目前支援 mp3、mp4、m4a、mpeg、mpga、wav、webm。")
    boundary = "----AgentAudioBoundary23721"
    mime = mimetypes.guess_type("audio." + ext)[0] or "application/octet-stream"
    body = (
        ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\ngpt-transcribe\r\n").encode()
        + ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio." + ext +
           "\"\r\nContent-Type: " + mime + "\r\n\r\n").encode()
        + ctx.payload + ("\r\n--" + boundary + "--\r\n").encode()
    )
    req = request.Request("https://api.openai.com/v1/audio/transcriptions",
                          data=body, method="POST",
                          headers={"Authorization": "Bearer " + key,
                                   "Content-Type": "multipart/form-data; boundary=" + boundary})
    try:
        with request.urlopen(req, timeout=90) as response:
            transcript = json.load(response)
        return {"type": "transcript", "text": str(transcript["text"])[:40000],
                "model": "gpt-transcribe"}
    except error.HTTPError as exc:
        raise DocumentError(f"轉錄服務錯誤（HTTP {exc.code}）。") from None
    except (OSError, ValueError, KeyError):
        raise DocumentError("音訊轉錄失敗。") from None


def subtitles_inspect(ctx: AgentContext, params: dict) -> dict:
    if params:
        raise DocumentError("字幕整理不接受其他參數。")
    _assert_payload(ctx, 1_000_000)
    txt = ctx.payload.decode("utf-8-sig", errors="replace")
    if not ctx.filename.lower().endswith((".srt", ".vtt")):
        raise DocumentError("請上傳 .srt 或 .vtt 字幕。")
    lines = []
    for line in txt.splitlines():
        value = line.strip()
        if (not value or value.isdigit() or value == "WEBVTT" or
                "-->" in value or value.startswith(("NOTE ", "STYLE", "REGION"))):
            continue
        clean = re.sub(r"<[^>]+>", "", value)
        if clean and (not lines or lines[-1] != clean):
            lines.append(clean)
        if sum(len(s) for s in lines) > 30000:
            break
    return {"type": "subtitles", "lines": len(lines), "text": "\n".join(lines)[:30000],
            "note": "已移除時間戳記；字幕原文不代表已核實的事實。"}


def register(registry: AgentRegistry) -> None:
    registry.register(Capability("document.pdf", "擷取 PDF 文字與頁數", pdf_inspect))
    registry.register(Capability("image.inspect", "圖片格式、大小與尺寸", image_inspect))
    registry.register(Capability("image.describe", "OpenAI 視覺理解（須核准外傳圖片）",
                                 image_describe, requires_approval=True))
    registry.register(Capability("audio.inspect", "WAV 音訊長度資訊", audio_inspect))
    registry.register(Capability("audio.transcribe", "OpenAI 音訊轉錄（須核准外傳音訊）",
                                 audio_transcribe, requires_approval=True))
    registry.register(Capability("video.subtitles", "整理上傳的 SRT/VTT 字幕",
                                 subtitles_inspect))
