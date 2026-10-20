"""Templates: content scenarios (optical, sar, optical_sar, sar_vs_sar) plus the bare page arrangements.

Importing the package registers them in `satviz.core.TEMPLATES`.
"""
from satviz.templates import generic, scenarios  # noqa: F401
from satviz.templates.base import Resolved, Template, TemplateError, default_recipe, pick_recipes  # noqa: F401
