# Changelog

## 0.1.0 (2026-11-14)

First release. Bounded local LAS/LAZ analysis from SQL:

- `height_metrics` — building/canopy height percentiles, ground-support status and sampled canopy cover per input polygon.
- `vegetation_clearance` — vegetation returns within a 3D distance of conductor segments.
- `demo_input` — bundled polygon / 3D conductor fixtures.
- Composed example queries joining canopy and clearance per span, plus a corridor agent task.

Targets: vgi-python 0.51 · VGI protocol 3.3 · Haybarn 2.0.0rc11 · vgi-lint-check 2.x (unpinned)
