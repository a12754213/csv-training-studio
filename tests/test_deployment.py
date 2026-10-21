"""Regression coverage for occupied ports and versioned training exports."""
import io
from pathlib import Path
import socket
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.serve import select_port
from preprocessing import PrepConfig, make_training_bundle, prepare_data, read_csv_bytes
from version import __version__


class DeploymentChecks(unittest.TestCase):
    def test_explicit_occupied_port_is_rejected(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen()
            with self.assertRaises(RuntimeError):
                select_port(sock.getsockname()[1])

    def test_export_includes_its_version_dependency(self):
        frame, _ = read_csv_bytes((ROOT / 'samples/demo_churn.csv').read_bytes())
        result = prepare_data(frame, PrepConfig(target='是否流失', task='classification'))
        self.assertEqual(result.report['version'], __version__)
        with zipfile.ZipFile(io.BytesIO(make_training_bundle(result))) as archive:
            self.assertEqual(archive.read('version.py'), (ROOT / 'version.py').read_bytes())


if __name__ == '__main__':
    unittest.main()
