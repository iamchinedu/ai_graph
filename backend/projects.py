"""Create-project flow (what the UI form will call): validates and assigns an ID."""
import uuid
from datetime import datetime, timezone

from depmap_sdk import store


def create_project(name, department_id, description="", project_id=None):
    name = (name or "").strip()
    if not 3 <= len(name) <= 80:
        raise ValueError("project name must be 3-80 characters")
    if len(description or "") > 500:
        raise ValueError("description must be at most 500 characters")
    if store.get("projects", name=name):
        raise ValueError(f"a project named {name!r} already exists")
    dept = store.get("departments", id=department_id)
    if dept is None:
        raise ValueError(f"unknown department id {department_id}")
    pid = project_id or f'prj_{dept["abbreviation"]}_{uuid.uuid4().hex[:6]}'
    row, _ = store.upsert("projects", {
        "id": pid, "name": name, "department_id": department_id,
        "description": description or "",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    return row
