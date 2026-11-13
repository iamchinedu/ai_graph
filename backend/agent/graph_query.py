"""The one composite step the orchestrator calls: question -> write the query -> run it -> compact result.

Doing the steps here, in plain Python, means the orchestrator pays for ONE tool call instead of
looping through load-skill / write-SQL / run-SQL / fix-SQL itself. Only the final, trimmed result
comes back into its context.

The query writer is a second Strands agent. It reads the relationship schemas as Strands *skills*
(the AgentSkills plugin loads every folder under skills/ that has a SKILL.md and lets the agent
activate them on demand) and replies with one JSON object:
    {"mode": "sql", "sql": "SELECT ..."}                              counts, lists, joins
    {"mode": "impact", "node": "HoneyHive", "environment": "prod"}    "what breaks if X"
    {"mode": "cannot", "reason": "..."}                                the map has no such data
"""
import json
import re

from backend import paths
from backend.agent import tools
from backend.agent.config import build_model
from backend.graph.impact import impact

MAX_ROWS = 25

WRITER_PROMPT = """You write ONE query against the AI dependency map. You never answer the question yourself.

Before writing SQL, activate the `schema-overview` and `relationships` skills with the skills tool
(also `node-dependencies` or `impact-analysis` when the question fits them). Skip skills you already
loaded earlier in this conversation.

Reply with exactly one JSON object and nothing else:
  {"mode": "sql", "sql": "SELECT ..."}                      for counts, lists, joins, rankings
  {"mode": "impact", "node": "<name>", "environment": ""}   for "what breaks if X goes away or fails"
                                                            (environment is dev, test, prod, or empty for all)
  {"mode": "cannot", "reason": "<what data is missing>"}

SQL rules: DuckDB, a single read-only SELECT (or WITH ... SELECT), only tables and columns from the schema skill.
The map does NOT contain: people or owners, PII or sensitivity labels, costs, contract dates, usage history,
vendor groupings. Answer {"mode": "cannot"} for those instead of guessing."""


def _parse(text):
    """Pull the JSON plan out of the writer's reply. A bare SELECT is accepted too."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    if re.match(r"\s*(select|with)\b", text, re.I):
        return {"mode": "sql", "sql": text.strip().rstrip(";")}
    return {"mode": "cannot", "reason": "the query writer did not return a usable plan"}


def _trim(markdown, max_rows=MAX_ROWS):
    """Keep the header and the first max_rows table rows, plus the row-count footer."""
    lines = markdown.splitlines()
    table = [l for l in lines if l.startswith("|")]
    footer = [l for l in lines if l.strip().startswith("(")]
    if len(table) <= max_rows + 2:
        return markdown
    return "\n".join(table[: max_rows + 2] + [f"... {len(table) - 2 - max_rows} more rows not shown"] + footer)


def _impact_text(rows, node, environment):
    projects = sorted({r["project_name"] for r in rows})
    if not rows:
        return f"No projects depend on {node} ({environment or 'all environments'})."
    lines = [f"{len(projects)} project(s) affected if {node} breaks ({environment or 'all environments'}): {', '.join(projects)}"]
    for r in rows[:MAX_ROWS]:
        lines.append(f"- {r['project_name']} [{r['environment']}] via {r['via']} (status {r['edge_status']})")
    return "\n".join(lines)


class GraphQuery:
    def __init__(self, session_dir=None, writer=None):
        self.dir = session_dir or (paths.SCRATCH_DIR / "adhoc")
        self._writer = writer            # a function(prompt) -> text; tests use it instead of a model
        self._agent = None
        self.usage = {"input": 0, "output": 0}

    def _write(self, prompt):
        if self._writer:
            return self._writer(prompt)
        if self._agent is None:
            from strands import Agent
            from strands.vended_plugins.skills import AgentSkills
            self._agent = Agent(model=build_model(writer=True), system_prompt=WRITER_PROMPT,
                                plugins=[AgentSkills(skills=str(paths.SKILLS_DIR))], callback_handler=None)
        result = self._agent(prompt)
        try:
            u = result.metrics.accumulated_usage
            self.usage = {"input": u["inputTokens"], "output": u["outputTokens"]}
        except Exception:  # noqa: BLE001
            pass
        return str(result)

    def run(self, question):
        """Write the query, run it read-only, and return the question, the query and a trimmed result."""
        plan = _parse(self._write(f"Question: {question}"))
        for attempt in range(2):
            mode = plan.get("mode")
            if mode == "cannot":
                return f"CANNOT ANSWER from the map: {plan.get('reason', 'no matching data')}"
            if mode == "impact":
                node, env = plan.get("node", ""), plan.get("environment") or ""
                return f"mode: impact\nresult: {_impact_text(impact(node, env or None), node, env)}"
            sql = (plan.get("sql") or "").strip().rstrip(";")
            out = tools.run_sql(sql, self.dir)
            if not out.startswith("query error"):
                return f"mode: sql\nquery: {' '.join(sql.split())}\nresult:\n{_trim(out)}"
            if attempt == 0:
                plan = _parse(self._write(f"That query failed: {out}\nFix it and reply with the JSON object only."))
        return f"CANNOT ANSWER: the query kept failing ({out})"
