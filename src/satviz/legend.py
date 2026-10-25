"""The how-to-read legend of a page with several products: every item says which product it belongs to.

A page of one product needs no names; with two or more, "RED = HH" alone could mean either, so items are prefixed with the
product ("NISAR L-BAND · RED = HH"). Products whose legends read the same share items. The six slots of the footer are shared
out by how many different legends there are: one gets them all, two get a row of three each, and three or more get one line
each (with a grey swatch) that lists the channels ("SENTINEL-2C · R B04 · G B03 · B B02")."""
from __future__ import annotations

import re

from satviz.core import LegendItem, Product

SLOTS = 6
SEP = " · "


def _day(p: Product) -> str:
    when = p.meta.get("start")
    return f"{when.day} {when:%b}" if when else ""


def group_names(groups: list[list[Product]]) -> list[str]:
    """One name per group of products: platform and label ('NISAR L-BAND'), with the date added as far as it takes to tell
    the groups apart."""
    def name(ps: list[Product], depth: int) -> str:
        p = ps[0]
        parts = [p.meta.get("platform", "")]
        if depth >= 1:
            parts.append(p.meta.get("label", ""))
        if depth >= 2:
            parts.append(" + ".join(dict.fromkeys(_day(q) for q in ps if _day(q))))
        return " ".join(x for x in parts if x).upper()

    for depth in (1, 2):
        names = [name(g, depth) for g in groups]
        if len(set(names)) == len(names):
            break
    return names


def _channel(item: LegendItem) -> str:
    left, sep, right = item.text.partition(" = ")
    if not sep:
        return item.text
    bare = re.sub(r"\s+BAND$", "", re.sub(r"\s*\(.*\)$", "", right).strip())
    return f"{left[0]} {bare}"


def named_legend(entries: list[tuple[Product, list[LegendItem]]]) -> list[LegendItem]:
    """The legend for products shown on one page: `entries` are (product, its recipe's legend) in reading order."""
    if len(entries) < 2:
        return list(entries[0][1])[:SLOTS] if entries else []
    groups: dict[tuple, tuple[list[Product], list[LegendItem]]] = {}
    for product, legend in entries:  # the same product (platform and label) with the same legend is one group
        key = (product.meta.get("platform"), product.meta.get("label"), tuple(i.text for i in legend))
        groups.setdefault(key, ([], legend))[0].append(product)
    members = [g[0] for g in groups.values()]
    names = group_names(members)
    legends = [g[1] for g in groups.values()]
    if len(groups) == 1:
        return [LegendItem(i.color, f"{names[0]}{SEP}{i.text}") for i in legends[0][:SLOTS]]
    if len(groups) == 2:
        return [LegendItem(i.color, f"{n}{SEP}{i.text}") for n, leg in zip(names, legends, strict=True) for i in leg[:3]]
    out = []
    for n, leg in zip(names, legends, strict=True):
        channels = [i for i in leg if i.color != "noise"][:3]
        out.append(LegendItem("noise", n + SEP + SEP.join(_channel(i) for i in channels)))  # (a grey swatch: no one colour)
    return out[:SLOTS]
