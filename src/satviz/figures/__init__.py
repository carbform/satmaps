"""One module per figure. Each exposes `render(scene, bands, out_dir, ...) -> list[Path]`.

`bands` maps "L"/"S" to datasets from `satviz.sensors.nisar_gcov.io.load_roi`.
"""
