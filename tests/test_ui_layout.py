"""Protect heading spacing on the homepage and the Agent multipage UI."""
from pathlib import Path
import sys
import unittest

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui_layout import PAGE_CSS, HOME_HEADING, PRODUCT_NAME


class PageLayoutChecks(unittest.TestCase):
    def test_shared_css_keeps_toolbar_clearance_and_mobile_safe_area(self):
        self.assertIn('padding-top: 5.5rem', PAGE_CSS)
        self.assertIn('safe-area-inset-top', PAGE_CSS)
        self.assertIn('line-height: 1.3', PAGE_CSS)
        self.assertIn('overflow-wrap: anywhere', PAGE_CSS)
        self.assertEqual(PRODUCT_NAME, "AI Agent Hub")
        self.assertIn("AI Agent Hub", HOME_HEADING)

    def test_all_six_pages_render_without_exception(self):
        for filename in ('app.py', 'pages/1_AI_Agent.py', 'pages/2_AI_Chat.py',
                         'pages/3_Web_Crawler.py', 'pages/4_Agent_Router.py',
                         'pages/5_Agent_Core.py'):
            with self.subTest(page=filename):
                app = AppTest.from_file(str(ROOT / filename), default_timeout=30).run()
                self.assertFalse(app.exception)
                self.assertTrue(app.title, f'{filename} did not render a title')


if __name__ == '__main__':
    unittest.main()
