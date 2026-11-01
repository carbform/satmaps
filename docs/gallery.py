"""Make the README gallery: python docs/gallery.py  (needs the Dibrugarh products in ./data; writes docs/img/*.jpg)."""
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

ROOT, IMG = Path(__file__).resolve().parents[1], Path(__file__).resolve().parent / "img"
DATA = ROOT / "data"
BBOX = ["--bbox", "94.7238", "27.4635", "95.0176", "27.7421"]  # the area of jobs/brahmaputra.toml


def find(prefix, suffix=""):
    return str(next(p for p in sorted(DATA.iterdir()) if p.name.startswith(prefix) and p.name.endswith(suffix)))


L, S, S1, S2 = find("NISAR_L2"), find("NISAR_S2_PR_GCOV_031_112"), find("S1D", ".SAFE"), find("S2C", ".SAFE")
ZOOMS = ["--zoom", "27.52,94.80,7=Hill edge", "--zoom", "27.60,94.93,7=River", "--zoom", "27.69,94.82,7=Town"]

FIGURES = {  # name: satmaps arguments
    "theme_retro_80s": ["quick", L, "--theme", "retro_80s", *BBOX],
    "theme_minimal": ["quick", L, "--theme", "minimal", *BBOX],
    "theme_neo_brutal": ["quick", L, "--theme", "neo_brutal", *BBOX],
    "theme_newspaper": ["quick", L, "--theme", "newspaper", *BBOX],
    "theme_xkcd": ["quick", L, "--theme", "xkcd", *BBOX],
    "layout_zooms": ["quick", L, "--theme", "retro_80s", *ZOOMS, *BBOX],
    "layout_side_by_side": ["quick", L, S, "--theme", "retro_80s", *BBOX],
    "layout_sar_optical": ["quick", S1, S2, "--theme", "minimal", *BBOX],
    "layout_bands": ["quick", S2, "--bands", "--theme", "minimal", *BBOX],
    "layout_optical_fcc": ["quick", S2, "--optical-fcc", "cir", "--theme", "newspaper", *BBOX],
    "layout_tiles": ["run", str(ROOT / "jobs" / "tiles.toml")],
}

for name, args in FIGURES.items():
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(["satmaps", *args, "--out", out, "--data-dir", str(DATA)], check=True, cwd=ROOT)
        png = next(Path(out).glob("*.png"))
        im = Image.open(png).convert("RGB")
        im.thumbnail((560, 700))
        im.save(IMG / f"{name}.jpg", quality=82, optimize=True)
        print(name, im.size)
