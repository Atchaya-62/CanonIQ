from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@lru_cache(maxsize=None)
def load_config(name: str, default: Any | None = None) -> Any:
    path = CONFIG_DIR / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def config_path(name: str) -> Path:
    return CONFIG_DIR / name

