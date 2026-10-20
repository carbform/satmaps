"""The page arrangements as templates: `single`, `compare` and `grid` take any inputs, with no scenario rules.

Kept so existing job files run unchanged. Prefer the scenario templates, which check what the inputs are and say how they relate.
"""
from __future__ import annotations

from satviz.templates.base import ARRANGEMENTS, Resolved, Template, TemplateError, pairs, pick_recipes, register


class _Generic(Template):
    default_arrangement = ""

    def arrangement_of(self, fig) -> str:
        return self.name

    def resolve(self, fig, combo, products, scene):
        # no scenario wording: these keep the exact output they always had
        return Resolved(self.name, pick_recipes(fig.recipes, products, combo))

    def plan(self, fig, job):
        ids = list(fig.inputs)
        if self.name == "single":
            return [(k,) for k in ids]
        if self.name == "compare":
            if fig.pairs == "all":
                if len(ids) < 2:
                    raise TemplateError("compare with pairs = \"all\" needs at least two inputs")
                return pairs(ids)
            if len(ids) != 2:
                raise TemplateError(f"compare needs exactly 2 inputs (or pairs = \"all\"), got {list(ids)}")
            return [tuple(ids)]
        if not 2 <= len(ids) <= 6:
            raise TemplateError(f"grid needs 2 to 6 inputs, got {len(ids)}")
        return [tuple(ids)]


for _name in ARRANGEMENTS:
    register(type(_name.title(), (_Generic,), {"name": _name, "summary": f"Page arrangement '{_name}' with no scenario rules"}))
