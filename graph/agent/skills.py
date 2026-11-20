"""Skills: instructions the agent reads (with the load_skill tool) before it writes a graph query.

Each skill is plain text. Keeping them here, not in the system prompt, means the prompt stays short and the agent
only pays for the skills a question needs. Add a skill by adding an entry to SKILLS.
"""

SKILLS = {}

SKILLS["graph-schema"] = {
    "summary": "What every node type, edge kind and attribute means, and which way edges point. Read this first.",
    "text": """\
<graph_schema>
The graph is a NetworkX MultiDiGraph named G. Every edge reads "source DEPENDS ON target".
So the things a node needs are its descendants, and the things that break when it fails are its ancestors.

<node_types>
Every node has `type` and `label`. G's node ids look like "<type>:<key>", e.g. "project:prj_HR_c04e1a".
- project: an AI project. `label` is its name, `id` its project id, `department`, and `environments`, a dict
  {env: {account_id, packages_valid, packages_reason, run_count, last_init_at}} (run_count = how many times it started).
- account: an AWS workload account. `label` is the 12-digit account id.
- packages: the package check of one project in one environment. `environment`, `valid` (True / False / None = never
  checked), `reason` (why it failed), `checked_at`, `python_version`, `package_count`.
- profile: a Bedrock inference profile a project calls. `label`, `profile_type`, `status` ("active" or not).
- model: a foundation model. `label`, `deprecated` (True / False), `end_of_life_date` ("YYYY-MM-DD" or None).
- tool: an observability tool (e.g. HoneyHive, Splunk).
- platform: a data platform (e.g. Snowflake, Databricks, AWS S3).
- database: a database on a platform. `label`, `environment`.
- table: a table in a database. `label` is "<database>.<table>", `environment`, `table_exists` (False = dropped).
</node_types>

<edge_kinds>
Every edge has `kind` and `environment` ("dev", "test", "prod", or None for structural links).
A project that runs in two environments has one edge per environment to the same target.
- project_account: project -> account (where it runs). `last_seen`.
- project_packages: project -> packages. `status` ("pass" / "fail"), `status_reason`, `last_seen`.
- project_profile: project -> profile (model calls). `count` = attempted calls, `last_seen`, `status`, `status_reason`.
- project_table: project -> table. `count` = queries that touched the table, `last_seen`, `status`, `status_reason`.
- project_tool: project -> tool. `count` = starts, `last_seen`.
- structural: profile -> model, table -> database, database -> platform. No environment.
</edge_kinds>

<rules>
- `status` == "fail" means the last check failed. It is the only "failing" signal on edges.
- A project is AT RISK when any of these holds: an edge from it has status "fail", its packages node has valid == False,
  it reaches a model with deprecated == True, or it reaches a table with table_exists == False.
- Projects reach models only through profiles (project -> profile -> model), and tables only through databases.
- The graph does NOT contain: people or owners, PII or sensitivity labels, costs, contract dates, usage history before
  the last check, or vendor groupings. Say so instead of guessing.
</rules>
</graph_schema>
""",
}

SKILLS["writing-queries"] = {
    "summary": "How to write and run a graph query with run_graph_query: the helper functions, NetworkX patterns, examples.",
    "text": """\
<writing_queries>
You query the graph by writing a short Python snippet and running it with run_graph_query(code).
The snippet runs read-only. Put the answer in a variable named `result`. Keep it small: names, counts, short lists.

<available>
- G: the graph (copy of it; changing it has no effect on later queries).
- nx: NetworkX (ancestors, descendants, has_path, shortest_path, descendants_at_distance, ...).
- Python basics: len, sorted, sum, min, max, any, all, set, list, dict, str, int, float, enumerate, zip, range, round,
  isinstance, filter, map, tuple, reversed, abs, bool. No imports, no files, no network, no names starting with "_".
- Helpers (already defined):
  find(text)                  node ids whose label contains `text` (case-insensitive). ALWAYS use this to resolve a name.
  label(node)                 the label of a node id.
  in_env(env)                 a view of G with only the edges of that environment (plus structural edges). env = None -> G.
  impacted(node, env=None)    sorted labels of the PROJECTS that break if `node` fails (ancestors that are projects).
  depends_on(node, env=None)  [{"label", "type"}] everything `node` needs, directly or indirectly.
</available>

<patterns>
# count nodes by type
counts = {}
for n, d in G.nodes(data=True):
    counts[d["type"]] = counts.get(d["type"], 0) + 1
result = counts

# which projects use the model "Claude 3 Sonnet", per environment
ids = find("claude 3 sonnet")
result = {env: impacted(ids[0], env) for env in ("dev", "test", "prod")} if ids else "no model with that name"

# edges that are failing right now
result = [(label(u), label(v), d["environment"], d["status_reason"])
          for u, v, d in G.edges(data=True) if d.get("status") == "fail"]

# what a project depends on in prod
p = find("HR policy bot")[0]
result = depends_on(p, "prod")

# deprecated models and the projects that use them
result = {label(n): impacted(n) for n, d in G.nodes(data=True) if d["type"] == "model" and d.get("deprecated")}
</patterns>

<tips>
- Unknown name: find() returns [] -> answer "not found in the map" and say which names exist if useful
  (e.g. sorted(label(n) for n, d in G.nodes(data=True) if d["type"] == "tool")).
- G.in_edges(n, data=True) / G.out_edges(n, data=True) give (source, target, attributes).
- Several nodes can match find(); if the question is ambiguous, check all matches and say which you used.
- If the query errors, read the message, fix the code and run again (at most two fixes).
</tips>
</writing_queries>
""",
}

SKILLS["impact-analysis"] = {
    "summary": "Recipe for what-if questions: what breaks, who is affected, what is at risk, by environment.",
    "text": """\
<impact_analysis>
For "what breaks if X goes away / is deprecated / fails", follow this recipe.

<steps>
1. Resolve X with find(). If it matches nothing, say so. If it matches several, handle each one.
2. Ask for the environment. If the user did not say which, run it for all environments and also split by environment:
   for env in ("dev", "test", "prod"): impacted(node, env)
3. impacted(node, env) gives the projects. For the "why", list the direct links from projects:
   [(label(u), d["environment"], d.get("count")) for u, v, d in G.in_edges(node, data=True)]
   For things reached through a profile or database, the direct links are on those intermediate nodes.
4. Mention severity signals when present: models that are deprecated (end_of_life_date), failing edges, invalid packages.
5. Report: headline number of projects, the project names, the environments, then what to do next if obvious.
</steps>

<example>
Question: "If we end the HoneyHive contract, which projects are affected?"
code:
  t = find("honeyhive")
  result = {label(n): {env: impacted(n, env) for env in ("dev", "test", "prod")} for n in t}
</example>

<example>
Question: "Which projects are at risk?"
code:
  risky = set()
  for u, v, d in G.edges(data=True):
      if d.get("status") == "fail":
          risky.add(label(u))
  for n, d in G.nodes(data=True):
      if d["type"] == "packages" and d.get("valid") is False:
          risky |= set(impacted(n))
      if d["type"] == "model" and d.get("deprecated"):
          risky |= set(impacted(n))
      if d["type"] == "table" and d.get("table_exists") is False:
          risky |= set(impacted(n))
  result = sorted(risky)
</example>
</impact_analysis>
""",
}


def skill_index():
    """One line per skill, for the system prompt."""
    return "\n".join(f"- {name}: {s['summary']}" for name, s in SKILLS.items())


def skill_names():
    return list(SKILLS)
