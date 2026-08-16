import sys
from pathlib import Path

# The package uses `from src.X import Y` imports, so ragbot/ must be on the path.
RAGBOT_DIR = Path(__file__).resolve().parent.parent / "ragbot"
sys.path.insert(0, str(RAGBOT_DIR))
