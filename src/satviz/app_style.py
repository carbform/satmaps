# ruff: noqa: E501  (stylesheet lines are CSS, kept one rule to a line)
"""The app's look: the monospace, hairline-border, 8 px-radius style of carbsat (IBM Plex Mono, one blue accent), light or dark.

One stylesheet, injected on every run, with the palette of the mode the person switched to. It sets every text and surface colour
itself, so the page reads the same whatever theme Streamlit or the operating system is in. The font ships with the package (SIL Open
Font License, `app_assets/OFL.txt`) and is embedded in the page, so nothing is fetched from a font service. The controls in the top
bar share one height and sit on an equal grid.
"""
from __future__ import annotations

import base64
from functools import cache
from pathlib import Path

# ink, muted, line, paper (page), tint (side panel, hover), field (inputs), accent, accent_hover, on_accent
LIGHT = dict(ink="#2c3e50", muted="#6b7a89", line="#e0e0e0", paper="#ffffff", tint="#f8f9fa", field="#ffffff",
             accent="#3d82cc", hover="#0056b3", on_accent="#ffffff", info="#e8f1fb", warn="#fff8e1", bad="#fdecea", good="#e6f4ea")
DARK = dict(ink="#cdd9e5", muted="#8892b0", line="#444c56", paper="#22272e", tint="#1c2128", field="#2d333b",
            accent="#3d82cc", hover="#58a6ff", on_accent="#ffffff", info="#1d2d44", warn="#3a3220", bad="#3d2426", good="#1f3a2a")
CONTROL_H = "2.75rem"  # every control in the top bar


@cache
def _font() -> str:
    return base64.b64encode((Path(__file__).parent / "app_assets" / "IBMPlexMono-Regular.ttf").read_bytes()).decode()


def stylesheet(dark: bool = False) -> str:
    c = DARK if dark else LIGHT
    return f"""<style>
@font-face {{ font-family: 'IBM Plex Mono'; font-weight: 400; font-style: normal;
  src: url(data:font/ttf;base64,{_font()}) format('truetype'); }}
html, body, .stApp, [class*="st-"], button, input, textarea, select {{
  font-family: 'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace !important; }}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background: {c['paper']}; }}
.stApp, .stApp p, .stApp span, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5,
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stWidgetLabel"] p {{ color: {c['ink']}; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1500px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
header[data-testid="stHeader"] *, [data-testid="stToolbar"] * {{ color: {c['muted']} !important; }}
h1 {{ font-size: 1.5rem !important; letter-spacing: 0.04em; font-weight: 400 !important; padding: 0 0 0.9rem 0 !important;
  border-bottom: 1px solid {c['line']}; margin-bottom: 1rem; }}
h5, h2, h3 {{ font-size: 0.8rem !important; text-transform: uppercase; letter-spacing: 0.12em; color: {c['muted']} !important;
  font-weight: 400 !important; padding: 0.2rem 0 0.4rem 0 !important; }}
[data-testid="stSidebar"] {{ background: {c['tint']}; border-right: 1px solid {c['line']}; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, .stCaption {{ color: {c['muted']}; font-size: 0.74rem; }}
label, [data-testid="stWidgetLabel"] p {{ font-size: 0.74rem !important; color: {c['muted']} !important; letter-spacing: 0.04em; }}
[data-testid="stCheckbox"] label p, [data-testid="stRadio"] label p {{ color: {c['ink']} !important; }}

/* buttons, and the pop-up buttons: one height, one text colour set on the button and everything inside it */
div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{ min-width: 0; }}
.stButton button, [data-testid="stPopover"] button, .stDownloadButton button {{
  width: 100%; height: {CONTROL_H}; min-height: {CONTROL_H}; border-radius: 8px; border: 1px solid {c['line']};
  background: {c['field']}; transition: border-color .2s ease, background .2s ease; }}
.stButton button *, [data-testid="stPopover"] button *, .stDownloadButton button * {{
  color: {c['ink']} !important; font-size: 0.82rem !important; letter-spacing: 0.04em; white-space: nowrap; }}
.stButton button:hover, [data-testid="stPopover"] button:hover, .stDownloadButton button:hover {{
  border-color: {c['accent']}; background: {c['tint']}; }}
.stButton button:hover *, [data-testid="stPopover"] button:hover *, .stDownloadButton button:hover * {{
  color: {c['accent']} !important; }}
.stButton button[kind="primary"] {{ background: {c['accent']}; border-color: {c['accent']}; }}
.stButton button[kind="primary"] * {{ color: {c['on_accent']} !important; }}
.stButton button[kind="primary"]:hover {{ background: {c['hover']}; border-color: {c['hover']}; }}
.stButton button[kind="primary"]:hover * {{ color: {c['on_accent']} !important; }}
.stButton button:disabled {{ background: {c['tint']}; border-color: {c['line']}; opacity: .75; }}
.stButton button:disabled * {{ color: {c['muted']} !important; }}

/* the dark-mode switch: a track you can see on either page, whatever Streamlit's own theme */
label[data-baseweb="checkbox"]:has(input[aria-label="Dark mode"]) p {{ color: {c['ink']} !important; font-size: 0.78rem !important; }}
label[data-baseweb="checkbox"]:has(input[aria-label="Dark mode"]) > div:first-child {{ background: {c['line']} !important; border: 1px solid {c['muted']}; }}
label[data-baseweb="checkbox"]:has(input[aria-label="Dark mode"]):has(input:checked) > div:first-child {{ background: {c['accent']} !important; border-color: {c['accent']}; }}
label[data-baseweb="checkbox"]:has(input[aria-label="Dark mode"]) > div:first-child > div {{ background: {c['paper']} !important; border: 1px solid {c['muted']}; }}

/* fields and menus */
div[data-baseweb="select"] > div, div[data-baseweb="input"], div[data-baseweb="base-input"], .stTextInput input, .stNumberInput input {{
  border-radius: 8px; border-color: {c['line']}; background: {c['field']} !important; color: {c['ink']} !important; }}
div[data-baseweb="select"] > div {{ min-height: {CONTROL_H}; }}
div[data-baseweb="select"] *, .stTextInput input, .stNumberInput input {{ font-size: 0.82rem !important; color: {c['ink']} !important; }}
div[data-baseweb="select"] svg {{ fill: {c['muted']} !important; }}
div[data-baseweb="popover"] > div, ul[role="listbox"], [data-testid="stPopoverBody"] {{
  background: {c['paper']} !important; border: 1px solid {c['line']}; color: {c['ink']}; }}
ul[role="listbox"] li {{ background: {c['paper']} !important; }}
ul[role="listbox"] li:hover, ul[role="listbox"] li[aria-selected="true"] {{ background: {c['tint']} !important; }}
[data-testid="stTooltipContent"], div[data-baseweb="tooltip"] div {{ background: {c['field']} !important; color: {c['ink']} !important; }}
span[data-baseweb="tag"] {{ background: {c['accent']} !important; }}
span[data-baseweb="tag"] * {{ color: {c['on_accent']} !important; }}
[data-testid="stAlert"] {{ border-radius: 8px; font-size: 0.78rem; padding: 0.5rem 0.8rem; background: {c['info']}; }}
[data-testid="stAlert"] * {{ color: {c['ink']} !important; }}
[data-testid="stAlert"] > div {{ background: transparent !important; }}
[data-testid="stExpander"] {{ border: 1px solid {c['line']}; border-radius: 8px; background: {c['paper']}; }}
[data-testid="stExpander"] summary {{ background: transparent; }}
[data-testid="stImage"] img {{ border: 1px solid {c['line']}; border-radius: 4px; }}
code, pre {{ background: {c['field']} !important; color: {c['ink']} !important; }}
hr {{ border-color: {c['line']}; }}
</style>"""
