"""Opt-in public search and bounded research tools, independent of CSV/AutoML.

Search results are NOT automatically crawled. Callers must display and approve
the exact selected URLs before dispatching web.crawl.
"""
from __future__ import annotations
import json
import re
from urllib import error, parse, request
from urllib.parse import urlsplit

from agent_hub import AgentContext, AgentRegistry, Capability
from agent_modules.web_crawler import _destination

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
MAX_QUERY_LENGTH = 300


class ResearchError(ValueError):
    pass


def search(context: AgentContext, params: dict) -> dict:
    if set(params) - {"query", "api_key", "count", "freshness"}:
        raise ResearchError("搜尋包含未知參數。")
    query = params.get("query", "")
    token = params.get("api_key", "")
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= MAX_QUERY_LENGTH:
        raise ResearchError("請輸入 2～300 字搜尋內容。")
    if not isinstance(token, str) or len(token.strip()) < 8:
        raise ResearchError("需要自己的 Brave Search API Key。")
    count = params.get("count", 5)
    if type(count) is not int or count < 1 or count > 10:
        raise ResearchError("單次最多取回 10 筆搜尋結果。")
    freshness = params.get("freshness", "")
    if freshness not in ("", "pd", "pw", "pm", "py"):
        raise ResearchError("不支援的搜尋日期區間。")
    args = {"q": query.strip(), "count": count, "safesearch": "moderate"}
    if freshness:
        args["freshness"] = freshness
    req = request.Request(
        BRAVE_ENDPOINT + "?" + parse.urlencode(args),
        headers={"Accept": "application/json", "X-Subscription-Token": token.strip()},
    )
    try:
        with request.urlopen(req, timeout=12) as response:
            raw = response.read(250_001)
    except error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ResearchError("搜尋 API 認證失敗。") from None
        if exc.code == 429:
            raise ResearchError("搜尋 API 速率或額度已達上限。") from None
        raise ResearchError(f"搜尋 API 回應 HTTP {exc.code}。") from None
    except (OSError, TimeoutError):
        raise ResearchError("搜尋 API 暫時無法連線。") from None
    if len(raw) > 250_000:
        raise ResearchError("搜尋 API 回傳資料過大。")
    try:
        docs = json.loads(raw)["web"]["results"]
        if not isinstance(docs, list):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        raise ResearchError("搜尋 API 回傳格式不正確。") from None
    results = []
    seen = set()
    for doc in docs[:count * 2]:
        if not isinstance(doc, dict):
            continue
        url = doc.get("url", "")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            continue
        parts = urlsplit(url)
        if (not parts.hostname or parts.username or parts.password
                or parts.fragment or parts.scheme != "https" or parts.port not in (None, 443)):
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append({"title": str(doc.get("title") or "")[:180],
                        "url": url, "snippet": re.sub("<[^>]*>", "", str(doc.get("description") or ""))[:500]})
        if len(results) >= count:
            break
    return {"query": query.strip(), "results": results, "count": len(results),
            "note": "此為搜尋索引結果，尚未擷取或驗證文章；請選擇並核准確切網址。"}


def research_selected(context: AgentContext, params: dict) -> dict:
    """Explicit URLs only; reuse the existing SSRF-guarded static crawler."""
    if set(params) != {"urls"}:
        raise ResearchError("只能指定 urls。")
    urls = params["urls"]
    if not isinstance(urls, list) or not 1 <= len(urls) <= 3:
        raise ResearchError("每次最多分析 3 個明確選擇的網址。")
    if not all(isinstance(u, str) for u in urls) or len(set(urls)) != len(urls):
        raise ResearchError("網址不得重複，且必須是字串。")
    from agent_modules.web_crawler import crawl
    output = []
    for url in urls:
        _destination(url)
        try:
            doc = crawl(AgentContext(), {"url": url})
            output.append({"url": doc["url"], "kind": doc["kind"], "title": doc["title"],
                           "text_preview": doc["text"][:1800],
                           "rows": doc["rows"], "columns": doc["columns"],
                           "status": "completed"})
        except ValueError:
            output.append({"url": url, "status": "unavailable"})
    return {"sources": output, "count": len(output),
            "note": "逐篇列出已成功讀到的資料；不可把摘要當成經過事實查核的結論。"}


def register(registry: AgentRegistry) -> None:
    registry.register(Capability("web.search", "使用 Brave API 搜尋公開網頁（獨立憑證）",
                                 search, requires_approval=True))
    registry.register(Capability("web.research_selected", "擷取使用者核准的最多三個網址",
                                 research_selected, requires_approval=True))
