# LiDAR heights and conductor clearance

Independent Python VGI worker: query geospatial analysis from SQL and join the resulting rows to your existing tables.

vgi-lidar 0.3.0 speaks VGI protocol 3.4, so it needs Haybarn 2.0.1 or newer (Haybarn 2.0.0 loads a 3.3 `vgi` extension that cannot attach it).

## Run it

Requires Python 3.14+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/Query-farm/vgi-lidar.git
cd vgi-lidar
uv sync --locked
make demo
make verify-stock
make check
```

`make demo` runs [demo.sql](demo.sql) in stock DuckDB 2.0.0. Demo datasets ship inside the wheel; no data credentials are required. The first run downloads dependencies and signed SQL extensions. `make verify-stock` asserts every expected result in [vgi-worker.json](vgi-worker.json), including empty inputs, joins and multiple batches.

## Analysis contract

`height_metrics((SELECT feature_id, geometry_wkb FROM areas), ...)` returns building/canopy height percentiles, point counts, ground-support status and sampled canopy coverage. `vegetation_clearance((SELECT feature_id, geometry_wkb FROM conductors), ...)` returns vegetation points within a specified 3D distance of the conductor segments.

**Acceptance:** the classified LAZ fixture yields building p95 height 11.9 m, maximum 12 m, and maximum canopy height 18 m. Exactly one vegetation return is within the default 3 m conductor clearance, at distance 2 m. The demo groups these conflicts by circuit. Its sample geometry is plain inline WKB over the bundled `demo://classified.laz` cloud (EPSG:32618): a 50 × 50 m site polygon (`site`) and a 3D conductor at 120 m (`line`), built with `ST_AsWKB('…'::GEOMETRY)`, which stock DuckDB 2.0 provides without Spatial.

Use classified LAS/LAZ with projected metre coordinates. Ground class 2 supplies nearest-neighbour elevations; classes 3/4/5 are vegetation, class 6 buildings. Noise classes 7/18 and withheld returns are excluded. An explicit `cloud_crs` can supply missing metadata. `z_scale_to_m` converts point-cloud Z; conductors must already have absolute metre elevations in the same vertical datum. XY reprojection does not transform vertical datums.

Ground support defaults to a 25 m radius. Unsupported heights are NULL and counted, not replaced with zero. Nearest-ground heights are estimates on steep/complex terrain. Canopy cover is the fraction of **fully ground-supported observed** grid cells with qualifying vegetation, accompanied by `observed_cell_fraction` and `ground_supported_cell_fraction`; cells containing unsupported points are excluded, and no supported cells yields NULL; it is not wall-to-wall canopy area. A zero clearance-result count means no sampled vegetation returns met the threshold, not a certified safe corridor.

The worker loads bounded local LAS/LAZ tiles (default 2 million points), rather than remotely streaming COPC. It uses existing classifications; it does not classify unlabelled clouds or extract conductor geometry. Grid calculations default to 5 m cells with a 100,000-cell cap.

## Use your data

From the repository directory after `uv sync`, launch the locked environment:

```sql
SET allow_extension_repositories = 'allowed';
CREATE EXTENSION REPOSITORY IF NOT EXISTS query_farm
  WITH PREFIX 'https://duckdb-extensions.query.farm';
INSTALL vgi FROM query_farm;
LOAD vgi FROM query_farm;
INSTALL spatial;
LOAD spatial;
ATTACH 'lidar' (TYPE vgi,
  LOCATION 'uv run --locked vgi-lidar-worker');
```

The following template expects your own source tables and paths:

```sql
SELECT feature_id, building_p95_m, canopy_max_m, observed_cell_fraction, status
FROM lidar.main.height_metrics(
    (SELECT asset_id AS feature_id, ST_AsWKB(geom) AS geometry_wkb FROM footprints),
    path := '/absolute/path/classified.laz', geometry_crs := 'EPSG:32618')
ORDER BY feature_id;
```

The two analyses combine per span: canopy over the right-of-way polygon from `height_metrics`, encroaching returns along the conductor from `vegetation_clearance`. On the bundled data this returns `Span 7 | 18.0 | 0.077 | 1 | 2 | 2.0`:

```sql
WITH site(feature_id, geometry_wkb) AS (VALUES ('site', ST_AsWKB(
    'POLYGON ((499995 4099995, 500045 4099995, 500045 4100045, 499995 4100045, 499995 4099995))'::GEOMETRY))),
conductor(feature_id, geometry_wkb) AS (VALUES ('line', ST_AsWKB(
    'LINESTRING Z (500025 4100030 120, 500040 4100030 120)'::GEOMETRY))),
spans(span_id, corridor_id, conductor_id) AS (VALUES ('Span 7', 'site', 'line')),
canopy AS (
    SELECT feature_id, canopy_max_m, canopy_cover_fraction
    FROM lidar.main.height_metrics((SELECT * FROM site))),
returns AS (
    SELECT feature_id, count(*) FILTER (WHERE clearance_m <= 3) AS within_3m,
           count(*) AS within_12m, min(clearance_m) AS closest_m
    FROM lidar.main.vegetation_clearance((SELECT * FROM conductor), clearance_m := 12)
    GROUP BY feature_id)
SELECT s.span_id, c.canopy_max_m, round(c.canopy_cover_fraction, 3) AS canopy_cover,
       coalesce(r.within_3m, 0) AS within_3m, coalesce(r.within_12m, 0) AS within_12m,
       round(r.closest_m, 2) AS closest_m
FROM spans s
JOIN canopy c ON c.feature_id = s.corridor_id
LEFT JOIN returns r ON r.feature_id = s.conductor_id
ORDER BY s.span_id;
```

WKB is an ordinary SQL BLOB with an explicit companion CRS, not an automatically transformed geometry. Use `ST_AsWKB` on input and `ST_GeomFromWKB` on output when using Spatial. Coordinates always use X/Y order. Do not join different coordinate systems without transforming them. Input IDs are retained as VARCHAR for joins. Invalid input schemas, geometries, coordinates and exceeded resource limits fail explicitly.

## Verification and provenance

- Scientific fixtures and edge cases: [tests/test_analysis.py](tests/test_analysis.py).
- Real SQL across stdio, launch and HTTP: [test/sql/gis.test](test/sql/gis.test), run by `make check`.
- Stock DuckDB contract: `make verify-stock` writes local evidence to `validation/stock-duckdb.json`.
- Full local checks: `make check`; generated validation output is intentionally untracked.
- Worker language: Python, pinned locally to 3.14. SDK: `vgi-python 0.51.1` with the starter's `>=0.51.1,<0.52` compatibility bound retained.
- Starter: [Query-farm/vgi-starter-python](https://github.com/Query-farm/vgi-starter-python), commit `9cca9105474d6e0052b8e343c8ea21f3d1a7503c`, template 1.3.0.
- Stock engine: DuckDB 2.0.0, signed VGI extension `e75482339d` from `query_farm`. The starter integration runner is separately pinned to `haybarn-unittest 2.0.1rc3`; it is not the stock DuckDB check.

`make check` includes formatting, Ruff, strict mypy, docstring checks, unit tests, all three SQL transports, executed metadata examples and stock DuckDB assertions. `make lint-ai` is an optional agent evaluation and is not part of the completed checks. All functions live in the `main` schema. Tests use synthetic known-answer fixtures, not a claim of production accuracy on every dataset.

Run `make release-check` to build a wheel from the source archive and verify its installed SQL interface outside the checkout. `make verify-container` builds locked runtime dependencies and checks every stock SQL assertion through a non-root, read-only HTTP container. See [PRODUCTION.md](PRODUCTION.md) for deployment, capacity limits, release evidence and operational boundaries.

## Support

Source and issue tracking are published at [Query-farm/vgi-lidar](https://github.com/Query-farm/vgi-lidar). No hosted deployment or container release is provided by publishing this source. Keep reports tied to the input CRS, resource limits and reproducible SQL. See [LICENSE](LICENSE) for the starter's license and dependency licenses for their terms.

## Notebook

[Executed LiDAR walkthroughs](notebooks/README.md) separate supported canopy heights from absolute conductor clearance.
