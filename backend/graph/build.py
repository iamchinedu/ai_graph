"""Build a NetworkX graph from the tables.

Edge direction = "depends on": X -> Y means X depends on Y.
    project -> account            (the AWS account it runs in, per environment)
    project -> packages           (one node per project and environment: valid, invalid or unchecked)
    project -> profile -> model
    project -> table -> database -> platform
    project -> tool
So everything that would be hit when node N breaks is ancestors(N); the projects among
them are the impacted projects.

Node IDs are "<type>:<key>": project:prj_FIN_7f3a2c, model:<id>, profile:<id>, account:<id>,
packages:<project_id>:<env>, platform:<name>, database:<id>, table:<id>, tool:<name>.
Parallel edges (one per environment) are allowed, so this is a MultiDiGraph. Project edges carry the environment; build_graph("prod") keeps only that environment.
"""
import json
import os

import networkx as nx

from backend import paths
from depmap_sdk import paths as data_paths
from depmap_sdk import store
from depmap_sdk.schema import ENVIRONMENTS, TABLES


def _short(profile_id):
    return profile_id.rsplit("/", 1)[-1] if profile_id.startswith("arn:") else profile_id


def build_graph(environment=None):
    G = nx.MultiDiGraph()
    departments = {d["id"]: d for d in store.read("departments")}
    platforms = {p["id"]: p for p in store.read("data_platforms")}
    databases = {d["id"]: d for d in store.read("databases")}
    tables = {t["id"]: t for t in store.read("db_tables")}
    tools = {t["id"]: t for t in store.read("observability_tools")}
    profiles = {p["id"]: p for p in store.read("inference_profiles")}
    models = {m["id"]: m for m in store.read("models")}

    def keep(env):
        return environment is None or env == environment

    for p in store.read("projects"):
        G.add_node(f'project:{p["id"]}', type="project", label=p["name"], id=p["id"],
                   department=departments.get(p["department_id"], {}).get("name"))
    for pe in store.read("project_environments"):
        node = f'project:{pe["project_id"]}'
        if node in G and keep(pe["environment"]):
            G.nodes[node].setdefault("environments", {})[pe["environment"]] = {
                "account_id": pe["account_id"], "packages_valid": pe["packages_valid"],
                "packages_reason": pe["packages_reason"],
                "run_count": pe.get("run_count"), "last_init_at": pe.get("last_init_at")}
            env = pe["environment"]
            if pe["account_id"]:
                an = f'account:{pe["account_id"]}'
                G.add_node(an, type="account", label=pe["account_id"], id=pe["account_id"])
                G.add_edge(node, an, key=env, kind="project_account", environment=env, count=None,
                           last_seen=pe.get("last_init_at"), status=None, status_reason=None)
            valid = pe["packages_valid"]
            status = "pass" if valid is True else "fail" if valid is False else None
            pk = f'packages:{pe["project_id"]}:{env}'
            G.add_node(pk, type="packages", label="Packages", id=f'{pe["project_id"]}:{env}', environment=env,
                       valid=valid, reason=pe["packages_reason"], checked_at=pe["packages_checked_at"],
                       python_version=pe["python_version"], package_count=len(pe["packages"] or []))
            G.add_edge(node, pk, key=env, kind="project_packages", environment=env, count=None,
                       last_seen=pe["packages_checked_at"], status=status, status_reason=pe["packages_reason"])

    def add_structural(src, dst):
        G.add_edge(src, dst, key="structural", kind="structural", environment=None)

    for e in store.read("project_profile_edges"):
        if not keep(e["environment"]):
            continue
        prof = profiles.get(e["profile_id"])
        pn = f'profile:{e["profile_id"]}'
        G.add_node(pn, type="profile", label=_short(e["profile_id"]), id=e["profile_id"],
                   profile_type=prof["type"] if prof else None, status=prof["status"] if prof else "unregistered")
        G.add_edge(f'project:{e["project_id"]}', pn, key=e["environment"], kind="project_profile", **{
            k: e[k] for k in ("environment", "count", "last_seen", "status", "status_reason")})
        if prof:
            mn = f'model:{prof["model_id"]}'
            m = models.get(prof["model_id"], {})
            G.add_node(mn, type="model", label=m.get("name", prof["model_id"]), id=prof["model_id"],
                       deprecated=m.get("deprecated"), end_of_life_date=m.get("end_of_life_date"))
            add_structural(pn, mn)

    for e in store.read("project_table_edges"):
        if not keep(e["environment"]):
            continue
        t = tables.get(e["table_id"])
        tn = f'table:{e["table_id"]}'
        if t is None:  # table removed from the registry: keep the edge visible, as a failing dependency
            G.add_node(tn, type="table", label=f'unknown table #{e["table_id"]} (removed)', id=e["table_id"],
                       environment=e["environment"])
        else:
            db = databases[t["database_id"]]
            plat = platforms[db["platform_id"]]
            dn, pn = f'database:{db["id"]}', f'platform:{plat["name"]}'
            G.add_node(tn, type="table", label=f'{db["name"]}.{t["table_name"]}', id=t["id"],
                       table_exists=t["table_exists"], environment=db["environment"])
            G.add_node(dn, type="database", label=db["name"], id=db["id"], environment=db["environment"])
            G.add_node(pn, type="platform", label=plat["name"], id=plat["id"])
            add_structural(tn, dn)
            add_structural(dn, pn)
        G.add_edge(f'project:{e["project_id"]}', tn, key=e["environment"], kind="project_table", **{
            k: e[k] for k in ("environment", "count", "last_seen", "status", "status_reason")})

    for e in store.read("project_observability_edges"):
        if not keep(e["environment"]):
            continue
        tool = tools[e["tool_id"]]
        tn = f'tool:{tool["name"]}'
        G.add_node(tn, type="tool", label=tool["name"], id=tool["id"])
        G.add_edge(f'project:{e["project_id"]}', tn, key=e["environment"], kind="project_tool", **{
            k: e[k] for k in ("environment", "count", "last_seen")}, status=None, status_reason=None)

    if environment is not None:  # drop projects with no presence in this environment
        for n in [n for n, d in G.nodes(data=True) if d["type"] == "project" and not d.get("environments")]:
            G.remove_node(n)
    return G


# ---- saved snapshots: what `python -m backend.graph build` writes and the agent reads ----------
# One file per view: graph_all.json plus graph_dev / graph_test / graph_prod.json.

def snapshot_path(environment=None):
    return paths.GRAPH_DIR / f"graph_{environment or 'all'}.json"


def build_and_save():
    """Build the graph from the tables for every view and save each as a JSON snapshot.
    Returns {view: (nodes, edges)}."""
    paths.GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}
    for env in (None, *ENVIRONMENTS):
        G = build_graph(env)
        tmp = snapshot_path(env).with_suffix(".tmp")
        tmp.write_text(json.dumps(nx.node_link_data(G, name="node", key="edge_key", edges="edges"), indent=1))
        os.replace(tmp, snapshot_path(env))
        summary[env or "all"] = (G.number_of_nodes(), G.number_of_edges())
    return summary


def _is_stale(environment):
    """True when the snapshot is missing or any table file changed after it was built."""
    snap = snapshot_path(environment)
    if not snap.exists():
        return True
    built = snap.stat().st_mtime_ns
    files = (data_paths.DATA_DIR / t / f"{t}.json" for t in TABLES)
    return any(f.exists() and f.stat().st_mtime_ns > built for f in files)


def load_graph(environment=None):
    """The graph the agent queries: the saved snapshot, rebuilt first if it is missing or out of date."""
    if _is_stale(environment):
        build_and_save()
    data = json.loads(snapshot_path(environment).read_text())
    return nx.node_link_graph(data, name="node", key="edge_key", edges="edges", multigraph=True, directed=True)
