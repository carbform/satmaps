"""Job file linter and pre-flight validator (`satmaps check`)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from satmaps.area import AreaError
from satmaps.autoarea import common_area
from satmaps.core import SENSORS, TEMPLATES, THEMES
from satmaps.job import JobError, load_job, read_toml
from satmaps.registry import load_builtin
from satmaps.sources import SourceError, resolve_one_file


def check_job(job_path: str | Path, data_dir: str | Path | None = None,
              layouts_dir: str | Path = "layouts", verbose: bool = False,
              stream: TextIO | None = None) -> int:
    """Validate a job TOML file without rendering pixels: check syntax, input files, footprints, overlap, and templates."""
    out = stream if stream is not None else sys.stdout
    path = Path(job_path)

    out.write(f"Checking job: {path}\n")

    if not path.exists():
        out.write(f"  ✗ Job file not found: {path}\n")
        out.write("Result: FAILED (1 error)\n")
        return 2

    # Step 1: TOML Syntax
    try:
        read_toml(path)
        out.write("  ✓ TOML syntax: valid\n")
    except (JobError, ValueError, OSError) as e:
        out.write(f"  ✗ TOML syntax error: {e}\n")
        out.write("Result: FAILED (1 error)\n")
        return 2

    # Step 2: Job schema & Structure
    try:
        job = load_job(path, data_dir)
        out.write("  ✓ Job structure and schema: valid\n")
    except (JobError, ValueError, FileNotFoundError) as e:
        out.write(f"  ✗ Job schema error: {e}\n")
        out.write("Result: FAILED (1 error)\n")
        return 2

    load_builtin()
    errors: list[str] = []
    infos: dict = {}

    # Step 3: Input files & Sensors
    out.write(f"  Inputs ({len(job.inputs)}):\n")
    for key, spec in job.inputs.items():
        if spec.sensor not in SENSORS:
            errors.append(f"Input '{key}': unknown sensor '{spec.sensor}'")
            out.write(f"    ✗ {key}: unknown sensor '{spec.sensor}'\n")
            continue

        try:
            resolved_file = resolve_one_file(spec, job.scene.data_dir)
        except (FileNotFoundError, SourceError) as e:
            errors.append(f"Input '{key}': {e}")
            out.write(f"    ✗ {key}: {e}\n")
            continue

        try:
            info = SENSORS[spec.sensor].describe(spec, job.scene.data_dir, None)
            infos[key] = info
            sensor_obj = SENSORS[spec.sensor]
            kind = getattr(sensor_obj, "kind", "sensor")
            res_str = f"{info.resolution_m:g}m pixels"
            epsg_str = f"EPSG:{info.epsg}"
            out.write(f"    ✓ {key}: {spec.sensor} ({kind}), {res_str}, {epsg_str} ({resolved_file.name})\n")
        except Exception as e:
            errors.append(f"Input '{key}': error reading metadata: {e}")
            out.write(f"    ✗ {key}: error reading metadata: {e}\n")

    # Step 4: Spatial Coverage & Overlap
    out.write("  Spatial Coverage:\n")
    if job.area is not None:
        try:
            bbox = job.area.lonlat_bbox()
            out.write(
                f"    ✓ Explicit area: W {bbox[0]:.3f} S {bbox[1]:.3f} E {bbox[2]:.3f} N {bbox[3]:.3f} (EPSG:{job.area.epsg})\n"
            )
        except Exception as e:
            errors.append(f"Area error: {e}")
            out.write(f"    ✗ Area error: {e}\n")
    else:
        needed = list(job.inputs.keys())
        missing_fps = [k for k in needed if k in infos and not infos[k].footprint]
        if missing_fps:
            err = f"No footprint metadata for input(s): {', '.join(missing_fps)}; job requires an explicit [area]"
            errors.append(err)
            out.write(f"    ✗ {err}\n")
        elif all(k in infos for k in needed):
            try:
                footprints = {k: infos[k].footprint for k in needed}
                labels = {k: f"{k} ({job.inputs[k].file or k})" for k in needed}
                common = common_area(footprints, labels)
                bbox = common.lonlat_bbox()
                area_km2 = getattr(common, "area_km2", 0.0)
                km2_str = f" (~{area_km2:.0f} km²)" if area_km2 > 0 else ""
                out.write(f"    ✓ Footprint overlap: W {bbox[0]:.3f} S {bbox[1]:.3f} E {bbox[2]:.3f} N {bbox[3]:.3f}{km2_str}\n")
            except AreaError as e:
                errors.append(f"Inputs do not overlap: {e}")
                out.write(f"    ✗ Inputs do not overlap: {e}\n")
        else:
            out.write("    - Overlap check skipped due to unresolved inputs.\n")

    # Step 5: Zooms
    if job.zoom_specs:
        out.write(f"  Zoom Insets ({len(job.zoom_specs)}):\n")
        if len(job.zoom_specs) > 3:
            err = f"{len(job.zoom_specs)} [[zooms]] defined; a figure has room for at most 3"
            errors.append(err)
            out.write(f"    ✗ {err}\n")
        for i, z in enumerate(job.zoom_specs, 1):
            key = str(z.get("key", chr(64 + i)))
            name = str(z.get("name", ""))
            name_str = f" ({name})" if name else ""
            if "rows" in z and "cols" in z:
                out.write(f"    ✓ Zoom {key}{name_str}: canvas rows {z['rows']}, cols {z['cols']}\n")
            elif "center" in z and "size_km" in z:
                out.write(f"    ✓ Zoom {key}{name_str}: center {z['center']}, size {z['size_km']} km\n")
            else:
                err = f"Zoom {key}: needs `center` + `size_km` or `rows` + `cols`"
                errors.append(err)
                out.write(f"    ✗ {err}\n")

    # Step 6: Figures & Templates
    out.write(f"  Figures ({len(job.figures)}):\n")
    for i, fig in enumerate(job.figures, 1):
        fig_label = fig.name or f"Figure {i}"
        fig_errors = []

        if fig.template not in TEMPLATES:
            fig_errors.append(f"unknown template '{fig.template}'; available: {', '.join(sorted(TEMPLATES))}")
        for th in fig.themes:
            if th not in THEMES:
                fig_errors.append(f"unknown theme '{th}'; available: {', '.join(sorted(THEMES))}")

        if fig.layout:
            name = Path(fig.layout).expanduser()
            if name.suffix != ".toml":
                name = name.with_name(name.name + ".toml")
            tried = [name] if name.is_absolute() else [job.path.parent / name, Path.cwd() / name, Path(layouts_dir) / name]
            if not any(t.is_file() for t in tried):
                fig_errors.append(f"layout '{fig.layout}' not found in: {', '.join(str(t.parent) for t in tried)}")

        if not fig_errors:
            try:
                combos = TEMPLATES[fig.template].plan(fig, job)
                themes_str = ", ".join(fig.themes)
                out.write(f"    ✓ {fig_label}: template '{fig.template}', {len(combos)} combination(s), theme(s): {themes_str}\n")
            except Exception as e:
                fig_errors.append(f"planning error: {e}")

        for fe in fig_errors:
            errors.append(f"{fig_label}: {fe}")
            out.write(f"    ✗ {fig_label}: {fe}\n")

    # Step 7: Final Result
    if errors:
        out.write(f"\nResult: FAILED ({len(errors)} error(s) found)\n")
        return 2

    out.write(f"\nResult: OK - job is valid and ready to run ({len(job.inputs)} input(s), {len(job.figures)} figure(s))\n")
    return 0
