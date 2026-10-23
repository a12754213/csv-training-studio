"""A standalone, deterministic text-inspection capability, not an LLM."""
from __future__ import annotations

import re
from agent_hub import AgentContext, AgentRegistry, Capability


def inspect(context: AgentContext, params: dict) -> dict:
    if params:
        raise ValueError("text.inspect 不接受額外參數")
    text = context.payload.decode("utf-8", errors="replace")[:12_000]
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        "characters": len(text),
        "paragraphs": len(paragraphs),
        "latin_words": len(re.findall(r"[A-Za-z]+", text)),
        "preview": "\n\n".join(paragraphs[:8])[:4000],
        "note": "這是文字擷取與概況，不是語言模型生成的新聞摘要或事實查核。",
    }


def register(registry: AgentRegistry) -> None:
    registry.register(Capability("text.inspect", "擷取文章段落及文字概況", inspect))
