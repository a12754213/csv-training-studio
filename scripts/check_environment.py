"""Validate the Python minor version and every applicable pinned dependency."""
from __future__ import annotations
import argparse
from importlib import import_module, metadata
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def check_environment() -> list[str]:
    errors = []
    if sys.version_info[:2] != (3, 12):
        errors.append(f"Python 3.12 required; found {sys.version.split()[0]}")
    try:
        from packaging.requirements import Requirement
    except ImportError:
        return errors + ["Dependencies have not been installed."]
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        req = Requirement(line)
        if req.marker and not req.marker.evaluate():
            continue
        try:
            found = metadata.version(req.name)
        except metadata.PackageNotFoundError:
            errors.append(f"Missing {req.name}")
            continue
        if found not in req.specifier:
            errors.append(f"{req.name}: expected {req.specifier}, found {found}")
    if not errors:
        for module in ("streamlit", "numpy", "pandas", "scipy", "sklearn", "jieba", "joblib"):
            try:
                import_module(module)
            except Exception as exc:
                errors.append(f"{module}: {exc}")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    issues = check_environment()
    if not args.quiet:
        print("\n".join(issues) if issues else f"Python {sys.version.split()[0]}: all locked dependencies verified.")
    sys.exit(bool(issues))
