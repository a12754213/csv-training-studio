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
from scipy import sparse
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preprocessing import (
    DataPreparationError, PrepConfig, TabularPreprocessor, clean_frame,
    make_training_bundle, prepare_data, read_csv_bytes, train_baseline,
)


def example(n=100):
    return pd.DataFrame({"row_id": [f"{i:05d}" for i in range(n)],
                         "value": [str(i % 17) for i in range(n)],
                         "category": ["A", "B", "A", "C"] * (n // 4),
                         "target": ["no", "yes"] * (n // 2)})


class PipelineChecks(unittest.TestCase):
    def test_ingestion_preserves_ids_na_and_big5(self):
        frame, info = read_csv_bytes("郵遞區號;城市;值\n001;台北;NA\n002;台中;\n".encode("cp950"))
        self.assertEqual(frame.iloc[0, 0], "001")
        self.assertEqual(clean_frame(frame).iloc[0, 2], "NA")
        self.assertTrue(pd.isna(clean_frame(frame).iloc[1, 2]))
        self.assertEqual(info["separator"], ";")

    def test_duplicate_headers_and_ragged_rows_rejected(self):
        for payload in [b"a,a\n1,2\n", b"a, a\n1,2\n", b"a,b\n1,2,3\n", b"a,b\n1\n"]:
            with self.assertRaises(DataPreparationError):
                read_csv_bytes(payload, separator=",")

    def test_imputation_uses_training_not_test(self):
        frame = pd.DataFrame({"time": pd.date_range("2020-01-01", periods=20).astype(str),
                              "x": list(range(8)) + [None] * 8 + [10000, 20000, 30000, 40000],
                              "empty_in_train": [None] * 16 + [1, 2, 3, 4], "target": range(20)})
        result = prepare_data(frame, PrepConfig("target", "regression", split_mode="time", split_column="time",
                                              preprocessor={"numeric_strategy": "mean", "scale_numeric": False}))
        fills = result.preprocessor.learned_values()["numeric_fill"]
        self.assertEqual(fills["f0000_x"], 3.5)
        self.assertNotIn("empty_in_train", [s["column"] for s in result.preprocessor.specs_])
        self.assertNotIn("target", result.report["feature_columns"])
        self.assertTrue(np.isfinite(result.X_train.data).all())

    def test_unseen_category_is_safe_and_same_dimension(self):
        pre = TabularPreprocessor().fit(pd.DataFrame({"x": [1, 2, None, 4], "cat": ["a", "b", "a", "b"]}))
        result = pre.transform(pd.DataFrame({"x": [10, None], "cat": ["UNSEEN", None]}))
        self.assertEqual(result.shape[1], len(pre.get_feature_names_out()))
        self.assertTrue(np.isfinite(result.data).all())
        self.assertEqual(pre.audit(pd.DataFrame({"x": [10], "cat": ["UNSEEN"]}))[1]["unknown_categories"], 1)

    def test_missing_target_is_quarantined_not_imputed(self):
        frame = example(); frame.loc[[0, 1], "target"] = None
        result = prepare_data(frame, PrepConfig("target"))
        self.assertEqual(len(result.unlabeled), 2)
        self.assertEqual(len(result.y_train) + len(result.y_test), 98)
        self.assertFalse(result.y_train.isna().any())

    def test_groups_never_overlap(self):
        frame = example(); frame["person"] = np.repeat(np.arange(20), 5)
        result = prepare_data(frame, PrepConfig("target", split_mode="group", split_column="person"))
        self.assertFalse(set(result.raw_train.person) & set(result.raw_test.person))
        self.assertNotIn("person", result.report["feature_columns"])

    def test_time_ties_do_not_cross(self):
        frame = example(); frame["time"] = np.repeat(pd.date_range("2020-01-01", periods=10).astype(str), 10)
        result = prepare_data(frame, PrepConfig("target", split_mode="time", split_column="time"))
        self.assertLess(result.raw_train.time.max(), result.raw_test.time.min())

    def test_exact_duplicates_do_not_cross(self):
        frame = pd.concat([example(), example().iloc[:10]], ignore_index=True)
        result = prepare_data(frame, PrepConfig("target"))
        self.assertEqual(result.report["rows"]["duplicates_removed"], 10)
        self.assertEqual(len(result.raw_train) + len(result.raw_test), 100)

    def test_forced_numeric_reports_invalid(self):
        pre = TabularPreprocessor(column_roles={"x": "numeric"}, scale_numeric=False)
        pre.fit(pd.DataFrame({"x": ["1", "2", "3", "wrong"]}))
        out = pre.transform(pd.DataFrame({"x": ["bad", "inf"]}))
        self.assertTrue(np.isfinite(out.data).all())
        self.assertEqual(pre.audit(pd.DataFrame({"x": ["bad", "inf"]}))[0]["invalid_converted_to_missing"], 2)

    def test_new_data_missing_column_raises(self):
        pre = TabularPreprocessor().fit(example().drop(columns="target"))
        with self.assertRaises(DataPreparationError):
            pre.transform(pd.DataFrame({"unrelated": [1, 2]}))

    def test_sklearn_clone_and_cv(self):
        frame = example()
        pre = TabularPreprocessor(column_roles={"value": "numeric"}, missing_tokens=("?",))
        clone(pre)
        pipe = Pipeline([("prep", pre), ("model", LogisticRegression())])
        scores = cross_val_score(pipe, frame.drop(columns="target"), frame.target, cv=3)
        self.assertEqual(len(scores), 3)
        self.assertTrue(np.isfinite(scores).all())

    def test_sparse_matrix_high_cardinality_is_bounded(self):
        pre = TabularPreprocessor(max_categories=12)
        matrix = pre.fit_transform(pd.DataFrame({"category": [f"item_{i}" for i in range(200)]}))
        self.assertTrue(sparse.issparse(matrix))
        self.assertLessEqual(matrix.shape[1], 12)

    def test_invalid_regression_labels_rejected(self):
        frame = example()
        with self.assertRaises(DataPreparationError):
            prepare_data(frame, PrepConfig("target", "regression"))

    def test_rare_class_split_has_clear_error(self):
        frame = example(); frame["target"] = "same"; frame.loc[0, "target"] = "rare"
        with self.assertRaisesRegex(DataPreparationError, "分層"):
            prepare_data(frame, PrepConfig("target"))

    def test_export_train_predict_roundtrip(self):
        result = prepare_data(example(), PrepConfig("target"))
        trained = train_baseline(result.preprocessor, result.X_train, result.X_test,
                                  result.y_train, result.y_test, "classification")
        data = make_training_bundle(result, trained)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                archive.extractall(p)
            before = joblib.load(p / "model.joblib").predict(result.raw_test)
            subprocess.run([sys.executable, "train.py", "--data", "."], cwd=p, capture_output=True, text=True, check=True)
            after = joblib.load(p / "model.joblib").predict(result.raw_test)
            np.testing.assert_array_equal(before, after)
            subprocess.run([sys.executable, "predict.py", "--csv", "raw_test.csv"], cwd=p,
                           capture_output=True, text=True, check=True)
            output = pd.read_csv(p / "predictions.csv")
            self.assertEqual(len(output), len(result.raw_test))
            self.assertEqual(sparse.load_npz(p / "X_train.npz").shape, result.X_train.shape)
            report = json.loads((p / "report.json").read_text())
            self.assertTrue(report["finite_output"])

    def test_regression_end_to_end(self):
        frame = example(); frame["target"] = np.arange(len(frame)) * 1.5
        result = prepare_data(frame, PrepConfig("target", "regression"))
        model, metrics, _ = train_baseline(result.preprocessor, result.X_train, result.X_test,
                                           result.y_train, result.y_test, "regression")
        self.assertIn("rmse", metrics["test_scores"])
        self.assertTrue(np.isfinite(model.predict(result.raw_test)).all())
        make_training_bundle(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
