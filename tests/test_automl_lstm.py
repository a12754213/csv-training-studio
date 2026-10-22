import importlib.util
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
from agent_planner import suggest_plan
from automl import train_prepared
from forecasting import ForecastConfig, make_forecast_bundle, prepare_forecast, train_forecast
from preprocessing import PrepConfig, make_training_bundle, prepare_data, read_csv_bytes


class AutoMLChecks(unittest.TestCase):
    def test_tabular_selection_does_not_use_holdout_labels(self):
        frame, _ = read_csv_bytes((ROOT / 'samples/demo_housing.csv').read_bytes())
        data = prepare_data(frame, PrepConfig('房價萬元', 'regression', model='auto'))
        first = train_prepared(data)
        data.y_test = data.y_test * -1000
        second = train_prepared(data)
        self.assertEqual(first[1]['model_comparison'], second[1]['model_comparison'])
        self.assertEqual(first[1]['selected_model'], second[1]['selected_model'])
        self.assertEqual(first[1]['selection_data'], 'inner_validation_only')

    def test_time_selection_does_not_use_future_test_values(self):
        frame, _ = read_csv_bytes((ROOT / 'samples/demo_timeseries.csv').read_bytes())
        config = ForecastConfig('銷量', '日期', model='auto', lookback=7, horizon=3)
        data = prepare_forecast(frame, config)
        first = train_forecast(data)
        frame.loc[data.test_positions[0]:, '銷量'] = '9999999'
        second = train_forecast(prepare_forecast(frame, config))
        self.assertEqual(first[1]['model_comparison'], second[1]['model_comparison'])
        selection = data.report['selection']
        self.assertLess(selection['train_last_target_position'], selection['validation_first_origin_position'])
        self.assertLess(selection['validation_last_target_position'], selection['test_first_target_position'])

    def test_planner_requires_target_and_forecast_intent(self):
        payload = (ROOT / 'samples/demo_timeseries.csv').read_bytes()
        self.assertTrue(suggest_plan(payload)['target_required'])
        regular = suggest_plan(payload, target='銷量')
        self.assertEqual(regular['suggested_options']['task'], 'regression')
        future = suggest_plan(payload, target='銷量', forecast_intent=True)
        self.assertEqual(future['suggested_options']['task'], 'time_series')
        self.assertEqual(future['suggested_options']['excluded_columns'], ['流水號'])

    def test_tabular_auto_export_retrains_independently(self):
        frame, _ = read_csv_bytes((ROOT / 'samples/demo_churn.csv').read_bytes())
        data = prepare_data(frame, PrepConfig('是否流失', model='auto', excluded_columns=('客戶編號',)))
        trained = train_prepared(data)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with zipfile.ZipFile(io.BytesIO(make_training_bundle(data, trained))) as z:
                z.extractall(folder)
            env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
            result = subprocess.run([sys.executable, 'train.py', '--data', '.'], cwd=folder, env=env,
                                     capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = json.loads((folder / 'metrics.json').read_text(encoding='utf-8'))
            self.assertEqual(metrics['selection_data'], 'inner_validation_only')


@unittest.skipUnless(importlib.util.find_spec('tensorflow'), 'optional TensorFlow not installed')
class LSTMChecks(unittest.TestCase):
    def test_lstm_can_join_automatic_comparison(self):
        frame, _ = read_csv_bytes((ROOT / 'samples/demo_timeseries.csv').read_bytes())
        data = prepare_forecast(frame.iloc[:100], ForecastConfig('銷量', '日期', model='auto', lookback=7,
                         include_lstm=True, lstm_epochs=1, lstm_units=8))
        result = train_forecast(data)
        self.assertEqual([c['candidate'] for c in result[1]['model_comparison']], ['ridge', 'random_forest', 'lstm'])
        self.assertIn(result[1]['selected_model'], ['ridge', 'random_forest', 'lstm'])

    def test_fit_keras_export_fresh_process_predict_and_scaled_shape(self):
        frame, _ = read_csv_bytes((ROOT / 'samples/demo_timeseries.csv').read_bytes())
        frame = frame.iloc[:100]
        data = prepare_forecast(frame, ForecastConfig('銷量', '日期', model='lstm', lookback=7,
                                                      lstm_epochs=2, lstm_units=8, feature_columns=('溫度',)))
        trained = train_forecast(data)
        expected = trained[0].forecast(frame)['prediction']
        self.assertLessEqual(trained[1]['lstm_refit_epochs'], 2)
        self.assertEqual(trained[0].estimator._sequence(trained[0].preprocessor.transform(data.windows)).shape[1:], (7, 2))
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with zipfile.ZipFile(io.BytesIO(make_forecast_bundle(data, trained))) as z:
                self.assertIn('model.keras', z.namelist())
                self.assertIn('preprocessor.joblib', z.namelist())
                self.assertIn('lstm_scaling.json', z.namelist())
                z.extractall(folder)
            env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
            run = subprocess.run([sys.executable, 'forecast.py', '--csv', 'history.csv', '--output', 'future.csv'],
                                 cwd=folder, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            actual = pd.read_csv(folder / 'future.csv').prediction.iloc[0]
            self.assertAlmostEqual(actual, expected, places=4)


if __name__ == '__main__':
    unittest.main()
