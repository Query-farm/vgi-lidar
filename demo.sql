-- Offline acceptance demos. Run with: uv run --with duckdb==2.0.0 python scripts/run_demo.py
-- The runner loads VGI, attaches this worker, and installs Spatial for geometry joins.

-- Demo LiDAR geometry on bundled synthetic data
SELECT feature_id FROM lidar.main.demo_input();

-- Building and canopy metrics on bundled synthetic data
SELECT feature_id, round(building_p95_m, 1), canopy_max_m FROM lidar.main.height_metrics((SELECT * FROM lidar.main.demo_input())) ORDER BY feature_id;

-- Vegetation conductor clearance on bundled synthetic data
SELECT feature_id, round(clearance_m, 2) FROM lidar.main.vegetation_clearance((SELECT * FROM lidar.main.demo_input(kind := 'conductor'))) ORDER BY feature_id, point_index;

-- Prioritize vegetation clearance by asset owner
WITH assets(feature_id, circuit_name) AS (VALUES ('line', 'Circuit 12')),
conflicts AS (SELECT * FROM lidar.main.vegetation_clearance((SELECT * FROM lidar.main.demo_input(kind := 'conductor'))))
SELECT a.circuit_name, count(*) AS vegetation_returns, round(min(c.clearance_m), 2) AS closest_m
FROM conflicts c JOIN assets a USING(feature_id) GROUP BY a.circuit_name ORDER BY a.circuit_name;
