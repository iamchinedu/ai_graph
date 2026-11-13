"""python -m backend.agent.simulate  -> a scripted leader conversation against the live agent.

Needs GEMINI_API_KEY (or OPENAI_API_KEY) in .env. Writes scratch/<session>/simulation.md with each answer and the token use.
It includes follow-ups ("and which of those are in prod?") to check the session keeps its context, and
questions the map cannot answer yet, to check it says so instead of guessing.
"""
import time

from backend.agent.orchestrator import ChatSession

TURNS = [
    ("vendor change", "If we end our HoneyHive contract, which projects are affected?"),
    ("follow-up", "And which of those are in prod?"),
    ("model lifecycle", "What breaks if Claude 3 Sonnet is deprecated?"),
    ("model lifecycle", "Which models reach end of life within the next 3 months?"),
    ("governance", "Which prod projects have no observability tool?"),
    ("insights", "Which data platform is used by the most projects?"),
    ("vendor change", "If we move off Snowflake, which databases and tables would have to migrate?"),
    ("follow-up", "Which projects does that touch?"),
    ("outage", "AWS account 222222222222 has an outage. What stops working?"),
    ("cannot answer", "Who owns the HR policy bot?"),
    ("cannot answer", "Which projects handle PII?"),
]

if __name__ == "__main__":
    s = ChatSession()
    out = [f"# Simulation {s.id}\n"]
    for kind, q in TURNS:
        t0 = time.time()
        try:
            a = s.ask(q)
        except Exception as exc:  # noqa: BLE001
            a = f"ERROR: {exc}"
        tok = s.tokens()
        block = f"## [{kind}] {q}\n\n{a}\n\n_{time.time() - t0:.1f}s · tokens so far: {tok}_\n"
        print(block)
        out.append(block)
    (s.dir / "simulation.md").write_text("\n".join(out))
    print(f"saved {s.dir / 'simulation.md'}")
