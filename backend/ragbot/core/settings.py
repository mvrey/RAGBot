"""Central place for filesystem paths.

Hardcoded, __file__-relative paths break inside a container, where the working
directory and the package's on-disk location don't line up with a host repo
checkout. Every path here defaults to something that works for local
development (relative to where the `ragbot` package lives on disk) but can be
overridden by environment variables so a container can point them at a mounted
volume instead.
"""

import os
from pathlib import Path

# backend/ragbot/core/settings.py -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def _env_path(var_name: str, default: Path) -> Path:
    value = os.getenv(var_name, '').strip()
    return Path(value) if value else default


# Repo mirror + embedding cache.
DATA_DIR = _env_path('RAGBOT_DATA_DIR', _BACKEND_ROOT / 'data')

# Interaction logs written by AgentLog.
LOG_DIR = _env_path('RAGBOT_LOG_DIR', _BACKEND_ROOT / 'logs')

REPO_CACHE_DIR = DATA_DIR / 'repos'
EMBEDDING_CACHE_DIR = DATA_DIR / 'index' / 'embeddings'
