"""Create a source ZIP from a clean Git commit and optional portable Git history."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import __version__


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def build(output_dir: Path, with_history: bool = False):
    if git('status', '--porcelain', '--untracked-files=normal').strip():
        raise RuntimeError('Commit all intended source changes before packaging.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', __version__):
        raise ValueError('Version must use MAJOR.MINOR.PATCH')
    commit = git('rev-parse', 'HEAD').decode().strip()
    archive_bytes = git('archive', '--format=zip', 'HEAD')
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / f'CSV_Training_Studio-v{__version__}.zip'
    prefix = 'CSV_Training_Studio/'
    blocked_dirs = {'.git', '.venv', '.runtime', 'data', 'uploads', 'outputs', 'models', 'dist'}
    blocked_suffixes = {'.joblib', '.pkl', '.pickle', '.npz', '.npy', '.parquet', '.xlsx', '.zip', '.pem', '.key'}
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as source, zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as out:
        for entry in source.infolist():
            if entry.is_dir():
                continue
            path = PurePosixPath(entry.filename)
            if (blocked_dirs.intersection(path.parts) or path.name == 'secrets.toml'
                or path.name == '.env' or path.name.startswith('.env.')
                or path.suffix in blocked_suffixes
                or (path.suffix in {'.csv', '.tsv'} and not (path.parent == PurePosixPath('samples') and path.name.startswith('demo_')))):
                raise RuntimeError(f'Refusing to package private/generated file: {path}')
            content = source.read(entry)
            if path.suffix in {'.ps1', '.bat'}:
                content = content.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
            entry.filename = prefix + entry.filename
            out.writestr(entry, content)
        out.writestr(prefix + 'BUILD_INFO.json', json.dumps({'version': __version__, 'commit': commit,
                      'python_minor': '3.12', 'history_included': with_history}, indent=2) + '\n')
        if with_history:
            bundle = output_dir / 'CSV_Training_Studio.bundle'
            subprocess.run(['git', '-C', str(ROOT), 'bundle', 'create', str(bundle.resolve()), '--all'], check=True)
            out.write(bundle, prefix + 'history/CSV_Training_Studio.bundle')
    checksum = hashlib.sha256(dest.read_bytes()).hexdigest()
    sums = output_dir / 'SHA256SUMS.txt'
    sums.write_text(f'{checksum}  {dest.name}\n', encoding='ascii')
    print(f'Built {dest}\nCommit: {commit}\nSHA256: {checksum}')
    return dest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--with-history', action='store_true')
    args = parser.parse_args()
    build(args.output.resolve(), args.with_history)
