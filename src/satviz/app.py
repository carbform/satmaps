"""The local app: pick one or two products, draw the area on a map, make the figure. The wording, the look and the false-colour
channels are in pop-ups beside the button.

Run it with `satviz app` (needs `pip install "satviz[app]"`). It holds no figure logic: it collects choices and calls
`satviz.api.build_job` and `satviz.run.run_job`, the same path as `satviz quick`; the preview is drawn by the same
arrangements and themes (`satviz.preview`). The page is served on localhost and nothing is uploaded. The one thing fetched is the
map's OpenStreetMap tiles, by your browser, and only while "Show the OpenStreetMap basemap" is ticked.

Settings come from the environment, set by `satviz app`: SATVIZ_DATA_DIR (where the products are), SATVIZ_OUT_DIR and
SATVIZ_CACHE_DIR (absolute, because the script runs from wherever Streamlit was started).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # the CLI sets this in main(); the app never goes through it

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from satviz.api import SAR_CHANNELS, TooLarge, auto_layout, band_choices, build_job, inspect, job_toml, layout_choices, scan  # noqa: E402
from satviz.app_style import stylesheet  # noqa: E402
from satviz.area import AreaError  # noqa: E402
from satviz.autoarea import common_area, coverage, group_by_ground, touches  # noqa: E402
from satviz.core import THEMES  # noqa: E402
from satviz.desktop import DesktopError, choose_folder
from satviz.detect import DetectError  # noqa: E402
from satviz.furniture import Furniture  # noqa: E402
from satviz.job import JobError  # noqa: E402
from satviz.layout import LayoutError  # noqa: E402
from satviz.preview import render_example  # noqa: E402
from satviz.quality import PROFILES  # noqa: E402
from satviz.registry import load_builtin  # noqa: E402
from satviz.run import run_job  # noqa: E402
from satviz.sources import SourceError  # noqa: E402

load_builtin()
USER_ERRORS = (TooLarge, DetectError, JobError, AreaError, SourceError, LayoutError, FileNotFoundError, KeyError, ValueError,
               ImportError)
BOX_KEYS = ("box_w", "box_s", "box_e", "box_n")
MAX_PRODUCTS = 2
OVERLAP, BOX = "Overlap of the products", "A box I choose"
AUTOMATIC = "Automatic"
area_map = components.declare_component("satviz_area_map", path=str(Path(__file__).parent / "app_component"))


@st.cache_resource
def render_lock() -> threading.Lock:
    """Matplotlib's state is global, so one figure is drawn at a time, whichever session asks."""
    return threading.Lock()


@st.cache_data(show_spinner=False)
def scan_folder(folder: str, stamp: int) -> list[dict]:
    """The products in a folder; `stamp` changes when the person presses Rescan or picks another folder."""
    return scan(folder)


@st.cache_data(show_spinner=False)
def footprint_of(path: str, mtime: float) -> dict:
    """Where a product has data (its footprint is read once; `mtime` makes a changed file read again)."""
    info = inspect(path)
    return {"kind": info["kind"], "ring": info["footprint"], "bbox": info["bbox"]}


@st.cache_data(show_spinner=False)
def example_page(kinds: tuple, layout: str, theme: str, words: tuple = (), furniture: tuple = (True, False, False),
                 channels: tuple = ()) -> bytes:
    """The example page for a layout, a theme, the kinds of products chosen, the wording typed so far, the map furniture and the
    false-colour channels picked."""
    scale, north, grid = furniture
    return render_example(list(kinds), layout, theme, furniture=Furniture(scale=scale, north=north, grid=grid),
                          channels={k: v for k, v in channels}, **dict(words))


def browse() -> None:
    """Button callback: ask the operating system for a folder (before the text box is drawn, so it can be set)."""
    st.session_state["folder_note"] = ""
    try:
        picked = choose_folder(st.session_state["folder"])
    except DesktopError as e:
        st.session_state["folder_note"] = str(e)
        return
    if picked:
        st.session_state["folder"] = picked
        st.session_state["stamp"] += 1


def use_suggested_box() -> None:
    """Button callback: fill the box fields from the large-area suggestion and switch to them."""
    for key, value in zip(BOX_KEYS, st.session_state["suggestion"], strict=True):
        st.session_state[key] = float(value)
    st.session_state["area_mode"] = BOX
    st.session_state["suggestion"] = None


def label(row: dict) -> str:
    return f"{row['sensor']} ({row['kind']})  ·  {row['name']}"  # the sensor first: the name is long and the tag cuts it off


def render(chosen: list[str], options: dict) -> None:
    """Draw the figure for the chosen products and keep it in the session; an error is kept as a message instead."""
    out, cache = Path(os.environ["SATVIZ_OUT_DIR"]), Path(os.environ["SATVIZ_CACHE_DIR"])
    st.session_state["error"] = st.session_state["results"] = st.session_state["suggestion"] = None
    try:
        with render_lock():
            job, raw = build_job(chosen, **options)
            toml = job_toml(raw)
            results = [{"png": p, "pdf": p.with_suffix(".pdf") if p.with_suffix(".pdf").exists() else None, "toml": toml,
                        "name": p.stem} for p in run_job(job, out, cache)]
    except TooLarge as e:
        st.session_state["error"] = str(e)
        st.session_state["suggestion"] = e.suggestion
        return
    except USER_ERRORS as e:
        st.session_state["error"] = str(e.args[0]) if isinstance(e, KeyError) and e.args else str(e)
        return
    st.session_state["results"] = results


def leave_out(labels: list[str]) -> None:
    """Button callback: take these products out of the selection."""
    st.session_state["picked"] = [x for x in st.session_state["picked"] if x not in labels]


def show_results(results: list[dict], key_prefix: str = "", show_job: bool = True) -> None:
    """Each figure with its downloads; several figures (a layout that makes one per product or pair) get a tab each."""
    spots = st.tabs([r["name"] for r in results]) if len(results) > 1 else [st.container()]
    for spot, r in zip(spots, results, strict=True):
        with spot:
            st.image(str(r["png"]), use_column_width=True)
            a, b, c = st.columns(3)
            a.download_button("Download PNG", r["png"].read_bytes(), f"{r['name']}.png", "image/png",
                              key=f"{key_prefix}png_{r['name']}")
            if r["pdf"]:
                b.download_button("Download PDF", r["pdf"].read_bytes(), f"{r['name']}.pdf", "application/pdf",
                                  key=f"{key_prefix}pdf_{r['name']}")
            c.download_button("Download job file", r["toml"], f"{r['name']}.toml", "text/plain",
                              key=f"{key_prefix}toml_{r['name']}", help="Run it again with `satviz run`, or edit it first")
    if show_job:  # (not inside another expander: Streamlit does not nest them)
        with st.expander("The job file behind this figure"):
            st.code(results[0]["toml"], language="toml")


def apply_drawn(state, drawn: dict | None) -> bool:
    """Write what the map sent back into the session: a new rectangle fills the four fields and switches the area to the box;
    Clear switches it back to the overlap. A value already applied (the map keeps sending its last one) is ignored.
    Returns whether anything changed."""
    if not drawn or drawn["n"] == state["last_draw"]:
        return False
    state["last_draw"] = drawn["n"]
    if drawn["box"]:
        for key, value in zip(BOX_KEYS, drawn["box"], strict=True):
            state[key] = round(float(value), 4)
        state["area_mode"] = BOX
    else:
        state["area_mode"] = OVERLAP
    return True


def area_section(chosen_rows: list[dict], by_label: dict) -> tuple[str, tuple | None, list[str], bool]:
    """Step 2: where the products are, on a map you can draw on, and the area that results.

    Returns (mode, box, outside, apart): `outside` names the products a drawn box does not touch (they cannot be drawn in it);
    `apart` is True when two products share no ground (a figure needs products that overlap)."""
    st.markdown("##### 2 · Area")
    prints = [{"name": r["name"][:24], **footprint_of(r["path"], Path(r["path"]).stat().st_mtime)} for r in chosen_rows]
    prints = [p for p in prints if p["ring"]]
    overlap, apart = None, False
    if len(prints) == len(chosen_rows) > 1:
        apart = len(group_by_ground([p["ring"] for p in prints])) > 1
        if not apart:
            overlap = [round(v, 4) for v in common_area({str(i): p["ring"] for i, p in enumerate(prints)}).lonlat_bbox()]
    if apart:
        st.error("These two products do not overlap: they cover different ground. A figure shows products that share ground, "
                 "so choose two that do (or leave one out).")
    box = [st.session_state[k] for k in BOX_KEYS] if st.session_state["area_mode"] == BOX and all(
        st.session_state[k] for k in BOX_KEYS) else None
    drawn = area_map(footprints=[{"name": p["name"], "kind": p["kind"], "ring": p["ring"]} for p in prints], overlap=overlap,
                     box=box, basemap=bool(st.session_state.get("basemap", True)),
                     dark=bool(st.session_state.get("dark", False)), key="area_map", default=None)
    apply_drawn(st.session_state, drawn)
    if not chosen_rows:  # the map of India waits for products; drawing a box before choosing any would have nothing to apply to
        st.caption("Choose one or two products in the sidebar (step 1): they appear here, and you can draw the area you want.")
        st.checkbox("OpenStreetMap basemap", value=True, key="basemap")
        return OVERLAP, None, [], False
    st.caption("Drag to draw the area · wheel to zoom · right-drag or shift-drag to move. The dashed rectangle is what is drawn "
               "when you draw nothing.")
    a, b = st.columns([3, 2])
    mode = a.radio("Area", [OVERLAP, BOX], key="area_mode", horizontal=True, label_visibility="collapsed")
    b.checkbox("OpenStreetMap basemap", value=True, key="basemap",
               help="Your browser fetches map tiles from openstreetmap.org, which sees roughly where you look. Untick to keep "
                    "the map to your data alone: nothing is then fetched.")
    box, outside = None, []
    if mode == BOX:
        cols = st.columns(4)
        for col, key, name in zip(cols, BOX_KEYS, ("West", "South", "East", "North"), strict=True):
            col.number_input(name, key=key, format="%.4f", step=0.05)
        box = tuple(st.session_state[k] for k in BOX_KEYS)
        for row in chosen_rows:  # say so before drawing: a box that misses a product leaves its panel empty
            ring = footprint_of(row["path"], Path(row["path"]).stat().st_mtime)["ring"]
            share = coverage(ring, box) if ring else 1.0
            if ring and not touches(ring, box):
                outside.append(label(row))
            elif share < 0.95:
                st.warning(f"{row['name'][:30]} has data in {share:.0%} of this box.")
        if outside:
            names = ", ".join(by_label[x]["name"][:30] for x in outside)
            st.error(f"This box is outside {names}: there is nothing of it to draw here.")
            st.button("Leave out the products outside the box", on_click=leave_out, args=(outside,))
    return mode, box, outside, apart


def summary(chosen_rows: list[dict], mode: str, box: tuple | None, outside: bool, apart: bool) -> tuple[bool, str]:
    """(ready, message): ready with no message, or what to do first. `mode` and `box` are kept for callers that say more."""
    if not chosen_rows:
        return False, "Not yet: choose a product in the sidebar (step 1)."
    if apart:
        return False, "Not yet: the two products cover different ground. Choose two that overlap."
    if outside:
        return False, "Not yet: the box misses some products. Redraw the box on the map, or leave those products out."
    return True, ""


def details_section() -> dict:
    """The wording, the same for every sensor. Sensors' own credits are always added; this adds to them."""
    st.text_input("Title", key="title", placeholder="left empty: says what the figure shows")
    st.text_input("Subtitle", key="subtitle", placeholder="left empty: says how the products relate")
    st.text_input("Place", key="place", placeholder="e.g. Dibrugarh, Assam")
    a, b = st.columns(2)
    a.text_input("Author", key="author")
    b.text_input("Website", key="website")
    st.text_input("Extra credit", key="credits", placeholder="e.g. Field photos by …",
                  help="One more credit line. The credits the products require (Copernicus, NISAR, NRSC/ISRO…) are always "
                       "printed.")
    return {k: st.session_state[k] or None for k in ("title", "subtitle", "place", "author", "website", "credits")}


def look_section(kinds: list[str]) -> dict:
    """How it looks: theme, layout and map furniture."""
    a, b = st.columns(2)
    theme = a.selectbox("Theme", sorted(THEMES), index=sorted(THEMES).index("minimal"))
    choices = layout_choices(kinds)
    layout_name = b.selectbox("Layout", [AUTOMATIC, *choices.values()],
                              help="How the products sit on the page. Automatic: one product alone, two side by side. Products "
                                   "of any sensors, tracks, frames or dates can be shown together: each panel and each legend "
                                   "item names its own product.")
    layout = None if layout_name == AUTOMATIC else next(k for k, v in choices.items() if v == layout_name)
    st.markdown("**Map furniture**")
    f1, f2, f3 = st.columns(3)
    grid = f1.checkbox("Lat/lon grid", value=False, help="Grid lines with latitude and longitude labels on every panel.")
    north = f2.checkbox("North arrow", value=False, help="Points at true north.")
    scalebar = f3.checkbox("Scale bar", value=True)
    return dict(theme=theme, layout=layout, grid=grid, north=north, scalebar=scalebar)


def pick_channels(prefix: str, options: dict, defaults: tuple) -> tuple:
    """Three selectors, red, green and blue, over `options` ({value: label}); a stale choice (the products changed) resets."""
    labels = list(options.values())
    back = {label: value for value, label in options.items()}
    picks = []
    for col, name, default in zip(st.columns(3), ("Red", "Green", "Blue"), defaults, strict=True):
        key = f"{prefix}_{name}"
        if key in st.session_state and st.session_state[key] not in labels:
            del st.session_state[key]
        picks.append(back[col.selectbox(name, labels, index=labels.index(options[default]), key=key)])
    return tuple(picks)


def channels_section(rows: list[dict]) -> dict:
    """The false-colour composite (FCC): which radar channel or optical band is drawn in red, green and blue. Returns the
    choices as {'sar': (r, g, b), 'optical': (r, g, b)} for the kinds chosen."""
    out = {}
    if not rows:
        st.caption("Choose products first: the channels depend on what they hold.")
        return out
    if any(r["kind"] == "sar" for r in rows):
        st.markdown("**Radar**")
        out["sar"] = pick_channels("fcc_sar", dict(SAR_CHANNELS), ("co", "cross", "ratio"))
        st.caption("Co and cross are the product's own polarisations (HH/HV, VV/VH…); the ratio is co ÷ cross in dB. "
                   "Compact-pol (RH/RV) products are drawn with the m-χ decomposition instead.")
    optical = [r for r in rows if r["kind"] == "optical"]
    if optical:
        st.markdown("**Optical**")
        bands = dict(band_choices([r["sensor"] for r in optical]))
        if len(bands) < 3:
            st.caption("These optical products share fewer than three bands, so they keep their usual composite.")
        else:
            natural = ("red", "green", "blue") if {"red", "green", "blue"} <= set(bands) else ("nir", "red", "green")
            out["optical"] = pick_channels("fcc_opt", bands, natural if set(natural) <= set(bands) else tuple(bands)[:3])
            st.caption("Red, green, blue = red, green, blue bands is true colour; anything else is a false-colour composite.")
    if len(rows) == 2 and rows[0]["kind"] == rows[1]["kind"]:
        st.caption("Both products use the same channels, so the colours mean the same in each.")
    return out


def quality_choice() -> str:
    """The quality profile, as a select that fits the top bar (its label is the first words of the option)."""
    picked = st.selectbox("Quality", [f"Quality: {name}" for name in PROFILES], label_visibility="collapsed",
                          help="quick: a small PNG in seconds · medium: finer · publication: full size, with a PDF")
    return picked.split(": ")[1]


HELP = """
**Make a figure in four steps**

1. **Products** (sidebar): pick the folder, then one or two products. Two must cover the same ground.
2. **Area**: leave it, and the figure covers what the products share. Or drag a rectangle on the map to choose a place.
3. **Make the figure** (top left). The page below shows what you will get; press the button to draw it with your data.
4. **Download** the PNG (and a PDF at publication quality), or the job file that reproduces it.

**The pop-ups at the top**

- **Quality**: quick is a small PNG in seconds, medium is finer, publication is full size with a PDF.
- **Title & credits**: your own wording. Left empty, the figure titles itself;
  the credits each product requires are always printed.
- **Look**: theme, page layout, and map furniture (lat/lon grid, north arrow, scale bar).
- **Colours**: the false-colour composite (FCC): which radar channel or optical band is drawn in red, green and blue.

**False-colour composite**

Three layers are assigned to red, green and blue. For radar they are HH, HV or their ratio HH/HV (or VV, VH, VV/VH). For
optical they are any three bands: red, green, blue is true colour; near-infrared, red, green shows vegetation in red.
The legend on the figure says what each colour is.

**Good to know**

- At most two products at once.
- A very large area is refused with a suggested box: press *Use the suggested box*.
- Everything runs on this machine. Only the map tiles come from openstreetmap.org, and you can untick that.
"""


def figure_pane(kinds: list[str], words: dict, look: dict, channels: dict, signature: tuple) -> None:
    """The one pane for the page you will get and the figure you made: the example page follows every change you make to the
    theme, layout or wording; the figure appears when you press the button and gives way to the example when settings change."""
    results, fresh = st.session_state["results"], st.session_state["made_with"] == signature
    layout = look["layout"] or (auto_layout(kinds) if kinds else "single")
    if st.session_state["error"]:
        st.error(st.session_state["error"])
        if st.session_state["suggestion"]:
            st.button("Use the suggested box", on_click=use_suggested_box)
    if results and fresh:
        show_results(results)
        return
    if results:
        st.info("The settings have changed since this figure was made. This is the page they give: press **Make the figure** "
                "to draw it with your data.")
    st.image(example_page(tuple(kinds), layout, look["theme"], tuple(sorted((k, v) for k, v in words.items() if v)),
                          (look["scalebar"], look["north"], look["grid"]), tuple(sorted(channels.items()))),
             use_column_width=True)
    if results:
        with st.expander("The figure made before the change"):
            show_results(results, key_prefix="old_", show_job=False)


def main() -> None:
    st.set_page_config(page_title="satviz", page_icon="🛰", layout="wide")
    title, mode_switch = st.columns([6, 1])
    title.title("satviz")
    dark = mode_switch.toggle("Dark mode", key="dark")
    st.markdown(stylesheet(dark), unsafe_allow_html=True)
    defaults = {"results": None, "error": None, "suggestion": None, "stamp": 0, "area_mode": OVERLAP, "last_draw": 0,
                "folder": os.environ.get("SATVIZ_DATA_DIR", "data"), "folder_note": "", "made_with": None, "picked": [],
                "dark": False,
                **dict.fromkeys(("title", "subtitle", "place", "author", "website", "credits"), "")}
    for key, default in {**defaults, **dict.fromkeys(BOX_KEYS, 0.0)}.items():
        st.session_state.setdefault(key, default)

    top = st.container()  # the button and the pop-ups sit at the top; they are filled in once the area is known

    with st.sidebar:
        st.header("1 · Products")
        st.caption("Pick the folder that holds your data, then choose one or two products that overlap.")
        st.text_input("Folder", key="folder")
        a, b = st.columns(2)
        a.button("Browse…", on_click=browse, help="Choose the folder in your system's own dialog")
        if b.button("Rescan"):
            st.session_state["stamp"] += 1
        if st.session_state["folder_note"]:
            st.caption(st.session_state["folder_note"])
        try:
            rows = scan_folder(st.session_state["folder"], st.session_state["stamp"])
        except ValueError as e:
            st.error(str(e))
            rows = []
        products = [r for r in rows if r["sensor"]]
        by_label = {label(r): r for r in products}
        picked = st.multiselect("Choose one or two", list(by_label), key="picked", max_selections=MAX_PRODUCTS)
        chosen_rows = [by_label[name] for name in picked]
        chosen = [r["path"] for r in chosen_rows]
        zips = [r["name"] for r in rows if not r["sensor"]]
        if zips:
            with st.expander(f"{len(zips)} zip{'s' if len(zips) > 1 else ''} skipped"):
                st.caption("The readers take unzipped folders: unzip these into the folder, then press Rescan.")
                st.write("\n".join(f"- {z}" for z in zips))
        if not products and not zips:
            st.info("No products found in this folder.")

    kinds = [r["kind"] for r in chosen_rows]
    left, right = st.columns(2)
    with left:
        mode, box, outside, apart = area_section(chosen_rows, by_label)

    with top:
        cells = st.columns(6)  # an equal grid: every control the same width and height
        ready, said = summary(chosen_rows, mode, box, bool(outside), apart)
        go = cells[0].button("Make the figure", type="primary", disabled=not ready, use_container_width=True)
        with cells[1]:
            quality = quality_choice()
        with cells[2].popover("Title & credits", use_container_width=True):
            words = details_section()
        with cells[3].popover("Look", use_container_width=True):
            look = look_section(kinds)
        with cells[4].popover("Colours", use_container_width=True):
            channels = channels_section(chosen_rows)
        with cells[5].popover("Help", use_container_width=True):
            st.markdown(HELP)
        if not ready:
            st.warning(said)

    signature = (tuple(chosen), mode, box, quality, tuple(sorted(words.items(), key=lambda kv: kv[0])), tuple(sorted(
        (k, str(v)) for k, v in look.items())), tuple(sorted(channels.items())))
    if go:
        options = dict(theme=look["theme"], quality=quality, area=box, arrangement=look["layout"],
                       bands=look["layout"] == "bands", grid=look["grid"], north=look["north"], scalebar=look["scalebar"],
                       channels=channels, **words)
        with right, st.spinner("Reading the products and drawing…"):
            render(chosen, options)
        st.session_state["made_with"] = signature
    with right:
        st.markdown("##### Figure")
        figure_pane(kinds, words, look, channels, signature)


if __name__ == "__main__":  # Streamlit runs the script as __main__; importing the module (the tests do) draws nothing
    main()
