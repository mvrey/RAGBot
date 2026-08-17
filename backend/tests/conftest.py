import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

# The package uses `from ragbot.core.X import Y` imports, so backend/ must be on
# the path (equivalent to an editable install, without requiring one for tests).
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Must be set before anything imports ragbot.core.settings: REPO_CACHE_DIR and
# EMBEDDING_CACHE_DIR are consumed as default-argument expressions (e.g.
# `def __init__(self, cache_dir=REPO_CACHE_DIR)`), which Python binds once at
# module load time - patching the env var afterwards would miss every one of
# those already-defined defaults. Redirecting it here keeps the whole test
# session off the real backend/data/ directory without every test needing to
# pass cache_dir= explicitly.
_TEST_DATA_DIR = tempfile.mkdtemp(prefix='ragbot-test-data-')
os.environ.setdefault('RAGBOT_DATA_DIR', _TEST_DATA_DIR)
os.environ.setdefault('RAGBOT_LOG_DIR', str(Path(_TEST_DATA_DIR) / 'logs'))
atexit.register(shutil.rmtree, _TEST_DATA_DIR, True)
