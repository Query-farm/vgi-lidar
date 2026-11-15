-- Offline acceptance demos. Run with: uv run --with duckdb==2.0.0 python scripts/run_demo.py
-- The runner loads VGI and attaches this worker. Sample geometry is inline WKB over the
-- bundled demo://classified.laz cloud (EPSG:32618): a 50 x 50 m site and a 3D conductor at 120 m.

-- Building and canopy metrics on bundled synthetic data
WITH site(feature_id, geometry_wkb) AS (VALUES ('site', ST_AsWKB('POLYGON ((499995 4099995, 500045 4099995, 500045 4100045, 499995 4100045, 499995 4099995))'::GEOMETRY))) SELECT feature_id, round(building_p95_m, 1), canopy_max_m FROM lidar.main.height_metrics((SELECT * FROM site)) ORDER BY feature_id;

-- Vegetation conductor clearance on bundled synthetic data
WITH conductor(feature_id, geometry_wkb) AS (VALUES ('line', ST_AsWKB('LINESTRING Z (500025 4100030 120, 500040 4100030 120)'::GEOMETRY))) SELECT feature_id, round(clearance_m, 2) FROM lidar.main.vegetation_clearance((SELECT * FROM conductor)) ORDER BY feature_id, point_index;

-- Prioritize vegetation clearance by asset owner
WITH conductor(feature_id, geometry_wkb) AS (VALUES ('line', ST_AsWKB('LINESTRING Z (500025 4100030 120, 500040 4100030 120)'::GEOMETRY))),
assets(feature_id, circuit_name) AS (VALUES ('line', 'Circuit 12')),
conflicts AS (SELECT * FROM lidar.main.vegetation_clearance((SELECT * FROM conductor)))
SELECT a.circuit_name, count(*) AS vegetation_returns, round(min(c.clearance_m), 2) AS closest_m
FROM conflicts c JOIN assets a USING(feature_id) GROUP BY a.circuit_name ORDER BY a.circuit_name;
