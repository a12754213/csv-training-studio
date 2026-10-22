import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preprocessing import DataPreparationError
from training_service import LocalTrainingService, run_training_bytes


class TrainingServiceChecks(unittest.TestCase):
    def test_import_train_poll_export_and_byte_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / 'inbox'; inbox.mkdir()
            payload = (ROOT / 'samples/demo_timeseries.csv').read_bytes()
            (inbox / 'input.csv').write_bytes(payload)
            service = LocalTrainingService(root / 'workspace', inbox)
            try:
                dataset = service.import_csv('input.csv')
                self.assertEqual(dataset['sha256'], hashlib.sha256(payload).hexdigest())
                self.assertIn('流水號', dataset['suggested_excluded_columns'])
                task = service.start_training(dataset['dataset_id'], {'task': 'time_series', 'target': '銷量',
                                              'time_column': '日期', 'excluded_columns': ['流水號']})
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    job = service.get_job(task['job_id'])
                    if job['status'] not in {'queued', 'running'}:
                        break
                    time.sleep(.05)
                self.assertEqual(job['status'], 'completed', job)
                self.assertEqual(job['summary']['excluded_columns'], ['流水號'])
                self.assertTrue(zipfile.is_zipfile(job['bundle_path']))
                self.assertEqual(hashlib.sha256(Path(job['bundle_path']).read_bytes()).hexdigest(), job['summary']['bundle_sha256'])
                with self.assertRaises(DataPreparationError):
                    LocalTrainingService(root / 'workspace', inbox)
                with self.assertRaises(DataPreparationError):
                    service.import_csv('../outside.csv')
                with self.assertRaises(DataPreparationError):
                    service.get_job('../../anything')
            finally:
                service.close()

    def test_tabular_engine_honors_exclusions_and_rejects_unknown_options(self):
        payload = (ROOT / 'samples/demo_churn.csv').read_bytes()
        bundle, report = run_training_bytes(payload, {'task': 'classification', 'target': '是否流失'})
        self.assertTrue(bundle.startswith(b'PK'))
        self.assertTrue(report['excluded_columns'])
        self.assertFalse(set(report['excluded_columns']) & set(report['used_columns']))
        with self.assertRaises(DataPreparationError):
            run_training_bytes(payload, {'target': '是否流失', 'bogus': True})

    def test_invalid_job_becomes_failed_and_restart_marks_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = LocalTrainingService(root / 'work', root / 'inbox')
            try:
                dataset = service.upload_csv('input.csv', b'x,y\n1,0\n2,1\n')
                job = service.start_training(dataset['dataset_id'], {'target': 'absent'})
            finally:
                service.close()
            self.assertEqual(service.get_job(job['job_id'])['status'], 'failed')
            status = root / 'work/jobs' / job['job_id'] / 'status.json'
            status.write_text(json.dumps({'job_id': job['job_id'], 'status': 'running'}))
            new = LocalTrainingService(root / 'work', root / 'inbox')
            try:
                self.assertEqual(new.get_job(job['job_id'])['status'], 'interrupted')
            finally:
                new.close()


if __name__ == '__main__':
    unittest.main()
