"""Pytest fixtures.

Environment variables are set *before* any ``app`` import so the Settings
singleton points at throwaway test storage.
"""
import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys_path_inserted = ROOT  # for clarity below

if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

# Isolated, throwaway test storage (cleaned up at session end).
os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT / 'data' / 'test_scans.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(ROOT / "data" / "test_uploads")
os.environ["MODEL_PATH"] = str(ROOT / "models" / "does-not-exist.pt")
os.environ["HEALTHY_CLASSES"] = "[]"
os.environ["ROBOFLOW_API_KEY"] = ""

sys_path_inserted = ROOT  # silence unused warning


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_storage():
    """Remove test DB/uploads created during the session."""
    yield
    for path in (ROOT / "data").glob("test_*"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
