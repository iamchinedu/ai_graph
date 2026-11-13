# ai_graph — AI dependency map (backend MVP)

Tracks which AI projects depend on which models, data tables, data platforms and observability
tools, per environment (dev / test / prod), so a chat agent can answer "what breaks if...?" questions.
Everything runs locally; data lives in `data/` as JSON, one folder per table.

## Quick start

```bash
source .venv/bin/activate            # already created; or: python3 -m venv .venv && pip install -e . --config-settings editable_mode=compat
python -m backend.seed               # wipe data/, load reference data + 5 sample projects
python -m backend.graph build          # build the graph snapshots the agent queries (graph/)
python -m backend.seed.demo_activity   # log runs for the 5 sample projects without AWS (fills data/ and builds the graph)
python -m sample_projects.run_all    # run the 5 sample projects (needs AWS credentials + Bedrock access)
python -m backend.graph impact "Claude 3 Sonnet"
python -m pytest -q tests
```

Look at `data/` in VS Code after `run_all` to see the edge tables fill up.

## Layout

| Path | What it is |
| --- | --- |
| `data/<table>/<table>.json` | The tables (nodes and edges). Schema is defined in `depmap_sdk/schema.py`. |
| `depmap_sdk/` | The package a project imports. The `DepMap` class (`depmap.py`) is the one object projects use; it delegates to `identity`, `registry`, `packages`, `recorder` and `store` (files under `data/`). Self-contained: it never imports `backend/`. |
| `backend/` | `store/` file store, `ingest.py` event handler, `checks/` edge status and package check, `graph/` NetworkX graph + impact, `query/` read-only DuckDB runner, `agent/` orchestrator, query writer and model settings (Gemini or OpenAI), `seed/` example data and break simulators. |
| `skills/` | What the agent loads: a router (`README.md`) and sub-skills for schema, relationships, single-node dependencies, impact analysis. |
| `frontend/` | Angular app: the dependency map screen. `cd frontend && npm install && npm start`, then open http://localhost:4210. It reads `graph/graph_all.json`. |
| `sample_projects/` | Five sample projects that use the SDK. |
| `scratch/` | Agent session folders (the SQL files it wrote and ran). Git-ignored. |

## Using the SDK in a project

```python
import depmap_sdk as depmap

depmap.init(project_id="prj_FIN_7f3a2c", environment="prod", account_id="222222222222",
            databases=[{"platform": "Snowflake", "database": "finance_db", "tables": ["invoices", "vendors"]}],
            observability_tools="HoneyHive")
model = depmap.log_model(BedrockModel(model_id=depmap.get_model("claude_sonnet_4_6")))   # any LLM: +1 on the profile edge, last_seen = now
conn = depmap.log_connection(conn, "Snowflake", "finance_db", ["invoices", "vendors"])   # one database, one or more tables (any platform)
```

What gets recorded
- `init`: the project+environment row, installed packages and the package check, declared tables (edge created, count 0), observability tools (count = number of starts).
- Bedrock wrapper: count and last-seen per inference profile (the `modelId` actually passed). Counts attempted calls.
- Connection wrapper: a declared table counts when its name appears in an executed statement. No SQL parsing, no columns.
- The SDK never raises into the host app and sends events from a background thread every second and at exit.
- Platforms and observability tools must come from the preselected lists (`data_platforms`, `observability_tools`); unknown ones are rejected with a warning. Unknown databases and tables are registered on first sight.

## Simulate things breaking

```bash
python -m backend.seed.simulate_break deprecate-model amazon.nova-pro-v1:0
python -m backend.seed.simulate_break drop-table finance_db invoices prod
python -m backend.seed.simulate_break invalidate-packages prj_FIN_7f3a2c prod "boto3 needs botocore<1.41"
python -m backend.seed.simulate_break --help    # restore-* counterparts
python -m backend.graph impact invoices --env prod
```

## Streamlit app

`streamlit_app/app.py` runs the map screen as a Streamlit component, with the chat agent behind its chat panel.
- The graph comes from Python (`build_graph`), not from a file. The refresh icon asks Python to rebuild it.
- A question typed in the chat panel goes to `ChatSession.ask()` and the answer comes back to the panel. The session remembers earlier questions
  for as long as the browser tab stays open. The selected node and environment are sent along as context.
- The message format between the screen and Streamlit is described at the top of `streamlit_app/app.py` and in `frontend/src/app/streamlit-bridge.ts`.
- Needs a model key in `.env`. Without one, or when the quota is used up, the chat shows a short message instead of an answer.

```bash
cd frontend && npm install && npm run build:streamlit   # once, and after any change to the screen
cd .. && streamlit run streamlit_app/app.py
```

The plain Angular app still works on its own (`cd frontend && npm start`); there the chat uses the built-in rule-based answers.

## Graph JSON (what the screen reads)

The Angular screen reads one JSON object and nothing else. The URL is the `GRAPH_URL` constant in
`frontend/src/app/graph.service.ts` (default `graph.json`); point it at a file or an endpoint that returns this shape.
The screen loads it once when it opens and again when you click the refresh icon. It never refreshes on a timer.
Locally the file comes from `python -m backend.graph build` (writes `graph/graph_all.json`), then `npm run sync:graph`
(or `npm start`) in `frontend/` copies it to `public/graph.json`. The TypeScript types are `RawGraph`, `RawNode` and `RawEdge` in
`frontend/src/app/graph.model.ts`.

```json
{
  "nodes": [ { "node": "project:prj_FIN_7f3a2c", "type": "project", "label": "Vendor-spend assistant", "id": "prj_FIN_7f3a2c", "...": "..." } ],
  "edges": [ { "source": "project:prj_FIN_7f3a2c", "target": "table:1", "kind": "project_table", "environment": "prod", "...": "..." } ]
}
```

Direction means "depends on": `source` depends on `target`. Edges reference nodes by their `node` key, which must be unique.
Extra top-level keys (`directed`, `multigraph`, `graph`) are ignored.

### Nodes

Every node has `node` (`<type>:<key>`, unique), `type`, `label` and `id`. The rest depends on the type.

| `type` | `node` key | Extra fields |
| --- | --- | --- |
| `project` | `project:<project_id>` | `department`; `environments`: `{ "<env>": { "account_id", "packages_valid", "packages_reason", "run_count", "last_init_at" } }` |
| `account` | `account:<aws_account_id>` | none (the label is the account id) |
| `packages` | `packages:<project_id>:<env>` | `environment`, `valid` (true / false / null = never checked), `reason`, `checked_at`, `python_version`, `package_count` |
| `model` | `model:<model_id>` | `deprecated` (bool), `end_of_life_date` (`YYYY-MM-DD` or null) |
| `profile` | `profile:<profile_arn>` | `profile_type`, `status`. Optional: the screen folds it away, so link a project straight to the model if you have no profiles |
| `tool` | `tool:<name>` | none (observability tool) |
| `platform` | `platform:<name>` | none (data platform, e.g. Snowflake) |
| `database` | `database:<id>` | `environment` |
| `table` | `table:<id>` | `environment`, `table_exists` (false shows as a failing dependency) |

`env` is `dev`, `test` or `prod`.

### Edges

Every edge has `source`, `target`, `kind` and `environment` (`dev`, `test`, `prod`, or null for structural links).
A project that runs in two environments gets one edge per environment.

| `kind` | From to | Extra fields |
| --- | --- | --- |
| `project_account` | project to account | `last_seen` |
| `project_packages` | project to packages | `status` (`pass` / `fail` / null), `status_reason`, `last_seen` |
| `project_profile` | project to profile (or straight to the model) | `count` (model calls), `last_seen`, `status`, `status_reason` |
| `project_table` | project to table | `count`, `last_seen`, `status`, `status_reason` |
| `project_tool` | project to tool | `count`, `last_seen` |
| `structural` | profile to model, table to database, database to platform | none |

`status` is `"pass"` or `"fail"`; `"fail"` draws the link red and the reason shows in the project's Issues list.
`count` sizes how many signals flow along the link.

### Minimal example

```json
{
  "nodes": [
    { "node": "account:111111111111", "type": "account", "label": "111111111111", "id": "111111111111" },
    { "node": "project:p1", "type": "project", "label": "HR bot", "id": "p1", "department": "HR",
      "environments": { "dev": { "account_id": "111111111111", "packages_valid": true, "run_count": 3, "last_init_at": "2026-11-12T10:00:00Z" } } },
    { "node": "model:m1", "type": "model", "label": "Claude Sonnet 4.6", "id": "m1", "deprecated": false, "end_of_life_date": null }
  ],
  "edges": [
    { "source": "project:p1", "target": "account:111111111111", "kind": "project_account", "environment": "dev" },
    { "source": "project:p1", "target": "model:m1", "kind": "project_profile", "environment": "dev", "count": 3, "status": "pass" }
  ]
}
```

## Chat agent (needs a Gemini or OpenAI key)

Put your key in `.env` (Gemini: https://aistudio.google.com/apikey, OpenAI: https://platform.openai.com/api-keys; `LLM_PROVIDER` picks which), then:

```bash
python -m backend.agent.orchestrator "If we end the HoneyHive contract, which projects are affected?"
python -m backend.agent.orchestrator      # interactive; the session remembers earlier questions
python -m backend.agent.simulate          # a scripted leader conversation, with token counts
```
The orchestrator has one tool, `ask_graph`. Inside it, plain Python runs: a query-writer agent (which reads the
schema and relationship skills through Strands' AgentSkills plugin) writes one SQL query or an impact lookup,
the query runs in the read-only sandbox, and a trimmed result comes back. The orchestrator writes the answer.

Each sample project is a small Strands agent: it calls `depmap.get_model(name)` to get the account's inference profile, so it needs AWS credentials and Bedrock access to run (tests use a fake agent).

## Known limits (MVP)

- Seed model IDs and ARNs are illustrative, not live Bedrock values. Replace them with real ones.
- JSON files allow one writer at a time (file lock). Move to SQLite if you run projects in parallel.
- The sample projects are untested against real Bedrock. The chat agent needs a Gemini or OpenAI key in `.env`.
- Table and observability counts are declarations and tracked accesses, not complete usage.
- No columns are tracked, so column-level breaks are invisible by design.
- Model/profile status and which tables exist come from the seed data (a dropped table is `table_exists = false` in `db_tables`, set by hand for now). Real Boto3 and platform sync jobs are not built yet.
