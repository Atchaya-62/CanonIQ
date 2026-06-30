from __future__ import annotations

import os
import tempfile
from pathlib import Path


WORKSPACE_TEMP = Path.cwd() / ".tmp"
WORKSPACE_TEMP.mkdir(exist_ok=True)
os.environ.setdefault("TMPDIR", str(WORKSPACE_TEMP))
os.environ.setdefault("TEMP", str(WORKSPACE_TEMP))
os.environ.setdefault("TMP", str(WORKSPACE_TEMP))
tempfile.tempdir = str(WORKSPACE_TEMP)

