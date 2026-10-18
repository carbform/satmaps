"""One module per figure. Each exposes `render(scene, bands, out_dir, ...) -> list[Path]`.

`bands` maps "L"/"S" to datasets from `nisar_viz.io.load_roi`.
"""
