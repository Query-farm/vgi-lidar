"""Classified LAS/LAZ height metrics and three-dimensional vegetation clearance."""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property
from itertools import pairwise
from typing import Annotated, Any, ClassVar

import laspy
import numpy as np
import pyarrow as pa
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import LineString, box
from vgi import Arg
from vgi.arguments import TableInput
from vgi.catalog import Table
from vgi.invocation import BindResponse
from vgi.table_function import (
    BindParams,
    OutputCollector,
    ProcessParams,
    TableFunctionGenerator,
    bind_fixed_schema,
    init_single_worker,
)
from vgi.table_in_out_function import TableInOutGenerator
from vgi_rpc import ArrowSerializableDataclass

from .support import (
    emit_rows,
    example,
    finite_parameters,
    geometry,
    identifier,
    metadata,
    metric_crs,
    require_columns,
    resource,
    schema_of,
)

GIS_DESCRIPTION = (
    "Read classified LAS/LAZ point clouds to estimate building and canopy heights above"
    " nearby classified ground, "
    "and find vegetation points within a three-dimensional clearance distance of "
    "supplied power-line geometry. "
    "Inputs and outputs retain caller feature IDs; horizontal coordinates and "
    "elevations must be metres. "
    "This worker uses existing ASPRS classifications: ground=2, vegetation=3/4/5, buildings=6."
)
INPUT = schema_of(
    [
        ("feature_id", pa.string(), "Caller-owned area or conductor identity."),
        ("geometry_wkb", pa.binary(), "Area polygon or 3D conductor LineString in geometry_crs."),
    ]
)
METRICS = schema_of(
    [
        ("feature_id", pa.string(), "Caller-owned polygon identity."),
        ("point_count", pa.int64(), "Number of non-noise points inside the polygon."),
        ("building_points", pa.int64(), "Class-6 points with nearby classified ground support."),
        ("building_p95_m", pa.float64(), "95th percentile building height above nearest classified ground, metres."),
        ("building_max_m", pa.float64(), "Maximum supported building height above nearest ground, metres."),
        ("vegetation_points", pa.int64(), "Class-3/4/5 points with nearby classified ground support."),
        ("canopy_p95_m", pa.float64(), "95th percentile supported vegetation height above ground, metres."),
        ("canopy_max_m", pa.float64(), "Maximum supported vegetation height above ground, metres."),
        (
            "canopy_cover_fraction",
            pa.float64(),
            "Fraction of fully ground-supported observed cells containing vegetation above canopy_height_m.",
        ),
        (
            "observed_cell_fraction",
            pa.float64(),
            "Fraction of polygon-intersecting grid cells with at least one usable point.",
        ),
        (
            "ground_supported_cell_fraction",
            pa.float64(),
            "Share of observed cells whose points all have ground support; denominator for canopy coverage.",
        ),
        ("unsupported_points", pa.int64(), "Building/vegetation points without ground within ground_radius_m."),
        ("status", pa.string(), "ok, partial_ground, no_ground, or no_points."),
        ("cloud_crs", pa.string(), "Projected metre CRS of the source cloud."),
    ]
)
CLEARANCE = schema_of(
    [
        ("feature_id", pa.string(), "Caller-owned conductor identity."),
        ("point_index", pa.int64(), "Zero-based original point-cloud record index."),
        (
            "clearance_m",
            pa.float64(),
            "Exact Euclidean 3D distance from vegetation return to the nearest conductor segment, metres.",
        ),
        ("x", pa.float64(), "Vegetation return X in cloud_crs."),
        ("y", pa.float64(), "Vegetation return Y in cloud_crs."),
        ("z_m", pa.float64(), "Vegetation return elevation in metres in the supplied vertical datum."),
        ("nearest_x", pa.float64(), "Nearest conductor position X in cloud_crs."),
        ("nearest_y", pa.float64(), "Nearest conductor position Y in cloud_crs."),
        ("nearest_z_m", pa.float64(), "Nearest conductor elevation, metres in the same vertical datum as the cloud."),
        ("cloud_crs", pa.string(), "Projected metre CRS for XY coordinates."),
    ]
)


@dataclass
class Cloud:
    """One batch's classified point arrays and lazily constructed reusable spatial indexes."""

    xyz: Any
    classes: Any
    usable: Any
    crs: Any

    @cached_property
    def point_tree(self) -> Any:
        """Index horizontal positions once per loaded tile."""
        return cKDTree(self.xyz[:, :2])

    @cached_property
    def ground(self) -> Any:
        """Retain only usable classified ground points."""
        return self.xyz[(self.classes == 2) & self.usable]

    @cached_property
    def ground_tree(self) -> Any:
        """Index ground positions once for every polygon in the batch."""
        return cKDTree(self.ground[:, :2]) if len(self.ground) else None

    def within(self, bounds: tuple[float, ...]) -> Any:
        """Return original point indices in an XY rectangle, in stable record order."""
        minx, miny, maxx, maxy = bounds
        center = ((minx + maxx) / 2, (miny + maxy) / 2)
        radius = max(maxx - minx, maxy - miny) / 2
        indices = np.asarray(sorted(self.point_tree.query_ball_point(center, radius, p=np.inf)), dtype="int64")
        points = self.xyz[indices]
        keep = (
            self.usable[indices]
            & (points[:, 0] >= minx)
            & (points[:, 0] <= maxx)
            & (points[:, 1] >= miny)
            & (points[:, 1] <= maxy)
        )
        return indices[keep]


def read_cloud(path: str, max_points: int, cloud_crs: str, z_scale_to_m: float) -> Cloud:
    """Read a bounded classified cloud, rejecting missing or nonmetric horizontal CRS."""
    with laspy.open(resource(path)) as reader:
        if reader.header.point_count > max_points:
            raise ValueError(f"Point cloud exceeds max_points={max_points}; provide a bounded tile")
        crs = metric_crs(cloud_crs or reader.header.parse_crs())
        cloud = reader.read()
    xyz = np.column_stack((cloud.x, cloud.y, np.asarray(cloud.z) * z_scale_to_m))
    if not np.isfinite(xyz).all():
        raise ValueError("Point cloud contains nonfinite coordinates")
    classes = np.asarray(cloud.classification)
    usable = ~np.isin(classes, [7, 18]) & ~np.asarray(cloud.withheld, dtype=bool)
    return Cloud(xyz, classes, usable, crs)


def height_metrics(row: dict[str, Any], cloud: Cloud, args: Any) -> dict[str, Any]:
    """Compute supported height percentiles and explicitly sampled canopy cover."""
    xyz, classes, crs = cloud.xyz, cloud.classes, cloud.crs
    key = identifier(row, "feature_id")
    poly = geometry(row["geometry_wkb"], args.geometry_crs, crs)
    candidates = cloud.within(poly.bounds)
    indices = candidates[shapely.intersects_xy(poly, xyz[candidates, 0], xyz[candidates, 1])]
    result = {
        "feature_id": key,
        "point_count": len(indices),
        "building_points": 0,
        "building_p95_m": None,
        "building_max_m": None,
        "vegetation_points": 0,
        "canopy_p95_m": None,
        "canopy_max_m": None,
        "canopy_cover_fraction": None,
        "observed_cell_fraction": 0.0,
        "ground_supported_cell_fraction": 0.0,
        "unsupported_points": 0,
        "status": "no_points",
        "cloud_crs": crs.to_string(),
    }
    if not len(indices):
        return result
    points, kinds = xyz[indices], classes[indices]
    ground = cloud.ground
    heights = np.full(len(points), np.nan)
    if len(ground):
        distances, nearest = cloud.ground_tree.query(points[:, :2])
        supported = distances <= args.ground_radius_m
        heights[supported] = points[supported, 2] - ground[nearest[supported], 2]
    buildings = (kinds == 6) & np.isfinite(heights)
    vegetation = np.isin(kinds, [3, 4, 5]) & np.isfinite(heights)
    wanted = np.isin(kinds, [3, 4, 5, 6])
    unsupported = int((wanted & ~np.isfinite(heights)).sum())
    result.update(
        building_points=int(buildings.sum()),
        vegetation_points=int(vegetation.sum()),
        unsupported_points=unsupported,
        status="no_ground" if not np.isfinite(heights).any() else "partial_ground" if unsupported else "ok",
    )
    for prefix, mask in [("building", buildings), ("canopy", vegetation)]:
        if mask.any():
            result[prefix + "_p95_m"] = float(np.percentile(heights[mask], 95))
            result[prefix + "_max_m"] = float(heights[mask].max())
    minx, miny, maxx, maxy = poly.bounds
    size = args.grid_size_m
    width, height = math.ceil((maxx - minx) / size), math.ceil((maxy - miny) / size)
    if width * height > args.max_grid_cells:
        raise ValueError("Canopy grid exceeds max_grid_cells; increase grid_size_m or reduce polygon size")
    # Count cells that intersect the polygon, so edge points cannot make coverage exceed one.
    cell_ids: set[tuple[int, int]] = set()
    for r in range(height):
        for c in range(width):
            if (
                poly.intersection(
                    box(minx + c * size, miny + r * size, minx + (c + 1) * size, miny + (r + 1) * size)
                ).area
                > 0
            ):
                cell_ids.add((c, r))
    point_cells = np.floor((points[:, :2] - [minx, miny]) / size).astype(int)
    point_cells[:, 0] = np.minimum(point_cells[:, 0], width - 1)
    point_cells[:, 1] = np.minimum(point_cells[:, 1], height - 1)
    observed = {tuple(map(int, cell)) for cell in point_cells} & cell_ids
    canopy = {tuple(map(int, cell)) for cell in point_cells[vegetation & (heights >= args.canopy_height_m)]} & observed
    result["observed_cell_fraction"] = len(observed) / len(cell_ids) if cell_ids else 0.0
    unsupported_cells = {tuple(map(int, cell)) for cell in point_cells[~np.isfinite(heights)]}
    supported_cells = observed - unsupported_cells
    result["ground_supported_cell_fraction"] = len(supported_cells) / len(observed) if observed else 0.0
    if supported_cells:
        result["canopy_cover_fraction"] = len(canopy & supported_cells) / len(supported_cells)
    return result


def conductor_clearance(row: dict[str, Any], cloud: Cloud, args: Any) -> Iterator[dict[str, Any]]:
    """Find vegetation returns inside a 3D corridor around a supplied conductor."""
    xyz, classes, crs = cloud.xyz, cloud.classes, cloud.crs
    key = identifier(row, "feature_id")
    line = geometry(row["geometry_wkb"], args.geometry_crs, crs, polygon=False)
    if line.geom_type not in {"LineString", "MultiLineString"} or not line.has_z:
        raise ValueError("Conductor geometry must be a 3D LineString or MultiLineString with absolute metre elevations")
    parts = list(line.geoms) if line.geom_type == "MultiLineString" else [line]
    if sum(len(part.coords) - 1 for part in parts) > args.max_segments:
        raise ValueError("Conductor exceeds max_segments; partition the conductor geometry")
    segments = [(np.asarray(a), np.asarray(b)) for part in parts for a, b in pairwise(part.coords)]
    if any(not np.isfinite(np.r_[a, b]).all() for a, b in segments):
        raise ValueError("Conductor coordinates must be finite")
    minx, miny, maxx, maxy = line.bounds
    d = args.clearance_m
    candidates = cloud.within((minx - d, miny - d, maxx + d, maxy + d))
    indices = candidates[np.isin(classes[candidates], [3, 4, 5])]
    if len(indices) * len(segments) > args.max_distance_evaluations:
        raise ValueError("Clearance exceeds max_distance_evaluations; partition the conductor or cloud")
    points = xyz[indices]
    distance = np.full(len(points), np.inf)
    nearest = np.zeros_like(points)
    for a, b in segments:
        direction = b - a
        squared_length = float(direction @ direction)
        t = np.clip((points - a) @ direction / squared_length, 0, 1) if squared_length else np.zeros(len(points))
        projected = a + t[:, None] * direction
        candidate = np.linalg.norm(points - projected, axis=1)
        better = candidate < distance
        nearest[better] = projected[better]
        distance[better] = candidate[better]
    for i in np.flatnonzero(distance <= d):
        yield {
            "feature_id": key,
            "point_index": int(indices[i]),
            "clearance_m": float(distance[i]),
            "x": float(points[i, 0]),
            "y": float(points[i, 1]),
            "z_m": float(points[i, 2]),
            "nearest_x": float(nearest[i, 0]),
            "nearest_y": float(nearest[i, 1]),
            "nearest_z_m": float(nearest[i, 2]),
            "cloud_crs": crs.to_string(),
        }


@dataclass(slots=True, frozen=True, kw_only=True)
class CloudArgs:
    """Shared relational input and classified-cloud interpretation."""

    data: Annotated[
        TableInput,
        Arg(0, doc="Rows with feature_id and geometry_wkb, as polygons for heights or 3D lines for clearance."),
    ]
    path: Annotated[
        str,
        Arg(
            "path",
            default="demo://classified.laz",
            doc="Local LAS/LAZ file; original ASPRS classifications are required.",
        ),
    ]
    geometry_crs: Annotated[
        str,
        Arg(
            "geometry_crs",
            default="EPSG:32618",
            doc=(
                "CRS for input WKB XY coordinates; conductor Z values must already be in metres in "
                "the cloud's vertical datum."
            ),
        ),
    ]
    cloud_crs: Annotated[
        str,
        Arg(
            "cloud_crs",
            default="",
            doc=(
                "Optional explicit CRS if LAS metadata are absent; otherwise use the LAS CRS. Must "
                "be projected in metres."
            ),
        ),
    ]
    z_scale_to_m: Annotated[
        float,
        Arg(
            "z_scale_to_m",
            default=1.0,
            gt=0,
            doc=(
                "Multiplier converting LAS Z values to metres; this does not perform a vertical datum transformation."
            ),
        ),
    ]
    max_points: Annotated[
        int,
        Arg("max_points", default=2000000, ge=1, doc="Maximum cloud point count; oversized tiles fail before loading."),
    ]
    ground_radius_m: Annotated[
        float,
        Arg(
            "ground_radius_m",
            default=25.0,
            gt=0,
            doc="Maximum distance to the nearest class-2 ground return for height estimates.",
        ),
    ]
    grid_size_m: Annotated[
        float, Arg("grid_size_m", default=5.0, gt=0, doc="Grid cell size for sampled canopy cover, metres.")
    ]
    canopy_height_m: Annotated[
        float,
        Arg("canopy_height_m", default=2.0, ge=0, doc="Minimum supported vegetation height counted in canopy cells."),
    ]
    max_grid_cells: Annotated[
        int, Arg("max_grid_cells", default=100000, ge=1, doc="Maximum canopy grid cells per polygon.")
    ]
    clearance_m: Annotated[
        float,
        Arg(
            "clearance_m",
            default=3.0,
            gt=0,
            doc="Return vegetation points at or below this 3D conductor distance, metres.",
        ),
    ]
    max_segments: Annotated[
        int, Arg("max_segments", default=10000, ge=1, doc="Maximum segments in one conductor geometry.")
    ]
    max_distance_evaluations: Annotated[
        int,
        Arg(
            "max_distance_evaluations",
            default=50000000,
            ge=1,
            doc="Maximum candidate-point times segment evaluations per conductor.",
        ),
    ]


HEIGHT_SQL = (
    "SELECT feature_id, round(building_p95_m, 1), canopy_max_m FROM "
    "lidar.main.height_metrics((SELECT * FROM lidar.main.demo_input())) ORDER BY "
    "feature_id"
)
CLEAR_SQL = (
    "SELECT feature_id, round(clearance_m, 2) FROM "
    "lidar.main.vegetation_clearance((SELECT * FROM lidar.main.demo_input(kind := "
    "'conductor'))) ORDER BY feature_id, point_index"
)

# Composed examples: each combines several of this worker's functions in one query.
SPAN_REPORT_SQL = (
    "WITH spans(span_id, corridor_id, conductor_id) AS (VALUES ('Span 7', 'site', 'line')), "
    "canopy AS (SELECT feature_id, canopy_max_m, canopy_cover_fraction FROM "
    "lidar.main.height_metrics((SELECT * FROM lidar.main.demo_input()))), "
    "returns AS (SELECT feature_id, count(*) FILTER (WHERE clearance_m <= 3) AS within_3m, "
    "count(*) AS within_12m, min(clearance_m) AS closest_m FROM "
    "lidar.main.vegetation_clearance((SELECT * FROM lidar.main.demo_input(kind := 'conductor')), "
    "clearance_m := 12) GROUP BY feature_id) "
    "SELECT s.span_id, c.canopy_max_m, round(c.canopy_cover_fraction, 3) AS canopy_cover, "
    "coalesce(r.within_3m, 0) AS within_3m, coalesce(r.within_12m, 0) AS within_12m, "
    "round(r.closest_m, 2) AS closest_m FROM spans s JOIN canopy c ON c.feature_id = s.corridor_id "
    "LEFT JOIN returns r ON r.feature_id = s.conductor_id ORDER BY s.span_id"
)
TALL_CANOPY_SQL = (
    "WITH any_canopy AS (SELECT feature_id, canopy_cover_fraction AS cover_2m FROM "
    "lidar.main.height_metrics((SELECT * FROM lidar.main.demo_input()))), "
    "tall AS (SELECT feature_id, canopy_cover_fraction AS cover_15m FROM "
    "lidar.main.height_metrics((SELECT * FROM lidar.main.demo_input()), canopy_height_m := 15)) "
    "SELECT feature_id, round(cover_2m, 3) AS cover_2m, round(cover_15m, 3) AS cover_15m, "
    "round(cover_15m / cover_2m, 2) AS tall_share FROM any_canopy JOIN tall USING (feature_id) "
    "ORDER BY feature_id"
)


class HeightMetrics(TableInOutGenerator[CloudArgs]):
    """Summarize classified building and vegetation points within polygon rows."""

    class Meta:
        """Height metrics metadata."""

        name = "height_metrics"
        description = "Estimate building and canopy heights from classified LAS/LAZ points"
        tags = metadata(
            "Building and canopy metrics",
            GIS_DESCRIPTION
            + (
                " Height normalization uses the nearest classified ground return within "
                "ground_radius_m; sparse ground is explicitly counted. No automatic classification "
                "or vertical datum correction is implied. Missing classes give NULL percentiles. "
                "Canopy cover uses observed cells with complete ground support; observation and "
                "ground-support coverage are reported separately. Output rows stream in batches of at most 4096."
            ),
            METRICS,
            HEIGHT_SQL,
            [["site", 11.9, 18.0]],
        )
        examples = example(HEIGHT_SQL, "Estimate heights above a known flat ground surface") + example(
            TALL_CANOPY_SQL,
            "Run height_metrics twice over the bundled site, at the default 2 m and at a 15 m canopy "
            "threshold, and join the results: canopy cover is 0.077 and 0.038, so half of the canopy "
            "cells hold vegetation at least 15 m tall",
        )

    @classmethod
    def on_bind(cls, params: BindParams[CloudArgs]) -> BindResponse:
        """Require feature IDs and geometry."""
        finite_parameters(params.args)
        require_columns(params.bind_call.input_schema, ("feature_id", "geometry_wkb"))
        return BindResponse(output_schema=METRICS)

    @classmethod
    def process(
        cls, params: ProcessParams[CloudArgs], state: None, batch: pa.RecordBatch, out: OutputCollector
    ) -> None:
        """Share one cloud load across all polygons in the input batch."""
        cloud = read_cloud(params.args.path, params.args.max_points, params.args.cloud_crs, params.args.z_scale_to_m)
        out.emit(
            pa.RecordBatch.from_pylist(
                [height_metrics(row, cloud, params.args) for row in batch.to_pylist()], schema=params.output_schema
            )
        )


class VegetationClearance(TableInOutGenerator[CloudArgs]):
    """Return vegetation encroachment candidates around true 3D conductor lines."""

    class Meta:
        """Clearance discovery and executable example."""

        name = "vegetation_clearance"
        description = "Find classified vegetation within a 3D power-line clearance distance"
        tags = metadata(
            "Vegetation conductor clearance",
            "Compare classified vegetation returns with supplied 3D LineString/MultiLineString "
            "conductor geometry. Return exact Euclidean distance, nearest conductor coordinate "
            "and original point index for each return within clearance_m. Input conductor Z and"
            " cloud Z must share a vertical datum and metre units. Two-dimensional lines fail. "
            "An empty result means no observed encroachments, not a certified safe corridor.",
            CLEARANCE,
            CLEAR_SQL,
            [["line", 2.0]],
        )
        examples = example(CLEAR_SQL, "Find a tree return two metres below a conductor") + example(
            SPAN_REPORT_SQL,
            "Span vegetation report: join canopy height and cover from height_metrics over the "
            "right-of-way polygon with vegetation_clearance returns along the conductor (12 m search); "
            "Span 7 has 18 m canopy, one return within 3 m, two within 12 m, the closest at 2 m",
        )

    @classmethod
    def on_bind(cls, params: BindParams[CloudArgs]) -> BindResponse:
        """Require feature IDs and 3D geometry columns."""
        finite_parameters(params.args)
        require_columns(params.bind_call.input_schema, ("feature_id", "geometry_wkb"))
        return BindResponse(output_schema=CLEARANCE)

    @classmethod
    def process(
        cls, params: ProcessParams[CloudArgs], state: None, batch: pa.RecordBatch, out: OutputCollector
    ) -> None:
        """Reuse a loaded point cloud across the conductor batch."""
        cloud = read_cloud(params.args.path, params.args.max_points, params.args.cloud_crs, params.args.z_scale_to_m)
        emit_rows(
            (item for row in batch.to_pylist() for item in conductor_clearance(row, cloud, params.args)),
            params.output_schema,
            out,
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class DemoArgs:
    """Select the bundled area or conductor input."""

    kind: Annotated[
        str,
        Arg(
            "kind",
            default="area",
            choices=["area", "conductor"],
            doc="Return a polygon for height metrics or a 3D line for clearance.",
        ),
    ]


@dataclass(kw_only=True)
class Cursor(ArrowSerializableDataclass):
    """Demo emission flag."""

    done: bool = False


DEMO_SQL = "SELECT feature_id FROM lidar.main.demo_input()"


@init_single_worker
@bind_fixed_schema
class DemoInput(TableFunctionGenerator[DemoArgs, Cursor]):
    """Supply synthetic site and conductor geometry."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = INPUT

    class Meta:
        """Demo fixture metadata."""

        name = "demo_input"
        description = "Synthetic site polygon or 3D conductor for the bundled classified cloud"
        tags = metadata(
            "Demo LiDAR geometry",
            "Return a site polygon or, with kind := 'conductor', a 3D line in EPSG:32618. Both "
            "overlay demo://classified.laz, whose flat ground is at 100 m and conductor at 120 "
            "m in a synthetic common vertical datum.",
            INPUT,
            DEMO_SQL,
            [["site"]],
        )
        examples = example(DEMO_SQL, "Inspect the bundled site identity")

    @classmethod
    def initial_state(cls, params: ProcessParams[DemoArgs]) -> Cursor:
        """Start before the fixture row."""
        return Cursor()

    @classmethod
    def process(cls, params: ProcessParams[DemoArgs], state: Cursor, out: OutputCollector) -> None:
        """Emit the selected fixture once."""
        if state.done:
            out.finish()
            return
        area = params.args.kind == "area"
        geom = (
            box(499995, 4099995, 500045, 4100045)
            if area
            else LineString([(500025, 4100030, 120), (500040, 4100030, 120)])
        )
        out.emit(
            pa.RecordBatch.from_pylist(
                [{"feature_id": "site" if area else "line", "geometry_wkb": geom.wkb}], schema=params.output_schema
            )
        )
        state.done = True


GIS_FUNCTIONS: list[type[Any]] = [DemoInput, HeightMetrics, VegetationClearance]

GIS_TABLES: list[Table] = []
