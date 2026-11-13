"""Plain-Python tool functions for the chat agent. No agent framework needed to test them.

Each session gets a folder under scratch/<session_id>/. run_sql saves the query there as a
numbered .sql file and executes it with the read-only runner, so every query is inspectable.
"""
import json
import re

from backend import paths
from backend.graph.impact import dependencies, impact
from backend.query.run_query import run_file

_SKILL_NAME = re.compile(r"^[a-z0-9-]+$|^README$")


def list_skills():
    return sorted(p.parent.name for p in paths.SKILLS_DIR.glob("*/SKILL.md"))


def read_skill(name: str) -> str:
    """Return a skill's text. Use 'README' for the router."""
    if not _SKILL_NAME.match(name):
        return f"invalid skill name {name!r}; available: README, {', '.join(list_skills())}"
    f = paths.SKILLS_DIR / "README.md" if name == "README" else paths.SKILLS_DIR / name / "SKILL.md"
    if not f.exists():
        return f"no skill named {name!r}; available: README, {', '.join(list_skills())}"
    return f.read_text()


def run_sql(sql: str, session_dir=None) -> str:
    """Save sql as a file in the session folder and run it read-only. Returns a markdown table or an error."""
    folder = session_dir or (paths.SCRATCH_DIR / "adhoc")
    folder.mkdir(parents=True, exist_ok=True)
    n = len(list(folder.glob("query_*.sql"))) + 1
    f = folder / f"query_{n:03d}.sql"
    f.write_text(sql)
    try:
        return run_file(f)
    except Exception as exc:  # noqa: BLE001
        return f"query error: {exc}"


def graph_impact(node: str, environment: str = "") -> str:
    """Projects affected if `node` breaks, one row per project and environment (JSON)."""
    rows = impact(node, environment or None)
    return json.dumps({"node": node, "environment": environment or "all",
                       "projects_affected": len({r["project"] for r in rows}), "rows": rows}, indent=2)


def graph_dependencies(node: str, environment: str = "") -> str:
    """Everything `node` depends on, grouped by node type (JSON)."""
    return json.dumps(dependencies(node, environment or None), indent=2)
