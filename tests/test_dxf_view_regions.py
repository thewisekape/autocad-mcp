"""Synthetic region tests for the optional DXF view heuristic."""

import ezdxf

from autocad_mcp.backends.dxf_view_regions import view_regions
from autocad_mcp.backends.ezdxf_backend import EzdxfBackend


def _frame(layout, x1, y1, x2, y2):
    return layout.add_lwpolyline(
        [(x1, y1), (x2, y1), (x2, y2), (x1, y2)], close=True, dxfattribs={"layer": "Frames"}
    )


def test_view_classification_requires_title_and_keeps_source_handles():
    doc = ezdxf.new()
    layout = doc.modelspace()
    frame = _frame(layout, 0, 0, 20, 20)
    unlabeled = _frame(layout, 25, 0, 45, 20)
    title = layout.add_text("PLAN VIEW", dxfattribs={"insert": (1, 1), "height": 1})
    member = layout.add_line((28, 3), (31, 4))
    layout.add_lwpolyline(
        [(0, 30, 1), (10, 30, 0), (10, 40, 0), (0, 40, 0)],
        format="xyb", close=True, dxfattribs={"layer": "Frames"},
    )

    result = view_regions(doc, "frames")
    assert result["count"] == 2
    plan, unknown = result["regions"]
    assert plan["frame_handle"] == frame.dxf.handle
    assert plan["view_type"] == "plan"
    assert plan["titles"] == [{"handle": title.dxf.handle, "text": "PLAN VIEW", "view_type": "plan"}]
    assert unknown["frame_handle"] == unlabeled.dxf.handle
    assert unknown["view_type"] == "unknown"
    assert unknown["members"][0]["handle"] == member.dxf.handle


def test_overlapping_frames_and_crossing_entities_are_ambiguous():
    doc = ezdxf.new()
    layout = doc.layouts.new("Sheet")
    first = _frame(layout, 0, 0, 20, 20)
    second = _frame(layout, 5, 0, 25, 20)
    title = layout.add_mtext("SECTION", dxfattribs={"insert": (8, 10), "char_height": 1})
    crossing = layout.add_line((-1, 2), (1, 2))

    left, right = view_regions(doc, "Frames", layout="Sheet")["regions"]
    assert left["overlapping_frames"] == [second.dxf.handle]
    assert right["overlapping_frames"] == [first.dxf.handle]
    for region in (left, right):
        assert region["ambiguous"]
        assert region["view_type"] == "unknown"
        assert region["titles"] == []
        assert any(member["handle"] == title.dxf.handle and member["ambiguous"] for member in region["members"])
    assert any(
        member["handle"] == crossing.dxf.handle and member["relation"] == "crosses_boundary"
        for member in left["members"]
    )


async def test_backend_view_regions_requires_explicit_frame_layer():
    backend = EzdxfBackend()
    assert not (await backend.query_view_regions("Frames")).ok
    await backend.initialize()
    assert not (await backend.query_view_regions("")).ok
    result = await backend.query_view_regions("Frames")
    assert result.ok
    assert result.payload["regions"] == []
