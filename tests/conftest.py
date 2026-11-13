import pytest

from backend import paths as backend_paths
from depmap_sdk import paths, store
from backend.projects import create_project
from depmap_sdk.schema import TABLES
from backend.seed import reference as ref


@pytest.fixture
def data(tmp_path, monkeypatch):
    """A fresh, seeded data folder per test."""
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(backend_paths, "GRAPH_DIR", tmp_path / "graph")
    seeds = {"departments": ref.DEPARTMENTS, "cloud_accounts": ref.CLOUD_ACCOUNTS, "models": ref.MODELS,
             "inference_profiles": ref.INFERENCE_PROFILES, "data_platforms": ref.DATA_PLATFORMS,
             "databases": ref.DATABASES, "db_tables": ref.DB_TABLES, "observability_tools": ref.OBSERVABILITY_TOOLS}
    for t in TABLES:
        store.write(t, seeds.get(t, []))
    for p in ref.PROJECTS:
        create_project(p["name"], p["department_id"], p["description"], project_id=p["id"])
    return tmp_path
