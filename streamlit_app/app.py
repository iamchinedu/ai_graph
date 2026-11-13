"""Streamlit host for the dependency map, with the Gemini/OpenAI chat agent behind the chat panel.

The map is the Angular screen, built into component/ and run as a Streamlit component. Streamlit and the screen
pass messages (see frontend/src/app/streamlit-bridge.ts):
  screen -> Python   {id, action: "ask", question, context}   the chat agent answers
  screen -> Python   {id, action: "refresh"}                  the graph is rebuilt from the tables
  Python -> screen   graph (always) and reply {id, text} (once per request)

Run:  streamlit run streamlit_app/app.py
Build the screen once first:  cd frontend && npm run build:streamlit
"""
import sys
from pathlib import Path

import networkx as nx
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agent.orchestrator import ChatSession  # noqa: E402
from backend.graph.build import build_graph  # noqa: E402

SCREEN = Path(__file__).parent / "component" / "browser"

st.set_page_config(page_title="Dependency map", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """<style>
    header[data-testid="stHeader"], footer, #MainMenu { display: none; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    /* pin the screen to the window so its bottom edge sits on the bottom of the browser */
    iframe[title*="depmap_map"] { position: fixed !important; inset: 0; width: 100vw !important; height: 100dvh !important; border: 0; z-index: 1; }
    [data-testid="stMain"] { overflow: hidden; }
    </style>""",
    unsafe_allow_html=True,
)

if not (SCREEN / "index.html").exists():
    st.error("The screen isn't built yet. Run:  cd frontend && npm install && npm run build:streamlit")
    st.stop()

depmap_map = components.declare_component("depmap_map", path=str(SCREEN))


def graph_data() -> dict:
    return nx.node_link_data(build_graph(None), name="node", key="edge_key", edges="edges")


def answer(question: str, context: str) -> str:
    """The chat agent keeps one session per browser tab, so follow-ups work."""
    try:
        if "chat" not in st.session_state:
            st.session_state.chat = ChatSession()
        return st.session_state.chat.ask(f"({context}) {question}" if context else question)
    except Exception as exc:  # show the person something readable, not a stack trace
        text = str(exc)
        if "RESOURCE_EXHAUSTED" in text or "429" in text:
            return "The AI model's request quota is used up for now. Try again later, or switch the model in .env."
        if isinstance(exc, RuntimeError) and "API_KEY" in text:
            return text
        return f"Sorry, I couldn't answer that: {text[:300]}"


st.session_state.setdefault("graph", graph_data())
st.session_state.setdefault("reply", None)
st.session_state.setdefault("last_id", None)

request = depmap_map(graph=st.session_state.graph, reply=st.session_state.reply, key="map", default=None)

# A request is handled once: the value stays set on later reruns, so remember the id we already answered.
if request and request.get("id") != st.session_state.last_id:
    st.session_state.last_id = request["id"]
    text = ""
    if request.get("action") == "refresh":
        st.session_state.graph = graph_data()
    elif request.get("action") == "ask":
        text = answer(request.get("question", ""), request.get("context", ""))
    st.session_state.reply = {"id": request["id"], "text": text}
    st.rerun()
