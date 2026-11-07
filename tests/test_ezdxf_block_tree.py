"""Offline regression tests for nested DXF block transforms and topology."""

import json

import pytest
from ezdxf.math import Matrix44

from autocad_mcp.backends.ezdxf_backend import EzdxfBackend


@pytest.fixture
async def backend():
    instance = EzdxfBackend()
    await instance.initialize()
    return instance


def transform(matrix, point):
    return tuple(Matrix44([value for row in matrix for value in row]).transform(point))


async def test_nested_inserts_compose_rotated_mirrored_and_nonuniform_scale(backend):
    doc = backend._doc
    child = doc.blocks.new("CHILD", base_point=(1, 2, 0))
    child.add_line((1, 2), (2, 2))
    parent = doc.blocks.new("PARENT", base_point=(2, 3, 0))
    nested = parent.add_blockref(
        "CHILD", (5, 7), dxfattribs={"xscale": 2, "yscale": -3, "rotation": 90},
    )
    nested.add_attrib("CODE", "A")
    top = backend._msp.add_blockref(
        "PARENT", (100, 200), dxfattribs={"xscale": -4, "yscale": 2, "rotation": 90},
    )
    other = backend._msp.add_blockref("PARENT", (9, 20))
    sheet = doc.layouts.new("Sheet A")
    sheet_ref = sheet.add_blockref("CHILD", (50, 70))

    result = await backend.query_block_tree()

    assert result.ok, result.error
    json.dumps(result.payload, allow_nan=False)
    definitions = {block["name"]: block for block in result.payload["blocks"]}
    layouts = {layout["name"]: layout["references"] for layout in result.payload["layouts"]}
    root, other_root = layouts["Model"]
    instance = root["children"][0]
    assert root["handle"] == top.dxf.handle
    assert root["insertion_point_wcs"] == pytest.approx([100, 200, 0])
    assert instance["handle"] == nested.dxf.handle
    assert instance["kind"] == "NestedBlockReference"
    assert instance["definition_handle"] == definitions["CHILD"]["handle"]
    assert instance["parent_id"] == root["id"]
    assert instance["parent_block"] == "PARENT"
    assert instance["nested_path"] == [top.dxf.handle, nested.dxf.handle]
    assert instance["attributes"] == {"CODE": "A"}
    assert instance["insertion_point_wcs"] == pytest.approx([92, 188, 0])
    assert transform(instance["world_transform"], (2, 2, 0)) == pytest.approx([88, 188, 0])
    assert transform(instance["world_transform"], (1, 3, 0)) == pytest.approx([92, 176, 0])
    assert other_root["handle"] == other.dxf.handle
    assert other_root["children"][0]["handle"] == nested.dxf.handle
    assert other_root["children"][0]["id"] != instance["id"]
    assert layouts["Sheet A"][0]["handle"] == sheet_ref.dxf.handle
    assert layouts["Sheet A"][0]["layout"] == "Sheet A"


async def test_insert_uses_ocs_and_expands_minsert_grid(backend):
    backend._doc.blocks.new("GRID")
    source = backend._msp.add_blockref(
        "GRID", (3, 4, 5), dxfattribs={"extrusion": (0, 1, 0), "rotation": 90, "xscale": 3},
    )
    source.grid((2, 2), (7, 11))

    result = await backend.query_block_tree()

    assert result.ok, result.error
    nodes = result.payload["layouts"][0]["references"]
    assert len(nodes) == 4
    assert len({node["id"] for node in nodes}) == 4
    assert {node["handle"] for node in nodes} == {source.dxf.handle}
    assert nodes[0]["insertion_point_ocs"] == [3, 4, 5]
    assert nodes[0]["insertion_point_wcs"] == pytest.approx([-3, 5, 4])
    assert nodes[1]["insertion_point_wcs"] == pytest.approx([-3, 5, 15])
    assert nodes[2]["insertion_point_wcs"] == pytest.approx([4, 5, 4])
    assert nodes[3]["insertion_point_wcs"] == pytest.approx([4, 5, 15])


async def test_block_tree_marks_cycles_missing_definitions_and_xrefs(backend):
    doc = backend._doc
    first = doc.blocks.new("FIRST")
    second = doc.blocks.new("SECOND")
    first.add_blockref("SECOND", (1, 0))
    second.add_blockref("FIRST", (2, 0))
    backend._msp.add_blockref("FIRST", (0, 0))
    backend._msp.add_blockref("MISSING", (0, 0))
    doc.add_xref_def("external.dwg", "EXTERNAL")
    backend._msp.add_blockref("EXTERNAL", (0, 0))

    result = await backend.query_block_tree()

    assert result.ok, result.error
    root, missing, xref = result.payload["layouts"][0]["references"]
    cycle = root["children"][0]["children"][0]
    assert cycle["warnings"] == ["cyclic_block_reference"]
    assert cycle["children"] == []
    assert missing["warnings"] == ["missing_block_definition"]
    assert missing["world_transform"] is None
    assert xref["definition_kind"] == "Xref"
    assert xref["warnings"] == ["xref_contents_not_resolved"]
    assert xref["children"] == []


async def test_block_tree_distinguishes_dynamic_and_anonymous_definitions(backend):
    doc = backend._doc
    for appid in ("AcDbDynamicBlockGUID", "AcDbBlockRepBTag"):
        doc.appids.new(appid)
    dynamic = doc.blocks.new("Dynamic")
    dynamic.block_record.set_xdata("AcDbDynamicBlockGUID", [(1000, "dynamic-id")])
    anonymous = doc.blocks.new_anonymous_block("U")
    anonymous.block_record.set_xdata(
        "AcDbBlockRepBTag", [(1005, dynamic.block_record.dxf.handle)],
    )
    backend._msp.add_blockref(anonymous.name, (0, 0))

    result = await backend.query_block_tree()

    assert result.ok, result.error
    definitions = {block["name"]: block for block in result.payload["blocks"]}
    assert definitions["Dynamic"]["kind"] == "DynamicBlock"
    assert definitions[anonymous.name]["kind"] == "AnonymousBlock"
    node = result.payload["layouts"][0]["references"][0]
    assert node["is_dynamic"]
    assert node["effective_name"] == "Dynamic"
