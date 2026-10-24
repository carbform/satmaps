"""The local app: pick products from a folder, choose how the figure looks, preview it, download it.

Run it with `satviz app` (needs `pip install "satviz[app]"`). It holds no figure logic: it collects choices and calls
`satviz.api.build_job` and `satviz.run.run_job`, the same path as `satviz quick`. Everything stays on this machine: the page is
served on localhost, nothing is uploaded, and nothing is fetched.

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

from satviz.api import TooLarge, build_job, job_toml, scan  # noqa: E402
from satviz.area import AreaError  # noqa: E402
from satviz.core import THEMES  # noqa: E402
from satviz.detect import DetectError  # noqa: E402
from satviz.job import JobError  # noqa: E402
from satviz.layout import LayoutError  # noqa: E402
from satviz.quality import PROFILES  # noqa: E402
from satviz.registry import load_builtin  # noqa: E402
from satviz.run import run_job  # noqa: E402
from satviz.sources import SourceError  # noqa: E402

load_builtin()
USER_ERRORS = (TooLarge, DetectError, JobError, AreaError, SourceError, LayoutError, FileNotFoundError, KeyError, ValueError,
               ImportError)
BOX_KEYS = ("box_w", "box_s", "box_e", "box_n")


@st.cache_resource
def render_lock() -> threading.Lock:
    """Matplotlib's state is global, so one figure is drawn at a time, whichever session asks."""
    return threading.Lock()


@st.cache_data(show_spinner=False)
def scan_folder(folder: str, stamp: int) -> list[dict]:
    """The products in a folder; `stamp` changes when the person presses Rescan."""
    return scan(folder)


def use_suggested_box() -> None:
    """Button callback: fill the box fields from the large-area suggestion and switch to them (runs before the widgets draw)."""
    for key, value in zip(BOX_KEYS, st.session_state["suggestion"], strict=True):
        st.session_state[key] = float(value)
    st.session_state["area_mode"] = "A box I choose"
    st.session_state["suggestion"] = None


def label(row: dict) -> str:
    return f"{row['sensor']} ({row['kind']})  ·  {row['name']}"  # the sensor first: the name is long and the tag cuts it off


def render(chosen: list[str], options: dict) -> None:
    """Draw the figure for the chosen products and keep the result in the session; an error is kept as a message instead."""
    out, cache = Path(os.environ["SATVIZ_OUT_DIR"]), Path(os.environ["SATVIZ_CACHE_DIR"])
    st.session_state["error"] = st.session_state["result"] = st.session_state["suggestion"] = None
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
    png = pngs[0]
    pdf = png.with_suffix(".pdf")
    st.session_state["result"] = {"png": png, "pdf": pdf if pdf.exists() else None, "toml": job_toml(raw), "name": png.stem}


def main() -> None:
    st.set_page_config(page_title="satviz", page_icon="🛰", layout="wide")
    st.title("satviz")
    st.caption("Quick looks and publication figures from SAR (NISAR, Sentinel-1, EOS-04) and optical (Sentinel-2, LISS-IV) "
               "products. Everything runs on this machine.")
    defaults = (("result", None), ("error", None), ("suggestion", None), ("stamp", 0), ("area_mode", "Overlap of the products"))
    for key, default in defaults:
        st.session_state.setdefault(key, default)
    for key, default in zip(BOX_KEYS, (0.0, 0.0, 0.0, 0.0), strict=True):
        st.session_state.setdefault(key, default)

    with st.sidebar:
        st.header("Products")
        folder = st.text_input("Folder", value=os.environ.get("SATVIZ_DATA_DIR", "data"))
        if st.button("Rescan"):
            st.session_state["stamp"] += 1
        try:
            rows = scan_folder(folder, st.session_state["stamp"])
        except ValueError as e:
            st.error(str(e))
            rows = []
        products = [r for r in rows if r["sensor"]]
        by_label = {label(r): r for r in products}
        picked = st.multiselect("Choose one or more", list(by_label))
        chosen = [by_label[name]["path"] for name in picked]
        zips = [r["name"] for r in rows if not r["sensor"]]
        if zips:
            with st.expander(f"{len(zips)} zip{'s' if len(zips) > 1 else ''} skipped"):
                st.caption("The readers take unzipped folders: unzip these into the folder, then press Rescan.")
                st.write("\n".join(f"- {z}" for z in zips))
        if not products and not zips:
            st.info("No products found in this folder.")

    left, right = st.columns([1, 2])
    with left:
        st.subheader("Figure")
        theme = st.selectbox("Look", sorted(THEMES), index=sorted(THEMES).index("minimal"))
        quality = st.radio("Quality", list(PROFILES), horizontal=True,
                           help="quick: a small PNG in seconds · medium: finer · publication: full size, with a PDF")
        title = st.text_input("Title", placeholder="left empty: says what the figure shows")
        mode = st.radio("Area", ["Overlap of the products", "A box I choose"], key="area_mode")
        box = None
        if mode == "A box I choose":
            c = st.columns(4)
            for col, key, name in zip(c, BOX_KEYS, ("West", "South", "East", "North"), strict=True):
                col.number_input(name, key=key, format="%.4f", step=0.05)
            box = tuple(st.session_state[k] for k in BOX_KEYS)
        kinds = {by_label[name]["kind"] for name in picked}
        bands = st.checkbox("One panel per spectral band", disabled=kinds != {"optical"} or len(chosen) != 1)
        different = st.checkbox("Allow NISAR products from different passes")
        large = st.checkbox("Draw a very large area anyway (slow)")
        go = st.button("Make the figure", type="primary", disabled=not chosen)

    if go:
        options = dict(theme=theme, quality=quality, title=title or None, area=box, bands=bands, allow_different_passes=different,
                       allow_large=large)
        with right, st.spinner("Reading the products and drawing…"):
            render(chosen, options)

    with right:
        if st.session_state["error"]:
            st.error(st.session_state["error"])
            if st.session_state["suggestion"]:
                st.button("Use the suggested box", on_click=use_suggested_box)
        result = st.session_state["result"]
        if result:
            st.image(str(result["png"]), use_column_width=True)
            a, b, c = st.columns(3)
            a.download_button("Download PNG", result["png"].read_bytes(), f"{result['name']}.png", "image/png")
            if result["pdf"]:
                b.download_button("Download PDF", result["pdf"].read_bytes(), f"{result['name']}.pdf", "application/pdf")
            c.download_button("Download job file", result["toml"], f"{result['name']}.toml", "text/plain",
                              help="Run it again with `satviz run`, or edit it first")
            with st.expander("The job file behind this figure"):
                st.code(result["toml"], language="toml")
        elif not st.session_state["error"]:
            st.info("Choose products on the left, then make the figure.")


main()
