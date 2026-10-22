import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from forecasting import ForecastConfig, make_forecast_bundle, prepare_forecast, train_forecast
from preprocessing import DataPreparationError, PrepConfig, prepare_data, train_baseline


def sequence(n=100):
    return pd.DataFrame({'time': pd.date_range('2024-01-01', periods=n).astype(str),
                         'value': np.arange(n, dtype=float), 'extra': np.arange(n) * 2.,
                         'id': np.arange(n)})


class FeatureSelectionChecks(unittest.TestCase):
    def test_explicit_exclusion_survives_override_export_and_inference(self):
        frame = sequence()
        config = PrepConfig('value', 'regression', excluded_columns=('id', 'time'),
                            preprocessor={'column_roles': {'id': 'numeric'}})
        data = prepare_data(frame, config)
        self.assertEqual(data.report['used_feature_columns'], ['extra'])
        self.assertEqual(data.report['excluded_columns'], ['id', 'time'])
        model, _, _ = train_baseline(data.preprocessor, data.X_train, data.X_test,
                                     data.y_train, data.y_test, 'regression')
        np.testing.assert_allclose(model.predict(frame), model.predict(frame[['extra']]))
        changed = frame.copy(); changed['id'] = 9999999
        np.testing.assert_allclose(model.predict(frame), model.predict(changed))

    def test_invalid_and_all_excluded_columns_fail(self):
        for excluded in [('oops',), ('value',), ('extra', 'time', 'id')]:
            with self.subTest(excluded=excluded), self.assertRaises(DataPreparationError):
                prepare_data(sequence(), PrepConfig('value', 'regression', excluded_columns=excluded))


class ForecastChecks(unittest.TestCase):
    def config(self, **changes):
        return ForecastConfig(**{'target': 'value', 'time_column': 'time', 'lookback': 4,
                                 'horizon': 3, 'feature_columns': ('extra',),
                                 'excluded_columns': ('id',), **changes})

    def test_windows_are_causal_and_boundary_labels_are_purged(self):
        data = prepare_forecast(sequence().sample(frac=1, random_state=42), self.config())
        for p in data.windows.index:
            np.testing.assert_array_equal(data.windows.loc[p].iloc[:4], np.arange(p - 6, p - 2))
            self.assertEqual(data.targets.loc[p], p)
        self.assertLess(data.train_positions.max(), data.test_positions.min() - data.config.horizon)
        self.assertEqual(data.report['rows']['purged'], 3)
        self.assertNotIn('id', ' '.join(data.windows.columns))
        self.assertTrue((pd.to_datetime(data.manifest.origin_time) < pd.to_datetime(data.manifest.target_time)).all())

    def test_future_mutation_cannot_change_fitted_training_rules(self):
        original = sequence()
        first = prepare_forecast(original, self.config())
        modified = original.copy()
        modified.loc[first.test_positions.min():, ['value', 'extra']] = 9999999
        second = prepare_forecast(modified, self.config())
        one, two = train_forecast(first), train_forecast(second)
        np.testing.assert_allclose(one[0].estimator.coef_, two[0].estimator.coef_)
        self.assertEqual(one[0].preprocessor.learned_values(), two[0].preprocessor.learned_values())

    def test_missing_target_does_not_compress_time_or_fill_answers(self):
        frame = sequence(); frame.loc[30, 'value'] = np.nan
        data = prepare_forecast(frame, self.config())
        self.assertEqual(len(data.history), len(frame))
        self.assertNotIn(30, data.targets.index)
        self.assertNotIn(33, data.targets.index)  # no observed Naive at this origin
        self.assertEqual(data.windows.loc[40].iloc[0], 34.)

    def test_naive_alignment_and_fresh_process_export_reload(self):
        frame = sequence()
        data = prepare_forecast(frame, self.config())
        trained = train_forecast(data)
        self.assertAlmostEqual(trained[1]['naive_scores']['mae'], 3.)
        np.testing.assert_allclose(trained[2].naive_prediction, trained[2].actual - 3.)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with zipfile.ZipFile(io.BytesIO(make_forecast_bundle(data, trained))) as archive:
                archive.extractall(folder)
            # Exported code must work without access to the source checkout.
            env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
            subprocess.run([sys.executable, 'forecast.py', '--csv', 'history.csv', '--output', 'future.csv'],
                           cwd=folder, env=env, check=True, capture_output=True, timeout=45)
            result = pd.read_csv(folder / 'future.csv')
            self.assertEqual(result.horizon_rows.iloc[0], 3)
            self.assertAlmostEqual(result.prediction.iloc[0], trained[0].forecast(frame)['prediction'])
            subprocess.run([sys.executable, 'forecast.py', '--retrain', '--csv', 'history.csv', '--output', 'new.zip'],
                           cwd=folder, env=env, check=True, capture_output=True, timeout=45)
            self.assertTrue(zipfile.is_zipfile(folder / 'new.zip'))

    def test_random_forest_and_prediction_without_excluded_fields(self):
        data = prepare_forecast(sequence(), self.config(model='random_forest'))
        model, _, _ = train_forecast(data)
        result = model.forecast(sequence().drop(columns='id'))
        self.assertTrue(np.isfinite(result['prediction']))
        self.assertEqual(result['horizon_rows'], 3)

    def test_irregular_dates_do_not_invent_future_timestamp(self):
        frame = sequence().drop(index=50)
        data = prepare_forecast(frame, self.config())
        model, _, _ = train_forecast(data)
        self.assertIsNone(model.forecast(frame)['forecast_time'])

    def test_invalid_data_and_config_have_clear_errors(self):
        duplicate = sequence(); duplicate.loc[1, 'time'] = duplicate.loc[0, 'time']
        bad = sequence(); bad['extra'] = bad['extra'].astype(object); bad.loc[20, 'extra'] = 'wrong'
        cases = [(duplicate, self.config()), (bad, self.config()), (sequence(10), self.config()),
                 (sequence(), self.config(horizon=0)), (sequence(), self.config(lookback=1000)),
                 (sequence(), self.config(excluded_columns=('value',))),
                 (sequence(), self.config(feature_columns=('unknown',)))]
        for frame, cfg in cases:
            with self.subTest(cfg=cfg), self.assertRaises(DataPreparationError):
                prepare_forecast(frame, cfg)


if __name__ == '__main__':
    unittest.main()
