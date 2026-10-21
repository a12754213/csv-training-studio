"""Streamlit 介面流程檢查（不需要啟動瀏覽器）。"""
from pathlib import Path
import sys
import unittest

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def widget(elements, label):
    return next(element for element in elements if element.label == label)


class AppChecks(unittest.TestCase):
    def test_three_examples_prepare_train_and_download(self):
        for sample in ["客戶流失｜分類", "房價預測｜回歸", "評論與單位｜混合特徵分類"]:
            with self.subTest(sample=sample):
                app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
                widget(app.selectbox, "範例").select(sample).run()
                self.assertFalse(app.exception)
                widget(app.button, "整理成訓練資料").click().run()
                self.assertFalse(app.exception)
                self.assertFalse(app.error)
                self.assertIn("prepared", app.session_state)
                widget(app.button, "訓練並查看測試結果").click().run()
                self.assertFalse(app.exception)
                self.assertFalse(app.error)
                self.assertIn("trained", app.session_state)
                widget(app.button, "產生可下載資料包").click().run()
                self.assertFalse(app.exception)
                self.assertTrue(app.session_state["download_bytes"].startswith(b"PK"))
                if "混合" in sample:
                    learned = app.session_state["prepared"].preprocessor.learned_values()
                    self.assertGreater(learned["text_columns"]["評論"]["vocabulary_size"], 0)
                    self.assertIn("尺寸", learned["quantity_columns"])

    def test_text_and_unit_changes_clear_old_results(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        widget(app.selectbox, "範例").select("評論與單位｜混合特徵分類").run()
        widget(app.button, "整理成訓練資料").click().run()
        widget(app.button, "產生可下載資料包").click().run()
        widget(app.text_area, "自訂詞（每行一個）").set_value("低噪音").run()
        self.assertFalse(app.exception)
        self.assertNotIn("prepared", app.session_state)
        self.assertNotIn("download_bytes", app.session_state)
        widget(app.button, "整理成訓練資料").click().run()
        self.assertEqual(app.session_state["prepared"].config.preprocessor["custom_words"], ("低噪音",))
        widget(app.checkbox, "將相容量值換成共同單位").uncheck().run()
        self.assertNotIn("prepared", app.session_state)
        widget(app.button, "整理成訓練資料").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        dimensions = app.session_state["prepared"].preprocessor.learned_values()["quantity_columns"]["尺寸"]
        self.assertIn("length_cm", dimensions)
        self.assertIn("length_m", dimensions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
