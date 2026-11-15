"""Discovery metadata: the one file to edit when you rename or extend the worker.

DuckDB, coding agents and the ``vgi-lint`` metadata checker all read these
tags. Keep every object documented and ``make lint`` stays at 100.

* Catalog-level tags (title, license, author, links, long description) live in
  ``CATALOG_TAGS`` below.
* Every function and table carries ``object_tags(...)``: a title, a category
  from ``SCHEMA_CATEGORIES``, search keywords, and LLM- and human-facing docs.
"""

from __future__ import annotations

import json
from typing import Any

import pyarrow as pa

CATALOG_NAME = "lidar"

SOURCE_URL = "https://github.com/Query-farm/vgi-lidar"

# Categories group functions in docs and agent tools. Every object's
# ``vgi.category`` must name one of these.
SCHEMA_CATEGORIES = [
    {
        "name": "gis",
        "title": "GIS Analysis",
        "description": "Spatial analysis over query results and geospatial assets.",
    },
]


def keywords_array(keywords: str) -> str:
    """Turn ``"a, b, c"`` into the JSON array string ``vgi.keywords`` requires."""
    return json.dumps([k.strip() for k in keywords.split(",") if k.strip()])


def object_tags(*, title: str, category: str, keywords: str, doc_llm: str, doc_md: str) -> dict[str, str]:
    """Build the standard per-object discovery tags."""
    if category not in {c["name"] for c in SCHEMA_CATEGORIES}:
        raise ValueError(f"unknown category {category!r}; add it to SCHEMA_CATEGORIES")
    return {
        "vgi.title": title,
        "vgi.category": category,
        "vgi.keywords": keywords_array(keywords),
        "vgi.doc_llm": doc_llm,
        "vgi.doc_md": doc_md,
    }


def column(name: str, type_: pa.DataType, comment: str, *, nullable: bool = True) -> pa.Field[Any]:
    """Build an Arrow field whose ``comment`` shows up in DuckDB's ``DESCRIBE`` and agent tools."""
    return pa.field(name, type_, nullable=nullable, metadata={b"comment": comment.encode()})


# Each task names its inputs inline: the site polygon and conductor below overlay the
# bundled demo://classified.laz cloud (EPSG:32618, synthetic vertical datum in metres).
_INPUTS = (
    " The site is the polygon with feature_id 'site' covering x 499995-500045, y 4099995-4100045 in "
    "EPSG:32618; the conductor is the 3D line with feature_id 'line' from (500025, 4100030, 120) to "
    "(500040, 4100030, 120). Use the bundled classified point cloud (the default path)."
)

AGENT_TEST_TASKS = [
    {
        "name": "gis_height_metrics",
        "prompt": "Estimate building and canopy heights above ground for the site. Return feature_id, building "
        "p95 height rounded to 1 decimal and maximum canopy height, ordered by feature_id." + _INPUTS,
    },
    {
        "name": "gis_vegetation_clearance",
        "prompt": "Find vegetation returns within the default clearance of the conductor. Return feature_id and "
        "clearance rounded to 2 decimals, ordered by feature_id and point index." + _INPUTS,
    },
    {
        "name": "gis_corridor_screen",
        "prompt": "Screen the power-line corridor: find the maximum canopy height inside the site polygon, "
        "count the vegetation returns within 15 metres of the conductor and find the closest one. Return one "
        "row with columns canopy_max_m (DOUBLE), returns_within_15m (BIGINT) and closest_clearance_m (DOUBLE, "
        "rounded to 2 decimals)." + _INPUTS,
    },
]
CATALOG_TAGS = {
    "vgi.title": "LiDAR analysis",
    "vgi.subtitle": "Classified point-cloud heights and vegetation clearance around power lines.",
    "vgi.source_url": SOURCE_URL,
    "vgi.icon_url": "https://query.farm/media-kit/products/vgi/vgi-logo.png",
    "vgi.license": "0BSD",
    "vgi.author": "Query.Farm",
    "vgi.copyright": "Copyright 2026 Query.Farm LLC",
    "vgi.keywords": keywords_array("vgi, duckdb, lidar, point cloud, canopy, building height, conductor clearance"),
    "vgi.support_contact": f"{SOURCE_URL}/issues",
    "vgi.support_policy_url": f"{SOURCE_URL}#support",
    # Public analyst tasks for `vgi-lint simulate`; private graders live in vgi-agent-tests.yaml.
    "vgi.agent_test_tasks": json.dumps(AGENT_TEST_TASKS),
}
