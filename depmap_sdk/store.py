"""File-backed table store: data/<table>.json (a JSON array of records).

Single writer at a time: all mutations take an exclusive file lock, and writes are
atomic (temp file + rename). Fine for the MVP; move to SQLite if you need parallel writers.
"""
import json
import os
import threading
import time
from contextlib import contextmanager

from depmap_sdk import paths
from depmap_sdk.schema import TABLES

_local = threading.local()

try:  # macOS / Linux
    import fcntl

    def _lock(fh):
        fcntl.flock(fh, fcntl.LOCK_EX)

    def _unlock(fh):
        fcntl.flock(fh, fcntl.LOCK_UN)
except ImportError:  # Windows
    import msvcrt

    def _lock(fh):
        fh.write(" "); fh.flush(); fh.seek(0)
        while True:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.05)

    def _unlock(fh):
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def _table_file(table):
    if table not in TABLES:
        raise KeyError(f"unknown table: {table}")
    return paths.DATA_DIR / f"{table}.json"


@contextmanager
def locked():
    """Re-entrant exclusive lock across processes."""
    depth = getattr(_local, "depth", 0)
    if depth:
        _local.depth = depth + 1
        try:
            yield
        finally:
            _local.depth -= 1
        return
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(paths.DATA_DIR / ".lock", "a+") as fh:
        _lock(fh)
        _local.depth = 1
        try:
            yield
        finally:
            _local.depth = 0
            _unlock(fh)


def read(table):
    f = _table_file(table)
    if not f.exists():
        return []
    with open(f) as fh:
        return json.load(fh)


def write(table, rows):
    f = _table_file(table)
    f.parent.mkdir(parents=True, exist_ok=True)
    with locked():
        tmp = f.with_suffix(".tmp")
        with open(tmp, "w") as fh:
            json.dump(rows, fh, indent=2)
        os.replace(tmp, f)


def init_all():
    """Create an empty file for every table that does not have one yet."""
    for t in TABLES:
        if not _table_file(t).exists():
            write(t, [])


def find(table, **match):
    return [r for r in read(table) if all(r.get(k) == v for k, v in match.items())]


def get(table, **match):
    rows = find(table, **match)
    return rows[0] if rows else None


def next_id(table):
    return max([r["id"] for r in read(table)], default=0) + 1


def upsert(table, record, update=None):
    """Insert record, or merge into the existing row with the same key.

    update(existing, record) -> merged row. Default: overwrite fields from record.
    Returns (row, created).
    """
    key = TABLES[table]["key"]
    with locked():
        rows = read(table)
        for i, r in enumerate(rows):
            if all(r.get(k) == record.get(k) for k in key):
                merged = update(r, record) if update else {**r, **record}
                rows[i] = merged
                write(table, rows)
                return merged, False
        full = {c: record.get(c) for c in TABLES[table]["columns"]}
        rows.append(full)
        write(table, rows)
        return full, True
