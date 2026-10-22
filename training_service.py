"""Shared headless training engine and local job storage (no network/API key)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

from forecasting import ForecastConfig, make_forecast_bundle, prepare_forecast, train_forecast
from automl import train_prepared
from preprocessing import (DataPreparationError, MAX_UPLOAD_BYTES, PrepConfig, _identifier_name,
                           json_text, make_training_bundle, prepare_data, profile_frame,
                           read_csv_bytes, train_baseline)

ROOT = Path(__file__).resolve().parent
DEFAULT_WORKSPACE = ROOT / 'outputs' / 'chatgpt'


def suggested_exclusions(frame, protected=()):
    # Name-based suggestions do not learn anything from the test population.
    return [c for c in frame if c not in protected and _identifier_name(c)]


def run_training_bytes(payload: bytes, options: dict):
    opts = dict(options)
    task = opts.pop('task', 'classification')
    encoding, separator = opts.pop('encoding', 'auto'), opts.pop('separator', 'auto')
    frame, info = read_csv_bytes(payload, encoding, separator)
    if task not in {'classification', 'regression', 'time_series'}:
        raise DataPreparationError('task 必須為 classification、regression 或 time_series。')
    if 'target' not in opts:
        raise DataPreparationError('請指定要預測的 target 欄位，不會擅自猜測目標。')
    if opts.get('excluded_columns') is None:
        opts['excluded_columns'] = suggested_exclusions(frame, [opts['target'], opts.get('time_column'), opts.get('split_column')])
    try:
        if task == 'time_series':
            config = ForecastConfig(**opts)
            data = prepare_forecast(frame, config)
            trained = train_forecast(data)
            bundle = make_forecast_bundle(data, trained)
            used = data.report['history_columns']
        else:
            config = PrepConfig(task=task, **opts)
            data = prepare_data(frame, config)
            trained = train_prepared(data)
            bundle = make_training_bundle(data, trained)
            used = data.report['used_feature_columns']
    except TypeError as exc:
        raise DataPreparationError(f'訓練設定不正確：{exc}') from exc
    summary = {'task': task, 'config': asdict(config), 'input': info,
               'input_sha256': hashlib.sha256(payload).hexdigest(),
               'rows': data.report['rows'], 'used_columns': used,
               'excluded_columns': list(config.excluded_columns),
               'metrics': trained[1], 'bundle_sha256': hashlib.sha256(bundle).hexdigest()}
    return bundle, summary


def write_json(path, data):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json_text(data), encoding='utf-8')
    temp.replace(path)


def valid_id(value):
    if not re.fullmatch('[0-9a-f]{32}', value):
        raise DataPreparationError('資料或工作編號無效。')
    return value


class LocalTrainingService:
    """One worker, bounded queue. All input paths stay inside an explicitly allowed inbox."""
    def __init__(self, workspace=DEFAULT_WORKSPACE, inbox=None):
        self.workspace = Path(workspace).resolve()
        self.inbox = Path(inbox or ROOT / 'uploads').resolve()
        self.datasets = self.workspace / 'datasets'
        self.jobs = self.workspace / 'jobs'
        for folder in (self.inbox, self.datasets, self.jobs):
            folder.mkdir(parents=True, exist_ok=True)
        self.lock = (self.workspace / 'server.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.lock.seek(0)
                if not self.lock.read(1):
                    self.lock.write(b'0')
                    self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.lock.close()
            raise DataPreparationError('這個工作資料夾已由另一個訓練服務使用，請先關閉另一個服務。') from exc
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='csv-training')
        self.slots = threading.BoundedSemaphore(4)
        # Only one server should own a workspace. Interrupted jobs never look successful.
        for status in self.jobs.glob('*/status.json'):
            record = json.loads(status.read_text(encoding='utf-8'))
            if record['status'] in {'queued', 'running'}:
                record.update(status='interrupted', error='上次服務中斷，請重新送出訓練。')
                write_json(status, record)

    def upload_csv(self, filename, content, encoding='auto', separator='auto'):
        if len(content) > MAX_UPLOAD_BYTES:
            raise DataPreparationError('CSV 超過 30 MB。')
        frame, info = read_csv_bytes(content, encoding, separator)
        dataset_id = uuid.uuid4().hex
        dest = self.datasets / dataset_id
        dest.mkdir()
        (dest / 'input.csv').write_bytes(content)
        summary = {'dataset_id': dataset_id, 'filename': Path(filename.replace('\\', '/')).name,
                   'rows': len(frame), 'columns': list(frame.columns),
                   'suggested_excluded_columns': suggested_exclusions(frame),
                   'profile': profile_frame(frame).to_dict(orient='records'), 'read_options': info,
                   'sha256': hashlib.sha256(content).hexdigest()}
        write_json(dest / 'dataset.json', summary)
        return summary

    def import_csv(self, path, encoding='auto', separator='auto'):
        candidate = Path(path)
        candidate = (candidate if candidate.is_absolute() else self.inbox / candidate).resolve()
        if not candidate.is_relative_to(self.inbox):
            raise DataPreparationError('只能讀取指定上傳資料夾內的 CSV；請先把附件複製到 inbox。')
        if candidate.suffix.lower() not in {'.csv', '.tsv', '.txt'} or not candidate.is_file():
            raise DataPreparationError('請提供存在的 CSV／TSV／TXT 檔案。')
        if candidate.stat().st_size > MAX_UPLOAD_BYTES:
            raise DataPreparationError('CSV 超過 30 MB。')
        return self.upload_csv(candidate.name, candidate.read_bytes(), encoding, separator)

    def list_datasets(self):
        return [{'dataset_id': r['dataset_id'], 'filename': r['filename'], 'rows': r['rows'], 'columns': r['columns']}
                for p in sorted(self.datasets.glob('*/dataset.json'))
                for r in [json.loads(p.read_text(encoding='utf-8'))]]

    def inspect_dataset(self, dataset_id):
        path = self.datasets / valid_id(dataset_id) / 'dataset.json'
        if not path.is_file():
            raise DataPreparationError('找不到這份資料，請先上傳。')
        return json.loads(path.read_text(encoding='utf-8'))

    def start_training(self, dataset_id, options):
        dataset = self.inspect_dataset(dataset_id)
        # Store exact effective reader settings along with the user's config.
        options = {'encoding': dataset['read_options']['encoding'],
                   'separator': dataset['read_options']['separator'], **options}
        if not self.slots.acquire(blocking=False):
            raise DataPreparationError('已有 4 個工作執行或等待，請等完成後再送出。')
        job_id = uuid.uuid4().hex
        folder = self.jobs / job_id
        try:
            folder.mkdir()
            record = {'job_id': job_id, 'dataset_id': dataset_id, 'status': 'queued',
                      'created_at': datetime.now(timezone.utc).isoformat(), 'options': options}
            write_json(folder / 'status.json', record)
            future = self.executor.submit(self._run, folder, record)
            future.add_done_callback(lambda _: self.slots.release())
        except Exception:
            self.slots.release()
            raise
        return {'job_id': job_id, 'status': 'queued'}

    def _run(self, folder, record):
        try:
            record['status'] = 'running'
            write_json(folder / 'status.json', record)
            payload = (self.datasets / record['dataset_id'] / 'input.csv').read_bytes()
            bundle, summary = run_training_bytes(payload, record['options'])
            temp = folder / 'training_data.zip.tmp'
            temp.write_bytes(bundle)
            temp.replace(folder / 'training_data.zip')
            write_json(folder / 'summary.json', summary)
            record.update(status='completed', finished_at=datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        write_json(folder / 'status.json', record)

    def get_job(self, job_id):
        folder = self.jobs / valid_id(job_id)
        path = folder / 'status.json'
        if not path.is_file():
            raise DataPreparationError('找不到這個工作。')
        record = json.loads(path.read_text(encoding='utf-8'))
        if record['status'] == 'completed':
            record['summary'] = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
            record['bundle_path'] = str(folder / 'training_data.zip')
            record['summary_path'] = str(folder / 'summary.json')
            record['artifact_uri'] = f'studio://jobs/{job_id}/training_data.zip'
        return record

    def close(self):
        self.executor.shutdown(wait=True)
        self.lock.close()
