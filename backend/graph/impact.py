"""Questions the graph answers: what does a node depend on, and what breaks if it goes away."""
from backend.graph.build import load_graph


def resolve(G, text):
    """Find nodes by exact node ID ('model:...'), or by label / ID / '<type>:<label>' (case-insensitive)."""
    if text in G:
        return [text]
    t = text.lower()
    typ, _, rest = t.partition(":")
    out = []
    for n, d in G.nodes(data=True):
        label, ident = str(d.get("label", "")).lower(), str(d.get("id", "")).lower()
        if t in (label, ident) or (rest and d["type"] == typ and rest in (label, ident)):
            out.append(n)
    if not out:  # fall back to substring match on the label
        out = [n for n, d in G.nodes(data=True) if t in str(d.get("label", "")).lower()]
    return out


def impact(node, environment=None):
    """Projects that depend (directly or through other nodes) on `node`: one row per project and environment."""
    import networkx as nx
    G = load_graph(environment)
    result = []
    for target in resolve(G, node):
        for anc in nx.ancestors(G, target):
            if G.nodes[anc]["type"] != "project":
                continue
            for _, head, edge in G.out_edges(anc, data=True):
                if head != target and not nx.has_path(G, head, target):
                    continue
                path = [anc] + nx.shortest_path(G, head, target)
                result.append({
                    "target": target, "project": G.nodes[anc]["id"], "project_name": G.nodes[anc]["label"],
                    "department": G.nodes[anc]["department"], "environment": edge["environment"],
                    "via": " -> ".join(G.nodes[x]["label"] for x in path),
                    "edge_status": edge["status"], "count": edge["count"], "last_seen": edge["last_seen"],
                })
    return sorted(result, key=lambda r: (r["target"], r["environment"] or "", r["project"]))


def dependencies(node, environment=None):
    """Everything `node` depends on, grouped by node type."""
    import networkx as nx
    G = load_graph(environment)
    out = {}
    for n in resolve(G, node):
        deps = {}
        for d in nx.descendants(G, n):
            deps.setdefault(G.nodes[d]["type"], []).append(G.nodes[d]["label"])
        out[n] = {k: sorted(v) for k, v in deps.items()}
    return out
