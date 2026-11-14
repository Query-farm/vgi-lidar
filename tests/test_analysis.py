from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from shapely.geometry import LineString, box

from lidar_worker.analysis import Cloud, conductor_clearance, height_metrics, read_cloud


def args(**updates: Any) -> SimpleNamespace:
    return SimpleNamespace(
        **{
            "geometry_crs": "EPSG:32618",
            "ground_radius_m": 25.0,
            "grid_size_m": 5.0,
            "canopy_height_m": 2.0,
            "max_grid_cells": 100000,
            "clearance_m": 3.0,
            "max_segments": 10000,
            "max_distance_evaluations": 50000000,
            **updates,
        }
    )


@pytest.fixture
def cloud() -> Any:
    return read_cloud("demo://classified.laz", 1000, "", 1.0)


def area() -> Any:
    return {"feature_id": "site", "geometry_wkb": box(499995, 4099995, 500045, 4100045).wkb}


def conductor(z: bool = True) -> Any:
    coordinates = [(500025, 4100030, 120), (500040, 4100030, 120)]
    return {"feature_id": "line", "geometry_wkb": LineString(coordinates if z else [p[:2] for p in coordinates]).wkb}


def test_known_building_and_canopy_heights(cloud: Any) -> None:
    result = height_metrics(area(), cloud, args())
    assert result["building_p95_m"] == pytest.approx(11.9)
    assert result["building_max_m"] == 12
    assert result["canopy_max_m"] == 18
    assert result["vegetation_points"] == 2
    assert 0 < result["canopy_cover_fraction"] <= 1
    assert 0 < result["observed_cell_fraction"] < 1
    assert result["status"] == "ok"


def test_actual_3d_clearance_excludes_lower_tree(cloud: Any) -> None:
    results = list(conductor_clearance(conductor(), cloud, args()))
    assert len(results) == 1
    assert results[0]["clearance_m"] == 2
    assert results[0]["z_m"] == 118
    assert results[0]["nearest_z_m"] == 120
    assert list(conductor_clearance(conductor(), cloud, args(clearance_m=1))) == []


def test_clearance_requires_absolute_3d_geometry(cloud: Any) -> None:
    with pytest.raises(ValueError, match="3D"):
        list(conductor_clearance(conductor(False), cloud, args()))


def test_missing_ground_is_explicit(cloud: Any) -> None:
    xyz, classes, usable, crs = cloud.xyz, cloud.classes, cloud.usable, cloud.crs
    kinds = classes.copy()
    kinds[kinds == 2] = 1
    result = height_metrics(area(), Cloud(xyz, kinds, usable, crs), args())
    assert result["status"] == "no_ground"
    assert result["building_p95_m"] is None
    assert result["unsupported_points"] == 4


def test_empty_polygon_and_limits(cloud: Any) -> None:
    result = height_metrics({"feature_id": "empty", "geometry_wkb": box(0, 0, 10, 10).wkb}, cloud, args())
    assert result["status"] == "no_points"
    assert result["canopy_cover_fraction"] is None
    with pytest.raises(ValueError, match="max_points"):
        read_cloud("demo://classified.laz", 2, "", 1.0)
    with pytest.raises(ValueError, match="max_grid_cells"):
        height_metrics(area(), cloud, args(max_grid_cells=2))


def test_ground_support_excludes_unknown_cells_from_canopy_denominator(cloud: Any) -> None:
    xyz = cloud.xyz.copy()
    xyz[cloud.classes == 2, :2] += 1000
    remote_ground = Cloud(xyz, cloud.classes, cloud.usable, cloud.crs)
    result = height_metrics(area(), remote_ground, args())
    assert result["status"] == "no_ground"
    assert result["ground_supported_cell_fraction"] == 0
    assert result["canopy_cover_fraction"] is None
    assert cloud.ground_tree is cloud.ground_tree
    assert cloud.point_tree is cloud.point_tree


def test_clearance_streams_large_results_and_bounds_work(cloud: Any) -> None:
    from lidar_worker.analysis import CLEARANCE
    from lidar_worker.support import emit_rows

    large = Cloud(
        np.tile([[500030.0, 4100030.0, 118.0]], (10001, 1)), np.full(10001, 5), np.ones(10001, dtype=bool), cloud.crs
    )
    sizes = []
    sink = SimpleNamespace(emit=lambda batch: sizes.append(batch.num_rows))
    emit_rows(conductor_clearance(conductor(), large, args()), CLEARANCE, sink)
    assert sizes == [4096, 4096, 1809]
    with pytest.raises(ValueError, match="max_distance_evaluations"):
        list(conductor_clearance(conductor(), large, args(max_distance_evaluations=10000)))
    bent = {
        "feature_id": "bent",
        "geometry_wkb": LineString([(500025, 4100030, 120), (500030, 4100030, 120), (500040, 4100030, 120)]).wkb,
    }
    with pytest.raises(ValueError, match="max_segments"):
        list(conductor_clearance(bent, cloud, args(max_segments=1)))


def test_partial_ground_support_is_reported_separately(cloud: Any) -> None:
    sample = Cloud(
        np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 4.0], [100.0, 0.0, 10.0]]),
        np.array([2, 5, 5]),
        np.ones(3, dtype=bool),
        cloud.crs,
    )
    result = height_metrics(
        {"feature_id": "sparse", "geometry_wkb": box(-5, -5, 105, 5).wkb}, sample, args(grid_size_m=10)
    )
    assert result["status"] == "partial_ground"
    assert result["unsupported_points"] == 1
    assert result["ground_supported_cell_fraction"] == 0.5
    assert result["canopy_cover_fraction"] == 1.0
