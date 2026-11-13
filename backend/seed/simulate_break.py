"""Flip registry facts to simulate things breaking, then recompute edge status.

  python -m backend.seed.simulate_break deprecate-model <model_id>
  python -m backend.seed.simulate_break restore-model <model_id>
  python -m backend.seed.simulate_break retire-profile <profile_id>
  python -m backend.seed.simulate_break restore-profile <profile_id>
  python -m backend.seed.simulate_break drop-table <database> <table> <env>
  python -m backend.seed.simulate_break restore-table <database> <table> <env>
  python -m backend.seed.simulate_break invalidate-packages <project_id> <env> "<reason>"   (simulated flag)
  python -m backend.seed.simulate_break restore-packages <project_id> <env>
"""
import sys

from depmap_sdk import store
from backend.checks import run_checks


def _set(table, match, **fields):
    rows = store.read(table)
    hit = [r for r in rows if all(r.get(k) == v for k, v in match.items())]
    if not hit:
        sys.exit(f"nothing matched {match} in {table}")
    for r in hit:
        r.update(fields)
    store.write(table, rows)


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd in ("deprecate-model", "restore-model"):
        _set("models", {"id": args[0]}, deprecated=cmd == "deprecate-model")
    elif cmd in ("retire-profile", "restore-profile"):
        _set("inference_profiles", {"id": args[0]}, status="inactive" if cmd == "retire-profile" else "active")
    elif cmd in ("drop-table", "restore-table"):
        db_name, table, env = args
        dbs = [d["id"] for d in store.find("databases", name=db_name, environment=env)]
        if not dbs:
            sys.exit(f"no database {db_name} in {env}")
        _set("db_tables", {"database_id": dbs[0], "table_name": table}, table_exists=cmd == "restore-table")
    elif cmd == "invalidate-packages":
        _set("project_environments", {"project_id": args[0], "environment": args[1]},
             packages_valid=False, packages_reason=args[2] if len(args) > 2 else "simulated package conflict")
    elif cmd == "restore-packages":
        _set("project_environments", {"project_id": args[0], "environment": args[1]},
             packages_valid=True, packages_reason=None)
    else:
        sys.exit(__doc__)
    print(run_checks())


if __name__ == "__main__":
    main(sys.argv[1:])
