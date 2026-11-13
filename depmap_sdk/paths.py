"""Where the data lives. DEPMAP_DATA_DIR overrides the data folder (tests, other machines)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DEPMAP_DATA_DIR", ROOT / "data"))
