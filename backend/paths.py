"""Backend-only folders. The data folder itself belongs to the package: depmap_sdk.paths.DATA_DIR."""
from depmap_sdk.paths import ROOT

SCRATCH_DIR = ROOT / "scratch"
SKILLS_DIR = ROOT / "skills"
GRAPH_DIR = ROOT / "graph"          # built graph snapshots (python -m backend.graph build)
