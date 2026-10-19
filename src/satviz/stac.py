"""Minimal STAC client (standard library only) for the two free providers we use.

- ``earth-search``: Element 84, public COGs on S3, no authentication (Sentinel-2 L2A).
- ``planetary-computer``: Microsoft, anonymous short-lived signing token per collection (Landsat C2 L2, Sentinel-1 RTC).

Landsat on Earth Search points at a requester-pays bucket (HTTP 403 without AWS credentials), which is why Landsat comes
from the Planetary Computer.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

TIMEOUT = 60


class StacError(RuntimeError):
    """A STAC request failed or returned nothing usable."""


@dataclass(frozen=True)
class Provider:
    name: str
    search_url: str
    sign_url: str | None = None  # token endpoint prefix; the collection id is appended


PROVIDERS = {
    "earth-search": Provider("earth-search", "https://earth-search.aws.element84.com/v1/search"),
    "planetary-computer": Provider(
        "planetary-computer", "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        "https://planetarycomputer.microsoft.com/api/sas/v1/token/"),
}


def provider(name: str) -> Provider:
    if name not in PROVIDERS:
        raise StacError(f"unknown STAC provider {name!r}; available: {', '.join(PROVIDERS)}")
    return PROVIDERS[name]


def _request(url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "satviz"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code < 500:
                raise StacError(f"{url}: HTTP {e.code}: {detail}") from None
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError) as e:
            last = str(getattr(e, "reason", e))
        time.sleep(1 + attempt)
    raise StacError(f"{url}: could not be reached ({last}); STAC inputs need network access")


def search(prov: str, collection: str, bbox: tuple, datetime_range: str, limit: int = 100, query: dict | None = None,
           ids: list[str] | None = None, max_items: int = 300) -> list[dict]:
    """Items of a collection touching the lon/lat bbox in the date range ("2026-09-20/2026-09-30"), oldest first."""
    p = provider(prov)
    body: dict = {"collections": [collection], "limit": limit}
    if ids:
        body["ids"] = ids
    else:
        body["bbox"] = [round(v, 6) for v in bbox]
        body["datetime"] = datetime_range
    if query:
        body["query"] = query
    items: list[dict] = []
    while len(items) < max_items:
        page = _request(p.search_url, body)
        items += page.get("features", [])
        nxt = next((ln for ln in page.get("links", []) if ln.get("rel") == "next"), None)
        if not nxt or not page.get("features"):
            break
        body = nxt.get("body") or body
    return sorted(items, key=lambda it: it["properties"]["datetime"])


_tokens: dict[str, tuple[str, float]] = {}


def sign(prov: str, collection: str, href: str) -> str:
    """The href, with the provider's anonymous access token appended when the provider needs one."""
    p = provider(prov)
    if not p.sign_url:
        return href
    tok, expiry = _tokens.get(collection, ("", 0.0))
    if time.time() > expiry - 300:
        data = _request(p.sign_url + collection)
        tok = data["token"]
        _tokens[collection] = (tok, time.time() + 3000)
    return f"{href}{'&' if '?' in href else '?'}{tok}"


def href_of(item: dict, asset: str) -> str:
    try:
        return item["assets"][asset]["href"]
    except KeyError:
        raise StacError(f"item {item.get('id')} has no asset {asset!r}; it has {sorted(item.get('assets', {}))}") from None


def scale_offset(item: dict, asset: str) -> tuple[float, float]:
    """Reflectance scaling published in the item's own metadata (never hardcoded): value = DN * scale + offset."""
    rb = (item["assets"][asset].get("raster:bands") or [{}])[0]
    return float(rb.get("scale", 1.0)), float(rb.get("offset", 0.0))
