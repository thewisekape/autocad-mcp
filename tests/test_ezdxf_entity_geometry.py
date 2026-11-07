"""Regression checks for raw and normalized offline geometry."""

import json
import math

import pytest

from autocad_mcp.backends.ezdxf_backend import EzdxfBackend


@pytest.fixture
async def backend():
    instance = EzdxfBackend()
    await instance.initialize()
    return instance


async def query(backend, entity):
    result = await backend.query_entity_geometry(entity.dxf.handle)
    assert result.ok, result.error
    json.dumps(result.payload, allow_nan=False)
    return result.payload


async def test_line_has_provenance_exact_length_and_bounds(backend, tmp_path):
    filename = str(tmp_path / "line.dxf")
    sheet = backend._doc.layouts.new("Sheet A")
    line = sheet.add_line((1, 2, 3), (4, 6, 15), dxfattribs={"layer": "A"})
    handle = line.dxf.handle
    await backend.drawing_save(filename)
    await backend.drawing_open(filename)

    geometry = await query(backend, backend._doc.entitydb[handle])

    assert geometry["source_file"] == filename
    assert geometry["layer"] == "A"
    assert geometry["layout"] == "Sheet A"
    assert geometry["start"] == [1, 2, 3]
    assert geometry["end"] == [4, 6, 15]
    assert geometry["length"] == 13
    assert geometry["bounding_box"] == {
        "min": [1, 2, 3], "max": [4, 6, 15], "space": "WCS", "approximate": False,
    }


async def test_arc_preserves_ocs_center_and_exposes_wcs_center(backend):
    arc = backend._msp.add_arc((3, 4, 5), 2, 350, 10, dxfattribs={"extrusion": (0, 1, 0)})

    geometry = await query(backend, arc)

    assert geometry["center"] == [3, 4, 5]
    assert geometry["coordinates"]["center_in_owner"] == [-3, 5, 4]
    assert geometry["arc_length"] == pytest.approx(math.radians(20) * 2)
    assert geometry["bounding_box"]["approximate"]


@pytest.mark.parametrize("dxftype", ["LWPOLYLINE", "POLYLINE"])
async def test_bulged_polylines_expose_ocs_and_wcs_vertices(backend, dxftype):
    points = [(0, 0, 1), (2, 0, 0)]
    if dxftype == "LWPOLYLINE":
        polyline = backend._msp.add_lwpolyline(
            points, format="xyb", dxfattribs={"extrusion": (0, 1, 0), "elevation": 3},
        )
    else:
        polyline = backend._msp.add_polyline2d(
            points, format="xyb", dxfattribs={"extrusion": (0, 1, 0), "elevation": (0, 0, 3)},
        )
    polyline.close()

    geometry = await query(backend, polyline)

    coordinates = geometry["coordinates"]
    assert coordinates["bulges"] == [1, 0]
    assert coordinates["vertices_ocs"] == [[0, 0, 3], [2, 0, 3]]
    assert coordinates["vertices_in_owner"] == [[0, 3, 0], [-2, 3, 0]]
    assert geometry["closed"]
    assert geometry["length"] == pytest.approx(math.pi + 2)


async def test_spline_definition_coordinates_are_labeled_local(backend):
    block = backend._doc.blocks.new("PART")
    spline = block.add_spline(fit_points=[(0, 0), (1, 2), (2, 0)])

    geometry = await query(backend, spline)

    assert geometry["parent_block"] == "PART"
    assert geometry["layout"] is None
    assert geometry["degree"] == 3
    assert geometry["fit_points"] == [[0, 0, 0], [1, 2, 0], [2, 0, 0]]
    assert geometry["coordinates"]["owner_space"] == "block_definition"
    assert "block_instance_path_required_for_layout_wcs" in geometry["warnings"]
