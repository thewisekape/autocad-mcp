import math
from types import SimpleNamespace

import pytest

from autocad_mcp.backends import dxf_export
from autocad_mcp.backends.ezdxf_backend import EzdxfBackend
from autocad_mcp.cad_document import export_cad_document


@pytest.mark.parametrize("kind", ["LWPOLYLINE", "POLYLINE"])
async def test_geometry_measurements_use_bulge_in_all_operations(kind):
    backend = EzdxfBackend()
    await backend.initialize()
    if kind == "LWPOLYLINE":
        entity = backend._msp.add_lwpolyline([(0, 0, 1), (2, 0, 0)], format="xyb", close=True)
    else:
        entity = backend._msp.add_polyline2d([(0, 0), (2, 0)], close=True)
        entity.vertices[0].dxf.bulge = 1
    handle = entity.dxf.handle
    length = await backend.geometry_length(handle)
    area = await backend.geometry_area(handle)
    info = await backend.geometry_polyline_info(handle)
    geometry = await backend.query_entity_geometry(handle)
    assert length.payload["length"] == pytest.approx(math.pi + 2)
    assert area.payload["area"] == pytest.approx(math.pi / 2)
    assert info.payload["area"] == pytest.approx(math.pi / 2)
    assert info.payload["total_length"] == pytest.approx(math.pi + 2)
    assert geometry.payload["length"] == pytest.approx(math.pi + 2)


async def test_ellipse_arc_length_uses_parameter_range_and_area_rejects_open_curve():
    backend = EzdxfBackend()
    await backend.initialize()
    curve = backend._msp.add_ellipse((0, 0), major_axis=(2, 0), ratio=1,
                                     start_param=1.5 * math.pi, end_param=0.5 * math.pi)
    length = await backend.geometry_length(curve.dxf.handle)
    area = await backend.geometry_area(curve.dxf.handle)
    assert length.payload["length"] == pytest.approx(2 * math.pi)
    assert length.payload["approximate"] is True
    assert not area.ok and "full ellipse" in area.error


async def test_3d_polyline_has_length_but_no_projected_area_claim():
    backend = EzdxfBackend()
    await backend.initialize()
    curve = backend._msp.add_polyline3d([(0, 0, 0), (2, 0, 1), (1, 2, 2)], close=True)
    assert not (await backend.geometry_area(curve.dxf.handle)).ok
    info = await backend.geometry_polyline_info(curve.dxf.handle)
    assert info.ok and "area" not in info.payload


async def test_document_reports_dimension_unavailable_and_exports_view_evidence():
    backend = EzdxfBackend()
    await backend.initialize()
    frame = backend._doc.blocks.new("Sheet Frame")
    frame.add_lwpolyline([(0, 0), (20, 0), (20, 10), (0, 10)], close=True)
    insert = backend._msp.add_blockref(frame.name, (0, 0))
    text = backend._msp.add_mtext("PLAN", {"insert": (2, 8), "char_height": .3})
    dimension = backend._msp.add_aligned_dim((2, 2), (5, 2), 1).dimension
    result = await export_cad_document(backend)
    assert result.ok, result.error
    entry, = result.payload["dimensions"]
    assert entry["source"]["handle"] == dimension.dxf.handle
    assert entry["validation_status"] == "partial"
    assert entry["display_text"] is None
    view, = result.payload["views"]
    assert view["frame"]["handle"] == insert.dxf.handle
    assert view["titles"][0]["source"]["handle"] == text.dxf.handle
    assert any(member["relation"] == "contained" for member in view["members"])


def test_export_retries_com_member_lookup_without_repeating_save(tmp_path, monkeypatch):
    source = tmp_path / "input.dwg"
    source.write_bytes(b"source")
    attempts = []

    class TransientCopy:
        @property
        def SaveAs(self):
            attempts.append("lookup")
            if attempts == ["lookup"]:
                raise AttributeError("Open.SaveAs")

            def save(path, version):
                attempts.append(("save", version))
                (tmp_path / path).write_text("fake", encoding="ascii")

            return save

        def Close(self, save):
            attempts.append(("close", save))

    doc = SimpleNamespace(FullName=str(source), Saved=True, Layouts=[])
    app = SimpleNamespace(ActiveDocument=doc, GetAcadState=lambda: SimpleNamespace(IsQuiescent=True),
                          Documents=SimpleNamespace(Open=lambda _: TransientCopy()))
    monkeypatch.setattr(dxf_export, "sleep", lambda _: None)
    monkeypatch.setattr(dxf_export, "_verify_dxf", lambda *_: {"status": "passed"})
    result = dxf_export.export_saved_dwg(doc, app, str(tmp_path / "output.dxf"), "R2013")
    assert result["validation"]["status"] == "passed"
    assert attempts == ["lookup", "lookup", ("save", 61), ("close", False)]


async def test_side_section_labels_and_mixed_sheet_evidence():
    backend = EzdxfBackend()
    await backend.initialize()
    block = backend._doc.blocks.new("Sheet Frame")
    block.add_lwpolyline([(0, 0), (20, 0), (20, 10), (0, 10)], close=True)
    backend._msp.add_blockref(block.name, (0, 0))
    backend._msp.add_blockref(block.name, (30, 0))
    backend._msp.add_mtext("A-A侧剖图", {"insert": (2, 5), "char_height": .3})
    backend._msp.add_mtext("立面图", {"insert": (32, 6), "char_height": .3})
    backend._msp.add_mtext("横剖图", {"insert": (32, 3), "char_height": .3})
    result = await backend.query_view_regions()
    assert result.ok
    section, mixed = result.payload["regions"]
    assert section["view_type"] == "section"
    assert mixed["view_type"] == "unknown" and mixed["classification_ambiguous"]
    assert {title["view_type"] for title in mixed["titles"]} == {"elevation", "section"}
