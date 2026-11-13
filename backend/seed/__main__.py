"""python -m backend.seed  -> wipes data/ and loads reference data + the 5 sample projects."""
from depmap_sdk import store
from backend.projects import create_project
from depmap_sdk.schema import TABLES
from backend.seed import reference as ref

REFERENCE = {
    "departments": ref.DEPARTMENTS, "cloud_accounts": ref.CLOUD_ACCOUNTS, "models": ref.MODELS,
    "inference_profiles": ref.INFERENCE_PROFILES, "data_platforms": ref.DATA_PLATFORMS,
    "databases": ref.DATABASES, "db_tables": ref.DB_TABLES, "observability_tools": ref.OBSERVABILITY_TOOLS,
}

for table in TABLES:
    store.write(table, REFERENCE.get(table, []))
for p in ref.PROJECTS:
    create_project(p["name"], p["department_id"], p["description"], project_id=p["id"])
print("Seeded:", {t: len(store.read(t)) for t in TABLES})
