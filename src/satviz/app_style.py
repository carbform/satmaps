"""The app's look: the monospace, hairline-border, 8 px-radius style of carbsat (IBM Plex Mono, light, one blue accent).

One stylesheet, injected once. The font ships with the package (SIL Open Font License, `app_assets/OFL.txt`) and is embedded in
the page, so nothing is fetched from a font service. The controls in the top bar share one height and sit on an equal grid.
"""
from __future__ import annotations

import base64
from functools import cache
from pathlib import Path

INK, MUTED, LINE, PAPER, TINT, ACCENT = "#2c3e50", "#7f8c8d", "#e0e0e0", "#ffffff", "#f8f9fa", "#3d82cc"
CONTROL_H = "2.75rem"  # every control in the top bar


@cache
def stylesheet() -> str:
    font = base64.b64encode((Path(__file__).parent / "app_assets" / "IBMPlexMono-Regular.ttf").read_bytes()).decode()
    return f"""<style>
@font-face {{ font-family: 'IBM Plex Mono'; font-weight: 400; font-style: normal;
  src: url(data:font/ttf;base64,{font}) format('truetype'); }}
html, body, .stApp, [class*="st-"], button, input, textarea, select {{
  font-family: 'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace !important; }}
.stApp {{ background: {PAPER}; color: {INK}; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1500px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
h1 {{ font-size: 1.5rem !important; letter-spacing: 0.04em; font-weight: 400 !important; padding: 0 0 0.9rem 0 !important;
  border-bottom: 1px solid {LINE}; margin-bottom: 1rem; }}
h5, h2, h3 {{ font-size: 0.8rem !important; text-transform: uppercase; letter-spacing: 0.12em; color: {MUTED};
  font-weight: 400 !important; padding: 0.2rem 0 0.4rem 0 !important; }}
[data-testid="stSidebar"] {{ background: {TINT}; border-right: 1px solid {LINE}; }}
[data-testid="stSidebar"] h2 {{ font-size: 0.8rem !important; }}
[data-testid="stCaptionContainer"], .stCaption {{ color: {MUTED}; font-size: 0.74rem; }}
label, [data-testid="stWidgetLabel"] p {{ font-size: 0.74rem !important; color: {MUTED}; letter-spacing: 0.04em; }}

/* the top bar: one row, equal cells, one height */
div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{ min-width: 0; }}
.stButton > button, [data-testid="stPopover"] > div > button, [data-testid="stPopover"] button,
.stDownloadButton > button {{
  width: 100%; height: {CONTROL_H}; min-height: {CONTROL_H}; border-radius: 8px; border: 1px solid {LINE};
  background: {PAPER}; color: {INK}; font-size: 0.82rem; letter-spacing: 0.04em; white-space: nowrap;
  transition: border-color .2s ease, background .2s ease; }}
.stButton > button:hover, [data-testid="stPopover"] button:hover, .stDownloadButton > button:hover {{
  border-color: {ACCENT}; color: {ACCENT}; background: {TINT}; }}
.stButton > button[kind="primary"] {{ background: {ACCENT}; border-color: {ACCENT}; color: #fff; }}
.stButton > button[kind="primary"]:hover {{ background: #0056b3; border-color: #0056b3; color: #fff; }}
.stButton > button:disabled {{ background: {TINT}; color: {MUTED}; border-color: {LINE}; opacity: .7; }}
button p, button div, button span {{ font-size: 0.82rem !important; letter-spacing: 0.04em; }}
div[data-baseweb="select"] * {{ font-size: 0.82rem !important; }}
div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
  border-radius: 8px; border-color: {LINE}; background: {PAPER}; font-size: 0.82rem; }}
div[data-baseweb="select"] > div {{ min-height: {CONTROL_H}; }}
[data-testid="stAlert"] {{ border-radius: 8px; font-size: 0.78rem; padding: 0.5rem 0.8rem; }}
[data-testid="stExpander"] {{ border: 1px solid {LINE}; border-radius: 8px; }}
[data-testid="stImage"] img {{ border: 1px solid {LINE}; border-radius: 4px; }}
hr {{ border-color: {LINE}; }}
</style>"""
