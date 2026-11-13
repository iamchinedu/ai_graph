"""python -m backend.graph build                          build the graph from the tables and save it for the agent
   python -m backend.graph impact <node> [--env prod]   projects affected if <node> breaks
   python -m backend.graph deps   <node> [--env prod]   what <node> depends on
   python -m backend.graph summary [--env prod]          counts of nodes and edges

<node> is a node ID (model:<id>) or a name (Snowflake, HoneyHive, "Claude 3 Sonnet", invoices).
"""
import argparse
import json

from backend.graph import build_and_save, load_graph
from backend.graph.impact import dependencies, impact

ap = argparse.ArgumentParser()
ap.add_argument("command", choices=["build", "impact", "deps", "summary"])
ap.add_argument("node", nargs="?")
ap.add_argument("--env", choices=["dev", "test", "prod"])
ap.add_argument("--json", action="store_true")
a = ap.parse_args()

if a.command == "build":
    from backend.graph.build import snapshot_path
    for view, (nodes, edges) in build_and_save().items():
        print(f"{view:>5}: {nodes:>3} nodes, {edges:>3} edges  ->  {snapshot_path(None if view == 'all' else view)}")
elif a.command == "summary":
    G = load_graph(a.env)
    kinds = {}
    for _, d in G.nodes(data=True):
        kinds[d["type"]] = kinds.get(d["type"], 0) + 1
    print({"environment": a.env or "all", "nodes": kinds, "edges": G.number_of_edges()})
elif not a.node:
    ap.error("node is required")
elif a.command == "impact":
    rows = impact(a.node, a.env)
    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{len({r['project'] for r in rows})} project(s), {len(rows)} project-environment link(s) affected"
              if rows else "no projects affected")
        for r in rows:
            print(f"  {r['project']}  {r['project_name']}  [{r['environment']}]  via {r['via']}  "
                  f"(edge {r['edge_status']}, count {r['count']})")
else:
    print(json.dumps(dependencies(a.node, a.env), indent=2))
