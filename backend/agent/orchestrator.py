"""The orchestrator agent (Strands). One ChatSession = one live agent, so it remembers the conversation.

    python -m backend.agent.orchestrator "If we end the HoneyHive contract, who is affected?"
    python -m backend.agent.orchestrator            # interactive, keeps context between questions

It has ONE tool, ask_graph, which runs the whole lookup (write query -> run -> trim) in plain Python.
The orchestrator keeps the conversation and writes the final answer from the trimmed result.
"""
import json
import sys
import uuid
from datetime import datetime, timezone

from backend import paths
from backend.agent.config import build_model
from backend.agent.graph_query import GraphQuery

SYSTEM_PROMPT = """You are a dependency-risk analyst for business leaders. You answer questions about which
AI projects depend on which models, data platforms, databases, tables and observability tools, and what a
change or outage would affect. You have one tool, ask_graph.

How to work
- For any question about the map, call ask_graph with a complete, standalone question. Resolve words like
  "it", "those" or "that one" from the conversation before you call it.
- One call per distinct question, at most three calls per message. Never call it twice for the same thing.
- Report numbers and names only from tool results. If the tool says it cannot answer, say what data is
  missing and stop. Do not guess.
- State which environment(s) your answer covers. Keep answers short: the headline first, then at most a
  short list. End with the decision the answer informs when that is obvious."""


class ChatSession:
    def __init__(self, model=None, graph_query=None):
        self.id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.dir = paths.SCRATCH_DIR / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.query = graph_query or GraphQuery(self.dir)
        self._model = model
        self._agent = None
        self.transcript = []
        self.usage = {"input": 0, "output": 0}

    def _build_agent(self):
        from strands import Agent, tool

        @tool
        def ask_graph(question: str) -> str:
            """Answer one question about the AI dependency map. Writes the query, runs it read-only and returns
            the query and a trimmed result. Pass a complete standalone question, for example
            'Which projects depend on HoneyHive, by environment?'"""
            return self.query.run(question)

        return Agent(model=self._model or build_model(), system_prompt=SYSTEM_PROMPT, tools=[ask_graph], callback_handler=None)

    def ask(self, message):
        """One turn. The same agent object is reused, so earlier turns stay in its context."""
        if self._agent is None:
            self._agent = self._build_agent()
        result = self._agent(message)
        reply = str(result)
        try:
            u = result.metrics.accumulated_usage
            self.usage = {"input": u["inputTokens"], "output": u["outputTokens"]}
        except Exception:  # noqa: BLE001
            pass
        self.transcript.append({"user": message, "assistant": reply})
        (self.dir / "transcript.json").write_text(json.dumps(self.transcript, indent=2))
        return reply

    def tokens(self):
        """Running token totals for this session: orchestrator and query writer."""
        return {"orchestrator": dict(self.usage), "query_writer": dict(self.query.usage)}


def main(argv):
    session = ChatSession()
    print(f"session {session.id}", file=sys.stderr)
    if argv:
        print(session.ask(" ".join(argv)))
        print(f"\n[tokens] {session.tokens()}", file=sys.stderr)
        return
    while True:
        try:
            q = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if q.lower() in ("exit", "quit", ""):
            return
        print("\n" + session.ask(q))
        print(f"[tokens] {session.tokens()}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
