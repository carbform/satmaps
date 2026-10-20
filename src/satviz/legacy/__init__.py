"""Legacy NISAR-only figures (`satviz render`): one module per figure.

Each exposes `render(scene, bands, out_dir, ...) -> list[Path]`. New work uses the job pipeline (`satviz run`) and templates.
`bands` maps "L"/"S" to datasets from `satviz.sensors.nisar_gcov.io.load_roi`.
"""
