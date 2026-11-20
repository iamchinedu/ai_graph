"""Dependency map, all in Python: header controls, the glowing map, the side panel and the AI chat.

Run:  streamlit run app.py     (from this folder, or: streamlit run graph/app.py from the repo root)

What happens when the page opens (and again on every browser reload):
  1. load_raw() reads the raw nodes and edges (data/*.json)             -> the map is drawn straight away
  2. get_store(raw) builds the NetworkX graph on a background thread    -> the agent's tools use it when it is ready
  The chat agent is created on the first question, one per browser tab, and keeps the conversation.

What is where
  app.py            this page: layout, controls, side panel, chat box
  network/          source.py (raw data), build.py (background NetworkX graph), view.py (what the map shows)
  map_component/    the map itself: a canvas drawn by plain JavaScript (glow, flowing signals, zoom, drag)
  agent/            the orchestrator agent: config, prompt, skills, tools, agent
"""
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import ask as ask_agent, create_agent  # noqa: E402
from map_component import dependency_map  # noqa: E402
from network.build import get_store  # noqa: E402
from network.source import load_raw  # noqa: E402
from network.view import ENVS, TYPE_INFO, View, build_model, eol_text, fmt, is_broken, is_deprecated, place, short_label  # noqa: E402

MAP_HEIGHT = 700


@st.cache_data(show_spinner=False)
def load_model(raw):
    return build_model(raw)


def describe_context(selected, environment):
    """One sentence about what is on screen, so 'this project' in a question has a meaning for the agent."""
    parts = []
    if selected:
        parts.append(f"The user has selected {selected['label']} ({selected['type']}).")
    if environment != "all":
        parts.append(f"They are looking at the {environment} environment.")
    return " ".join(parts)


# ---- callbacks (they run before the script reruns) -------------------------------------------

def select(node_id):
    st.session_state.selected = node_id


def on_map_click():
    """A click on a node selects it, a second click on the same node lets go, a click on the background clears."""
    click = st.session_state["map"].click
    if click:
        st.session_state.selected = None if click["id"] in (None, st.session_state.selected) else click["id"]


def refresh():
    """Pull the raw data again. The map redraws at once; if the data changed, the agent's graph rebuilds in the background."""
    st.session_state.raw = load_raw()
    st.session_state.loaded_at = datetime.now()


def reset():
    st.session_state.update(env="all", layout="Brain", query="", selected=None)


def queue_question(question):
    st.session_state.pending = question


def start_chat():
    """Opening the chat folds the summary away to make room."""
    st.session_state.update(chat_open=True, summary_open=False)


def close_chat():
    st.session_state.update(chat_open=False, summary_open=True)


def toggle_summary():
    st.session_state.summary_open = not st.session_state.summary_open


# ---- state -----------------------------------------------------------------------------------

st.set_page_config(page_title="Dependency map", layout="wide", initial_sidebar_state="collapsed")
if "raw" not in st.session_state:       # a new browser tab, or a reload: pull the data again
    refresh()
st.session_state.setdefault("selected", None)
st.session_state.setdefault("env", "all")
st.session_state.setdefault("layout", "Brain")
st.session_state.setdefault("query", "")
st.session_state.setdefault("messages", [])          # what the chat panel shows
st.session_state.setdefault("chat_open", False)
st.session_state.setdefault("summary_open", True)
store = get_store(st.session_state.raw)              # starts the background graph build if this data is new

# ---- header: title and controls --------------------------------------------------------------

head_l, head_r = st.columns([2, 5], vertical_alignment="bottom")
with head_r:
    bar = st.container(horizontal=True, vertical_alignment="bottom")
    with bar:
        env = st.segmented_control("Environment", ENVS, key="env", format_func=lambda e: "All" if e == "all" else e) or "all"
        layout = (st.segmented_control("View option", ["Brain", "Ladder"], key="layout") or "Brain").lower()
        query = st.text_input("Find a node", placeholder="Find a node", key="query", label_visibility="collapsed", width=200)
        st.button("", icon=":material/refresh:", on_click=refresh, key="refresh",
                  help=f"Data loaded {st.session_state.loaded_at:%H:%M:%S}. Click to reload.")
        st.button("Reset", on_click=reset, key="reset")

nodes, tlinks, vlinks = load_model(st.session_state.raw)
view = View(nodes, tlinks, vlinks, env, query, st.session_state.selected)
sel = nodes.get(view.selected) if view.selected else None
with head_l:
    st.header("Dependency map")
    st.caption(f"{len(nodes)} nodes · {len(vlinks)} links · {view.failing()} failing")

map_col, side_col = st.columns([3, 1.4])

# ---- the map ---------------------------------------------------------------------------------

with map_col:
    dependency_map(view.scene(place(nodes, vlinks, layout), layout, MAP_HEIGHT), key="map", on_click=on_map_click)

# ---- side panel: a summary card that can be hidden, and the chat that opens below it -----------

def link_row(text, key, node_id):
    """A line of text on the left and a small arrow on the right that opens that node."""
    left, right = st.columns([7, 1], vertical_alignment="center")
    left.markdown(text)
    right.button("", icon=":material/arrow_forward:", key=key, on_click=select, args=(node_id,), type="tertiary", help="Open")


def render_overview(view):
    ov = view.overview()
    a, b, c = st.columns(3)
    a.metric("Projects", ov["projects"])
    b.metric("Dependencies", ov["dependencies"])
    c.metric("At risk", ov["at_risk"])
    if ov["at_risk"]:
        st.error(f"**{ov['at_risk']} of {ov['projects']} projects need attention**", icon=":material/error:")
    else:
        st.success("No projects at risk", icon=":material/check_circle:")
    ended = any(s["over"] for s in ov["soon"])
    for title, why, color, rows in (("Package dependency", "invalid packages", "red", ov["risk_pkg"]),
                                    ("Model deprecation", "deprecated model", "red" if ended else "orange", ov["risk_model"]),
                                    ("Other failing dependency", "failing", "red", ov["risk_other"])):
        if rows:
            st.markdown(f":{color}[**{title}**] :{color}-badge[{len(rows)}]")
            for p in rows:
                link_row(f"**{p['label']}** :{color}-badge[{why}]", f"risk:{why}:{p['id']}", p["id"])
    if ov["soon"]:
        st.markdown(f":orange[**Models deprecated within 3 months**] :orange-badge[{len(ov['soon'])}]")
        for s in ov["soon"]:
            color = "red" if s["over"] else "orange"
            n = s["projects"]
            link_row(f"**{s['model']['label']}** · {n} {'project' if n == 1 else 'projects'} "
                     f":{color}-badge[{'ended' if s['over'] else 'ends'} {s['ends']}]", f"soon:{s['model']['id']}", s["model"]["id"])


def render_selected(view, sel):
    r = sel["raw"]
    st.caption(TYPE_INFO[sel["type"]][0] + (f" · {r.get('environment')}" if sel["type"] == "packages" else ""))
    if is_deprecated(sel):
        st.error(f"Deprecated. {eol_text(r.get('end_of_life_date'))}.", icon=":material/error:")
    if sel["type"] == "table" and r.get("table_exists") is False:
        st.error("This table no longer exists.", icon=":material/error:")
    if sel["type"] == "packages":
        if r.get("valid") is False:
            st.error(r.get("reason") or "A package requirement is not met.", icon=":material/error:")
        elif r.get("valid") is True:
            st.success("Every installed package's requirements are met.", icon=":material/check_circle:")
        else:
            st.caption("Packages were never checked for this run.")
        st.markdown(f"**Packages** {r.get('package_count')}  \n**Python** {r.get('python_version') or 'unknown'}  \n**Checked** {fmt(r.get('checked_at'))}")
    if sel["type"] == "profile":
        st.caption(f"{r.get('profile_type')} · {r.get('status')}")
    if sel["type"] == "project":
        issues = view.issues_of(sel)
        st.markdown(f":{'red' if issues else 'green'}[**Issues**] :{'red' if issues else 'green'}-badge[{len(issues)}]")
        for k, it in enumerate(issues):
            link_row(f":red[**{it['title']}**]  \n{it['detail']}", f"issue:{k}:{it['id']}", it["id"])
        if not issues:
            st.caption("No issues found.")
        st.markdown("**Runs**")
        for run in view.env_runs(sel):
            flag = ":red-badge[packages invalid]" if run["pkgs"] is False else ":green-badge[packages valid]" if run["pkgs"] is True else ""
            st.markdown(f"**{run['env']}** · {run['runs'] or 0} runs · last {fmt(run['last'])} {flag}")
    else:
        rows = view.impacted_rows()
        st.markdown(f":{'orange' if rows else 'green'}[**If this breaks**] :{'orange' if rows else 'green'}-badge[{len(rows)}]")
        if not rows:
            st.caption("Nothing depends on this.")
        for row in rows:
            link_row(f"**{row['project']['label']}** · {', '.join(row['envs'])}" + (" :red-badge[failing]" if row["status"] == "fail" else ""),
                     f"hit:{row['project']['id']}", row["project"]["id"])
    groups = view.depends_by_type()
    if groups:
        st.markdown("**Depends on**")
    for t, items in groups:
        st.caption(TYPE_INFO[t][1])
        with st.container(horizontal=True):
            for d in items:
                st.button(view.pill_label(d), key=f"dep:{d['id']}", on_click=select, args=(d["id"],), type="primary" if is_broken(d) else "secondary")


chat_open, summary_open = st.session_state.chat_open, st.session_state.summary_open
# heights are chosen so the panel is about as tall as the map
summary_h = 500 if not chat_open else 190
thread_h = 378 if not summary_open else 193

with side_col:
    with st.container(border=True):
        head = st.container(horizontal=True, vertical_alignment="center")
        with head:
            st.markdown(f"**{short_label(sel) if sel else 'Overview'}**")
            if sel:
                st.button("", icon=":material/close:", on_click=select, args=(None,), help="Clear selection", key="clear", type="tertiary")
            st.button("Hide" if summary_open else "Show", icon=":material/expand_less:" if summary_open else ":material/expand_more:",
                      on_click=toggle_summary, key="toggle_summary", type="tertiary")
        if summary_open:
            with st.container(height=summary_h, border=False):
                if sel:
                    render_selected(view, sel)
                else:
                    render_overview(view)
        else:
            st.caption(view.brief(sel))

    if not chat_open:
        st.button("Start chat", icon=":material/chat:", type="primary", width="stretch", on_click=start_chat, key="start_chat")
        st.caption("Ask what breaks, who is affected, or what a project relies on.")
    else:
        # ---- the chat: one agent per browser tab. It keeps the conversation, so follow-up questions work. ----
        with st.container(border=True):
            head = st.container(horizontal=True, vertical_alignment="center")
            with head:
                st.markdown(f"**AI chat**{f' · {short_label(sel)}' if sel else ''}")
                st.button("Close", icon=":material/close:", on_click=close_chat, key="close_chat", type="tertiary")
            st.caption(":red[The AI's graph failed to build.]" if store.error else "The AI's graph is ready." if store.ready else "The AI's graph is still building…")
            thread = st.container(height=thread_h, border=False)
            prompt = st.chat_input("Ask about any impact or dependency") or st.session_state.pop("pending", None)
            with thread:
                if not st.session_state.messages and not prompt:
                    st.html("<div style='text-align:center;padding:1.6rem 0 .4rem'>"
                            "<div style='font-size:1.35rem;font-weight:600'>What breaks? Who is affected?</div>"
                            "<div style='opacity:.65;margin-top:.35rem'>Ask what a decision would change, or what a project relies on.</div></div>")
                    for q in view.suggestions():
                        st.button(q, key=f"sugg:{q}", on_click=queue_question, args=(q,), width="stretch")
                for m in st.session_state.messages:
                    with st.chat_message(m["role"]):
                        st.write(m["text"])
                if prompt:
                    with st.chat_message("user"):
                        st.write(prompt)
                    with st.chat_message("assistant"):
                        with st.spinner("Thinking…"):
                            if "agent" not in st.session_state:
                                st.session_state.agent = create_agent()
                            context = describe_context(sel, env)
                            reply = ask_agent(st.session_state.agent, f"({context}) {prompt}" if context else prompt)
                        st.write(reply)
                    st.session_state.messages += [{"role": "user", "text": prompt}, {"role": "assistant", "text": reply}]
