"""No-network regression tests for the modular web crawler and tool router."""
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_hub import AgentContext
from agent_modules import build_registry
from agent_modules.web_crawler import CrawlError, _destination, _table_csv, _Extractor
from agent_router import run_web_workflow

TABLE = b"""<html><head><title>Demo</title></head>
<body><p>Public demonstration data.</p><table>
<tr><th>Age</th><th>Label</th></tr>
<tr><td>20</td><td>0</td></tr>
<tr><td>30</td><td>1</td></tr>
<tr><td>40</td><td>0</td></tr>
<tr><td>50</td><td>1</td></tr>
</table></body></html>"""
ARTICLE = b"<html><title>News</title><p>First paragraph about the news.</p></html>"


def fake_public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))]


class CrawlerRoutingTests(unittest.TestCase):
    def setUp(self):
        self.registry = build_registry()

    def test_registered_separate_tools_and_approval_gate(self):
        names = {x["name"] for x in self.registry.available()}
        self.assertTrue({"web.crawl", "text.inspect", "csv.inspect", "csv.train"} <= names)
        with self.assertRaises(PermissionError):
            self.registry.run("web.crawl", AgentContext(), {"url": "https://example.com"})

    def test_disallow_local_private_credentials_ports(self):
        invalid = ["http://127.0.0.1/", "http://localhost/",
                   "http://169.254.169.254/latest/meta-data",
                   "http://10.0.0.2/", "https://user:pass@example.com/",
                   "https://example.com:8443/", "file:///etc/passwd"]
        with patch("socket.getaddrinfo", return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.4", 443))
        ]):
            for value in invalid:
                with self.subTest(value=value), self.assertRaises(CrawlError):
                    _destination(value)

    def test_extract_table_csv_without_training(self):
        with patch("socket.getaddrinfo", side_effect=fake_public_dns), \
             patch("agent_modules.web_crawler._robots_allowed", return_value=True), \
             patch("agent_modules.web_crawler._get", return_value=(
                 "https://example.com/data", TABLE, "text/html", 200)):
            result = run_web_workflow(self.registry, "https://example.com/data", target="Label")
        self.assertEqual(result["route"], "csv_training")
        self.assertEqual(result["steps"], ["web.crawl", "csv.inspect", "csv.plan"])
        self.assertEqual(result["overview"]["rows"], 4)
        self.assertEqual(result["overview"]["columns"], ["Age", "Label"])
        self.assertTrue(result["target_valid"])
        self.assertTrue(result["plan"]["suggested_options"])
        self.assertNotIn("csv.train", result["steps"])
        self.assertIn(b"Age,Label", result["fetched"]["csv_bytes"])

    def test_article_routes_to_text_inspection(self):
        with patch("socket.getaddrinfo", side_effect=fake_public_dns), \
             patch("agent_modules.web_crawler._robots_allowed", return_value=True), \
             patch("agent_modules.web_crawler._get", return_value=(
                 "https://example.com/news", ARTICLE, "text/html", 200)):
            result = run_web_workflow(self.registry, "https://example.com/news")
        self.assertEqual(result["route"], "text_analysis")
        self.assertEqual(result["steps"], ["web.crawl", "text.inspect"])
        self.assertIn("First paragraph", result["text_info"]["preview"])

    def test_no_crawl_on_robots_denial(self):
        with patch("socket.getaddrinfo", side_effect=fake_public_dns), \
             patch("agent_modules.web_crawler._robots_allowed", return_value=False), \
             patch("agent_modules.web_crawler._get") as get:
            with self.assertRaises(CrawlError):
                self.registry.run("web.crawl", AgentContext(),
                                  {"url": "https://example.com/blocked"}, approved=True)
            get.assert_not_called()

    def test_html_escape_and_table_column_dedup(self):
        parser = _Extractor()
        parser.feed("<table><tr><th>A</th><th>A</th></tr>"
                    "<tr><td>&amp; Hi</td><td>Yes</td></tr></table>")
        csv_data, rows, columns = _table_csv(parser.tables)
        self.assertEqual((rows, columns), (1, 2))
        self.assertIn(b"A,A_2", csv_data)
        self.assertIn(b"& Hi", csv_data)


if __name__ == "__main__":
    unittest.main()
