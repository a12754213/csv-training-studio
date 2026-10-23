"""Opt-in JavaScript rendering with all browser requests served via pinned HTTPS.

Never browser-fetch arbitrary subresources. Every allowed request uses existing
pin/robots checks, same-host policy and strict byte/request limits. For public
multi-tenant deployment, run browser in an isolated no-egress container.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit
from agent_hub import AgentContext, AgentRegistry, Capability
from agent_modules.web_crawler import (_destination, _get, _robots_allowed,
                                       CrawlError, _Extractor)

MAX_REQUESTS = 16
MAX_TOTAL_BYTES = 3_000_000


class BrowserError(ValueError):
    pass


def render(context: AgentContext, params: dict) -> dict:
    if set(params) != {"url"} or not isinstance(params.get("url"), str):
        raise BrowserError("動態瀏覽器只接受網址。")
    if os.environ.get("AI_AGENT_ISOLATED_BROWSER") != "1":
        raise BrowserError("動態網頁功能預設停用。需在無直接網路出口的隔離容器中啟用。")
    url = params["url"]
    _destination(url)
    if not _robots_allowed(url):
        raise BrowserError("網站 robots.txt 不允許擷取。")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise BrowserError("請於隔離的 worker 安裝 Playwright 與 Chromium。") from None

    host = urlsplit(url).hostname
    counter = {"requests": 0, "bytes": 0}

    def serve(route):
        req = route.request
        target = req.url
        parts = urlsplit(target)
        if (req.method != "GET" or parts.scheme not in ("http", "https") or
                parts.hostname != host or parts.username or parts.password or
                req.resource_type in ("media", "image", "font", "websocket", "eventsource") or
                counter["requests"] >= MAX_REQUESTS):
            route.abort()
            return
        counter["requests"] += 1
        try:
            _destination(target)
            final, data, mime, code = _get(
                target, check_policy=lambda u: urlsplit(u).hostname == host and _robots_allowed(u))
            if urlsplit(final).hostname != host or counter["bytes"] + len(data) > MAX_TOTAL_BYTES:
                route.abort()
                return
            counter["bytes"] += len(data)
            route.fulfill(status=code, content_type=mime or "text/plain", body=data,
                          headers={"Cache-Control": "no-store"})
        except (ValueError, OSError):
            route.abort()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-background-networking"])
        try:
            ctx = browser.new_context(service_workers="block", accept_downloads=False)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.add_init_script("""
                for (const name of ['WebSocket', 'EventSource', 'Worker', 'SharedWorker']) {
                    Object.defineProperty(window, name, {
                        configurable: false,
                        value: class { constructor() { throw new Error('disabled in isolated browser'); } }
                    });
                }
            """)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=14000)
                page.wait_for_timeout(900)
            except Exception:
                raise BrowserError("動態網頁載入逾時或受到網站限制。") from None
            rendered_html = page.content()[:100_000]
            title = page.title()[:200]
            body_text = page.locator("body").inner_text(timeout=4000)[:12000]
            return {"url": url, "title": title, "text": body_text,
                    "html_preview": rendered_html[:2000], "requests": counter["requests"],
                    "note": "JS 僅在隔離瀏覽器內執行；跨站資源與網頁媒體均遭封鎖。"}
        finally:
            browser.close()


def register(registry: AgentRegistry) -> None:
    registry.register(Capability("web.render", "Playwright 動態網頁擷取（僅隔離 worker）",
                                 render, requires_approval=True))
