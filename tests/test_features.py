import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preprocessing import (PrepConfig, TabularPreprocessor, infer_kind, make_training_bundle,
                           prepare_data, preview_transformations, read_csv_bytes, train_baseline)
from text_features import SafeTextVectorizer, WordTokenizer, parse_quantity


class TextAndQuantityChecks(unittest.TestCase):
    def test_auto_types_and_identifiers_are_preserved(self):
        for values, name, expected in [
            (["AB123", "RTX4070"], "型號", "categorical"),
            (["00123", "00456"], "郵遞區號", "categorical"),
            (["30cm", "40cm"], "model_code", "categorical"),
            (["00123", "00456"], "訂單編號", "identifier"),
            (["很好用，安裝簡單", "包裝有破損"], "評論", "text"),
            (["30cm", "0.5m"], "尺寸", "quantity"),
            (["30cm", "AB123"], "混合內容", "categorical"),
            (["42", "51"], "年齡", "numeric"),
            (["台北", "台中"], "城市", "categorical"),
        ]:
            with self.subTest(name=name):
                self.assertEqual(infer_kind(pd.Series(values), name), expected)
        pre = TabularPreprocessor(min_frequency=1).fit(pd.DataFrame({"型號": ["AB123", "RTX4070", "00123"]}))
        self.assertEqual(pre.training_categories_["型號"], {"AB123", "RTX4070", "00123"})

    def test_tokenizer_custom_dictionary_isolation_and_codes(self):
        phrase = "量子超導散熱器"
        plain_before = WordTokenizer()(phrase)
        custom = WordTokenizer(custom_words=(phrase,), stop_words=("and",))
        tokens = custom(f"{phrase} and RTX4070 AB-123 00123 不 好")
        self.assertIn(phrase, tokens)
        self.assertNotIn("and", tokens)
        self.assertIn("rtx4070", tokens)
        self.assertIn("ab-123", tokens)
        self.assertIn("00123", tokens)
        self.assertIn("不", tokens)
        self.assertEqual(WordTokenizer()(phrase), plain_before)
        self.assertNotIn(phrase, plain_before)
        self.assertEqual(WordTokenizer(lowercase=False)("RTX4070"), ["RTX4070"])

    def test_vocabulary_and_idf_only_use_training_documents(self):
        vectorizer = SafeTextVectorizer(ngram_range=(1, 1)).fit(pd.Series(["shared alpha", "shared beta", "", None]))
        records = {r["token"]: r for r in vectorizer.vocabulary_records()}
        self.assertAlmostEqual(records["shared"]["idf"], np.log(5 / 3) + 1)
        before = vectorizer.vectorizer_.idf_.copy()
        transformed = vectorizer.transform(pd.Series(["holdoutsecret", "shared holdoutsecret"]))
        self.assertEqual(transformed.getrow(0).nnz, 0)
        self.assertNotIn("holdoutsecret", vectorizer.vectorizer_.vocabulary_)
        np.testing.assert_array_equal(before, vectorizer.vectorizer_.idf_)

    def test_time_split_cannot_learn_holdout_words_or_dimensions(self):
        frame = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=20).astype(str),
                              "review": [f"shared token{i}" for i in range(16)] + ["holdoutsecret"] * 4,
                              "size": [f"{i + 1}cm" for i in range(16)] + ["1kg"] * 4,
                              "target": ["A", "B"] * 10})
        result = prepare_data(frame, PrepConfig("target", split_mode="time", split_column="time"))
        self.assertNotIn("holdoutsecret", {r["token"] for r in result.preprocessor.text_vocabularies()["review"]})
        self.assertEqual(result.preprocessor.learned_values()["quantity_columns"]["size"], {"length": "m"})
        audit = {r["column"]: r for r in result.report["test_audit"]}
        self.assertEqual(audit["review"]["text_nonempty_zero_vectors"], 4)
        self.assertEqual(audit["size"]["unseen_quantity_dimensions"], 4)

    def test_empty_and_pruned_vocabulary_remain_finite(self):
        for docs, kwargs in [(["!!!", "???"], {}), (["alpha", "beta"], {"min_df": 2}),
                             (["alpha", "beta"], {"min_df": 4}),
                             (["alpha", "alpha"], {"stop_words": ("alpha",)})]:
            with self.subTest(kwargs=kwargs):
                vec = SafeTextVectorizer(**kwargs).fit(pd.Series(docs))
                self.assertEqual(vec.vocabulary_size_, 0)
                self.assertTrue(vec.empty_reason_)
                out = vec.transform(pd.Series(["new token", None]))
                self.assertEqual(out.shape, (2, 1))
                self.assertEqual(out.nnz, 0)
        pre = TabularPreprocessor(column_roles={"review": "text"}, drop_constant=False)
        out = pre.fit_transform(pd.DataFrame({"review": ["!!!", "???"]}))
        self.assertTrue(np.isfinite(out.data).all())
        self.assertTrue(pre.learned_values()["text_columns"]["review"]["empty_vocabulary_warning"])

    def test_feature_bounds_truncation_and_missing_text(self):
        vec = SafeTextVectorizer(max_features=3, max_text_chars=5, ngram_range=(1, 1))
        out = vec.fit_transform(pd.Series(["alpha hidden", "beta", "gamma", "delta", None]))
        self.assertLessEqual(out.shape[1], 3)
        self.assertNotIn("hidden", vec.get_feature_names_out())
        self.assertEqual(vec.audit(pd.Series(["alpha hidden", "zzz", None]))["text_truncated_rows"], 1)
        pre = TabularPreprocessor(column_roles={"review": "text"}, scale_numeric=False).fit(
            pd.DataFrame({"review": ["alpha", "beta"]}))
        names = list(pre.get_feature_names_out())
        out = pre.transform(pd.DataFrame({"review": [None]})).toarray()
        self.assertEqual(out[0, names.index("num__f0000_review_text_missing")], 1)
        self.assertTrue(np.isfinite(out).all())

    def test_quantity_values_and_currency_separation(self):
        for value, expected, unit, dimension in [
            ("尺寸30cm", .3, "m", "length"), ("0.3m", .3, "m", "length"),
            ("５００ｇ", .5, "kg", "mass"), ("500ml", .5, "L", "volume"),
            ("2小時", 7200, "s", "duration"), ("50%", .5, "ratio", "ratio"),
            ("32°F", 0, "°C", "temperature"), ("NT$1,200", 1200, "TWD", "currency_TWD"),
            ("500元", 500, "元", "currency_unspecified"), ("500美元", 500, "USD", "currency_USD"),
        ]:
            with self.subTest(value=value):
                parsed = parse_quantity(value)
                self.assertIsNotNone(parsed)
                self.assertAlmostEqual(parsed.normalized_value, expected)
                self.assertEqual((parsed.normalized_unit, parsed.dimension), (unit, dimension))

    def test_ambiguous_or_multiple_quantities_are_not_guessed(self):
        for value in ["RTX4070", "00123", "AB30cm", "10-20cm", "30x40cm", "30×40cm",
                      "尺寸30cm x 40cm", "$500", "1,5cm", "500", "1e999cm", "30cm plus 40cm"]:
            with self.subTest(value=value):
                self.assertIsNone(parse_quantity(value))

    def test_quantity_transform_new_units_errors_and_schema(self):
        pre = TabularPreprocessor(column_roles={"q": "quantity"}, scale_numeric=False).fit(
            pd.DataFrame({"q": ["30cm", "40cm", "500g", "600g", None, "bad"]}))
        original_names = pre.get_feature_names_out().copy()
        frame = pd.DataFrame({"q": ["0.3m", "0.5kg", "1L", "bad", None]})
        out = pre.transform(frame).toarray()
        names = list(original_names)
        self.assertAlmostEqual(out[0, names.index("num__f0000_q_length_value_m")], .3)
        self.assertAlmostEqual(out[1, names.index("num__f0000_q_mass_value_kg")], .5)
        self.assertEqual(out[2, names.index("num__f0000_q_unseen_dimension")], 1)
        self.assertEqual(out[3, names.index("num__f0000_q_invalid")], 1)
        self.assertEqual(out[4, names.index("num__f0000_q_missing")], 1)
        self.assertEqual(out[3, names.index("num__f0000_q_mass_value_kg")], 0)
        np.testing.assert_array_equal(original_names, pre.get_feature_names_out())
        self.assertTrue(np.isfinite(out).all())
        audit = pre.audit(frame)[0]
        self.assertEqual(audit["unseen_quantity_dimensions"], 1)
        self.assertEqual(audit["invalid_converted_to_missing"], 1)
        self.assertEqual(audit["missing_input"], 1)

    def test_disabled_unit_normalization_keeps_units_separate(self):
        pre = TabularPreprocessor(normalize_units=False, scale_numeric=False).fit(
            pd.DataFrame({"size": ["30cm", "40cm", "0.3m", "0.4m"]}))
        schema = pre.learned_values()["quantity_columns"]["size"]
        self.assertEqual(schema, {"length_cm": "cm", "length_m": "m"})
        self.assertEqual(pre.audit(pd.DataFrame({"size": ["300mm"]}))[0]["unseen_quantity_dimensions"], 1)

    def test_mixed_preprocessor_supports_clone_and_cross_validation(self):
        frame = pd.DataFrame({"review": ["good product", "bad product", "easy to use", "not good"] * 12,
                              "size": ["30cm", "40cm", "0.5m", "0.6m"] * 12})
        pre = TabularPreprocessor(custom_words=("散熱器",), stop_words=("to",), text_ngram_range=[1, 2])
        clone(pre)
        pipe = Pipeline([("prep", pre), ("model", LogisticRegression())])
        scores = cross_val_score(pipe, frame, ["yes", "no"] * 24, cv=3)
        self.assertTrue(np.isfinite(scores).all())

    def test_preview_does_not_fit_and_uses_selected_roles(self):
        frame = pd.DataFrame({"q": ["30cm", "bad"], "型號": ["RTX4070", "00123"], "review": ["hello world", None]})
        preview = preview_transformations(frame, {"q": "quantity"})
        self.assertIn("0.3 m", preview.loc[0, "處理預覽"])
        self.assertIn("無法辨識", preview.loc[1, "處理預覽"])
        self.assertIn("完整字串", preview.loc[2, "處理預覽"])
        self.assertIn("hello | world", preview.loc[4, "處理預覽"])

    def test_mixed_bundle_predicts_in_clean_subprocess(self):
        root = Path(__file__).resolve().parents[1]
        frame, _ = read_csv_bytes((root / "samples" / "demo_reviews.csv").read_bytes())
        result = prepare_data(frame, PrepConfig("是否推薦", preprocessor={"custom_words": ("低噪音",)}))
        trained = train_baseline(result.preprocessor, result.X_train, result.X_test,
                                  result.y_train, result.y_test, "classification")
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            with zipfile.ZipFile(io.BytesIO(make_training_bundle(result, trained))) as archive:
                archive.extractall(p)
            vocabularies = json.loads((p / "text_vocabulary.json").read_text(encoding="utf-8"))
            self.assertIn("評論", vocabularies)
            self.assertIn("低噪音", {r["token"] for r in vocabularies["評論"]})
            self.assertTrue((p / "text_features.py").is_file())
            self.assertTrue((p / "transformation_preview.csv").is_file())
            before = trained[0].predict(result.raw_test)
            subprocess.run([sys.executable, "train.py", "--data", "."], cwd=p, capture_output=True, text=True, encoding="utf-8", check=True)
            subprocess.run([sys.executable, "predict.py", "--csv", "raw_test.csv"], cwd=p, capture_output=True, text=True, encoding="utf-8", check=True)
            np.testing.assert_array_equal(before, pd.read_csv(p / "predictions.csv")["prediction"].to_numpy())
            np.testing.assert_array_equal(before, joblib.load(p / "model.joblib").predict(result.raw_test))


if __name__ == "__main__":
    unittest.main(verbosity=2)
