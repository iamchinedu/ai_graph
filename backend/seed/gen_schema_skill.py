"""Regenerate skills/schema-overview/SKILL.md from depmap_sdk/schema.py so the two never drift.

    python -m backend.seed.gen_schema_skill
"""
from backend import paths
from depmap_sdk.schema import TABLES

HEAD = """---
name: schema-overview
description: Every table in the dependency map, its columns, types and meaning. Load this before writing any SQL.
---

# Schema overview

All tables are queryable by name in SQL (DuckDB over `data/<table>.json`).

Conventions
- Timestamps are ISO-8601 UTC strings (VARCHAR), e.g. `2026-11-11T21:14:02Z`. Compare them as strings, or `CAST(x AS TIMESTAMP)`.
- Edge tables hold IDs only. Join to the node tables to get names.
- `environment` is one of `dev`, `test`, `prod`. Every project edge carries one. Filter on it whenever the question names an environment.
- `status` on an edge is `pass`, `fail`, or `pending` (not yet checked). `status_reason` explains a `fail`.
- `count` meanings differ by edge (see each table). Never present a count as more than what it measures.
- Observability edges have no status and never fail.
- Columns are NOT tracked anywhere. Do not answer column-level questions.

"""

out = [HEAD]
for kind, title in (("node", "Node tables"), ("edge", "Edge tables")):
    out.append(f"## {title}\n")
    for name, spec in TABLES.items():
        if spec["kind"] != kind:
            continue
        out.append(f"### {name}\n\n{spec['doc']}\n\nKey: `{', '.join(spec['key'])}`\n")
        out.append("| column | type |\n| --- | --- |")
        out.extend(f"| {c} | {t} |" for c, t in spec["columns"].items())
        out.append("")
(paths.SKILLS_DIR / "schema-overview").mkdir(parents=True, exist_ok=True)
(paths.SKILLS_DIR / "schema-overview" / "SKILL.md").write_text("\n".join(out))
print("wrote skills/schema-overview/SKILL.md")
