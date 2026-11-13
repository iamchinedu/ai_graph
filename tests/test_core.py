import pytest

import depmap_sdk as depmap
from depmap_sdk import store
from backend.checks import run_checks
from depmap_sdk.packages import evaluate
from backend.graph.impact import impact
from depmap_sdk.recorder import handle_event
from backend.projects import create_project
from backend.query.run_query import execute_sql

FIN = "prj_FIN_7f3a2c"


def test_package_check_flags_unmet_requirement_and_skips_other_platform_markers():
    pk = [{"name": "boto3", "version": "1.40.0", "requires": ["botocore<1.41.0,>=1.40.0", "colorama; sys_platform=='win32'"]},
          {"name": "botocore", "version": "1.41.0", "requires": []}]
    valid, reason = evaluate(pk, {"sys_platform": "linux"})
    assert not valid and "botocore" in reason and "colorama" not in reason
    pk[1]["version"] = "1.40.5"
    assert evaluate(pk, {"sys_platform": "linux"}) == (True, None)


def test_missing_required_package_fails():
    valid, reason = evaluate([{"name": "a", "version": "1", "requires": ["b>=1"]}], {})
    assert not valid and "not installed" in reason


def test_create_project_validates(data):
    with pytest.raises(ValueError):
        create_project("ab", 1)
    with pytest.raises(ValueError):
        create_project("Vendor-spend assistant", 1)  # duplicate name
    p = create_project("Brand new agent", 1)
    assert p["id"].startswith("prj_FIN_")


def test_ingest_rejects_unknown_project_and_bad_environment(data):
    assert not handle_event({"type": "model.call", "project_id": "nope", "environment": "prod", "model_id": "x"})["accepted"]
    assert not handle_event({"type": "model.call", "project_id": FIN, "environment": "staging", "model_id": "x"})["accepted"]


def test_ingest_counts_accumulate_and_skip_unknown_lists(data):
    init = {"type": "project.init", "project_id": FIN, "environment": "prod", "ts": "2026-11-11T10:00:00Z",
            "databases": [{"platform": "Snowflake", "database": "finance_db", "tables": ["invoices"]},
                          {"platform": "NoSuchPlatform", "database": "x", "tables": ["y"]}],
            "observability": ["HoneyHive", "NotATool"]}
    res = handle_event(init)
    assert res["accepted"] and len(res["warnings"]) == 2
    handle_event(init)  # second start
    assert store.get("project_observability_edges", project_id=FIN)["count"] == 2
    for n in (3, 2):
        handle_event({"type": "table.access", "project_id": FIN, "environment": "prod", "platform": "Snowflake",
                      "database": "finance_db", "table": "invoices", "n": n, "ts": "2026-11-11T11:00:00Z"})
    edge = store.get("project_table_edges", project_id=FIN)
    assert edge["count"] == 5 and edge["last_seen"] == "2026-11-11T11:00:00Z"


def test_sdk_logs_models_and_tables(data):
    dm = depmap.DepMap()
    dm.init(project_id=FIN, environment="dev", check_packages=False, account_id="111111111111",
            databases=[{"platform": "Snowflake", "database": "finance_db", "tables": ["invoices", "vendors"]}])
    conn = object()
    assert dm.log_connection(conn, "Snowflake", "finance_db", "invoices") is conn
    dm.log_connection(conn, "Snowflake", "finance_db", ["invoices", "vendors"])
    by_table = {store.get("db_tables", id=e["table_id"])["table_name"]: e["count"]
                for e in store.find("project_table_edges", project_id=FIN)}
    assert by_table == {"invoices": 2, "vendors": 1}
    model = "arn:aws:bedrock:us-east-1:111111111111:application-inference-profile/finance-sonnet"
    assert dm.log_model(model) == model
    dm.log_model(type("M", (), {"config": {"model_id": model}})())
    edge = store.get("project_profile_edges", project_id=FIN)
    assert edge["count"] == 2 and edge["last_seen"]


def test_sdk_never_raises_when_backend_is_broken(data, monkeypatch):
    from depmap_sdk import recorder
    monkeypatch.setattr(recorder, "handle_event", lambda ev: (_ for _ in ()).throw(RuntimeError("down")))
    dm = depmap.DepMap()
    dm.init(project_id=FIN, environment="dev", check_packages=False)
    dm.log_connection(None, "Snowflake", "finance_db", "invoices")  # must not raise
    dm.log_model("some-model")


def test_checks_and_impact_follow_deprecation_and_dropped_table(data):
    handle_event({"type": "model.call", "project_id": FIN, "environment": "prod",
                  "model_id": "arn:aws:bedrock:us-east-1:222222222222:application-inference-profile/finance-sonnet"})
    handle_event({"type": "table.access", "project_id": FIN, "environment": "prod", "platform": "Snowflake",
                  "database": "finance_db", "table": "invoices"})
    assert run_checks() == {"pass": 2, "fail": 0}
    store.upsert("models", {"id": "anthropic.claude-sonnet-4-6-v1:0", "deprecated": True})
    tbl = store.get("db_tables", table_name="invoices", database_id=1)
    store.upsert("db_tables", {"id": tbl["id"], "table_exists": False})
    assert run_checks() == {"pass": 0, "fail": 2}
    rows = impact("Claude Sonnet 4.6")
    assert [r["project"] for r in rows] == [FIN] and rows[0]["edge_status"] == "fail"


def test_environments_stay_separate_in_graph(data):
    for env in ("dev", "prod"):
        handle_event({"type": "project.init", "project_id": FIN, "environment": env, "observability": ["HoneyHive"]})
    assert {r["environment"] for r in impact("HoneyHive")} == {"dev", "prod"}
    assert {r["environment"] for r in impact("HoneyHive", "prod")} == {"prod"}


def test_query_sandbox_is_read_only(data):
    for bad in ("DROP TABLE models", "SELECT 1; SELECT 2", "SELECT * FROM read_csv('/etc/hosts')", ""):
        with pytest.raises(Exception):
            execute_sql(bad)
    cols, rows = execute_sql("SELECT COUNT(*) FROM models")
    assert rows == [(3,)]


def test_seed_shape(data):
    accounts = store.read("cloud_accounts")
    assert len(accounts) == 9
    for env in ("dev", "test", "prod"):
        assert len([a for a in accounts if a["environment"] == env]) == 3
    assert all(p["account_id"] and p["model_id"] for p in store.read("inference_profiles"))
    forbidden = {"first_seen"}
    for table in ("db_tables", "project_profile_edges", "project_table_edges", "project_observability_edges"):
        from depmap_sdk.schema import TABLES
        assert not forbidden & set(TABLES[table]["columns"])


def test_short_system_profile_id_resolves_to_account_arn(data):
    handle_event({"type": "project.init", "project_id": FIN, "environment": "dev", "account_id": "111111111111"})
    handle_event({"type": "model.call", "project_id": FIN, "environment": "dev",
                  "model_id": "us.anthropic.claude-sonnet-4-6-v1:0"})
    edge = store.get("project_profile_edges", project_id=FIN)
    assert edge["profile_id"] == "arn:aws:bedrock:us-east-1:111111111111:inference-profile/us.anthropic.claude-sonnet-4-6-v1:0"
    assert run_checks()["fail"] == 0


def test_get_model_reads_data_files(data):
    assert depmap.get_model("claude_sonnet_4_6", account_id="222222222222").endswith("application-inference-profile/finance-sonnet")
    assert depmap.get_model("Claude Sonnet 4.6", account_id="333333333333").endswith("inference-profile/us.anthropic.claude-sonnet-4-6-v1:0")
    assert depmap.get_model("amazon_nova_pro", account_id="111111111111").endswith("procurement-nova")
    with pytest.raises(depmap.ModelNotFoundError):
        depmap.get_model("amazon_nova_pro", account_id="333333333333")
    with pytest.raises(depmap.ModelNotFoundError):
        depmap.get_model("no_such_model", account_id="222222222222")


@pytest.mark.parametrize("module", ["project_01", "project_02", "project_03", "project_04", "project_05"])
def test_sample_projects_resolve_model_and_report(data, monkeypatch, module):
    """Each sample runs with a fake Agent that makes one stubbed Bedrock call through the wrapped client."""
    import importlib
    from depmap_sdk import identity
    main = importlib.import_module(f"sample_projects.{module}.main")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "x")

    class FakeAgent:
        def __init__(self, model, system_prompt, callback_handler):
            self.model = model
        def __call__(self, text):
            return "ok"

    acct = {"project_01": "222222222222", "project_02": "111111111111", "project_03": "333333333333",
            "project_04": "333333333333", "project_05": "222222222222"}[module]
    monkeypatch.delenv("DEPMAP_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(identity, "get_caller_identity", lambda: {"Account": acct, "Arn": "arn:x", "UserId": "U"})
    monkeypatch.setattr(main, "Agent", FakeAgent)
    assert main.run_agent("hello") == "ok"
    edges = store.find("project_profile_edges", project_id=main.PROJECT_ID)
    assert len(edges) == 1 and edges[0]["count"] == 1


def test_get_identity_fields(monkeypatch):
    from depmap_sdk import identity as models
    monkeypatch.delenv("DEPMAP_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(models, "get_caller_identity", lambda: {"Account": "123", "Arn": "arn:x", "UserId": "U"})
    assert models.get_identity("account_id") == "123"
    assert models.get_identity("arn") == "arn:x"
    with pytest.raises(ValueError):
        models.get_identity("nope")
    monkeypatch.setenv("DEPMAP_ACCOUNT_ID", "999")
    assert models.get_identity("account_id") == "999"


def test_run_count_and_last_init_increase_on_each_init(data):
    for ts, runs in (("2026-11-12T10:00:00Z", 1), ("2026-11-12T11:00:00Z", 2), ("2026-11-12T12:00:00Z", 3)):
        handle_event({"type": "project.init", "project_id": FIN, "environment": "dev", "ts": ts})
        row = store.get("project_environments", project_id=FIN, environment="dev")
        assert row["run_count"] == runs and row["last_init_at"] == ts
    handle_event({"type": "project.init", "project_id": FIN, "environment": "prod", "ts": "2026-11-12T12:00:00Z"})
    assert store.get("project_environments", project_id=FIN, environment="prod")["run_count"] == 1


def test_graph_snapshots_are_built_saved_and_rebuilt_when_data_changes(data):
    import time
    from backend import paths as backend_paths
    from backend.graph import build_and_save, load_graph
    summary = build_and_save()
    assert set(summary) == {"all", "dev", "test", "prod"}
    assert all((backend_paths.GRAPH_DIR / f"graph_{v}.json").exists() for v in summary)
    assert load_graph("prod").number_of_edges() == 0
    time.sleep(0.01)
    handle_event({"type": "project.init", "project_id": FIN, "environment": "prod", "account_id": "222222222222"})
    handle_event({"type": "model.call", "project_id": FIN, "environment": "prod",
                  "model_id": "arn:aws:bedrock:us-east-1:222222222222:application-inference-profile/finance-sonnet"})
    G = load_graph("prod")  # snapshot was older than the data, so it is rebuilt first
    assert any(d["kind"] == "project_profile" for _, _, d in G.edges(data=True))
    assert not any(d["kind"] == "project_profile" for _, _, d in load_graph("dev").edges(data=True))


def test_graph_has_account_and_packages_nodes_per_project_environment(data):
    from backend.graph import build_graph
    handle_event({"type": "project.init", "project_id": FIN, "environment": "prod", "account_id": "222222222222",
                  "packages": [{"name": "a", "version": "1", "requires": ["b>=2"]}, {"name": "b", "version": "1", "requires": []}]})
    G = build_graph()
    pk = G.nodes[f"packages:{FIN}:prod"]
    assert pk["type"] == "packages" and pk["valid"] is False and "b" in pk["reason"]
    edges = {d["kind"]: d for _, v, d in G.out_edges(f"project:{FIN}", data=True) if d["environment"] == "prod"}
    assert edges["project_packages"]["status"] == "fail" and "project_account" in edges
    assert "account:222222222222" in G
    from backend.graph.impact import impact
    assert [r["project"] for r in impact(f"packages:{FIN}:prod")] == [FIN]


# ---- the orchestrator and its composite tool (no network: the query writer is replaced by a function) ----

def _writer(*replies):
    seq = iter(replies)
    return lambda prompt: next(seq)


def test_graph_query_runs_sql_trims_and_retries_once(data, tmp_path):
    from backend.agent.graph_query import GraphQuery
    bad = '{"mode": "sql", "sql": "SELECT nope FROM projects"}'
    good = '{"mode": "sql", "sql": "SELECT id, name FROM projects"}'
    out = GraphQuery(tmp_path, writer=_writer(bad, good)).run("list projects")
    assert out.startswith("mode: sql") and "Vendor-spend assistant" in out and "5 rows" in out


def test_graph_query_impact_cannot_and_bad_output(data, tmp_path):
    from backend.agent.graph_query import GraphQuery
    handle_event({"type": "project.init", "project_id": FIN, "environment": "prod", "account_id": "222222222222",
                  "observability": ["HoneyHive"]})
    out = GraphQuery(tmp_path, writer=_writer('{"mode": "impact", "node": "HoneyHive", "environment": "prod"}')).run("who uses HoneyHive?")
    assert "1 project(s) affected" in out and "Vendor-spend assistant" in out
    assert GraphQuery(tmp_path, writer=_writer('{"mode": "cannot", "reason": "no owners"}')).run("who owns it?").startswith("CANNOT ANSWER")
    assert GraphQuery(tmp_path, writer=_writer("I think so")).run("?").startswith("CANNOT ANSWER")
    assert GraphQuery(tmp_path, writer=_writer("SELECT count(*) AS n FROM projects")).run("how many?").count("5") >= 1


def test_graph_query_trims_long_results(data, tmp_path):
    from backend.agent.graph_query import _trim
    md = "\n".join(["| a |", "| --- |"] + [f"| {i} |" for i in range(60)] + ["", "(60 rows)"])
    out = _trim(md)
    assert "more rows not shown" in out and "(60 rows)" in out and out.count("\n") < 40


def test_orchestrator_has_one_tool_and_writer_loads_skills(monkeypatch, tmp_path):
    from backend.agent import config, orchestrator
    from backend.agent.graph_query import GraphQuery
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    s = orchestrator.ChatSession(graph_query=GraphQuery(tmp_path, writer=_writer()))
    agent = s._build_agent()
    assert agent.tool_names == ["ask_graph"]
    from strands import Agent
    from strands.vended_plugins.skills import AgentSkills
    from backend import paths
    plugin = AgentSkills(skills=str(paths.SKILLS_DIR))
    writer = Agent(model=config.build_model(writer=True), plugins=[plugin], callback_handler=None)
    names = {sk.name for sk in plugin.get_available_skills(writer)}
    assert {"schema-overview", "relationships", "node-dependencies", "impact-analysis"} <= names


def test_api_key_placeholder_is_rejected(monkeypatch):
    from backend.agent import config
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "your-gemini-api-key-here")
    with pytest.raises(RuntimeError):
        config.api_key()
