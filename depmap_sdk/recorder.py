"""Turns SDK events into table updates. This is the write path: every log call ends up here.

Event types (all carry project_id, environment, ts):
  project.init  : packages + declared databases/tables + observability tools
  model.call    : model_id (profile ID/ARN), n
  table.access  : platform, database, table, n

Unknown project IDs are rejected. Unknown platforms / observability tools are rejected
(they are preselected lists). Unknown databases and tables are registered on first sight.
"""
import hashlib
from datetime import datetime, timezone

from depmap_sdk import store
from depmap_sdk.packages import evaluate
from depmap_sdk.schema import ENVIRONMENTS


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _later(a, b):
    return max([x for x in (a, b) if x], default=None)


def _bump_edge(table, record, n, ts):
    """Create the edge, or add n to its count and move last_seen forward."""
    def merge(existing, new):
        existing["count"] = (existing.get("count") or 0) + n
        if n:
            existing["last_seen"] = _later(existing.get("last_seen"), ts)
        return existing
    rec = {**record, "count": n, "last_seen": ts if n else None}
    if table != "project_observability_edges":
        rec.update(status="pending", status_reason=None, status_checked_at=None)
    return store.upsert(table, rec, update=merge)


def _ensure_table(platform, database, table, environment, ts, warnings):
    plat = store.get("data_platforms", name=platform)
    if plat is None:
        warnings.append(f"unknown data platform {platform!r}; skipped")
        return None
    db = next((d for d in store.find("databases", name=database, environment=environment)
               if d["platform_id"] == plat["id"]), None)
    if db is None:
        db, _ = store.upsert("databases", {
            "id": store.next_id("databases"), "name": database,
            "platform_id": plat["id"], "environment": environment,
        })
    tbl = next((t for t in store.find("db_tables", database_id=db["id"])
                if t["table_name"] == table), None)
    if tbl is None:
        tbl, _ = store.upsert("db_tables", {
            "id": store.next_id("db_tables"), "database_id": db["id"], "table_name": table,
            "last_checked_at": None, "table_exists": True,
        })
    return tbl


def _canonical_profile_id(model_id, project_id, environment):
    """Calls may pass a short system-defined ID (us.anthropic...); the registry stores the full ARN
    per account. Resolve using the account this project reported at init."""
    if model_id.startswith("arn:"):
        return model_id
    env_row = store.get("project_environments", project_id=project_id, environment=environment)
    account = env_row and env_row.get("account_id")
    if account:
        for p in store.find("inference_profiles", account_id=account):
            if p["id"].endswith("/" + model_id):
                return p["id"]
    return model_id


def _packages_hash(packages, python_version):
    items = sorted(f'{p["name"].lower()}=={p["version"]}' for p in packages)
    return hashlib.sha256(("|".join(items) + f"|py{python_version}").encode()).hexdigest()[:16]


def _handle_init(ev, ts, warnings):
    pid, env = ev["project_id"], ev["environment"]
    packages = ev.get("packages") or []
    valid, reason = (None, None)
    if packages:
        valid, reason = evaluate(packages, ev.get("marker_env"))
    def count_run(existing, new):
        return {**existing, **new, "run_count": (existing.get("run_count") or 0) + 1}

    store.upsert("project_environments", {
        "project_id": pid, "environment": env, "account_id": ev.get("account_id"),
        "python_version": ev.get("python_version"),
        "packages": [{"name": p["name"], "version": p["version"]} for p in packages],
        "packages_hash": _packages_hash(packages, ev.get("python_version")) if packages else None,
        "packages_valid": valid, "packages_reason": reason,
        "packages_checked_at": ts if packages else None, "last_init_at": ts, "run_count": 1,
    }, update=count_run)
    for decl in ev.get("databases") or []:
        for table in decl.get("tables") or []:
            tbl = _ensure_table(decl["platform"], decl["database"], table, env, ts, warnings)
            if tbl:
                _bump_edge("project_table_edges",
                           {"project_id": pid, "table_id": tbl["id"], "environment": env}, 0, ts)
    for name in ev.get("observability") or []:
        tool = store.get("observability_tools", name=name)
        if tool is None:
            warnings.append(f"unknown observability tool {name!r}; skipped")
            continue
        _bump_edge("project_observability_edges",
                   {"project_id": pid, "tool_id": tool["id"], "environment": env}, 1, ts)


def handle_event(ev):
    """Apply one event. Returns {"accepted": bool, "warnings": [...]}."""
    warnings = []
    try:
        if ev.get("environment") not in ENVIRONMENTS:
            return {"accepted": False, "warnings": [f'invalid environment {ev.get("environment")!r}']}
        if store.get("projects", id=ev.get("project_id")) is None:
            return {"accepted": False, "warnings": [f'unknown project {ev.get("project_id")!r}']}
        ts = ev.get("ts") or _now()
        with store.locked():
            kind = ev.get("type")
            if kind == "project.init":
                _handle_init(ev, ts, warnings)
            elif kind == "model.call":
                _bump_edge("project_profile_edges", {
                    "project_id": ev["project_id"],
                    "profile_id": _canonical_profile_id(ev["model_id"], ev["project_id"], ev["environment"]),
                    "environment": ev["environment"]}, int(ev.get("n", 1)), ts)
            elif kind == "table.access":
                tbl = _ensure_table(ev["platform"], ev["database"], ev["table"],
                                    ev["environment"], ts, warnings)
                if tbl:
                    _bump_edge("project_table_edges", {
                        "project_id": ev["project_id"], "table_id": tbl["id"],
                        "environment": ev["environment"]}, int(ev.get("n", 1)), ts)
            else:
                return {"accepted": False, "warnings": [f"unknown event type {kind!r}"]}
        return {"accepted": True, "warnings": warnings}
    except Exception as exc:  # a bad event must not crash the caller
        return {"accepted": False, "warnings": [f"error: {exc}"]}
