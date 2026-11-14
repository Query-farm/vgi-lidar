# LiDAR notebook

[01 · Height support changes the population](01_height_support_changes_the_population.ipynb) uses the worker's explicitly synthetic packaged LAZ, site and conductor. It explains why a stricter ground-support radius can raise a canopy percentile without any physical growth, and distinguishes ground-normalized heights from absolute 3D clearance.

Run from this directory alone with [uv](https://docs.astral.sh/uv/) and Git:

```sh
uv sync --locked
uv run --locked python execute.py
uv run --locked python execute.py --parameters '{"GROUND_RADIUS_M":2.0}' --output-dir validation/radius-2
```

For interactive use, register the environment with `uv run --locked python -m ipykernel install --user --name lidar-notebooks --display-name 'Python (LiDAR notebooks)'`, select that kernel in Jupyter and Restart Kernel → Run All after parameter edits. The runner uses a fresh temporary kernel, replaces saved defaults only after success, requires separate experiment destinations, and copies branding/docs/runtime companions. Generated outputs and validation evidence are ignored.

## Portable source and data

The visible literal ATTACH launches `uvx --python 3.13 --from git+https://github.com/Query-farm/vgi-lidar.git@7d25870f8d6e6afec091fdf75a7bf602eb88a0de --constraints worker-constraints.txt vgi-lidar-worker`. uv fetches/builds this immutable public revision and caches the installed package; no worker checkout, parent path or local worker executable is required. Worker constraints are exported from that revision's root lock, retaining SDK 0.51.1/RPC 0.53.1, laspy/lazrs, SciPy, NumPy, Shapely and pyproj. Update source pin and constraints together after revalidation. The independent notebook environment pins Haybarn 2.0.0rc11.

The packaged `demo://classified.laz` is a 29-return constructed scientific fixture, not a real survey. There are 25 class-2 ground returns at 100 m, two building returns and two vegetation returns, in EPSG:32618 with metre X/Y and a synthetic common vertical datum. The worker supplies the 50 × 50 m polygon and 3D conductor at 120 m. No observation date is invented. Three deliberate worker analyses materialize a reference at 25 m, selected support radius, and a fixed 12 m clearance envelope. All later analysis reads those ordinary in-memory tables. Bounds: 100 cloud points, 100 grid cells, 10 segments and 100 candidate-distance evaluations. No live/replay mode or fallback data exists.

Every execution uses a fresh temporary secret directory with persistent secrets disabled, drains and asserts an empty SQL secret inventory before ATTACH, and cleans up after closing the connection. These computational functions need no credentials.

## Interpretation and experiment

Ground support is the inclusive horizontal distance to the nearest usable class-2 ground return. Unsupported building/vegetation returns do not enter height percentiles. Canopy cover uses fully ground-supported observed grid cells; observed-cell and ground-support fractions have different denominators. This sparse fixture observes 26 of 100 cells. Tightening `GROUND_RADIUS_M` from 25 to 2 excludes the lower vegetation return, raising canopy p95 from 17.6 to 18 m and changing the canopy fraction from 2/26 to 1/25. It does not change the point cloud or observed footprint.

The fixed clearance envelope returns distances 2 and 10 m from the same conductor. Those depend on absolute 3D coordinates, not ground normalization, and stay fixed across the support experiment. The local 3 m screen is illustrative, not a safety/regulatory standard. Neither a zero count nor these sparse returns certify a corridor. Ground classifications, nearest-neighbor suitability, positioning, vertical datum and conductor geometry must be established for real data.

Nine SQL invariants, CRS/population controls and a reference/clearance fingerprint verify the analytical distinctions. The default and a detached notebook-only 2 m experiment are executed separately, charts visually reviewed, and three runner guards protect the saved default. Audits live under ignored `artifacts/` and `validation/`.

Source validation includes 14 units on Python 3.13 and 3.14, 97 stdio/97 Unix/61 HTTP SQL assertions, metadata 100/L2, lint/type/doc gates, six stock DuckDB checks and six checks through an isolated sdist-built wheel. Python 3.14 emits four upstream laspy ctypes deprecation warnings. Docker is unavailable; no container check or deployment is claimed. See [STANDARD.md](STANDARD.md) and the root source documentation.
