"""Recompute edge status from the registry. Only conditions we can actually determine:

  profile edge : fails if the profile is not in the registry, is not active, or its model is deprecated
  table edge   : fails if the table is not in the registry or table_exists is false
  observability: no status, never fails
"""
from datetime import datetime, timezone

from depmap_sdk import store


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _profile_result(edge, profiles, models):
    prof = profiles.get(edge["profile_id"])
    if prof is None:
        return "fail", "inference profile is not in the registry"
    if prof["status"] != "active":
        return "fail", f'inference profile status is {prof["status"]}'
    model = models.get(prof["model_id"])
    if model is None:
        return "fail", "profile points at a model that is not in the registry"
    if model["deprecated"]:
        return "fail", f'model {model["name"]} is deprecated'
    return "pass", None


def _table_result(edge, tables, databases):
    tbl = tables.get(edge["table_id"])
    if tbl is None:
        return "fail", "table is not in the registry"
    if not tbl["table_exists"]:
        db = databases.get(tbl["database_id"], {})
        return "fail", f'table {db.get("name", "?")}.{tbl["table_name"]} no longer exists'
    return "pass", None


def run_checks():
    """Update status on every profile and table edge. Returns a summary dict."""
    now = _now()
    with store.locked():
        profiles = {p["id"]: p for p in store.read("inference_profiles")}
        models = {m["id"]: m for m in store.read("models")}
        tables = {t["id"]: t for t in store.read("db_tables")}
        databases = {d["id"]: d for d in store.read("databases")}

        summary = {"pass": 0, "fail": 0}
        p_edges = store.read("project_profile_edges")
        for e in p_edges:
            e["status"], e["status_reason"] = _profile_result(e, profiles, models)
            e["status_checked_at"] = now
            summary[e["status"]] += 1
        store.write("project_profile_edges", p_edges)

        t_edges = store.read("project_table_edges")
        for e in t_edges:
            e["status"], e["status_reason"] = _table_result(e, tables, databases)
            e["status_checked_at"] = now
            summary[e["status"]] += 1
        store.write("project_table_edges", t_edges)

        for t in tables.values():
            t["last_checked_at"] = now
        store.write("db_tables", list(tables.values()))
    return summary
