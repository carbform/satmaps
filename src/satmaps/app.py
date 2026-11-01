"""The local app: pick one or two products, draw the area on a map, make the figure. The wording, the look and the false-colour
channels are in pop-ups beside the button.

Run it with `satmaps app` (needs `pip install "satmaps[app]"`). It holds no figure logic: it collects choices and calls
`satmaps.api.build_job` and `satmaps.run.run_job`, the same path as `satmaps quick`; the preview is drawn by the same
arrangements and themes (`satmaps.preview`). The page is served on localhost and nothing is uploaded. The one thing fetched is the
map's OpenStreetMap tiles, by your browser, and only while "Show the OpenStreetMap basemap" is ticked.

Settings come from the environment, set by `satmaps app`: SATMAPS_DATA_DIR (where the products are), SATMAPS_OUT_DIR and
SATMAPS_CACHE_DIR (absolute, because the script runs from wherever Streamlit was started).
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # the CLI sets this in main(); the app never goes through it

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from satmaps.api import (  # noqa: E402
    OPTICAL_FCC_PRESETS,
    SAR_CHANNELS,
    SAR_FCC_PRESETS,
    TooLarge,
    auto_layout,
    band_choices,
    build_job,
    inspect,
    job_toml,
    layout_choices,
    scan,
)
from satmaps.app_style import sidebar_brand, stylesheet  # noqa: E402
from satmaps.area import AreaError  # noqa: E402
from satmaps.autoarea import common_area, coverage, group_by_ground, overlap_share, touches  # noqa: E402
from satmaps.core import THEMES  # noqa: E402
from satmaps.desktop import DesktopError, choose_folder
from satmaps.detect import DetectError  # noqa: E402
from satmaps.furniture import Furniture  # noqa: E402
from satmaps.job import JobError  # noqa: E402
from satmaps.layout import LayoutError  # noqa: E402
from satmaps.preview import render_example  # noqa: E402
from satmaps.quality import PROFILES  # noqa: E402
from satmaps.registry import load_builtin  # noqa: E402
from satmaps.run import run_job  # noqa: E402
from satmaps.sources import SourceError  # noqa: E402

load_builtin()
USER_ERRORS = (TooLarge, DetectError, JobError, AreaError, SourceError, LayoutError, FileNotFoundError, KeyError, ValueError,
               ImportError)
BOX_KEYS = ("box_w", "box_s", "box_e", "box_n")
ZOOM_KEYS = ("A", "B", "C")
AREA_TOOL = "Main area"
MAX_PRODUCTS = 2
OVERLAP, BOX = "Overlap of the products", "A box I choose"
AUTOMATIC = "Automatic"
area_map = components.declare_component("satmaps_area_map", path=str(Path(__file__).parent / "app_component"))


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
def product_meta(path_str: str, name: str, sensor: str | None, kind: str | None, mtime: float) -> dict:
    """Extract quick human-readable metadata badges for a product."""
    import re
    from datetime import datetime

    p = Path(path_str)
    date_str, band_str, pols_str, orbit_str, extra_str = "", "", "", "", ""

    if sensor == "nisar" or name.startswith("NISAR_"):
        if "_L2_" in name or "LSAR" in name or name.startswith("L."):
            band_str = "L-band"
        elif "_S2_" in name or "SSAR" in name or name.startswith("S."):
            band_str = "S-band"
        if "_A_" in name or "_ASC" in name.upper():
            orbit_str = "Asc"
        elif "_D_" in name or "_DESC" in name.upper():
            orbit_str = "Desc"
        if "DHDH" in name or "DHNA" in name or "HHHH" in name:
            pols_str = "HH/HV"
        elif "CRNA" in name or "RHRH" in name:
            pols_str = "RH/RV"
        m = re.search(r"(\d{8})T\d{6}", name)
        if m:
            try:
                date_str = datetime.strptime(m.group(1), "%Y%m%d").strftime("%d %b %Y")
            except ValueError:
                pass
    elif sensor == "sentinel1" or name.startswith("S1"):
        band_str = "C-band"
        if "1SDV" in name or "_DV_" in name:
            pols_str = "VV/VH"
        elif "1SDH" in name or "_DH_" in name:
            pols_str = "HH/HV"
        m = re.search(r"(\d{8})T\d{6}", name)
        if m:
            try:
                date_str = datetime.strptime(m.group(1), "%Y%m%d").strftime("%d %b %Y")
            except ValueError:
                pass
    elif sensor == "sentinel2" or name.startswith("S2"):
        m = re.search(r"(\d{8})T\d{6}", name)
        if m:
            try:
                date_str = datetime.strptime(m.group(1), "%Y%m%d").strftime("%d %b %Y")
            except ValueError:
                pass
        mtd = p / "MTD_MSIL2A.xml" if p.is_dir() else None
        if mtd and mtd.is_file():
            try:
                text = mtd.read_text(errors="ignore", encoding="utf-8")[:8000]
                cm = re.search(r"<Cloud_Coverage_Assessment>([\d.]+)</Cloud_Coverage_Assessment>", text)
                if cm:
                    extra_str = f"{float(cm.group(1)):.0f}% cloud"
            except Exception:
                pass
    elif sensor == "eos04" or name.startswith("E04"):
        band_str = "C-band"
        pols_str = "HH/HV"
        m = re.search(r"(\d{2}[A-Z]{3}\d{4})", name, re.IGNORECASE)
        if m:
            try:
                date_str = datetime.strptime(m.group(1).upper(), "%d%b%Y").strftime("%d %b %Y")
            except ValueError:
                date_str = m.group(1)
    elif sensor == "liss4" or name.startswith("RAF"):
        extra_str = "5.8m"
        m = re.search(r"(\d{2}[A-Z]{3}\d{4})", name, re.IGNORECASE)
        if m:
            try:
                date_str = datetime.strptime(m.group(1).upper(), "%d%b%Y").strftime("%d %b %Y")
            except ValueError:
                date_str = m.group(1)

    tokens = [x for x in (date_str, band_str, pols_str, orbit_str, extra_str) if x]
    return {
        "date": date_str, "band": band_str, "pols": pols_str,
        "orbit": orbit_str, "extra": extra_str, "tokens": tokens,
        "summary": " · ".join(tokens)
    }


@st.cache_data(show_spinner=False)
def example_page(kinds: tuple, layout: str, theme: str, words: tuple = (), furniture: tuple = (True, False, False),
                 channels: tuple = (), zoom_panels: int = 0) -> bytes:
    """The example page for a layout, a theme, the kinds of products chosen, the wording typed so far, the map furniture and the
    false-colour channels picked."""
    scale, north, grid = furniture
    return render_example(list(kinds), layout, theme, furniture=Furniture(scale=scale, north=north, grid=grid),
                          channels={k: v for k, v in channels}, zoom_panels=zoom_panels, **dict(words))


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
    st.session_state["suggestion"] = None


def label(row: dict) -> str:
    return f"{row['sensor']} ({row['kind']})  ·  {row['name']}"  # the sensor first: the name is long and the tag cuts it off


def shorten(text: str, width: int = 26) -> str:
    """A product's tick-box label with the middle of its long name left out (the tooltip has the whole of it)."""
    head, sep, name = text.partition("  ·  ")
    if len(name) > width:
        name = f"{name[:width // 2]}…{name[-(width // 2 - 1):]}"
    return f"{head}{sep}{name}"


def render(chosen: list[str], options: dict) -> None:
    """Draw the figure for the chosen products and keep it in the session; an error is kept as a message instead."""
    out, cache = Path(os.environ["SATMAPS_OUT_DIR"]), Path(os.environ["SATMAPS_CACHE_DIR"])
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
    for name in labels:
        st.session_state[PICK + name] = False


def render_lightbox(png_path: Path | str, name: str, height: int = 650, dark: bool = False) -> None:
    """Embedded interactive pan-and-zoom lightbox viewer for high-resolution figure inspection."""
    import base64
    import html
    import io

    from PIL import Image

    data = Path(png_path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    try:
        w, h = Image.open(io.BytesIO(data)).size
    except Exception:
        w, h = 1200, 1500

    bg_color = "#121418" if dark else "#1e222b"
    bar_bg = "rgba(18, 20, 24, 0.88)" if dark else "rgba(30, 34, 43, 0.88)"
    text_color = "#e6edf3"
    border_color = "rgba(255, 255, 255, 0.15)"
    accent_color = "#4ba3e3"

    lightbox_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      html, body {{ width: 100%; height: 100%; overflow: hidden; font-family: monospace; background: transparent; }}
      #viewport {{
        position: relative;
        width: 100%;
        height: {height}px;
        background: {bg_color};
        border-radius: 8px;
        overflow: hidden;
        user-select: none;
        touch-action: none;
        box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.4);
      }}
      #viewport:fullscreen {{
        width: 100vw;
        height: 100vh;
        border-radius: 0;
      }}
      #viewport:-webkit-full-screen {{
        width: 100vw;
        height: 100vh;
        border-radius: 0;
      }}
      #stage {{
        position: absolute;
        top: 0;
        left: 0;
        transform-origin: 0 0;
        cursor: grab;
        will-change: transform;
      }}
      #stage.dragging {{
        cursor: grabbing;
      }}
      #stage img {{
        display: block;
        max-width: none;
        pointer-events: none;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
      }}
      .toolbar {{
        position: absolute;
        top: 12px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        align-items: center;
        gap: 6px;
        background: {bar_bg};
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid {border_color};
        border-radius: 24px;
        padding: 5px 12px;
        z-index: 100;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
        color: {text_color};
        font-size: 12px;
      }}
      .btn {{
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid {border_color};
        color: {text_color};
        border-radius: 14px;
        padding: 3px 9px;
        font-size: 12px;
        font-weight: 500;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        transition: all 0.15s ease;
      }}
      .btn:hover {{
        background: rgba(255, 255, 255, 0.18);
        border-color: rgba(255, 255, 255, 0.3);
      }}
      .btn:active {{
        transform: scale(0.96);
      }}
      .badge {{
        padding: 0 6px;
        font-variant-numeric: tabular-nums;
        font-weight: 600;
        color: {accent_color};
        min-width: 48px;
        text-align: center;
        cursor: pointer;
      }}
      .badge:hover {{
        text-decoration: underline;
      }}
      .sep {{
        width: 1px;
        height: 14px;
        background: {border_color};
        margin: 0 4px;
      }}
      .tag {{
        font-size: 11px;
        color: #94a3b8;
        letter-spacing: 0.3px;
      }}
      .hints {{
        position: absolute;
        bottom: 12px;
        left: 50%;
        transform: translateX(-50%);
        background: {bar_bg};
        border: 1px solid {border_color};
        border-radius: 16px;
        padding: 3px 12px;
        font-size: 11px;
        color: #94a3b8;
        pointer-events: none;
        z-index: 90;
        opacity: 0.85;
      }}
    </style>
    </head>
    <body>
    <div id="viewport" tabindex="0">
      <div class="toolbar">
        <button class="btn" id="btn-out" title="Zoom out (−)">−</button>
        <span class="badge" id="zoom-badge" title="Click to reset to 100%">100%</span>
        <button class="btn" id="btn-in" title="Zoom in (+)">+</button>
        <div class="sep"></div>
        <button class="btn" id="btn-fit" title="Fit image to view (0)">⛶ Fit</button>
        <button class="btn" id="btn-100" title="100% Native Resolution (1)">1:1</button>
        <div class="sep"></div>
        <button class="btn" id="btn-fs" title="Toggle full-screen view (F)">⛶ Fullscreen</button>
        <div class="sep"></div>
        <span class="tag">{w} × {h} px</span>
      </div>
      <div class="hints">Scroll to zoom · Drag to pan · Double-click to zoom 1:1</div>
      <div id="stage">
        <img id="img" src="data:image/png;base64,{b64}" width="{w}" height="{h}" alt="{html.escape(name)}" />
      </div>
    </div>
    <script>
      (function() {{
        const viewport = document.getElementById("viewport");
        const stage = document.getElementById("stage");
        const zoomBadge = document.getElementById("zoom-badge");
        const btnIn = document.getElementById("btn-in");
        const btnOut = document.getElementById("btn-out");
        const btnFit = document.getElementById("btn-fit");
        const btn100 = document.getElementById("btn-100");
        const btnFs = document.getElementById("btn-fs");

        const imgW = {w};
        const imgH = {h};

        let scale = 1.0;
        let tx = 0;
        let ty = 0;
        let isDragging = false;
        let startX = 0;
        let startY = 0;

        function updateTransform() {{
          stage.style.transform = `translate3d(${{tx}}px, ${{ty}}px, 0) scale(${{scale}})`;
          zoomBadge.textContent = Math.round(scale * 100) + "%";
        }}

        function fitToView() {{
          const vw = viewport.clientWidth;
          const vh = viewport.clientHeight;
          if (vw <= 0 || vh <= 0) return;
          const pad = 30;
          scale = Math.min((vw - pad * 2) / imgW, (vh - pad * 2) / imgH);
          if (scale > 1.0) scale = 1.0;
          tx = (vw - imgW * scale) / 2;
          ty = (vh - imgH * scale) / 2;
          updateTransform();
        }}

        function zoomTo(targetScale, cx, cy) {{
          targetScale = Math.max(0.08, Math.min(25.0, targetScale));
          if (cx === undefined || cy === undefined) {{
            cx = viewport.clientWidth / 2;
            cy = viewport.clientHeight / 2;
          }}
          tx = cx - (cx - tx) * (targetScale / scale);
          ty = cy - (cy - ty) * (targetScale / scale);
          scale = targetScale;
          updateTransform();
        }}

        viewport.addEventListener("wheel", function(e) {{
          e.preventDefault();
          const rect = viewport.getBoundingClientRect();
          const cx = e.clientX - rect.left;
          const cy = e.clientY - rect.top;
          const factor = e.deltaY < 0 ? 1.2 : 0.833;
          zoomTo(scale * factor, cx, cy);
        }}, {{ passive: false }});

        viewport.addEventListener("pointerdown", function(e) {{
          if (e.target.closest(".toolbar")) return;
          isDragging = true;
          startX = e.clientX - tx;
          startY = e.clientY - ty;
          stage.classList.add("dragging");
          viewport.setPointerCapture(e.pointerId);
        }});

        viewport.addEventListener("pointermove", function(e) {{
          if (!isDragging) return;
          tx = e.clientX - startX;
          ty = e.clientY - startY;
          updateTransform();
        }});

        function endDrag(e) {{
          if (isDragging) {{
            isDragging = false;
            stage.classList.remove("dragging");
            try {{ viewport.releasePointerCapture(e.pointerId); }} catch(_) {{}}
          }}
        }}

        viewport.addEventListener("pointerup", endDrag);
        viewport.addEventListener("pointercancel", endDrag);

        viewport.addEventListener("dblclick", function(e) {{
          if (e.target.closest(".toolbar")) return;
          const rect = viewport.getBoundingClientRect();
          const cx = e.clientX - rect.left;
          const cy = e.clientY - rect.top;
          if (Math.abs(scale - 1.0) < 0.1) {{
            fitToView();
          }} else {{
            zoomTo(1.0, cx, cy);
          }}
        }});

        btnIn.addEventListener("click", () => zoomTo(scale * 1.25));
        btnOut.addEventListener("click", () => zoomTo(scale * 0.8));
        btn100.addEventListener("click", () => zoomTo(1.0));
        zoomBadge.addEventListener("click", () => zoomTo(1.0));
        btnFit.addEventListener("click", fitToView);

        function toggleFs() {{
          if (!document.fullscreenElement && !document.webkitFullscreenElement) {{
            if (viewport.requestFullscreen) viewport.requestFullscreen();
            else if (viewport.webkitRequestFullscreen) viewport.webkitRequestFullscreen();
          }} else {{
            if (document.exitFullscreen) document.exitFullscreen();
            else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
          }}
        }}
        btnFs.addEventListener("click", toggleFs);

        function onFsChange() {{
          const isFs = Boolean(document.fullscreenElement || document.webkitFullscreenElement);
          btnFs.textContent = isFs ? "✕ Exit" : "⛶ Fullscreen";
          setTimeout(fitToView, 80);
        }}
        document.addEventListener("fullscreenchange", onFsChange);
        document.addEventListener("webkitfullscreenchange", onFsChange);

        viewport.addEventListener("keydown", function(e) {{
          if (e.key === "+" || e.key === "=") {{ zoomTo(scale * 1.25); e.preventDefault(); }}
          else if (e.key === "-" || e.key === "_") {{ zoomTo(scale * 0.8); e.preventDefault(); }}
          else if (e.key === "0") {{ fitToView(); e.preventDefault(); }}
          else if (e.key === "1") {{ zoomTo(1.0); e.preventDefault(); }}
          else if (e.key.toLowerCase() === "f") {{ toggleFs(); e.preventDefault(); }}
        }});

        setTimeout(fitToView, 40);
        window.addEventListener("resize", fitToView);
      }})();
    </script>
    </body>
    </html>
    """
    components.html(lightbox_html, height=height + 10)


def show_results(results: list[dict], key_prefix: str = "", show_job: bool = True) -> None:
    """Each figure with its downloads; several figures (a layout that makes one per product or pair) get a tab each."""
    spots = st.tabs([r["name"] for r in results]) if len(results) > 1 else [st.container()]
    for spot, r in zip(spots, results, strict=True):
        with spot:
            t_col, d1, d2, d3 = st.columns([1.5, 1, 1, 1])
            with t_col:
                inspect = st.toggle("🔍 High-res lightbox (pan & zoom)", key=f"{key_prefix}lightbox_{r['name']}",
                                    help="Interactive pan & zoom viewer with full-screen inspection")
            with d1:
                st.download_button("Download PNG", r["png"].read_bytes(), f"{r['name']}.png", "image/png",
                                   key=f"{key_prefix}png_{r['name']}")
            with d2:
                if r["pdf"]:
                    st.download_button("Download PDF", r["pdf"].read_bytes(), f"{r['name']}.pdf", "application/pdf",
                                       key=f"{key_prefix}pdf_{r['name']}")
            with d3:
                st.download_button("Download job file", r["toml"], f"{r['name']}.toml", "text/plain",
                                   key=f"{key_prefix}toml_{r['name']}", help="Run it again with `satmaps run`, or edit it first")
            if inspect:
                render_lightbox(r["png"], r["name"], dark=st.session_state.get("dark", False))
            else:
                st.image(str(r["png"]), use_column_width=True)
    if show_job:  # (not inside another expander: Streamlit does not nest them)
        with st.expander("The job file behind this figure"):
            st.code(results[0]["toml"], language="toml")


def box_of(state) -> tuple | None:
    """The main area's box (west, south, east, north) when all four fields are filled in, else None: the figure then covers
    what the products share."""
    values = tuple(state[k] for k in BOX_KEYS)
    return values if all(values) else None


def apply_drawn(state, drawn: dict | None) -> bool:
    """Write what the map sent back into the session: a new rectangle fills the four fields of the main area; a zoom box is kept
    on its own; Clear removes everything drawn (the main area and the zoom boxes) and leaves the products' own coverage.
    A value already applied (the map keeps sending its last one) is ignored. Returns whether anything changed."""
    if not drawn or drawn["n"] == state["last_draw"]:
        return False
    state["last_draw"] = drawn["n"]
    target = drawn.get("target", "area")
    if target == "all":
        for key in BOX_KEYS:
            state[key] = 0.0
        for k in ZOOM_KEYS:
            state[f"zoom_{k}"] = None
    elif target in ZOOM_KEYS:  # a zoom box: it does not touch the main area
        state[f"zoom_{target}"] = tuple(round(float(v), 5) for v in drawn["box"]) if drawn["box"] else None
    elif drawn["box"]:
        for key, value in zip(BOX_KEYS, drawn["box"], strict=True):
            state[key] = round(float(value), 4)
    else:
        for key in BOX_KEYS:
            state[key] = 0.0
    return True


def drawn_zooms(state) -> list[tuple[str, tuple, str]]:
    """The zoom boxes to use, (letter, (west, south, east, north), name) in A, B, C order: those drawn among the first
    `zoom_n`, and none unless the zoom panels are on and exactly one product is chosen."""
    if not (state.get("zoom_on") and state.get("zoom_ok")):
        return []
    return [(k, state[f"zoom_{k}"], (state.get(f"zoom_name_{k}") or "").strip())
            for k in ZOOM_KEYS[:int(state.get("zoom_n", 3))] if state.get(f"zoom_{k}")]


def zoom_boxes(state) -> list[dict]:
    """`drawn_zooms` as the job asks for them: {"box": ..., "name": ...}."""
    return [{"box": box, "name": name} for _, box, name in drawn_zooms(state)]


def zooms_outside(state, area: tuple | None) -> list[str]:
    """Letters of the zoom boxes whose centre is not inside the area (west, south, east, north); none if the area is not known."""
    if not area:
        return []
    w, s, e, n = area
    return [k for k, z, _ in drawn_zooms(state) if not (w <= (z[0] + z[2]) / 2 <= e and s <= (z[1] + z[3]) / 2 <= n)]


def area_section(chosen_rows: list[dict], by_label: dict) -> tuple[str, tuple | None, list[str], bool]:
    """Step 2: where the products are, on a map you can draw on, and the area that results.

    Returns (mode, box, outside, apart): `outside` names the products a drawn box does not touch (they cannot be drawn in it);
    `apart` is True when two products share no ground (a figure needs products that overlap)."""
    st.markdown("##### 2 · Main area")
    prints = [{"name": r["name"][:24], **footprint_of(r["path"], Path(r["path"]).stat().st_mtime)} for r in chosen_rows]
    prints = [p for p in prints if p["ring"]]
    overlap, apart = None, False
    if len(prints) == len(chosen_rows) > 1:
        apart = len(group_by_ground([p["ring"] for p in prints])) > 1
        if not apart:
            overlap = [round(v, 4) for v in common_area({str(i): p["ring"] for i, p in enumerate(prints)}).lonlat_bbox()]
    if apart:
        st.error("These products do not overlap: they cover different ground. A figure shows products that share ground, "
                 "so choose products that do (or leave one out).")
    box = box_of(st.session_state)
    w, s_, e, n = box or (0, 0, 1, 1)
    st.session_state["box_bad"] = not (w < e and s_ < n)  # west must be west of east, south south of north
    if st.session_state["box_bad"]:
        box = None
    st.session_state["zoom_ok"] = len(chosen_rows) == 1  # zoom panels go with a single product
    on = bool(st.session_state["zoom_on"] and st.session_state["zoom_ok"])
    n_zoom = int(st.session_state["zoom_n"])
    tools = [AREA_TOOL, *(f"Zoom {k}" for k in ZOOM_KEYS[:n_zoom])]
    if st.session_state["zoom_tool"] not in tools:  # fewer panels than before: the tool that went is no longer there
        st.session_state["zoom_tool"] = AREA_TOOL
    tool = st.session_state["zoom_tool"].removeprefix("Zoom ") if on and st.session_state["zoom_tool"] != AREA_TOOL else "area"
    drawn = area_map(footprints=[{"name": p["name"], "kind": p["kind"], "ring": p["ring"]} for p in prints], overlap=overlap,
                     box=box, basemap=bool(st.session_state.get("basemap", True)),
                     dark=bool(st.session_state.get("dark", False)), key="area_map", default=None,
                     zooms=({k: st.session_state.get(f"zoom_{k}") for k in ZOOM_KEYS[:n_zoom]} if on else {}),
                     tool=tool)
    apply_drawn(st.session_state, drawn)
    if not chosen_rows:  # the map of India waits for products; drawing a box before choosing any would have nothing to apply to
        st.caption("Choose products in the sidebar (step 1): they appear here, and you can draw the area you want.")
        st.checkbox("OpenStreetMap basemap", value=True, key="basemap")
        return OVERLAP, None, [], False
    st.caption("Pan mode: drag to move map · Draw mode: drag to draw box (or Shift+drag) · drag box edges/corners to resize. "
               "The dashed rectangle is what is drawn when you draw nothing.")
    st.checkbox("OpenStreetMap basemap", value=True, key="basemap",
               help="Your browser fetches map tiles from openstreetmap.org, which sees roughly where you look. Untick to keep "
                    "the map to your data alone: nothing is then fetched.")
    if st.session_state["zoom_ok"]:
        z1, z2 = st.columns([2, 3])
        z1.checkbox("Zoom side panels", key="zoom_on",
                    help="Small windows beside the picture, each marked and named on it. For one product at a time.")
        if st.session_state["zoom_on"]:
            z2.radio("How many", [1, 2, 3], key="zoom_n", horizontal=True, help="Up to this many zoom panels (1, 2 or 3).")
            st.radio("Draw", tools, key="zoom_tool", horizontal=True, label_visibility="collapsed",
                     help="What a drag on the map draws: the area, or a zoom box.")
            names = st.columns(n_zoom)
            for col, k in zip(names, ZOOM_KEYS, strict=False):
                col.text_input(f"Name of zoom {k}", key=f"zoom_name_{k}", placeholder="optional, e.g. Hill edge")
            count = len(drawn_zooms(st.session_state))
            st.caption(f"{count} of {n_zoom} drawn. Pick a zoom above, then drag a box on the map." if count < n_zoom
                       else "All drawn. Drag again to move one; Clear removes every box you drew.")
    outside = []
    st.caption("Main area, in degrees. Drag on the map or type it; leave it empty for the area the products share.")
    cols = st.columns(4)
    for col, key, name in zip(cols, BOX_KEYS, ("West", "South", "East", "North"), strict=True):
        col.number_input(name, key=key, format="%.4f", step=0.05,
                         help="The main area's edges in degrees: filled in when you drag on the map, or type them. "
                              "Empty (0) means the area the products share.")
    if st.session_state["box_bad"]:
        st.error("West must be less than east, and south less than north.")
    mode = BOX if box else OVERLAP
    if box:
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
    area = box or (tuple(overlap) if overlap else (prints[0]["bbox"] if len(prints) == 1 and prints[0].get("bbox") else None))
    if lost := zooms_outside(st.session_state, area):
        st.warning(f"Zoom {', '.join(lost)} {'is' if len(lost) == 1 else 'are'} outside the area: draw it inside the area, "
                   "or pick a larger area.")
    return mode, box, outside, apart


def summary(chosen_rows: list[dict], mode: str, box: tuple | None, outside: bool, apart: bool,
            bad: bool = False) -> tuple[bool, str]:
    """(ready, message): ready with no message, or what to do first. `mode` and `box` are kept for callers that say more."""
    if not chosen_rows:
        return False, ""  # the button is off and the sidebar says step 1: no message needed
    if bad:
        return False, "Not yet: the main area's west must be less than its east, and its south less than its north."
    if apart:
        return False, "Not yet: the products cover different ground. Choose products that overlap."
    if outside:
        return False, "Not yet: the box misses some products. Redraw the box on the map, or leave those products out."
    return True, ""


PICK = "pick::"  # session-state key prefix of a product's tick box
WORDS = ("title", "subtitle", "place", "author", "website", "credits", "notices", "legend")


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
    st.text_area("Notices", key="notices", height=68, placeholder="one per line, added to the notices your products carry",
                 help="Printed in the notice strip after the notices the products require, which are always kept.")
    st.text_area("Legend items", key="legend", height=68, placeholder="one per line, in the order of the legend",
                 help="Replaces the text of each legend item in order and keeps its colour. An empty line keeps that item "
                      "as it is. Up to six items fit.")
    return {k: st.session_state[k] or None for k in WORDS}


THEME_DESCRIPTIONS = {
    "minimal": "**Minimal Studio** — Clean, modern publication layout with hairline rules and neutral card framing.",
    "retro_80s": "**Retro '80s** — 1980s synthwave styling with neon pink accents, terminal mono type, and offset shadows.",
    "newspaper": "**Classic Newspaper** — Authentic broadsheet on white paper with classic serif type and ruled columns.",
    "neo_brutal": "**Neo-Brutalist** — High-impact neo-brutalist style with bold borders, electric hues, and heavy drop shadows.",
    "xkcd": "**Hand-Drawn Sketch (xkcd)** — Playful comic look with sketched outlines and informal lettering.",
}


def look_section(kinds: list[str]) -> dict:
    """How it looks: theme, layout and map furniture."""
    a, b = st.columns(2)
    theme = a.selectbox("Theme", sorted(THEMES), index=sorted(THEMES).index("minimal"))
    choices = layout_choices(kinds)
    options = [AUTOMATIC, *choices.values()]
    if "layout_choice" in st.session_state and st.session_state["layout_choice"] not in options:
        st.session_state["layout_choice"] = AUTOMATIC
    current = st.session_state.get("layout_choice", AUTOMATIC)
    idx = options.index(current) if current in options else 0
    layout_name = b.selectbox("Layout", options, index=idx, key="layout_choice",
                              help="How the products sit on the page. Automatic: 1 alone, 2 side by side.")
    layout = None if layout_name == AUTOMATIC else next(k for k, v in choices.items() if v == layout_name)
    if theme in THEME_DESCRIPTIONS:
        st.caption(f"🎨 **Theme**: {THEME_DESCRIPTIONS[theme]}")
    if "bands" in choices:
        st.caption("🔬 **Band by band**: Draws each spectral band (B01-B12) in its own panel.")
    st.markdown("**Map furniture**")
    f1, f2, f3 = st.columns(3)
    grid = f1.checkbox("Lat/lon grid", value=False, help="Grid lines with latitude and longitude labels on every panel.")
    north = f2.checkbox("North arrow", value=False, help="Points at true north.")
    scalebar = f3.checkbox("Scale bar", value=True)
    return dict(theme=theme, layout=layout, grid=grid, north=north, scalebar=scalebar)


def _on_preset_change(prefix: str, avail_presets: dict, options: dict) -> None:
    chosen_label = st.session_state.get(f"{prefix}_preset")
    for p in avail_presets.values():
        if p["label"] == chosen_label:
            target = p.get("bands") or p.get("channels")
            st.session_state[f"{prefix}_Red"] = options[target[0]]
            st.session_state[f"{prefix}_Green"] = options[target[1]]
            st.session_state[f"{prefix}_Blue"] = options[target[2]]
            break


def _on_rgb_change(prefix: str, back: dict, tuple_to_label: dict) -> None:
    r_label = st.session_state.get(f"{prefix}_Red")
    g_label = st.session_state.get(f"{prefix}_Green")
    b_label = st.session_state.get(f"{prefix}_Blue")
    if r_label and g_label and b_label:
        current_tuple = (back.get(r_label), back.get(g_label), back.get(b_label))
        st.session_state[f"{prefix}_preset"] = tuple_to_label.get(current_tuple, "Custom")


def pick_channels(prefix: str, options: dict, defaults: tuple, presets: dict | None = None) -> tuple:
    """Preset dropdown and three selectors, red, green and blue, over `options` ({value: label})."""
    labels = list(options.values())
    back = {label: value for value, label in options.items()}
    avail_presets = {k: p for k, p in (presets or {}).items()
                     if set(p.get("bands") or p.get("channels") or ()) <= set(options.keys())}
    tuple_to_label = {tuple(p.get("bands") or p.get("channels")): p["label"] for p in avail_presets.values()}
    label_to_preset = {p["label"]: p for p in avail_presets.values()}
    preset_choices = [p["label"] for p in avail_presets.values()] + ["Custom"]
    default_preset = tuple_to_label.get(defaults, "Custom")

    # Clean up stale session keys if options changed (e.g. products changed)
    rgb_stale = False
    for name in ("Red", "Green", "Blue"):
        k = f"{prefix}_{name}"
        if k in st.session_state and st.session_state[k] not in labels:
            del st.session_state[k]
            rgb_stale = True

    preset_key = f"{prefix}_preset"
    if rgb_stale or (preset_key in st.session_state and st.session_state[preset_key] not in preset_choices):
        if preset_key in st.session_state:
            del st.session_state[preset_key]

    if avail_presets:
        curr_preset = st.session_state.get(preset_key, default_preset)
        p_idx = preset_choices.index(curr_preset) if curr_preset in preset_choices else preset_choices.index(default_preset)
        st.selectbox("Recipe preset", preset_choices,
                     index=p_idx,
                     key=preset_key,
                     on_change=_on_preset_change,
                     args=(prefix, avail_presets, options),
                     help="Select a standard false-colour composite preset or customize RGB channels below.")

    cols = st.columns(3)
    picks = []
    for col, name, default in zip(cols, ("Red", "Green", "Blue"), defaults, strict=True):
        k = f"{prefix}_{name}"
        curr_val = st.session_state.get(k)
        idx = labels.index(curr_val) if curr_val in labels else labels.index(options[default])
        chosen_label = col.selectbox(name, labels,
                                     index=idx,
                                     key=k,
                                     on_change=_on_rgb_change,
                                     args=(prefix, back, tuple_to_label))
        picks.append(back[chosen_label])

    cur_preset = st.session_state.get(preset_key, default_preset)
    if cur_preset in label_to_preset:
        p_info = label_to_preset[cur_preset]
        st.caption(f"**{p_info['name']}**: {p_info['summary']}")
        if "colors" in p_info:
            st.caption(f"🎨 **Colors**: {p_info['colors']}")
    elif cur_preset == "Custom":
        st.caption(f"**Custom**: Red = {picks[0]}, Green = {picks[1]}, Blue = {picks[2]}")

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
        out["sar"] = pick_channels("fcc_sar", dict(SAR_CHANNELS), ("co", "cross", "ratio"), SAR_FCC_PRESETS)
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
            default_opt = natural if set(natural) <= set(bands) else tuple(bands)[:3]
            out["optical"] = pick_channels("fcc_opt", bands, default_opt, OPTICAL_FCC_PRESETS)
            st.caption("Red, green, blue = red, green, blue bands is true colour; anything else is a false-colour composite.")
    if len(rows) >= 2 and len(set(r["kind"] for r in rows)) == 1:
        st.caption("All products share the same channels, so the colours mean the same across panels.")
    return out


def quality_choice() -> str:
    """The quality profile, as a select that fits the top bar (the option names are short: the cell is one sixth of the page)."""
    picked = st.selectbox("Quality", [name.capitalize() for name in PROFILES], label_visibility="collapsed",
                          help="Quality. Quick: a small PNG in seconds · Medium: finer · Publication: full size, with a PDF")
    return picked.lower()


CREDITS = ('<div class="credits"><b>Carbform</b> &nbsp;·&nbsp; '
           '<a href="https://carbform.github.io" target="_blank" rel="noopener">carbform.github.io</a> &nbsp;·&nbsp; '
           '<a href="https://github.com/carbform/satmaps" target="_blank" rel="noopener">Find this on GitHub</a></div>')

HELP = """
**Make a figure in four steps**

1. **Products** (sidebar): pick the folder, then choose a product (or two that overlap).
   Multiple products must cover the same ground.
2. **Main area**: leave it, and the figure covers what the products share. Or drag a rectangle on the map,
   or type its west, south, east and north.
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
        st.info('The settings have changed since this figure was made. Click on "**Make the figure**" to update.')
    st.image(example_page(tuple(kinds), layout, look["theme"], tuple(sorted((k, v) for k, v in words.items() if v)),
                          (look["scalebar"], look["north"], look["grid"]), tuple(sorted(channels.items())), look["zoom_panels"]),
             use_column_width=True)
    if results:
        with st.expander("The figure made before the change"):
            show_results(results, key_prefix="old_", show_job=False)


def main() -> None:
    page_icon_file = Path(__file__).parent / "app_assets" / "logo_icon.png"
    st.set_page_config(page_title="satmaps", page_icon=str(page_icon_file) if page_icon_file.exists() else "🛰",
                       layout="wide", initial_sidebar_state="expanded")
    title, mode_switch = st.columns([10, 1])
    title.title("satmaps")
    dark = mode_switch.toggle("Dark mode", key="dark", label_visibility="collapsed", help="Dark mode")
    st.markdown(stylesheet(dark), unsafe_allow_html=True)
    defaults = {"results": None, "error": None, "suggestion": None, "stamp": 0, "box_bad": False, "last_draw": 0,
                "folder": os.environ.get("SATMAPS_DATA_DIR", "data"), "folder_note": "", "made_with": None, "picked": [],
                "dark": False, "zoom_on": False, "zoom_tool": AREA_TOOL, "zoom_n": 3, "zoom_ok": False,
                **dict.fromkeys(WORDS, "")}
    for key, default in {**defaults, **dict.fromkeys(BOX_KEYS, 0.0), **{f"zoom_{k}": None for k in ZOOM_KEYS},
                                    **{f"zoom_name_{k}": "" for k in ZOOM_KEYS}}.items():
        st.session_state.setdefault(key, default)

    top = st.container()  # the button and the pop-ups sit at the top; they are filled in once the area is known

    with st.sidebar:
        st.markdown(sidebar_brand(dark), unsafe_allow_html=True)
        st.header("1 · Products")
        st.caption("Pick the folder that holds your data, then choose a product (or two that overlap).")
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
        taken = sum(bool(st.session_state.get(PICK + name)) for name in by_label)
        picked_pre = [name for name in by_label if st.session_state.get(PICK + name)]

        # Staging Deck / Selection Tray
        if picked_pre:
            tcol1, tcol2 = st.columns([3, 1])
            count = len(picked_pre)
            tcol1.markdown(f"**Selected ({count} product{'s' if count > 1 else ''})**")
            if tcol2.button("Clear", key="clear_all_picks", help="Deselect all products"):
                for n_ in by_label:
                    st.session_state[PICK + n_] = False
                st.session_state["picked"] = []
                st.rerun()
            tag_tokens = []
            for p_name in picked_pre:
                pr = by_label[p_name]
                meta = product_meta(pr["path"], pr["name"], pr["sensor"], pr["kind"], Path(pr["path"]).stat().st_mtime)
                sensor_tag = meta["tokens"][0] if meta["tokens"] else (pr["sensor"] or "").upper()
                tag_tokens.append(f"`{sensor_tag}` {shorten(p_name)}")
            st.caption(" · ".join(tag_tokens))
        elif products:
            st.caption("Choose a product to map, or two that overlap to compare.")

        # Multi-product overlap reference
        ref_fps = [footprint_of(by_label[p]["path"], Path(by_label[p]["path"]).stat().st_mtime) for p in picked_pre]
        ref_rings = [fp["ring"] for fp in ref_fps if fp.get("ring")]

        picked = []
        for name, r in by_label.items():
            on = bool(st.session_state.get(PICK + name))
            meta = product_meta(r["path"], r["name"], r["sensor"], r["kind"], Path(r["path"]).stat().st_mtime)
            help_text = f"{r['name']}\n{meta['summary']}" if meta["summary"] else r["name"]
            if st.checkbox(shorten(name), key=PICK + name, help=help_text, disabled=taken >= MAX_PRODUCTS and not on):
                picked.append(name)

            badges = list(meta["tokens"])
            overlap_badge = ""
            if on:
                overlap_badge = ":blue[●] Selected"
            elif ref_rings:
                cand_fp = footprint_of(r["path"], Path(r["path"]).stat().st_mtime)
                if cand_fp.get("ring"):
                    share = min(overlap_share(r_ring, cand_fp["ring"]) for r_ring in ref_rings)
                    if share >= 0.70:
                        overlap_badge = f":green[●] **{share:.0%} overlap**"
                    elif share >= 0.05:
                        overlap_badge = f":orange[●] **{share:.0%} partial**"
                    else:
                        overlap_badge = ":red[●] **0% overlap**"
            sub = "  ·  ".join([x for x in (overlap_badge, *badges) if x])
            if sub:
                st.caption(sub)

        st.session_state["picked"] = picked
        if products:
            if not picked:
                st.caption("Tick a product to map, or tick two to compare.")
            elif len(picked) == 1:
                st.caption("✓ 1 product selected (or tick a 2nd overlapping product to compare).")
            else:
                st.caption("✓ 2 products selected to compare (maximum).")
        chosen_rows = [by_label[name] for name in picked]
        chosen = [r["path"] for r in chosen_rows]
        zips = [r["name"] for r in rows if not r["sensor"]]
        if zips:
            with st.expander(f"📦 {len(zips)} zip{'s' if len(zips) > 1 else ''} not shown"):
                st.caption(f"{len(zips)} zip{'s' if len(zips) > 1 else ''} not shown: the readers take unzipped folders. "
                           "Extract into the folder, then press Rescan.")
                for zname in zips:
                    zcol1, zcol2 = st.columns([3, 2])
                    zcol1.caption(zname[:18] + "…" if len(zname) > 18 else zname)
                    if zcol2.button("Extract", key=f"unzip_{zname}"):
                        import zipfile

                        zpath = Path(st.session_state["folder"]) / zname
                        with st.spinner(f"Extracting {zname}…"):
                            with zipfile.ZipFile(zpath, "r") as zf:
                                zf.extractall(st.session_state["folder"])
                        st.session_state["stamp"] += 1
                        st.rerun()
        if not products and not zips:
            st.info("No products found in this folder.")

    kinds = [r["kind"] for r in chosen_rows]
    left, right = st.columns(2)
    with left:
        mode, box, outside, apart = area_section(chosen_rows, by_label)

    with top:
        cells = st.columns(6)  # an equal grid: every control the same width and height
        ready, said = summary(chosen_rows, mode, box, bool(outside), apart, st.session_state["box_bad"])
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
        if said:
            st.warning(said)

        if chosen_rows:
            active_lay = look["layout"] or (auto_layout(kinds) if kinds else "single")
            if set(kinds) == {"optical"}:
                wcol1, wcol2 = st.columns([4, 2])
                if active_lay == "bands":
                    wcol1.caption("🔬 **Active Layout: Band-by-band spectral breakdown** — Draws every band in its own panel.")
                    if wcol2.button("Switch to Composite", key="wf_btn_comp", help="Render RGB False-Colour Composite"):
                        st.session_state["layout_choice"] = AUTOMATIC
                        st.rerun()
                else:
                    wcol1.caption("🎨 **Active Layout: False-Colour Composite (RGB)** — Click to inspect all spectral bands.")
                    if wcol2.button("View Band by Band", key="wf_btn_bands", help="Render all spectral bands individually"):
                        st.session_state["layout_choice"] = "Band by band"
                        st.rerun()

    zooms = zoom_boxes(st.session_state)
    shown = bool(st.session_state["zoom_on"]) and len(chosen_rows) == 1
    look = {**look, "zoom_panels": int(st.session_state["zoom_n"]) if shown else 0}
    signature = (tuple(chosen), mode, box, quality, tuple((tuple(z["box"]), z["name"]) for z in zooms),
                 tuple(sorted(words.items(), key=lambda kv: kv[0])), tuple(sorted((k, str(v)) for k, v in look.items())),
                 tuple(sorted(channels.items())))
    if go:
        options = dict(theme=look["theme"], quality=quality, area=box, arrangement=look["layout"],
                       bands=look["layout"] == "bands", grid=look["grid"], north=look["north"], scalebar=look["scalebar"],
                       channels=channels, zooms=zooms or None, **words)
        with right, st.spinner("Reading the products and drawing…"):
            render(chosen, options)
        st.session_state["made_with"] = signature
    with right:
        st.markdown("##### Figure")
        figure_pane(kinds, words, look, channels, signature)
    st.markdown(CREDITS, unsafe_allow_html=True)


if __name__ == "__main__":  # Streamlit runs the script as __main__; importing the module (the tests do) draws nothing
    main()
