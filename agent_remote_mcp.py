"""Optional authenticated read-only Streamable HTTP MCP adapter for Agent Hub.

Not enabled by Streamlit or standard STDIO MCP. Run deliberately on loopback.
A public deployment additionally needs TLS, trusted ingress, and client-specific
authentication compatibility verification; a bearer token is NOT OAuth.
"""
from __future__ import annotations

import argparse
import hmac
import os
import secrets
from typing import Any

from agent_engine import make_task, run_until_gate
from agent_modules import build_registry
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

REMOTE_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)


class TokenASGI:
    """Authenticate all HTTP requests before they reach the MCP protocol handler."""
    def __init__(self, app, token: str, allowed_origins: set[str] | None = None):
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError("遠端 MCP 權杖至少要 32 個字元。")
        self.app = app
        self.token = token
        self.allowed_origins = allowed_origins or set()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode("ascii", errors="ignore")
        origin = headers.get(b"origin", b"").decode("ascii", errors="ignore")
        path = scope.get("path", "")
        body_size = headers.get(b"content-length", b"0")
        if path not in ("/mcp", "/mcp/"):
            return await self._deny(send, 404)
        if origin and origin not in self.allowed_origins:
            return await self._deny(send, 403)
        if (not auth.startswith("Bearer ") or
                not hmac.compare_digest(auth[7:], self.token)):
            return await self._deny(send, 401)
        if body_size.isdigit() and int(body_size) > 65536:
            return await self._deny(send, 413)
        return await self.app(scope, receive, send)

    @staticmethod
    async def _deny(send, code: int):
        body = b"Access denied"
        await send({"type": "http.response.start", "status": code,
                    "headers": [(b"content-type", b"text/plain"),
                                (b"cache-control", b"no-store"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def build_remote_mcp(token: str, *, allowed_origins: set[str] | None = None):
    """Return an auth-gated ASGI app and separate MCP object for integration tests."""
    # Stateless protocol avoids unauthenticated long-lived sessions and keeps
    # the HTTP adapter independent from the local training/file workspace.
    server = FastMCP(
        "AI Agent Hub Remote Read-Only",
        instructions="Only inspect explicitly supplied public URLs. No training, uploads or filesystem tools.",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
    )

    @server.tool(annotations=REMOTE_READ, structured_output=True)
    def list_public_agent_tools() -> list[dict[str, Any]]:
        """List the fixed public read-only capabilities (not local training tools)."""
        return [x for x in build_registry().available() if x["name"] in
                {"web.crawl", "text.inspect", "csv.inspect", "csv.plan"}]

    @server.tool(annotations=REMOTE_READ, structured_output=True)
    def search_public_web(query: str, count: int = 5) -> dict[str, Any]:
        """Search the public index. Requires BRAVE_SEARCH_API_KEY on the server.

        Search never auto-crawls results; the caller must select/authorize URLs.
        """
        import os
        from agent_hub import AgentContext
        from agent_modules import build_registry
        key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
        if not key:
            return {"status": "not_configured", "message": "Server Brave Search API not connected."}
        return build_registry().run("web.search", AgentContext(),
                                    {"query": query, "api_key": key, "count": count}, approved=True)

    @server.tool(annotations=REMOTE_READ, structured_output=True)
    def preview_public_agent_task(url: str, target: str = "") -> dict[str, Any]:
        """Preview ONE user-provided public URL without contacting it."""
        task = make_task(f"讀取 {url}", target=target or None)
        return {"id": task.id, "sources": [{"kind": "web", "url": url}],
                "requires_source_approval_in_client": True,
                "may_call": ["web.crawl", "text.inspect", "csv.inspect", "csv.plan"],
                "trains": False}

    @server.tool(annotations=REMOTE_READ, structured_output=True)
    def inspect_public_agent_task(url: str, target: str = "") -> dict[str, Any]:
        """Run bounded read-only workflow for ONE explicitly authorized public URL.

        The client/user is responsible for approving this external-access tool call.
        No CSV file or model is stored and no training is exposed here.
        """
        task = make_task(f"讀取 {url}", target=target or None)
        result = run_until_gate(task, build_registry(), approved_urls={url})
        if task.status != "completed":
            return {"status": task.status, "last_error_type": task.last_error,
                    "tool_trace": task.events, "decision": result}
        summaries = []
        for entry in task.results:
            if entry["kind"] == "table":
                overview = entry.get("overview", {})
                plan = entry.get("plan") or {}
                summaries.append({"kind": "table", "rows": overview.get("rows", 0),
                                  "columns": overview.get("columns", [])[:100],
                                  "suggested_exclusions": overview.get("suggested_excluded_columns", [])[:100],
                                  "plan": plan.get("suggested_options", {})})
            else:
                info = entry.get("text_info") or {}
                summaries.append({"kind": "text",
                                  "characters": info.get("characters", 0),
                                  "preview": info.get("preview", "")[:1200]})
        return {"status": task.status, "tool_trace": task.events, "sources": summaries,
                "training_available": False}

    app = server.streamable_http_app()
    return TokenASGI(app, token, allowed_origins), server


def main() -> None:
    import uvicorn
    parser = argparse.ArgumentParser(description="Opt-in authenticated read-only MCP adapter")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-nonlocal", action="store_true",
                        help="Only behind your own HTTPS/auth reverse proxy. Not suitable for direct exposure.")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "::1", "localhost") and not args.allow_nonlocal:
        raise SystemExit("拒絕公開綁定。若有獨立 HTTPS 反向代理，才明確加 --allow-nonlocal。")
    token = os.environ.get("AI_AGENT_REMOTE_TOKEN", "")
    origins = set(filter(None, os.environ.get("AI_AGENT_ALLOWED_ORIGINS", "").split(",")))
    app, _ = build_remote_mcp(token, allowed_origins=origins)
    uvicorn.run(app, host=args.host, port=args.port, proxy_headers=False,
                forwarded_allow_ips="")


if __name__ == "__main__":
    main()
