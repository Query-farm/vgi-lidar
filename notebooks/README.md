# LiDAR analysis walkthroughs

- [01 · A higher canopy statistic does not imply growth](01_height_support_changes_the_population.ipynb) holds a classified synthetic point cloud fixed while tightening ground support. It separates a changed percentile population from a fixed absolute 3D conductor-clearance calculation.
It covers both public SQL functions, `height_metrics` and `vegetation_clearance`. Every result comes from actual released-worker calls; all data are explicitly synthetic. No private credentials are involved.

## Run locally or in Colab

Install [uv](https://docs.astral.sh/uv/) and Git, then run from `notebooks/`:

```sh
uv sync --locked
uv run --locked vgi-notebooks 01_height_support_changes_the_population.ipynb
```

An editor can use `notebooks/.venv/bin/python` with `notebooks/` as its working directory. Restart/run all after changing parameters. Each Colab badge opens the same source. Its bootstrap installs the shared **base** package; local publication adds `[runner]`. The notebook is self-contained and uses this short literal released launcher:

```sql
ATTACH 'lidar' (TYPE vgi,
 LOCATION 'uvx --python 3.13 --from git+https://github.com/Query-farm/vgi-lidar@v0.1.0 vgi-lidar-worker');
```

The worker owns its dependency constraints and runs in its own Python 3.13 environment. The old source-SHA constraints file and extra SDK pins are unnecessary. laspy/lazrs, SciPy, Shapely and PyProj stay outside the notebook kernel. First use downloads Git/package dependencies and VGI. Source is release-pinned; transitive versions follow the release's declared constraints, while local notebook dependencies are locked.

Shared connections use an empty temporary SQL secret directory with persistent secrets disabled. No SQL secret is created; cleanup closes the connection.

## Fixed scientific fixture and support experiment

`demo://classified.laz` contains 29 constructed returns: 25 class-2 ground returns at 100 m, two building returns and two vegetation returns. EPSG:32618 X/Y and a synthetic common vertical datum are in metres. Inline `VALUES` rows (WKB from `ST_AsWKB('…'::GEOMETRY)`) supply a 50 × 50 m site and a conductor at 120 m. There is no observation date, surveyed place, live/replay mode or fallback dataset.

Three worker analyses materialize a fixed 25 m reference, the selected ground-support radius and a fixed 12 m conductor-clearance envelope. Later queries use local tables. Bounds are 100 cloud points, 100 grid cells, 10 segments and 100 candidate-distance evaluations; oversized work is rejected rather than truncated.

Ground support is the inclusive horizontal distance to the nearest usable class-2 return. Unsupported building/vegetation points are excluded from height percentiles. Canopy cover uses fully ground-supported **observed** cells; observed-cell and ground-support fractions have different denominators. This sparse fixture observes only 26 of the site's 100 cells.

```sh
uv run --locked vgi-notebooks 01_height_support_changes_the_population.ipynb \
  --parameters '{"GROUND_RADIUS_M":2.0}' --output-dir validation/radius-2
```

The authored parameter domain is 2–25 m; the worker accepts other positive radii. Tightening from 25 to 2 m excludes the lower vegetation return, raising canopy p95 from 17.6 to 18 m and changing canopy cover from 2/26 to 1/25. The point cloud and observed footprint do not change. This is a population effect, not growth.

The fixed clearance distances are 2 and 10 m. They depend on absolute 3D coordinates, not ground normalization, and remain unchanged across the experiment. The local 3 m screen is illustrative, not a safety or regulatory standard. Sparse returns cannot certify a corridor. Real use requires appropriate classifications, ground support, positioning, a common vertical datum and valid conductor geometry. The worker does no classification or conductor extraction.

## Evidence and limitations

[coverage.json](coverage.json) binds the public names to visible executed SQL, outputs and interpretation. Complete native function/table/view exports are in [coverage/](coverage/), including empty exports. They were captured from the released v0.1.0 catalog through actual Haybarn 2.0.0rc11 at source revision `c8ef3ade82d791857046e8bd0083a90506717e97`, which still contained the starter template's `examples` schema and `demo_input`; both were removed in 0.2.0. Regenerate the coverage captures and re-execute the notebook against the 0.2.0 release launcher once it is tagged.

The default and notebook-only detached experiments execute independently. Nine scientific SQL invariants plus two population/CRS controls verify the stated distinctions. The reference/clearance fingerprint stays fixed under the support experiment. The runner protects successful defaults, rejects unknown parameters and requires separate experiment destinations.

Charts use shared SVG presentation and linked assets under `charts/`; review PNGs and diagnostics are ignored. One fresh preloaded Python 3.12 kernel exercises the complete worker/fixture bootstrap without replacing loaded pandas, Matplotlib, IPython, ipykernel or jupyter-client, and without installing runner/GIS packages in the kernel. Hosted Colab was not manually executed.

Existing green [source CI at the unchanged baseline](https://github.com/Query-farm/vgi-lidar/actions/runs/43619199893) is reused. No worker rebuild, repeated full source suite or container publication is part of this notebook-only update. Full notebook standards live in the [shared package](https://github.com/Query-farm/vgi-example-notebooks/blob/main/docs/standard.md).
