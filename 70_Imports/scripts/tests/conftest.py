import os
from pathlib import Path
import re
import tempfile
import uuid

import pytest


def stock_pytest_tmp_base() -> Path:
    configured = os.environ.get("STOCK_PYTEST_TMPDIR")
    if configured:
        return Path(configured).expanduser()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "06_Stock" / "pytest_tmp_cases"

    return Path(tempfile.gettempdir()) / "06_Stock" / "pytest_tmp_cases"


@pytest.fixture
def tmp_path(request) -> Path:
    base = stock_pytest_tmp_base()
    safe_name = re.sub(r"[^0-9A-Za-z_.-]+", "_", request.node.name)
    path = base / f"{safe_name}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path
