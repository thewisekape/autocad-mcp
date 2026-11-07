"""Spatial query regression tests with synthetic DXF entities."""

from __future__ import annotations

import pytest

from autocad_mcp.backends.ezdxf_backend import EzdxfBackend


@pytest.fixture
async def backend():
    backend = EzdxfBackend()
    await backend.initialize()
    return backend


async def test_window_contains_or_intersects_inclusive_xy_boxes(backend):
    inside = backend._msp.add_line((0, 0, 7), (2, 2, 9))
    crossing = backend._msp.add_line((-2, 1), (1, 1))
    touching = backend._msp.add_line((2, 2), (4, 2))
    backend._msp.add_line((3, 3), (4, 4))

    contained = await backend.search_by_window(2, 2, 0, 0)
    assert contained.ok
    assert contained.payload["mode"] == "contains"
    assert [item["handle"] for item in contained.payload["matches"]] == [inside.dxf.handle]

    intersecting = await backend.search_by_window(0, 0, 2, 2, mode="intersects")
    assert intersecting.ok
    assert [item["handle"] for item in intersecting.payload["matches"]] == [
        inside.dxf.handle, crossing.dxf.handle, touching.dxf.handle
    ]


async def test_proximity_preserves_center_default_and_supports_nearest_box(backend):
    backend._msp.add_line((0, 0), (20, 0))

    center = await backend.search_by_proximity(0, 0, 0)
    assert center.ok
    assert center.payload["count"] == 0
    assert center.payload["diagnostics"]["status"] == "complete"

    nearest = await backend.search_by_proximity(-3, 4, 5, metric="bbox_nearest")
    assert nearest.ok
    assert nearest.payload["matches"][0]["distance"] == 5
    assert nearest.payload["matches"][0]["center"] == [10, 0]


async def test_layout_type_and_layer_filters_apply_to_search_and_bounds(backend):
    backend._msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "Walls"})
    sheet = backend._doc.layouts.new("Sheet A")
    line = sheet.add_line((2, 3, 4), (5, 7, 10), dxfattribs={"layer": "Walls"})
    sheet.add_circle((2, 3), 1, dxfattribs={"layer": "Walls"})
    sheet.add_line((0, 0), (1, 1), dxfattribs={"layer": "Doors"})
    options = {"layout": "sheet a", "entity_type": "line", "layer": "walls"}

    window = await backend.search_by_window(0, 0, 10, 10, **options)
    assert window.ok
    assert window.payload["matches"] == [{
        "handle": line.dxf.handle,
        "type": "LINE",
        "layer": "Walls",
        "layout": "Sheet A",
        "bbox_min": [2, 3],
        "bbox_max": [5, 7],
    }]
    proximity = await backend.search_by_proximity(0, 0, 10, **options)
    assert proximity.ok
    assert proximity.payload["count"] == 1

    bounds = await backend.geometry_bounding_box(**options)
    assert bounds.ok
    assert bounds.payload["min"] == [2, 3, 4]
    assert bounds.payload["max"] == [5, 7, 10]
    assert bounds.payload["width"] == 3
    assert bounds.payload["height"] == 4


async def test_unavailable_bounds_distinguished_from_empty_query(backend):
    infinite = backend._msp.add_xline((0, 0), (1, 0))
    unsupported_only = await backend.search_by_window(0, 0, 1, 1)
    assert not unsupported_only.ok
    assert "XLINE" in unsupported_only.error

    backend._msp.add_line((5, 5), (6, 6))
    partial = await backend.search_by_window(0, 0, 1, 1)
    assert partial.ok
    assert partial.payload["count"] == 0
    diagnostics = partial.payload["diagnostics"]
    assert diagnostics["status"] == "partial"
    assert diagnostics["skipped_count"] == 1
    assert diagnostics["issues"][0]["handle"] == infinite.dxf.handle

    empty = await backend.search_by_window(0, 0, 1, 1, entity_type="CIRCLE")
    assert empty.ok
    assert empty.payload["count"] == 0
    assert empty.payload["diagnostics"]["status"] == "complete"


async def test_rejects_invalid_spatial_parameters(backend):
    assert not (await backend.search_by_window(0, 0, float("nan"), 1)).ok
    assert not (await backend.search_by_window(0, 0, 1, 1, mode="unknown")).ok
    assert not (await backend.search_by_window(0, 0, 1, 1, layout="missing")).ok
    assert not (await backend.search_by_proximity(0, 0, -1)).ok
    assert not (await backend.search_by_proximity(0, 0, True)).ok
