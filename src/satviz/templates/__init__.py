"""Templates: the three content scenarios (`sar`, `optical`, `sar_optical`).

Importing the package registers them in `satviz.core.TEMPLATES`.
"""
from satviz.templates import scenarios  # noqa: F401
from satviz.templates.base import Resolved, Template, TemplateError, default_recipe, pick_recipes  # noqa: F401
