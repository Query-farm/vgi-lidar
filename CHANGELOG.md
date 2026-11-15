# Changelog

## 0.2.0 (2026-11-14)

- Removed the starter template's demo schema (examples.greet/fetch_items/sequence_table), demo_input and the placeholder lidar_api secret type. The worker now exposes only `main.height_metrics` and `main.vegetation_clearance` and declares no credentials.
- Examples, SQL tests, the stock DuckDB manifest, demo.sql and agent tasks build their sample site polygon and 3D conductor as inline WKB (`ST_AsWKB('…'::GEOMETRY)`) over the bundled `demo://classified.laz` cloud. Callers of `demo_input()` should do the same.
- Removed the starter's SDK recipes (`examples/`), its mock REST API and starter unit/SQL tests, and the starter-only pagination notebook.

## 0.1.0 (2026-11-14)

First release. Bounded local LAS/LAZ analysis from SQL:

- `height_metrics` — building/canopy height percentiles, ground-support status and sampled canopy cover per input polygon.
- `vegetation_clearance` — vegetation returns within a 3D distance of conductor segments.
- `demo_input` — bundled polygon / 3D conductor fixtures.
- Composed example queries joining canopy and clearance per span, plus a corridor agent task.

Targets: vgi-python 0.51 · VGI protocol 3.3 · Haybarn 2.0.0rc11 · vgi-lint-check 2.x (unpinned)
