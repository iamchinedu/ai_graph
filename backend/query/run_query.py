"""Read-only SQL over the data/ tables, via DuckDB. This is the agent's query sandbox.

    python -m backend.query.run_query path/to/query.sql [--format markdown|json]

Every table is loaded into a throwaway in-memory database, then external access and further
configuration changes are switched off, so a query cannot read other files or change data/.
Only a single SELECT / WITH / DESCRIBE / SHOW / EXPLAIN statement is accepted.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import duckdb

from depmap_sdk import paths
from depmap_sdk.schema import TABLES

_ALLOWED = ("select", "with", "describe", "show", "explain")


def _connect():
    con = duckdb.connect(":memory:")
    for table, spec in TABLES.items():
        f = paths.DATA_DIR / f"{table}.json"
        cols = ", ".join(f"'{c}': '{t}'" for c, t in spec["columns"].items())
        if f.exists() and f.stat().st_size > 2:
            con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_json('{f}', format='array', columns={{{cols}}})")
        else:
            ddl = ", ".join(f"{c} {t}" for c, t in spec["columns"].items())
            con.execute(f"CREATE TABLE {table} ({ddl})")
    con.execute("SET enable_external_access=false")
    con.execute("SET lock_configuration=true")
    return con


def _check(sql):
    stripped = re.sub(r"/\*.*?\*/", " ", re.sub(r"--[^\n]*", " ", sql), flags=re.S).strip().rstrip(";").strip()
    if not stripped:
        raise ValueError("empty query")
    if ";" in stripped:
        raise ValueError("only one statement is allowed")
    if stripped.split(None, 1)[0].lower() not in _ALLOWED:
        raise ValueError(f"only {', '.join(_ALLOWED)} statements are allowed")
    return stripped


def execute_sql(sql):
    """Return (column_names, rows). Raises ValueError for disallowed SQL."""
    stmt = _check(sql)
    con = _connect()
    try:
        cur = con.execute(stmt)
        return [d[0] for d in cur.description], cur.fetchall()
    finally:
        con.close()


def format_result(columns, rows, fmt="markdown", limit=200):
    shown = rows[:limit]
    if fmt == "json":
        return json.dumps([dict(zip(columns, r)) for r in shown], indent=2, default=str)
    head = "| " + " | ".join(columns) + " |\n| " + " | ".join("---" for _ in columns) + " |"
    body = "\n".join("| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in shown)
    note = f"\n\n({len(rows)} rows, showing {limit})" if len(rows) > limit else f"\n\n({len(rows)} rows)"
    return head + ("\n" + body if body else "") + note


def run_file(path, fmt="markdown"):
    cols, rows = execute_sql(Path(path).read_text())
    return format_result(cols, rows, fmt)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--format", default="markdown", choices=["markdown", "json"])
    a = ap.parse_args()
    try:
        print(run_file(a.file, a.format))
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"query error: {exc}")
