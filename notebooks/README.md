# LiDAR analysis walkthroughs

- [01 · A higher canopy statistic does not imply growth](01_height_support_changes_the_population.ipynb) holds a classified synthetic point cloud fixed while tightening ground support. It separates a changed percentile population from a fixed absolute 3D conductor-clearance calculation.
- [02 · Complete the input before previewing a report](02_paginated_inventory_report.ipynb) separately demonstrates the public `examples` schema: local synthetic API pagination, generated budget scenarios and NULL-preserving report previews. This common starter-workflow pattern is also used by the Terrain sibling; here it executes through the released LiDAR worker. These functions do not perform point-cloud analysis.

Together they cover all six distinct public SQL names. Every result comes from actual released-worker calls; all data are explicitly synthetic. No private credentials, real purchasing decisions or messages are involved.

## Run locally or in Colab

Install [uv](https://docs.astral.sh/uv/) and Git, then run from `notebooks/`:

```sh
uv sync --locked
uv run --locked vgi-notebooks 01_height_support_changes_the_population.ipynb
uv run --locked vgi-notebooks 02_paginated_inventory_report.ipynb
```

An editor can use `notebooks/.venv/bin/python` with `notebooks/` as its working directory. Restart/run all after changing parameters. Each Colab badge opens the same source. Its bootstrap installs the shared **base** package; local publication adds `[runner]`. The first notebook is self-contained. The second retrieves its immutable, hash-verified companion through the shared `lidar` registry, without cloning the repository.

Both use this short literal released launcher:

```sql
ATTACH 'lidar' (TYPE vgi,
 LOCATION 'uvx --python 3.13 --from git+https://github.com/Query-farm/vgi-lidar@v0.1.0 vgi-lidar-worker');
```

The worker owns its dependency constraints and runs in its own Python 3.13 environment. The old source-SHA constraints file and extra SDK pins are unnecessary. laspy/lazrs, SciPy, Shapely and PyProj stay outside the notebook kernel. First use downloads Git/package dependencies and VGI. Source is release-pinned; transitive versions follow the release's declared constraints, while local notebook dependencies are locked.

Shared connections use an empty temporary SQL secret directory with persistent secrets disabled. The starter fixture additionally clears/restores `LIDAR_API_TOKEN` privately, rejects Authorization headers and binds only to loopback. It records sanitized pagination, never credentials. No SQL secret is created; cleanup closes the connection and local server.

## Fixed scientific fixture and support experiment

`demo://classified.laz` contains 29 constructed returns: 25 class-2 ground returns at 100 m, two building returns and two vegetation returns. EPSG:32618 X/Y and a synthetic common vertical datum are in metres. The worker's `demo_input` supplies a 50 × 50 m site and a conductor at 120 m. There is no observation date, surveyed place, live/replay mode or fallback dataset.

Three worker analyses materialize a fixed 25 m reference, the selected ground-support radius and a fixed 12 m conductor-clearance envelope. Later queries use local tables. Bounds are 100 cloud points, 100 grid cells, 10 segments and 100 candidate-distance evaluations; oversized work is rejected rather than truncated.

Ground support is the inclusive horizontal distance to the nearest usable class-2 return. Unsupported building/vegetation points are excluded from height percentiles. Canopy cover uses fully ground-supported **observed** cells; observed-cell and ground-support fractions have different denominators. This sparse fixture observes only 26 of the site's 100 cells.

```sh
uv run --locked vgi-notebooks 01_height_support_changes_the_population.ipynb \
  --parameters '{"GROUND_RADIUS_M":2.0}' --output-dir validation/radius-2
```

The authored parameter domain is 2–25 m; the worker accepts other positive radii. Tightening from 25 to 2 m excludes the lower vegetation return, raising canopy p95 from 17.6 to 18 m and changing canopy cover from 2/26 to 1/25. The point cloud and observed footprint do not change. This is a population effect, not growth.

The fixed clearance distances are 2 and 10 m. They depend on absolute 3D coordinates, not ground normalization, and remain unchanged across the experiment. The local 3 m screen is illustrative, not a safety or regulatory standard. Sparse returns cannot certify a corridor. Real use requires appropriate classifications, ground support, positioning, a common vertical datum and valid conductor geometry. The worker does no classification or conductor extraction.

## Generic starter workflow experiment

The separate starter notebook serves six invented equipment prices from three loopback API pages. The actual worker follows pagination; materialization prevents duplicate fetches during display. SQL converts prices to decimals and uses `sequence_table` to generate seven fixed budgets. Affordability compares one item at a time, not a combined basket.

```sh
uv run --locked vgi-notebooks 02_paginated_inventory_report.ipynb \
  --parameters '{"BUDGET_USD":75}' --output-dir validation/budget-75
```

The 50 USD default selects three items; 75 USD selects four. IDs, prices, three requests and the full budget grid remain fixed. The selected bar, item highlights and two local reviewer-preview texts change. `greet` preserves a third reviewer's NULL name under both overloads; salutation formatting neither validates an identity nor sends a message. The notebook explicitly repeats the shared starter contracts, not new LiDAR capabilities.

## Evidence and limitations

[coverage.json](coverage.json) binds all six public names to visible executed SQL, outputs and interpretation. Complete native function/table/view exports are in [coverage/](coverage/), including empty exports. Both main and examples schemas remain in the denominator, including optional-auth `fetch_items`; `greet` overloads count once. Release and current catalogs were captured through actual Haybarn 2.0.0rc11 at identical source revision `c8ef3ade82d791857046e8bd0083a90506717e97`.

Both defaults and notebook-only detached experiments execute independently. Nine scientific SQL invariants plus two population/CRS controls, seven starter SQL checks and an exact three-request audit verify the stated distinctions. The reference/clearance fingerprint stays fixed under the support experiment. The runner protects successful defaults, rejects unknown parameters and requires separate experiment destinations.

Charts use shared SVG presentation and linked assets under `charts/`; review PNGs and diagnostics are ignored. One fresh preloaded Python 3.12 kernel exercises the complete worker/fixture bootstrap without replacing loaded pandas, Matplotlib, IPython, ipykernel or jupyter-client, and without installing runner/GIS packages in the kernel. A synthetic token sentinel verifies suppression and restoration. Hosted Colab was not manually executed.

Existing green [source CI at the unchanged baseline](https://github.com/Query-farm/vgi-lidar/actions/runs/43619199893) is reused. No worker rebuild, repeated full source suite or container publication is part of this notebook-only update. Full notebook standards live in the [shared package](https://github.com/Query-farm/vgi-example-notebooks/blob/main/docs/standard.md).
