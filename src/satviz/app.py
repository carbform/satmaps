"""The local app: pick products, choose a layout and a theme, see the page, draw the area, make the figure, download it.

Run it with `satviz app` (needs `pip install "satviz[app]"`). It holds no figure logic: it collects choices and calls
`satviz.api.build_job` and `satviz.run.run_job`, the same path as `satviz quick`; the layout preview is drawn by the same
arrangements and themes (`satviz.preview`). Everything stays on this machine: the page is served on localhost, nothing is
uploaded, and nothing is fetched.

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

from satviz.api import TooLarge, auto_layout, build_job, inspect, job_toml, layout_choices, scan  # noqa: E402
from satviz.area import AreaError  # noqa: E402
from satviz.autoarea import common_area, coverage  # noqa: E402
from satviz.core import THEMES  # noqa: E402
from satviz.desktop import DesktopError, choose_folder  # noqa: E402
from satviz.detect import DetectError  # noqa: E402
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
def example_page(kinds: tuple, layout: str, theme: str) -> bytes:
    """The example page for a layout, a theme and the kinds of products chosen."""
    return render_example(list(kinds), layout, theme)


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
    """Draw the figures for the chosen products and keep them in the session; an error is kept as a message instead."""
    out, cache = Path(os.environ["SATVIZ_OUT_DIR"]), Path(os.environ["SATVIZ_CACHE_DIR"])
    st.session_state["error"] = st.session_state["results"] = st.session_state["suggestion"] = None
    try:
        with render_lock():
            job, raw = build_job(chosen, **options)
            pngs = run_job(job, out, cache)
    except TooLarge as e:
        st.session_state["error"] = str(e)
        st.session_state["suggestion"] = e.suggestion
        return
    except USER_ERRORS as e:
        st.session_state["error"] = str(e.args[0]) if isinstance(e, KeyError) and e.args else str(e)
        return
    toml = job_toml(raw)
    st.session_state["results"] = [{"png": p, "pdf": p.with_suffix(".pdf") if p.with_suffix(".pdf").exists() else None,
                                    "toml": toml, "name": p.stem} for p in pngs]


def show_results(results: list[dict]) -> None:
    """Each figure with its downloads; several figures (a layout that makes one per product or pair) get a tab each."""
    spots = st.tabs([r["name"] for r in results]) if len(results) > 1 else [st.container()]
    for spot, r in zip(spots, results, strict=True):
        with spot:
            st.image(str(r["png"]), use_column_width=True)
            a, b, c = st.columns(3)
            a.download_button("Download PNG", r["png"].read_bytes(), f"{r['name']}.png", "image/png", key=f"png_{r['name']}")
            if r["pdf"]:
                b.download_button("Download PDF", r["pdf"].read_bytes(), f"{r['name']}.pdf", "application/pdf",
                                  key=f"pdf_{r['name']}")
            c.download_button("Download job file", r["toml"], f"{r['name']}.toml", "text/plain", key=f"toml_{r['name']}",
                              help="Run it again with `satviz run`, or edit it first")
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


def area_tab(chosen_rows: list[dict]) -> None:
    """Where the products are, with a rectangle to draw: the box you draw is written to the fields on the left."""
    if not chosen_rows:
        st.info("Choose products on the left to see where they are, and draw the area you want on the map.")
        return
    prints = [{"name": r["name"][:24], **footprint_of(r["path"], Path(r["path"]).stat().st_mtime)} for r in chosen_rows]
    prints = [p for p in prints if p["ring"]]
    overlap = None
    if prints:
        try:
            a = common_area({str(i): p["ring"] for i, p in enumerate(prints)}).lonlat_bbox()
            overlap = [round(v, 4) for v in a]
        except AreaError:
            st.warning("These products share no ground: they do not overlap, so draw a box over the one you want, or drop one.")
    box = [st.session_state[k] for k in BOX_KEYS] if st.session_state["area_mode"] == BOX and all(
        st.session_state[k] for k in BOX_KEYS) else None
    drawn = area_map(footprints=[{"name": p["name"], "kind": p["kind"], "ring": p["ring"]} for p in prints], overlap=overlap,
                     box=box, key="area_map", default=None)
    apply_drawn(st.session_state, drawn)
    st.caption("Drag on the map to draw the area. The dashed rectangle is what is drawn when you draw nothing.")


def main() -> None:
    st.set_page_config(page_title="satviz", page_icon="🛰", layout="wide")
    st.title("satviz")
    st.caption("Quick looks and publication figures from SAR (NISAR, Sentinel-1, EOS-04) and optical (Sentinel-2, LISS-IV) "
               "products. Everything runs on this machine.")
    defaults = {"results": None, "error": None, "suggestion": None, "stamp": 0, "area_mode": OVERLAP, "last_draw": 0,
                "folder": os.environ.get("SATVIZ_DATA_DIR", "data"), "folder_note": ""}
    for key, default in {**defaults, **dict.fromkeys(BOX_KEYS, 0.0)}.items():
        st.session_state.setdefault(key, default)

    with st.sidebar:
        st.header("Products")
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
        picked = st.multiselect("Choose one or more", list(by_label))
        chosen_rows = [by_label[name] for name in picked]
        chosen = [r["path"] for r in chosen_rows]
        zips = [r["name"] for r in rows if not r["sensor"]]
        if zips:
            with st.expander(f"{len(zips)} zip{'s' if len(zips) > 1 else ''} skipped"):
                st.caption("The readers take unzipped folders: unzip these into the folder, then press Rescan.")
                st.write("\n".join(f"- {z}" for z in zips))
        if not products and not zips:
            st.info("No products found in this folder.")

    left, right = st.columns([1, 2])
    with right:
        figure_tab, preview_tab, area_tab_ = st.tabs(["Figure", "Layout preview", "Area"])
    with area_tab_:  # before the fields on the left: a drawn box is written to them
        area_tab(chosen_rows)

    kinds = [r["kind"] for r in chosen_rows]
    with left:
        st.subheader("Figure")
        theme = st.selectbox("Theme", sorted(THEMES), index=sorted(THEMES).index("minimal"))
        choices = layout_choices(kinds)
        names = [AUTOMATIC, *choices.values()]
        layout_name = st.selectbox("Layout", names, help="How the products sit on the page. Automatic: one product alone, "
                                   "two side by side, three to six on one page.")
        layout = None if layout_name == AUTOMATIC else next(k for k, v in choices.items() if v == layout_name)
        quality = st.radio("Quality", list(PROFILES), horizontal=True,
                           help="quick: a small PNG in seconds · medium: finer · publication: full size, with a PDF")
        title = st.text_input("Title", placeholder="left empty: says what the figure shows")
        mode = st.radio("Area", [OVERLAP, BOX], key="area_mode")
        box = None
        if mode == BOX:
            cols = st.columns(4)
            for col, key, name in zip(cols, BOX_KEYS, ("West", "South", "East", "North"), strict=True):
                col.number_input(name, key=key, format="%.4f", step=0.05)
            box = tuple(st.session_state[k] for k in BOX_KEYS)
            for row in chosen_rows:  # say so before drawing: a box that misses a product leaves its panel empty
                ring = footprint_of(row["path"], Path(row["path"]).stat().st_mtime)["ring"]
                share = coverage(ring, box) if ring else 1.0
                if share < 0.95:
                    st.warning(f"{row['name'][:30]} has data in {share:.0%} of this box.")
        different = st.checkbox("Allow NISAR products from different passes")
        large = st.checkbox("Draw a very large area anyway (slow)")
        go = st.button("Make the figure", type="primary", disabled=not chosen)

    if go:
        options = dict(theme=theme, quality=quality, title=title or None, area=box, arrangement=layout,
                       bands=layout == "bands", allow_different_passes=different, allow_large=large)
        with right, st.spinner("Reading the products and drawing…"):
            render(chosen, options)

    shown_layout = layout or (auto_layout(kinds) if kinds else "single")
    with preview_tab:
        st.image(example_page(tuple(kinds), shown_layout, theme), use_column_width=True)
        st.caption("An example page in this layout and theme, with made-up pictures: your products fill the panels, and their "
                   "own notices and credits appear where the examples are.")
    with figure_tab:
        if st.session_state["error"]:
            st.error(st.session_state["error"])
            if st.session_state["suggestion"]:
                st.button("Use the suggested box", on_click=use_suggested_box)
        if st.session_state["results"]:
            show_results(st.session_state["results"])
        elif not st.session_state["error"]:
            st.info("Choose products, a layout and a theme, then press **Make the figure**. This is the page it will use.")
            st.image(example_page(tuple(kinds), shown_layout, theme), use_column_width=True)


if __name__ == "__main__":  # Streamlit runs the script as __main__; importing the module (the tests do) draws nothing
    main()
