"""Remote MCP adapter security checks; no socket or external website access."""
import asyncio
import unittest

from agent_remote_mcp import TokenASGI, build_remote_mcp


async def dummy_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def invoke(app, *, token="", path="/mcp", origin=None, size=None):
    headers = []
    if token:
        headers.append((b"authorization", b"Bearer " + token.encode()))
    if origin:
        headers.append((b"origin", origin.encode()))
    if size:
        headers.append((b"content-length", str(size).encode()))
    events = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(response):
        events.append(response)
    await app({"type": "http", "path": path, "headers": headers}, receive, send)
    return events[0]["status"]


class RemoteMCPTests(unittest.TestCase):
    def test_token_is_required_and_allows_exact_match_only(self):
        with self.assertRaises(ValueError):
            TokenASGI(dummy_app, "short")
        secret = "a" * 48
        gate = TokenASGI(dummy_app, secret, {"https://chatgpt.com"})
        self.assertEqual(asyncio.run(invoke(gate)), 401)
        self.assertEqual(asyncio.run(invoke(gate, token="wrong" * 10)), 401)
        self.assertEqual(asyncio.run(invoke(gate, token=secret)), 200)
        self.assertEqual(asyncio.run(invoke(gate, token=secret, path="/internal")), 404)
        self.assertEqual(asyncio.run(invoke(gate, token=secret, origin="https://evil.example")), 403)
        self.assertEqual(asyncio.run(invoke(gate, token=secret, origin="https://chatgpt.com")), 200)
        self.assertEqual(asyncio.run(invoke(gate, token=secret, size=100000)), 413)

    def test_remote_app_build_does_not_start_server(self):
        app, server = build_remote_mcp("b" * 48)
        self.assertIsInstance(app, TokenASGI)
        self.assertIsNotNone(server)
        self.assertEqual(asyncio.run(invoke(app)), 401)


if __name__ == "__main__":
    unittest.main()
