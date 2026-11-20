"""Run from the graph/ folder:  python -m pytest -q     (needs: pip install pytest)
No AWS login is needed: the agent is only built, never called."""
import json
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from agent.agent import create_agent, friendly_error
from agent.prompt import ORCHESTRATOR_PROMPT
from agent.skills import SKILLS
from agent.tools import check_code, run_query
from network.build import GraphStore, build_graph, get_store
from network.source import load_raw
from network.view import View, build_model, place

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(scope="module")
def raw():
    return load_raw()


@pytest.fixture(scope="module")
def graph(raw):
    return build_graph(raw)


def query(graph, code):
    return json.loads(run_query(code, graph))


# ---- data and background build ---------------------------------------------------------------

def test_raw_data_is_consistent(raw):
    ids = [n["node"] for n in raw["nodes"]]
    assert len(ids) == len(set(ids))
    assert all(e["source"] in ids and e["target"] in ids for e in raw["edges"])


def test_graph_is_built_in_the_background_and_reused(raw):
    store = get_store(raw)
    assert store.wait(timeout=10).number_of_nodes() == len(raw["nodes"])
    assert get_store(raw) is store                                  # same data: no second build
    changed = {"nodes": raw["nodes"], "edges": raw["edges"][:-1]}
    other = get_store(changed)
    assert other is not store and other.wait(timeout=10).number_of_edges() == len(raw["edges"]) - 1


def test_wait_times_out_while_still_building(raw, monkeypatch):
    monkeypatch.setattr("network.build.build_graph", lambda r: time.sleep(0.5))
    store = GraphStore(raw)
    with pytest.raises(TimeoutError):
        store.wait(timeout=0.01)
    assert not store.ready
    store.wait(timeout=5)
    assert store.ready


# ---- the agent's tools -----------------------------------------------------------------------

def test_helpers_agree_with_the_data(raw, graph):
    direct = {graph.nodes[u]["label"] for u, v in graph.in_edges("tool:HoneyHive")}
    assert query(graph, 'result = impacted(find("honeyhive"))') == sorted(direct)
    prod = query(graph, 'result = impacted(find("honeyhive"), "prod")')
    assert set(prod) <= direct


def test_environment_filter_and_depends_on(graph):
    project = next(n for n, d in graph.nodes(data=True) if d["type"] == "project")
    everything = query(graph, f'result = depends_on("{project}")')
    assert any(x["type"] == "model" for x in everything)
    only_prod = query(graph, f'result = depends_on("{project}", "prod")')
    assert len(only_prod) <= len(everything)


def test_queries_can_use_plain_networkx_and_comprehensions(graph):
    counts = query(graph, 'counts = {}\nfor n, d in G.nodes(data=True):\n    counts[d["type"]] = counts.get(d["type"], 0) + 1\nresult = {k: v for k, v in counts.items()}')
    assert counts["project"] == 5


@pytest.mark.parametrize("code, expected", [
    ("import os\nresult = 1", "imports are not allowed"),
    ("result = open('/etc/passwd').read()", "NameError"),
    ("result = G.__class__", "not allowed"),
    ("while True:\n    pass", "while loops are not allowed"),
    ("result = nx.write_gml(G, '/tmp/x.gml')", "not allowed"),
    ("x = 1", "set a variable named `result`"),
    ("result = 1 +", "invalid syntax"),
    ("result = find('x')[0]", "IndexError"),
    ("result = impacted('nope')", "unknown node id"),
])
def test_guardrails_and_errors_come_back_as_text(graph, code, expected):
    out = run_query(code, graph)
    assert out.startswith("query error:") and expected in out


def test_a_query_cannot_change_the_shared_graph(graph):
    before = graph.number_of_nodes()
    run_query('G.nodes["project:prj_HR_c04e1a"]["label"] = "changed"\nresult = 1', graph)
    assert graph.nodes["project:prj_HR_c04e1a"]["label"] != "changed" and graph.number_of_nodes() == before


def test_long_results_are_cut(graph):
    out = run_query("result = list(range(100000))", graph)
    assert len(out) < 7000 and "cut" in out


# ---- the agent -------------------------------------------------------------------------------

def test_prompt_is_split_into_xml_sections_and_names_every_skill():
    for tag in ("role", "task", "tools", "workflow", "constraints", "conversation", "output_format"):
        assert f"<{tag}>" in ORCHESTRATOR_PROMPT and f"</{tag}>" in ORCHESTRATOR_PROMPT
    assert all(name in ORCHESTRATOR_PROMPT for name in SKILLS)


def test_agent_is_built_with_its_tools_and_a_model_from_config(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    agent = create_agent()
    assert set(agent.tool_names) == {"load_skill", "run_graph_query"}
    assert agent.model.config["model_id"] == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert agent.messages == []                                       # a fresh conversation


def test_errors_become_sentences():
    assert "credentials" in friendly_error(RuntimeError("Unable to locate credentials"))
    assert "expired" in friendly_error(RuntimeError("ExpiredTokenException: The security token included in the request is expired"))
    assert "refused" in friendly_error(RuntimeError("AccessDeniedException"))
    assert friendly_error(ValueError("boom")).startswith("Sorry, I couldn't answer that")


def test_every_skill_can_be_loaded():
    from agent.tools import load_skill
    for name in SKILLS:
        assert load_skill(name=name).startswith("<")
    assert "Unknown skill" in load_skill(name="nope")


# ---- what the map shows ----------------------------------------------------------------------

def test_scene_is_ready_to_paint(raw):
    nodes, tlinks, vlinks = build_model(raw)
    scene = View(nodes, tlinks, vlinks, "all", "", None).scene(place(nodes, vlinks, "brain"), "brain", 700)
    ids = {n["id"] for n in scene["nodes"]}
    assert len(ids) == len(nodes) and all(0 <= n["opacity"] <= 1 for n in scene["nodes"])
    assert all(l["s"] in ids and l["t"] in ids for l in scene["links"])
    assert any(l["bad"] for l in scene["links"]) and any(l["feeds"] for l in scene["links"])


def test_selecting_a_node_dims_the_rest(raw):
    nodes, tlinks, vlinks = build_model(raw)
    project = next(i for i, n in nodes.items() if n["type"] == "project")
    scene = View(nodes, tlinks, vlinks, "all", "", project).scene(place(nodes, vlinks, "ladder"), "ladder", 700)
    by_id = {n["id"]: n for n in scene["nodes"]}
    assert by_id[project]["selected"] and by_id[project]["opacity"] == 1
    assert any(n["opacity"] < 0.2 for n in scene["nodes"])


# ---- the page --------------------------------------------------------------------------------

def test_page_loads_filters_and_selects():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("nodes" in c.value and "links" in c.value for c in at.caption)
    at.session_state["env"] = "prod"
    at.session_state["layout"] = "Ladder"
    at.run()
    assert not at.exception
    at.session_state["env"] = "all"
    at.run()
    risk = [b for b in at.button if str(b.key).startswith("risk:")]
    assert risk, "the overview lists at-risk projects"
    risk[0].click().run()
    assert not at.exception and at.session_state["selected"].startswith("project:")
    at.button(key="clear").click().run()
    assert at.session_state["selected"] is None


def test_start_chat_opens_the_chat_and_folds_the_summary():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception and at.session_state["summary_open"] and not at.session_state["chat_open"]
    at.button(key="start_chat").click().run()
    assert not at.exception
    assert at.session_state["chat_open"] and not at.session_state["summary_open"]
    assert at.chat_input, "the chat box is there"
    at.button(key="toggle_summary").click().run()
    assert at.session_state["summary_open"] and at.session_state["chat_open"]
    at.button(key="close_chat").click().run()
    assert not at.session_state["chat_open"] and at.session_state["summary_open"]
