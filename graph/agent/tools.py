"""The orchestrator's tools.

  load_skill(name)        returns the instructions of one skill (agent/skills.py)
  run_graph_query(code)   runs a short Python snippet against the NetworkX graph and returns `result`

The snippet is written by the model, so it runs behind guardrails: no imports, no files, no names starting with "_",
no `while` loops, a time limit, and a throwaway copy of the graph. These are sensible limits for a local app, not a
hardened sandbox. Do not point this at a graph or a machine you would not let the model touch.
"""
import ast
import builtins
import json
import threading

import networkx as nx
from strands import tool

from agent.skills import SKILLS, skill_names
from network.build import current_graph

MAX_CHARS = 6000
TIMEOUT_SECONDS = 10

_BUILTINS = {name: getattr(builtins, name) for name in (
    "abs all any bool dict enumerate filter float int isinstance len list map max min range reversed round set sorted "
    "str sum tuple zip Exception KeyError ValueError IndexError TypeError").split()}
_NX_BLOCKED = ("read", "write", "nx_", "utils", "config", "draw")     # NetworkX parts that touch files or plotting


def check_code(code):
    """Parse the snippet and refuse anything outside the guardrails. Returns the parsed tree."""
    tree = ast.parse(code, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("imports are not allowed; G, nx and the helpers are already available")
        if isinstance(node, ast.While):
            raise ValueError("while loops are not allowed; use a for loop")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError(f"the name {node.id!r} is not allowed")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ValueError(f"the attribute {node.attr!r} is not allowed")
            if isinstance(node.value, ast.Name) and node.value.id == "nx" and node.attr.startswith(_NX_BLOCKED):
                raise ValueError(f"nx.{node.attr} is not allowed")
    return tree


def make_helpers(G):
    """Short functions the snippet can call, so common questions take one line."""

    def label(n):
        return G.nodes[n].get("label", n)

    def find(text):
        t = str(text).lower()
        return sorted(n for n, d in G.nodes(data=True) if t in str(d.get("label", "")).lower())

    def in_env(env=None):
        if not env:
            return G
        return nx.subgraph_view(G, filter_edge=lambda u, v, k: G.edges[u, v, k].get("environment") in (None, env))

    def _ids(node):
        ids = [node] if isinstance(node, str) else list(node)
        for n in ids:
            if n not in G:
                raise ValueError(f"unknown node id {n!r}; get ids from find()")
        return ids

    def impacted(node, env=None):
        H, out = in_env(env), set()
        for n in _ids(node):
            out |= {m for m in nx.ancestors(H, n) if G.nodes[m]["type"] == "project"}
        return sorted(label(m) for m in out)

    def depends_on(node, env=None):
        H, out = in_env(env), set()
        for n in _ids(node):
            out |= nx.descendants(H, n)
        return sorted(({"label": label(m), "type": G.nodes[m]["type"]} for m in out), key=lambda x: (x["type"], x["label"]))

    return {"label": label, "find": find, "in_env": in_env, "impacted": impacted, "depends_on": depends_on}


def to_text(value):
    def default(o):
        if isinstance(o, (set, frozenset)):
            try:
                return sorted(o)
            except TypeError:
                return list(o)
        try:
            return list(o)
        except TypeError:
            return str(o)

    text = json.dumps(value, default=default, ensure_ascii=False)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + f"... [cut: {len(text)} characters in all; ask for less]"


def run_query(code, graph):
    """Run a snippet against a copy of `graph` and return `result` as text, or a short 'query error: ...' message."""
    try:
        tree = check_code(code)
    except (SyntaxError, ValueError) as exc:
        return f"query error: {exc}"
    G = graph.copy()
    ns = {"__builtins__": dict(_BUILTINS), "G": G, "nx": nx, **make_helpers(G)}
    outcome = {}

    def work():
        try:
            exec(compile(tree, "<query>", "exec"), ns)  # noqa: S102  guarded above
        except Exception as exc:  # noqa: BLE001  returned to the model so it can fix the code
            outcome["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(TIMEOUT_SECONDS)
    if thread.is_alive():
        return f"query error: it ran longer than {TIMEOUT_SECONDS} seconds; make it cheaper"
    if "error" in outcome:
        return f"query error: {outcome['error']}"
    if "result" not in ns:
        return "query error: set a variable named `result` with the answer"
    return to_text(ns["result"])


@tool
def load_skill(name: str) -> str:
    """Return the instructions of one skill. Load a skill before you rely on it, and only once per conversation.

    Args:
        name: The skill name, exactly as listed in your instructions.
    """
    if name in SKILLS:
        return SKILLS[name]["text"]
    return f"Unknown skill {name!r}. Available: {', '.join(skill_names())}"


@tool
def run_graph_query(code: str) -> str:
    """Run a short, read-only Python snippet against the dependency graph and return the value of `result`.

    The snippet can use G (the graph), nx (NetworkX) and the helpers find, label, in_env, impacted and depends_on.
    It must assign its answer to a variable named `result`. Read the writing-queries skill first.

    Args:
        code: The Python snippet. No imports, no while loops, no names starting with an underscore.
    """
    try:
        graph = current_graph(timeout=30)
    except Exception as exc:  # noqa: BLE001
        return f"query error: {exc}"
    return run_query(code, graph)


TOOLS = [load_skill, run_graph_query]
