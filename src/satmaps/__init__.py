"""satmaps: quick and publication-quality figures from SAR (NISAR, Sentinel-1, EOS-04) and optical (Sentinel-2, LISS-IV) data."""
from __future__ import annotations

__version__ = "0.1.0"


def render(paths, **options):
    """Render a figure from product paths: see `satmaps.api.render`."""
    from satmaps.api import render as _render

    return _render(paths, **options)


def inspect(path):
    """What satmaps knows about a product without reading its pixels: see `satmaps.api.inspect`."""
    from satmaps.api import inspect as _inspect

    return _inspect(path)


__all__ = ["inspect", "render", "__version__"]
