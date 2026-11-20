# graph: the dependency map with an AI agent

A Streamlit page that shows which AI projects depend on which models, data platforms, tables, tools and AWS accounts
(glowing map, side panel), with a chat on the side. The chat is an orchestrator agent (AWS Strands Agents, Claude on
Amazon Bedrock) that answers by writing small queries against a NetworkX graph.

## Run it

```bash
cd graph
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The map and panel work with no AWS login. The chat needs AWS credentials that may call your Bedrock model:

```bash
aws configure sso                       # once
aws sso login --profile <profile>       # when the session expires
export AWS_PROFILE=<profile> AWS_REGION=<region>     # Windows PowerShell: $env:AWS_PROFILE="<profile>"
```

Then set your model in [agent/config.py](agent/config.py): `CLAUDE_MODEL_ID` is the inference profile ID
(`aws bedrock list-inference-profiles --region <region> --profile <profile>`).

## What is where

| Path | What it does |
| --- | --- |
| `app.py` | The page: controls, map, side panel, chat box. Calls `create_agent()` and `ask(agent, prompt)`. |
| `agent/config.py` | One variable: `CLAUDE_MODEL_ID`. |
| `agent/prompt.py` | The orchestrator's instructions, in XML sections (role, task, tools, workflow, constraints, conversation, output format). |
| `agent/skills.py` | Instructions the agent loads on demand: what the graph's nodes, edges and fields mean, how to write a query, the impact-analysis recipe. |
| `agent/tools.py` | `load_skill(name)` and `run_graph_query(code)`. The query runs Python against the graph behind guardrails (no imports, files or `while` loops, a time limit, a copy of the graph). |
| `agent/agent.py` | `create_agent()` builds the Strands agent (`BedrockModel` + prompt + tools). `ask()` sends one message and returns the reply. |
| `network/source.py` | `load_raw()`: the one place raw nodes and edges come from. Today `data/nodes.json` and `data/edges.json` (placeholders). |
| `network/build.py` | Builds the NetworkX graph on a background thread (`get_store`). |
| `network/view.py` | What the map shows: the tree that is drawn, positions, risks, brightness. |
| `map_component/` | The map: an HTML canvas drawn by plain JavaScript (no build step). |
| `tests/` | `pip install pytest` then `python -m pytest -q` (no AWS needed). |

## What happens when the page opens, and when it is reloaded

A browser reload starts a new Streamlit session, so the same two things happen every time:

1. `load_raw()` pulls the raw nodes and edges, and the map is drawn at once.
2. `get_store(raw)` builds the NetworkX graph on a background thread. If the data is the same as last time it reuses the finished
   graph, so a reload costs nothing; if the data changed it builds a new one.

The agent's `run_graph_query` tool waits for the graph if it is still building. The chat shows "The AI's graph is ready" or "still
building". The refresh icon does the same pull without losing your chat. A reload does clear the chat and starts a new agent.

## Why build a graph when you already have nodes and edges?

The lists are enough to draw the map. They are not enough to answer "what breaks if this fails?" cheaply: that is a multi-hop
question (table, then database, then platform, then every project that uses any of them), per environment. NetworkX has it built in
(`ancestors`, `descendants`, paths), so the agent writes one short line instead of looping over lists. On a few dozen nodes the build
takes milliseconds; on a large graph it takes seconds, which is why it runs in the background.

## Using your real data

Replace the body of `load_raw()` in `network/source.py` (API, S3, database) so it returns
`{"nodes": [...], "edges": [...]}` in the shape of the JSON files. An edge reads "source depends on target". Field meanings
are in `agent/skills.py` (the `graph-schema` skill).

## Known limits

- The chat history lives in the browser tab's session. Reloading the page clears it.
- The query guardrails suit a local app. They are not a hardened sandbox.
- The agent was tested here with Gemini standing in for Claude, because this machine has no AWS login. Its prompt, skills, tools and
  multi-turn behaviour worked. The Bedrock call itself has not been run from here.
