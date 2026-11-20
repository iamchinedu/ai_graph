"""The graph the agent queries, built in the background.

Two things happen with the raw nodes and edges, and they do not wait for each other:
  1. The page draws the map straight from the raw lists (fast).
  2. A background thread builds a NetworkX graph from the same lists, which the agent's tools use.

Why build a graph at all, when the lists already hold everything? Drawing only needs the lists. Questions like
"what breaks if this fails?" need multi-hop reachability (a table feeds a database, which feeds a platform, which
projects use). NetworkX has that built in and indexed (ancestors, descendants, paths), so the agent writes one
short, correct line instead of looping over lists by hand. On a few dozen nodes the build takes milliseconds; on a
large graph it takes seconds, which is why it runs in the background.

The same data gives the same graph: get_store() reuses the finished graph when the raw data did not change, so a page
reload costs nothing, and builds a new one only when the data is different.
"""
import hashlib
import json
import threading

import networkx as nx

_KEEP = 3          # finished graphs kept in memory (the latest few data versions)


def fingerprint(raw):
    return hashlib.sha1(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()


def build_graph(raw):
    """Raw nodes and edges -> a read-only NetworkX MultiDiGraph (one edge per project and environment)."""
    g = nx.MultiDiGraph()
    for n in raw["nodes"]:
        g.add_node(n["node"], **{k: v for k, v in n.items() if k != "node"})
    for e in raw["edges"]:
        if e["source"] in g and e["target"] in g:
            g.add_edge(e["source"], e["target"], **{k: v for k, v in e.items() if k not in ("source", "target")})
    return nx.freeze(g)


class GraphStore:
    """Builds the graph on a background thread. The page never waits for it; the agent's tools do."""

    def __init__(self, raw):
        self.fingerprint = fingerprint(raw)
        self.graph = None
        self.error = None
        self._done = threading.Event()
        threading.Thread(target=self._build, args=(raw,), name="graph-build", daemon=True).start()

    def _build(self, raw):
        try:
            self.graph = build_graph(raw)
        except Exception as exc:  # noqa: BLE001  kept, and shown to whoever asks for the graph
            self.error = exc
        finally:
            self._done.set()

    @property
    def ready(self):
        return self._done.is_set() and self.error is None

    def wait(self, timeout=60):
        """The finished graph. Waits up to `timeout` seconds if it is still building."""
        if not self._done.wait(timeout):
            raise TimeoutError("The graph is still being built. Try again in a few seconds.")
        if self.error:
            raise RuntimeError(f"The graph could not be built: {self.error}")
        return self.graph


_lock = threading.Lock()
_stores = {}       # fingerprint -> GraphStore, oldest first
_latest = None


def get_store(raw):
    """The store for this data: the existing one if the data is unchanged, otherwise a new background build."""
    global _latest
    fp = fingerprint(raw)
    with _lock:
        store = _stores.pop(fp, None) or GraphStore(raw)
        _stores[fp] = store                       # most recent last
        while len(_stores) > _KEEP:
            _stores.pop(next(iter(_stores)))
        _latest = store
        return store


def current_graph(timeout=60):
    """The graph for the latest data (this is what the agent's tools call)."""
    if _latest is None:
        raise RuntimeError("No graph data has been loaded yet.")
    return _latest.wait(timeout)
