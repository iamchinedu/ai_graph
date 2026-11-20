"""What the map shows, computed in plain Python (no Streamlit in here, so it is easy to test).

  build_model(raw)   raw graph JSON -> the real dependencies (tlinks) and the tree that is drawn (vlinks)
  place(...)         fixed x/y positions for the Brain (rings) and Ladder (rows) views
  View(...)          everything for one environment / search / selection: what is bright or dim, the issues,
                     the overview numbers, the sample questions, and scene() for the map component
"""
import math
from collections import defaultdict
from datetime import date, timedelta

# ---- look and feel ---------------------------------------------------------------------------

TYPE_INFO = {  # label, plural, node radius
    "project": ("Project", "Projects", 15),
    "account": ("AWS account", "AWS accounts", 11),
    "packages": ("Packages", "Package checks", 11),
    "model": ("Model", "Models", 14),
    "profile": ("Inference profile", "Inference profiles", 9),
    "tool": ("Observability tool", "Observability tools", 11),
    "platform": ("Data platform", "Data platforms", 13),
    "database": ("Database", "Databases", 11),
    "table": ("Table", "Tables", 8),
}
LAYERS = ["account", "project", "packages", "model", "tool", "platform", "database", "table"]  # ladder rows, top to bottom
FAMILY = {  # one color per family, shared by everything under it
    "project": ("Project", "#b8a6ff"),
    "account": ("AWS account", "#ffc247"),
    "ai": ("AI: model", "#ff9b78"),
    "obs": ("Observability tool", "#6db8ff"),
    "data": ("Data: platform, database, table", "#4de8c4"),
    "packages": ("Package check (per project)", "#d4f25a"),
}
FAMILY_OF = {"model": "ai", "profile": "ai", "tool": "obs", "platform": "data", "database": "data", "table": "data",
             "packages": "packages", "account": "account", "project": "project"}
BAD = "#ff5f6d"
LABEL_ALWAYS = {"project", "model", "platform", "tool", "database", "account"}
ENVS = ["all", "dev", "test", "prod"]
TAU = math.pi * 2
CX, CY = 500, 430
RING = {"account": 70, "project": 210, "packages": 285, "model": 345, "tool": 345, "platform": 345, "database": 415, "table": 475}


# ---- the graph model -------------------------------------------------------------------------

def is_deprecated(n):
    return n["type"] == "model" and n["raw"].get("deprecated") is True


def is_broken(n):
    r, t = n["raw"], n["type"]
    return ((t == "packages" and r.get("valid") is False) or (t == "table" and r.get("table_exists") is False)
            or r.get("status") == "unregistered" or (t == "profile" and bool(r.get("status")) and r["status"] != "active")
            or is_deprecated(n))


def short_label(n):
    if n["type"] == "packages":
        return f"Packages · {n['raw'].get('environment')}"
    if n["type"] == "account":
        return f"AWS {n['label']}"
    if n["type"] == "table":
        return ".".join(n["label"].split(".")[1:]) or n["label"]
    return n["label"]


def link_visible(link, env):
    return env == "all" or not link["envs"] or env in link["envs"]


def add_view_link(vmap, mine, env, parent, child, count, kind):
    link = vmap.setdefault((parent, child), {"s": parent, "t": child, "edges": [], "envs": [], "count": 0,
                                             "fail_envs": set(), "kind": kind, "feeds": set()})
    if env not in link["envs"]:
        link["envs"].append(env)
    link["count"] += count
    if link not in mine:
        mine.append(link)
    return link


def build_model(raw):
    """From the raw graph: the real dependencies (tlinks) and the tree that gets drawn (vlinks).

    The tree is: AWS account -> project -> models, tools, platforms (-> databases -> tables) and the package check.
    """
    nodes = {n["node"]: {"id": n["node"], "type": n["type"], "label": n["label"], "raw": n} for n in raw["nodes"]}
    merged = {}
    for e in raw["edges"]:
        s, t = e["source"], e["target"]
        if s not in nodes or t not in nodes:
            continue
        link = merged.setdefault((s, t), {"s": s, "t": t, "edges": [], "envs": []})
        link["edges"].append(e)
        if e["environment"] and e["environment"] not in link["envs"]:
            link["envs"].append(e["environment"])

    # an inference profile is only the way a project reaches a model, so draw project -> model directly
    model_of = {l["s"]: l["t"] for l in merged.values() if nodes[l["s"]]["type"] == "profile" and nodes[l["t"]]["type"] == "model"}
    collapsed = {}
    for l in merged.values():
        if l["s"] in model_of:
            continue
        link = {"s": l["s"], "t": model_of.get(l["t"], l["t"]), "edges": list(l["edges"]), "envs": list(l["envs"])}
        have = collapsed.get((link["s"], link["t"]))
        if have is None:
            collapsed[(link["s"], link["t"])] = link
        else:
            have["edges"] += link["edges"]
            have["envs"] += [e for e in link["envs"] if e not in have["envs"]]
    tlinks = list(collapsed.values())
    shown = {i: n for i, n in nodes.items() if i not in model_of}
    return shown, tlinks, derive_view(shown, tlinks)


def derive_view(nodes, tlinks):
    out = defaultdict(list)
    for l in tlinks:
        out[l["s"]].append(l)
    fail_nodes = defaultdict(set)
    for l in tlinks:
        for e in l["edges"]:
            if e.get("status") == "fail" and e.get("environment"):
                fail_nodes[e["environment"]].add(l["t"])

    def reach(start, env):
        seen, stack = set(), [start]
        while stack:
            for l in out.get(stack.pop(), []):
                if (not l["envs"] or env in l["envs"]) and l["t"] not in seen:
                    seen.add(l["t"])
                    stack.append(l["t"])
        return seen

    def calls_to(p, target, env):
        return sum((e.get("count") or 0) for l in out.get(p, []) if l["t"] == target for e in l["edges"] if e.get("environment") == env)

    vmap = {}
    for p in [n for n in nodes.values() if n["type"] == "project"]:
        for env in p["raw"].get("environments", {}):
            acct_link = next((l for l in out.get(p["id"], []) if nodes[l["t"]]["type"] == "account" and env in l["envs"]), None)
            if not acct_link:
                continue
            mine = []
            root = add_view_link(vmap, mine, env, acct_link["t"], p["id"], 0, "account_project")
            for i in sorted(reach(p["id"], env)):
                n = nodes.get(i)
                if n is None:
                    continue
                calls = calls_to(p["id"], i, env)
                t = n["type"]
                if t == "packages":
                    add_view_link(vmap, mine, env, p["id"], i, 0, "project_packages"); root["feeds"].add("packages")
                elif t == "model":
                    add_view_link(vmap, mine, env, p["id"], i, calls, "model"); root["feeds"].add("ai")
                elif t == "tool":
                    add_view_link(vmap, mine, env, p["id"], i, calls, "tool"); root["feeds"].add("obs")
                elif t == "platform":
                    add_view_link(vmap, mine, env, p["id"], i, 0, "platform"); root["feeds"].add("data")
                elif t == "database":
                    for l in out.get(i, []):
                        if nodes[l["t"]]["type"] == "platform":
                            add_view_link(vmap, mine, env, l["t"], i, 0, "database")
                elif t == "table":
                    for l in out.get(i, []):
                        if nodes[l["t"]]["type"] == "database":
                            add_view_link(vmap, mine, env, l["t"], i, calls, "table")
            # something failing marks every link on its way inward, up to the account
            kids = defaultdict(list)
            for l in mine:
                kids[l["s"]].append(l)

            def bad(i):
                return is_broken(nodes[i]) or i in fail_nodes[env] or any(bad(c["t"]) for c in kids[i])

            for l in mine:
                if bad(l["t"]):
                    l["fail_envs"].add(env)
    return list(vmap.values())


# ---- layout: fixed positions, so the map stays put when you click things -----------------------

def circ_mean(angles):
    x, y = sum(math.cos(a) for a in angles), sum(math.sin(a) for a in angles)
    return angles[0] if abs(x) < 1e-9 and abs(y) < 1e-9 else math.atan2(y, x)


def spread_circle(desired):
    """Keep each node near its wanted angle but never on top of another one."""
    items = sorted(desired.items(), key=lambda kv: (kv[1] % TAU, kv[0]))
    n = len(items)
    ang = [a % TAU for _, a in items]
    if n > 1:
        gap = TAU / n * 0.7
        for _ in range(100):
            moved = False
            for i in range(n):
                j = (i + 1) % n
                d = (ang[j] - ang[i]) % TAU
                if d < gap:
                    ang[i] -= (gap - d) / 2
                    ang[j] += (gap - d) / 2
                    moved = True
            if not moved:
                break
    return {k: a for (k, _), a in zip(items, ang)}


def spread_line(desired, lo, hi):
    items = sorted(desired.items(), key=lambda kv: (kv[1], kv[0]))
    n = len(items)
    xs = [min(hi, max(lo, x)) for _, x in items]
    if n > 1:
        gap = (hi - lo) / n * 0.75
        for _ in range(100):
            moved = False
            for i in range(n - 1):
                d = xs[i + 1] - xs[i]
                if d < gap:
                    xs[i] -= (gap - d) / 2
                    xs[i + 1] += (gap - d) / 2
                    moved = True
            xs = [min(hi, max(lo, x)) for x in xs]
            if not moved:
                break
    return {k: x for (k, _), x in zip(items, xs)}


def place(nodes, vlinks, mode):
    adj = defaultdict(set)
    for l in vlinks:
        adj[l["s"]].add(l["t"])
        adj[l["t"]].add(l["s"])
    by_type = defaultdict(list)
    for i, n in nodes.items():
        by_type[n["type"]].append(i)
    pos = {}
    if mode == "brain":   # accounts in the middle, projects around them, then what the projects use, then data
        ang = {}
        for types in (["account"], ["project"], ["packages"], ["model", "tool", "platform"], ["database"], ["table"]):
            ids = [i for t in types for i in by_type[t]]
            desired = {}
            for k, i in enumerate(ids):
                near = [ang[j] for j in sorted(adj[i]) if j in ang]
                desired[i] = circ_mean(near) if near else -math.pi / 2 + TAU * k / len(ids)
            ang.update(desired if types == ["account"] else spread_circle(desired))
        for i, a in ang.items():
            r = RING[nodes[i]["type"]]
            pos[i] = (CX + r * math.cos(a), CY + r * math.sin(a))
    else:                 # ladder: one row per kind of thing
        for row, t in enumerate(LAYERS):
            ids = by_type[t]
            desired = {}
            for k, i in enumerate(ids):
                near = [pos[j][0] for j in sorted(adj[i]) if j in pos]
                desired[i] = sum(near) / len(near) if near else 60 + 880 * (k + 0.5) / len(ids)
            for i, x in (desired if t == "account" else spread_line(desired, 60, 940)).items():
                pos[i] = (x, 60 + row * 105)
    return pos


# ---- everything the screen shows, for one environment / search / selection --------------------

def eol_text(d):
    if not d:
        return "End-of-life date not set"
    days = (date.fromisoformat(str(d)[:10]) - date.today()).days
    unit = lambda k: "day" if k == 1 else "days"  # noqa: E731
    return f"Ended on {d} ({-days} {unit(-days)} ago)" if days < 0 else f"End of life {d} (in {days} {unit(days)})"


def fmt(ts):
    return ts.replace("T", " ").replace("Z", " UTC") if ts else "never"


class View:
    def __init__(self, nodes, tlinks, vlinks, env, query, selected):
        self.nodes, self.tlinks, self.vlinks, self.env = nodes, tlinks, vlinks, env
        self.query = query.strip().lower()
        self.selected = selected if selected in nodes else None
        self.act = self._active_set()
        self.impacted = self.walk(self.selected, "up") if self.selected else set()
        self.depends = self.walk(self.selected, "down") if self.selected else set()
        self.focus = self._focus_set()

    # which things exist in the chosen environment, and what a selected node touches
    def _active_set(self):
        if self.env == "all":
            return None
        out = defaultdict(list)
        for l in self.tlinks:
            if link_visible(l, self.env):
                out[l["s"]].append(l["t"])
        seen, stack = set(), [i for i, n in self.nodes.items() if n["type"] == "project" and i in out]
        while stack:
            i = stack.pop()
            if i not in seen:
                seen.add(i)
                stack += out.get(i, [])
        return seen

    def walk(self, start, direction):
        adj = defaultdict(list)
        for l in self.tlinks:
            if link_visible(l, self.env):
                a, b = (l["s"], l["t"]) if direction == "down" else (l["t"], l["s"])
                adj[a].append(b)
        seen, stack = set(), [start]
        while stack:
            for nxt in adj.get(stack.pop(), []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    def _focus_set(self):
        sel = self.selected
        if not sel:
            return None
        s = {sel} | self.impacted | self.depends
        if self.nodes[sel]["type"] == "account":   # the whole world of this account
            for l in self.vlinks:
                if l["s"] != sel:
                    continue
                envs, stack = set(l["envs"]), [l["t"]]
                s.add(l["t"])
                while stack:
                    cur = stack.pop()
                    for v in self.vlinks:
                        if v["s"] == cur and envs & set(v["envs"]) and v["t"] not in s:
                            s.add(v["t"])
                            stack.append(v["t"])
            return s
        for l in self.tlinks:
            if self.nodes[l["t"]]["type"] == "account" and l["s"] in s and link_visible(l, self.env):
                s.add(l["t"])
        return s

    # how bright things are drawn
    def node_opacity(self, n):
        if self.act is not None and n["id"] not in self.act:
            return 0.08
        if self.query and self.query not in n["label"].lower():
            return 0.12
        return 0.1 if self.focus is not None and n["id"] not in self.focus else 1.0

    def link_opacity(self, l):
        if not link_visible(l, self.env) or (self.act is not None and not (l["s"] in self.act and l["t"] in self.act)):
            return 0.03
        if self.focus is not None:
            return 1.0 if l["s"] in self.focus and l["t"] in self.focus else 0.04
        return 0.6

    def edge_status(self, l):
        rel = [e for e in l["edges"] if self.env == "all" or not e["environment"] or e["environment"] == self.env]
        if any(e.get("status") == "fail" for e in rel):
            return "fail"
        return "pass" if any(e.get("status") == "pass" for e in rel) else None

    def is_failing(self, l):
        return bool(l["fail_envs"]) if self.env == "all" else self.env in l["fail_envs"]

    def failing(self):
        return sum(1 for l in self.tlinks if self.edge_status(l) == "fail" and link_visible(l, self.env))

    def color(self, i):
        return FAMILY[FAMILY_OF[self.nodes[i]["type"]]][1]

    # side panel content
    def env_runs(self, n):
        return [{"env": k, "runs": v.get("run_count"), "last": v.get("last_init_at"), "pkgs": v.get("packages_valid"), "reason": v.get("packages_reason")}
                for k, v in (n["raw"].get("environments") or {}).items()]

    def impacted_projects(self):
        return [self.nodes[i] for i in sorted(self.impacted) if self.nodes[i]["type"] == "project"]

    def impacted_rows(self):
        rows = []
        for p in self.impacted_projects():
            envs, status = set(), None
            for l in self.tlinks:
                if l["s"] != p["id"]:
                    continue
                for e in l["edges"]:
                    if e["environment"] and self.env in ("all", e["environment"]):
                        envs.add(e["environment"])
                        status = "fail" if e.get("status") == "fail" else (status or e.get("status"))
            rows.append({"project": p, "envs": sorted(envs), "status": status})
        return rows

    def depends_by_type(self):
        return [(t, [self.nodes[i] for i in sorted(self.depends) if self.nodes[i]["type"] == t]) for t in LAYERS
                if any(self.nodes[i]["type"] == t for i in self.depends)]

    def issues_of(self, n):
        if n["type"] != "project":
            return []
        out = []
        for r in self.env_runs(n):
            if r["pkgs"] is False and self.env in ("all", r["env"]):
                out.append({"title": f"Package dependency conflict ({r['env']})", "detail": r["reason"] or "A package requirement is not met.",
                            "id": f"packages:{n['raw']['id']}:{r['env']}"})
        for l in self.tlinks:
            t = self.nodes[l["t"]]
            if l["s"] != n["id"] or t["type"] == "packages":
                continue
            bad = [e for e in l["edges"] if e.get("status") == "fail" and self.env in ("all", e["environment"])]
            if not bad and not (is_deprecated(t) and link_visible(l, self.env)):
                continue
            envs = ", ".join(sorted({e["environment"] for e in (bad or l["edges"]) if self.env in ("all", e["environment"])}))
            if t["type"] == "model":
                out.append({"title": f"Model deprecated: {t['label']}", "detail": f"{eol_text(t['raw'].get('end_of_life_date'))}. Used in {envs or 'this project'}.", "id": t["id"]})
            else:
                out.append({"title": f"{TYPE_INFO[t['type']][0]} failing: {t['label']}", "detail": (bad[0].get("status_reason") if bad else None) or "The last check failed.", "id": t["id"]})
        return out

    def pill_label(self, d):
        r = d["raw"]
        if is_deprecated(d):
            return f"{d['label']} · ends {r.get('end_of_life_date') or 'unknown'}"
        if d["type"] == "packages":
            return f"{short_label(d)} · {'invalid' if r.get('valid') is False else 'valid' if r.get('valid') is True else 'not checked'}"
        if d["type"] == "table" and r.get("table_exists") is False:
            return f"{short_label(d)} · missing"
        return short_label(d)

    def overview(self):
        env, ns = self.env, self.nodes
        in_env = lambda e: env == "all" or not e or e == env  # noqa: E731
        projects = [n for n in ns.values() if n["type"] == "project" and (self.act is None or n["id"] in self.act)]
        dependencies = sum(1 for l in self.vlinks if link_visible(l, env) and (self.act is None or (l["s"] in self.act and l["t"] in self.act)))
        by_pkg, by_model, by_other = set(), set(), set()
        for n in ns.values():
            if n["type"] == "packages" and n["raw"].get("valid") is False and in_env(n["raw"].get("environment")):
                owner = str(n["raw"]["id"]).split(":")[0]
                by_pkg |= {p["id"] for p in projects if p["raw"]["id"] == owner}
        for l in self.tlinks:
            t = ns[l["t"]]
            if any(e.get("status") == "fail" and in_env(e["environment"]) for e in l["edges"]):
                (by_model if t["type"] == "model" else by_pkg if t["type"] == "packages" else by_other).add(l["s"])
            if t["type"] == "model" and t["raw"].get("deprecated") and link_visible(l, env):
                by_model.add(l["s"])
        pick = lambda ids: [p for p in projects if p["id"] in ids]  # noqa: E731
        horizon, today = date.today() + timedelta(days=92), date.today()
        soon = []
        for m in ns.values():
            eol = m["raw"].get("end_of_life_date")
            if m["type"] == "model" and m["raw"].get("deprecated") and eol and date.fromisoformat(str(eol)[:10]) <= horizon:
                users = {l["s"] for l in self.tlinks if l["t"] == m["id"] and link_visible(l, env)}
                soon.append({"model": m, "ends": str(eol)[:10], "over": date.fromisoformat(str(eol)[:10]) < today, "projects": len(users)})
        soon.sort(key=lambda s: s["ends"])
        return {"projects": len(projects), "dependencies": dependencies, "risk_pkg": pick(by_pkg), "risk_model": pick(by_model),
                "risk_other": pick(by_other), "at_risk": len(by_pkg | by_model | by_other), "soon": soon}

    def suggestions(self):
        n = self.nodes.get(self.selected) if self.selected else None
        if n and n["type"] == "project":
            return [f"What does {n['label']} depend on?", "Which projects are at risk?", "What breaks if Claude 3 Sonnet is deprecated?"]
        if n:
            return [f"What breaks if {n['label']} fails?", "Which projects are at risk?", "How many projects depend on HoneyHive?"]
        return ["What breaks if Claude 3 Sonnet is deprecated?", "How many projects depend on HoneyHive?", "Which projects are at risk?", "What does HR policy bot depend on?"]

    def brief(self, n=None):
        """One line for the collapsed summary."""
        if n is None:
            o = self.overview()
            return f"{o['projects']} projects · {o['dependencies']} dependencies · {o['at_risk']} at risk"
        if n["type"] == "project":
            issues = len(self.issues_of(n))
            runs = sum(r["runs"] or 0 for r in self.env_runs(n))
            return f"{runs} runs · {f'{issues} issue' + ('' if issues == 1 else 's') if issues else 'no issues'}"
        p = len(self.impacted_projects())
        return f"{p} project{'s' if p != 1 else ''} depend{'s' if p == 1 else ''} on this"

    # what the map component draws: positions, colors and brightness, decided here and only painted there
    def scene(self, pos, fit_key, height):
        nodes = []
        for i, n in self.nodes.items():
            o = self.node_opacity(n)
            nodes.append({
                "id": i, "x": pos[i][0], "y": pos[i][1], "r": TYPE_INFO[n["type"]][2], "color": self.color(i), "opacity": o,
                "label": short_label(n), "big": n["type"] in ("project", "model", "account"),
                "always": n["type"] in LABEL_ALWAYS or i == self.selected or (self.selected is not None and o > 0.9),
                "broken": is_broken(n), "selected": i == self.selected,
            })
        links = []
        for l in self.vlinks:
            bad = self.is_failing(l)
            feeds = [FAMILY[f][1] for f in sorted(l["feeds"])] if l["kind"] == "account_project" else []
            links.append({"s": l["s"], "t": l["t"], "color": BAD if bad else self.color(l["t"]), "opacity": self.link_opacity(l),
                          "bad": bad, "count": l["count"], "feeds": feeds})
        legend = [{"label": label, "color": color} for label, color in FAMILY.values()] + [{"label": "Failing", "color": BAD}]
        return {"fit_key": fit_key, "height": height, "nodes": nodes, "links": links, "legend": legend}
