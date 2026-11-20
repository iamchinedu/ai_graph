"""The glowing dependency map as a Streamlit component (HTML canvas + plain JavaScript, no build step).

    clicked = dependency_map(scene, key="map", on_click=callback)

`scene` comes from graph_view.View.scene(). A click on a node (or on the background, id = None) arrives as
st.session_state["map"].click == {"id": ..., "n": ...}.
"""
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).parent

_MAP = st.components.v2.component(
    "dependency_map",
    html="""<div class="stage">
  <canvas role="img" aria-label="Dependency map: accounts, projects and what each project depends on"></canvas>
  <span class="hint">Drag a node or the background. Scroll to zoom. Click a node to trace it.</span>
  <div class="legend"></div>
</div>""",
    css=(_HERE / "map.css").read_text(),
    js=(_HERE / "map.js").read_text(),
)


def dependency_map(scene, *, key="map", on_click=None):
    return _MAP(key=key, data=scene, width="stretch", height="content", on_click_change=on_click or (lambda: None))
