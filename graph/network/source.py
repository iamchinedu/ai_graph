"""The one place the app gets its raw graph data.

Today it reads two JSON files in data/ (placeholders: swap them for your real extract).
Later, replace the body of load_raw() with a call to your API, S3 or a database. Nothing else changes,
as long as it returns the same shape:

    {"nodes": [{"node": "project:p1", "type": "project", "label": "HR bot", ...}, ...],
     "edges": [{"source": "project:p1", "target": "model:m1", "kind": "project_profile", "environment": "prod", ...}, ...]}

An edge reads "source depends on target". See agent/skills.py for what every field means.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_raw():
    return {
        "nodes": json.loads((DATA_DIR / "nodes.json").read_text()),
        "edges": json.loads((DATA_DIR / "edges.json").read_text()),
    }
