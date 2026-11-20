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


# ---- state -----------------------------------------------------------------------------------

st.set_page_config(page_title="Dependency map", layout="wide", initial_sidebar_state="collapsed")
if "raw" not in st.session_state:       # a new browser tab, or a reload: pull the data again
    refresh()
st.session_state.setdefault("selected", None)
st.session_state.setdefault("env", "all")
st.session_state.setdefault("layout", "Brain")
st.session_state.setdefault("query", "")
st.session_state.setdefault("messages", [])          # what the chat panel shows
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

# ---- side panel: overview, or the selected node ----------------------------------------------

with side_col:
    with st.container(height=340, border=True):
        if sel is None:
            ov = view.overview()
            st.subheader("Overview")
            a, b = st.columns(2)
            a.metric("Projects", ov["projects"], border=True)
            b.metric("Dependencies", ov["dependencies"], border=True)
            st.markdown(f"**Projects at risk** :{'red' if ov['at_risk'] else 'green'}-badge[{ov['at_risk']}]")
            for title, rows, why in (("Package dependency", ov["risk_pkg"], "invalid packages"), ("Model deprecation", ov["risk_model"], "deprecated model"),
                                     ("Other failing dependency", ov["risk_other"], "failing")):
                if rows or title != "Other failing dependency":
                    st.caption(title)
                    for p in rows:
                        st.button(f"{p['label']} · {why}", key=f"risk:{why}:{p['id']}", on_click=select, args=(p["id"],), icon=":material/warning:", width="stretch")
                    if not rows:
                        st.write("No projects")
            st.markdown(f"**Models deprecated within 3 months** :{'red' if ov['soon'] else 'green'}-badge[{len(ov['soon'])}]")
            for s in ov["soon"]:
                st.button(f"{s['model']['label']} · {s['projects']} {'project' if s['projects'] == 1 else 'projects'} · {'ended' if s['over'] else 'ends'} {s['ends']}",
                          key=f"soon:{s['model']['id']}", on_click=select, args=(s["model"]["id"],), width="stretch")
            if not ov["soon"]:
                st.write("None")
        else:
            r = sel["raw"]
            top = st.container(horizontal=True, vertical_alignment="center")
            with top:
                st.subheader(f"Packages {'valid' if r.get('valid') is True else 'invalid' if r.get('valid') is False else 'not checked'}" if sel["type"] == "packages" else short_label(sel))
                st.button("", icon=":material/close:", on_click=select, args=(None,), help="Clear selection", key="clear")
            st.caption(TYPE_INFO[sel["type"]][0] + (f" · {r.get('environment')}" if sel["type"] == "packages" else ""))
            if is_deprecated(sel):
                st.error(f"Deprecated. {eol_text(r.get('end_of_life_date'))}.")
            if sel["type"] == "table" and r.get("table_exists") is False:
                st.error("This table no longer exists.")
            if sel["type"] == "packages":
                if r.get("valid") is False:
                    st.error(r.get("reason") or "A package requirement is not met.")
                elif r.get("valid") is True:
                    st.success("Every installed package's requirements are met.")
                else:
                    st.caption("Packages were never checked for this run.")
                st.markdown(f"**Packages** {r.get('package_count')}  \n**Python** {r.get('python_version') or 'unknown'}  \n**Checked** {fmt(r.get('checked_at'))}")
            if sel["type"] == "profile":
                st.caption(f"{r.get('profile_type')} · {r.get('status')}")
            if sel["type"] == "project":
                issues = view.issues_of(sel)
                st.markdown(f"**Issues** :{'red' if issues else 'green'}-badge[{len(issues)}]")
                for k, it in enumerate(issues):
                    st.button(f"{it['title']}  \n{it['detail']}", key=f"issue:{k}:{it['id']}", on_click=select, args=(it["id"],), width="stretch")
                if not issues:
                    st.write("No issues found.")
                st.markdown("**Runs**")
                for run in view.env_runs(sel):
                    flag = ":red-badge[packages invalid]" if run["pkgs"] is False else ":green-badge[packages valid]" if run["pkgs"] is True else ""
                    st.markdown(f"**{run['env']}** · {run['runs'] or 0} runs · last {fmt(run['last'])} {flag}")
            else:
                rows = view.impacted_rows()
                st.markdown(f"**If this breaks** :{'red' if rows else 'green'}-badge[{len(rows)}]")
                if not rows:
                    st.write("Nothing depends on this.")
                for row in rows:
                    st.button(f"{row['project']['label']} · {', '.join(row['envs'])}{' · failing' if row['status'] == 'fail' else ''}",
                              key=f"hit:{row['project']['id']}", on_click=select, args=(row["project"]["id"],), width="stretch")
            groups = view.depends_by_type()
            if groups:
                st.markdown("**Depends on**")
            for t, items in groups:
                st.caption(TYPE_INFO[t][1])
                with st.container(horizontal=True):
                    for d in items:
                        st.button(view.pill_label(d), key=f"dep:{d['id']}", on_click=select, args=(d["id"],), type="primary" if is_broken(d) else "secondary")

    # ---- the chat: one agent per browser tab. It keeps the conversation, so follow-up questions work. ----
    st.markdown(f"**AI chat**{f' · About {short_label(sel)}' if sel else ''}")
    st.caption("The AI's graph failed to build." if store.error else "The AI's graph is ready." if store.ready else "The AI's graph is still building…")
    thread = st.container(height=250, border=True)
    prompt = st.chat_input("Ask AI about impact or dependencies") or st.session_state.pop("pending", None)
    with thread:
        if not st.session_state.messages and not prompt:
            st.markdown("**Assess the impact of a decision around a dependency**")
            st.caption("Ask what breaks, who is affected, or what a project relies on.")
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
