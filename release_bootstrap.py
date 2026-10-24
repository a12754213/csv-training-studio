"""Refresh changed release modules when Streamlit keeps its Python process alive.

Streamlit Cloud can replace source files while retaining imported modules.
Reload only this release's changed modules, in dependency order. Core context
and training classes retain their identities; existing training objects remain valid.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path
import sys
import threading

_LOCK = threading.RLock()
_MODULES = (
    "version",
    "agent_modules.market_tools",
    "agent_modules.research_tools",
    "agent_modules",
    "agent_supervisor",
    "ui_layout",
)


def current_source_version() -> str:
    source = Path(__file__).with_name("version.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise RuntimeError("無法讀取目前程式版本。")


def ensure_current_release() -> str:
    """Load the on-disk release once per process, before constructing page tools."""
    with _LOCK:
        expected = current_source_version()
        version = importlib.import_module("version")
        if version.__version__ != expected:
            importlib.invalidate_caches()
            for name in _MODULES:
                module = sys.modules.get(name)
                if module is not None:
                    importlib.reload(module)
            # Stable training modules keep their classes, but exported report
            # metadata must identify the release now on disk.
            for name in ("preprocessing", "forecasting", "training_service", "automl"):
                module = sys.modules.get(name)
                if module is not None and hasattr(module, "__version__"):
                    module.__version__ = expected
        if version.__version__ != expected:
            raise RuntimeError("程式更新尚未載入完成，請在 Streamlit 管理介面重新啟動。")
        return expected
