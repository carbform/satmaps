"""Templates: the three content scenarios (`sar`, `optical`, `sar_optical`).

Importing the package registers them in `satmaps.core.TEMPLATES`.
"""
from satmaps.templates import scenarios  # noqa: F401
from satmaps.templates.base import Resolved, Template, TemplateError, default_recipe, pick_recipes  # noqa: F401
