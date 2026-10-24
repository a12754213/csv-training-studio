"""Bounded public-web extraction, kept separate from the CSV training engine.

Only explicit, public HTTP(S) destinations are supported. Every hop, including
robots.txt, is DNS-validated and connected to a pinned public IP to prevent SSRF.
No browser automation, logins, anti-bot bypass, or arbitrary site-wide crawling.
"""
from __future__ import annotations

import csv
import io
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from agent_hub import AgentContext, AgentRegistry, Capability

USER_AGENT = "CSVTrainingStudioBot"
MAX_BYTES = 1_500_000
MAX_REDIRECTS = 3
MAX_ROWS = 1000
MAX_COLUMNS = 32
MAX_CHARS = 12_000


class CrawlError(ValueError):
    """A safe, user-visible crawler failure."""


class _PinnedHTTP(HTTPConnection):
    def __init__(self, hostname: str, port: int, address: str):
        super().__init__(hostname, port, timeout=8)
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)


class _PinnedHTTPS(HTTPSConnection):
    def __init__(self, hostname: str, port: int, address: str):
        super().__init__(hostname, port, timeout=8)
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)


def _destination(url: str):
    if not isinstance(url, str) or not 8 <= len(url) <= 2048:
        raise CrawlError("請提供長度合理的公開 http/https 網址。")
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("scheme")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValueError("credentials or fragment")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if port != (443 if parsed.scheme == "https" else 80):
            raise ValueError("non-default port")
        hostname = parsed.hostname.rstrip(".")
        if not hostname or "." not in hostname or hostname.lower().endswith((".local", ".internal", ".localhost")):
            raise ValueError("local domain")
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        ips = sorted({record[4][0] for record in addresses})
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError("non-public address")
        return parsed, port, ips[0]
    except (ValueError, socket.gaierror, UnicodeError, OverflowError):
        raise CrawlError("網址必須指向可公開存取的標準 HTTP(S) 網站，不能連到內網或本機。") from None


def _get(url: str, *, max_redirects: int = MAX_REDIRECTS, check_policy=None) -> tuple[str, bytes, str, int]:
    for redirects in range(max_redirects + 1):
        parsed, port, address = _destination(url)
        conn = (_PinnedHTTPS if parsed.scheme == "https" else _PinnedHTTP)(parsed.hostname, port, address)
        try:
            path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            conn.request("GET", path, headers={
                "Host": parsed.netloc,
                "User-Agent": USER_AGENT,
                "Accept": "text/html,text/plain,text/csv,application/csv",
                "Accept-Encoding": "identity",
                "Connection": "close",
            })
            response = conn.getresponse()
            status = response.status
            if status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location or redirects == max_redirects:
                    raise CrawlError("網址重新導向過多或缺少目標位置。")
                next_url = urljoin(url, location)
                if parsed.scheme == "https" and urlsplit(next_url).scheme == "http":
                    raise CrawlError("拒絕從 HTTPS 轉向不安全的 HTTP。")
                # Check robots policy BEFORE requesting the redirected document.
                if check_policy is not None and not check_policy(next_url):
                    raise CrawlError("轉址後頁面不允許爬取。")
                url = next_url
                continue
            if status != 200:
                return url, b"", "", status
            size = response.getheader("Content-Length")
            if size and size.isdecimal() and int(size) > MAX_BYTES:
                raise CrawlError("網頁超過 1.5 MB，請使用較小的公開頁面。")
            encoding = response.getheader("Content-Encoding", "identity").lower()
            if encoding not in ("identity", ""):
                raise CrawlError("網站未提供可直接讀取的內容格式。")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise CrawlError("網頁超過 1.5 MB，已停止下載。")
            ctype = response.getheader("Content-Type", "").lower().split(";")[0].strip()
            return url, body, ctype, status
        except (OSError, TimeoutError, ssl.SSLError) as exc:
            raise CrawlError("無法連接網頁，可能有網站限制或連線逾時。") from exc
        finally:
            conn.close()
    raise CrawlError("重新導向超出限制。")


def _robots_allowed(url: str) -> bool:
    parts = urlsplit(url)
    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    final_url, body, _, status = _get(robots_url)
    if urlsplit(final_url).netloc.lower() != parts.netloc.lower():
        raise CrawlError("robots.txt 轉址到其他網站，為安全起見停止抓取。")
    if status in (401, 403):
        return False
    if status == 404 or 400 <= status < 500:
        return True
    if status != 200:
        raise CrawlError("無法確認網站爬蟲政策，已停止抓取。")
    rules = RobotFileParser()
    rules.parse(body.decode("utf-8", errors="replace").splitlines())
    return rules.can_fetch(USER_AGENT, url)


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.title_depth = 0
        self.title = ""
        self.published_at = ""
        self.block = None
        self.blocks: list[str] = []
        self.tables: list[list[tuple[list[str], bool]]] = []
        self.table = None
        self.row = None
        self.cell = None
        self.cell_header = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
        if self.skip:
            return
        if tag == "meta":
            metadata = dict(attrs)
            label = (metadata.get("property") or metadata.get("name") or "").lower()
            if label in ("article:published_time", "datepublished", "pubdate"):
                self.published_at = str(metadata.get("content") or "")[:80]
        if tag == "title":
            self.title_depth += 1
        if tag in ("p", "h1", "h2", "h3", "li") and self.block is None:
            self.block = []
        if tag == "table" and self.table is None and len(self.tables) < 10:
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
            self.cell_header = tag == "th"

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        if tag in ("p", "h1", "h2", "h3", "li") and self.block is not None:
            value = " ".join("".join(self.block).split())
            if value and len(self.blocks) < 100:
                self.blocks.append(value[:1000])
            self.block = None
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            value = " ".join("".join(self.cell).split())[:1500]
            if len(self.row) < MAX_COLUMNS:
                self.row.append((value, self.cell_header))
            self.cell = None
        if tag == "tr" and self.row is not None and self.table is not None:
            if self.row and len(self.table) <= MAX_ROWS:
                self.table.append(([x for x, _ in self.row], any(h for _, h in self.row)))
            self.row = None
        if tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.title_depth:
            self.title += data
        if self.block is not None:
            self.block.append(data)
        if self.cell is not None:
            self.cell.append(data)


def _table_csv(tables) -> tuple[bytes, int, int]:
    for table in tables:
        if len(table) < 2:
            continue
        width = min(MAX_COLUMNS, max(len(row) for row, _ in table))
        if width < 2:
            continue
        header = table[0][0] if table[0][1] else [f"column_{i + 1}" for i in range(width)]
        data = table[1:] if table[0][1] else table
        names = []
        for index in range(width):
            original = (header[index] if index < len(header) else "").strip() or f"column_{index + 1}"
            candidate = original
            count = 2
            while candidate in names:
                candidate = f"{original}_{count}"
                count += 1
            names.append(candidate)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(names)
        for row, _ in data[:MAX_ROWS]:
            writer.writerow((row + [""] * width)[:width])
        return output.getvalue().encode("utf-8-sig"), len(data[:MAX_ROWS]), width
    return b"", 0, 0


def crawl(context: AgentContext, params: dict) -> dict:
    if set(params) != {"url"}:
        raise CrawlError("爬蟲只接受 url 參數；不允許任意命令。")
    url = params["url"]
    _destination(url)
    if not _robots_allowed(url):
        raise CrawlError("網站 robots.txt 不允許抓取此網址。")
    final_url, body, ctype, status = _get(url, check_policy=_robots_allowed)
    if status != 200:
        raise CrawlError(f"網站拒絕或找不到頁面（HTTP {status}）。")
    if ctype in ("text/csv", "application/csv") or (
        urlsplit(final_url).path.lower().endswith(".csv") and ctype not in ("text/html", "application/xhtml+xml")
    ):
        from preprocessing import read_csv_bytes
        try:
            frame, _ = read_csv_bytes(body)
        except (ValueError, UnicodeError) as exc:
            raise CrawlError("已下載 CSV，但格式無法辨識。") from exc
        if len(frame) > MAX_ROWS or len(frame.columns) > MAX_COLUMNS:
            raise CrawlError("CSV 超過首版 1,000 列／32 欄的上限。")
        return dict(url=final_url, kind="table", title="", text="", csv_bytes=body,
                    rows=len(frame), columns=len(frame.columns), tables=1)
    if ctype not in ("text/html", "application/xhtml+xml", "text/plain", ""):
        raise CrawlError(f"目前不支援 {ctype or '未知'} 檔案格式。")
    if ctype == "text/plain":
        text = body.decode("utf-8-sig", errors="replace")[:MAX_CHARS]
        return dict(url=final_url, kind="text", title="", text=text, csv_bytes=b"",
                    rows=0, columns=0, tables=0)
    parser = _Extractor()
    parser.feed(body.decode("utf-8-sig", errors="replace"))
    data, rows, columns = _table_csv(parser.tables)
    text = "\n".join(parser.blocks)[:MAX_CHARS]
    return dict(url=final_url, kind="table" if data else "text",
                title=" ".join(parser.title.split())[:300], text=text,
                csv_bytes=data, rows=rows, columns=columns, tables=len(parser.tables),
                published_at=parser.published_at)


def register(registry: AgentRegistry) -> None:
    registry.register(Capability("web.crawl", "擷取單一公開網頁／HTML 表格／CSV（需確認）",
                                 crawl, requires_approval=True))
