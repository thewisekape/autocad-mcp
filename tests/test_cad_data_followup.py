import json
from pathlib import Path
from types import SimpleNamespace

import ezdxf
import pytest
from ezdxf.math import BoundingBox
from jsonschema import Draft202012Validator

from autocad_mcp import client, server
from autocad_mcp.backends import com_spatial, dxf_spatial
from autocad_mcp.backends.ezdxf_backend import EzdxfBackend
from autocad_mcp.data_router import read_cad_data


async def test_com_spatial_retries_rejected_calls_and_returns_real_empty(monkeypatch):
    class Busy(Exception):
        hresult = -2147418111

    entity = SimpleNamespace(Handle="42", ObjectName="AcDbLine", Layer="FRAME")
    attempts = iter([Busy(), BoundingBox([(0, 0, 0), (2, 2, 0)])])

    def extents(_):
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(com_spatial.COMScan, "extents", staticmethod(extents))
    app = SimpleNamespace(GetAcadState=lambda: SimpleNamespace(IsQuiescent=True))
    doc = SimpleNamespace(ModelSpace=[entity])
    result = await com_spatial.run_spatial(app, doc, dxf_spatial.window_query, 0, 0, 3, 3)
    assert result.ok and result.payload["matches"][0]["handle"] == "42"
    assert result.payload["diagnostics"]["busy_retries"] == 1
    empty = await com_spatial.run_spatial(app, doc, dxf_spatial.window_query, 0, 0, 3, 3, entity_type="ARC")
    assert empty.ok and empty.payload["count"] == 0

    app.GetAcadState = lambda: SimpleNamespace(IsQuiescent=False)
    busy = await com_spatial.run_spatial(app, doc, dxf_spatial.window_query, 0, 0, 3, 3, retry_timeout=0)
    assert not busy.ok and "busy" in busy.error


async def test_snapshot_rejects_unsaved_or_unverified_sources(tmp_path, monkeypatch):
    from autocad_mcp import data_snapshot

    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"saved drawing")
    app = SimpleNamespace(GetAcadState=lambda: SimpleNamespace(IsQuiescent=True))
    doc = SimpleNamespace(FullName=str(source), Saved=False, Layouts=SimpleNamespace(Count=1))
    backend = SimpleNamespace(name="com", _cad_type="autocad", _app=app, _doc=doc)

    def unverified(*args):
        return {"validation": {"status": "passed", "unchecked_source_types": ["ProxyEntity"]}}

    monkeypatch.setattr(data_snapshot, "export_saved_dwg", unverified)
    unsaved = await read_cad_data(backend, "query.view_regions")
    assert not unsaved.ok and "no pending changes" in unsaved.error
    doc.Saved = True
    failed = await read_cad_data(backend, "query.view_regions")
    assert not failed.ok and "did not verify" in failed.error


async def test_snapshot_routes_read_and_cleans_up(tmp_path, monkeypatch):
    from autocad_mcp import data_snapshot

    source = tmp_path / "drawing.dwg"
    source.write_bytes(b"saved drawing")
    app = SimpleNamespace(GetAcadState=lambda: SimpleNamespace(IsQuiescent=True))
    doc = SimpleNamespace(FullName=str(source), Saved=True, Layouts=SimpleNamespace(Count=1))
    backend = SimpleNamespace(name="com", _cad_type="autocad", _app=app, _doc=doc)
    created = []

    def verified(_doc, _app, path, version):
        created.append(Path(path))
        ezdxf.new(version).saveas(path)
        return {"validation": {"status": "passed", "unchecked_source_types": [], "checked_entities": 0}}

    monkeypatch.setattr(data_snapshot, "export_saved_dwg", verified)
    result = await read_cad_data(backend, "query.view_regions")
    assert result.ok and result.payload["regions"] == []
    assert result.payload["provenance"]["source_file"] == str(source)
    assert created and not created[0].parent.exists()
    assert source.read_bytes() == b"saved drawing"

    def changed(*args):
        report = verified(*args)
        source.write_bytes(b"changed drawing")
        return report

    monkeypatch.setattr(data_snapshot, "export_saved_dwg", changed)
    stale = await read_cad_data(backend, "query.view_regions")
    assert not stale.ok and "Source drawing changed" in stale.error
    assert not created[-1].parent.exists()


async def test_named_frame_and_full_document_export(tmp_path, monkeypatch):
    backend = EzdxfBackend()
    await backend.initialize()
    frame = backend._doc.blocks.new("Sheet Frame")
    frame.add_lwpolyline([(0, 0), (20, 0), (20, 10), (0, 10)], close=True)
    insert = backend._msp.add_blockref(frame.name, (100, 100))
    backend._msp.add_mtext("平面图", {"insert": (102, 108), "char_height": 0.3})
    backend._msp.add_lwpolyline([(3, 3), (4, 3), (4, 4), (3, 4)], close=True)
    monkeypatch.setattr(client, "_backend", backend)

    regions = json.loads(await server.query(operation="view_regions"))["payload"]["regions"]
    assert [(region["frame_handle"], region["view_type"]) for region in regions] == [(insert.dxf.handle, "plan")]
    output = tmp_path / "drawing.json"
    written = json.loads(await server.export(operation="cad_document", data={"path": str(output)}))
    assert written["ok"], written.get("error")
    document = json.loads(output.read_text(encoding="utf-8"))
    schema = Path(__file__).resolve().parents[1] / "docs" / "cad-document.v1.schema.json"
    Draft202012Validator(json.loads(schema.read_text(encoding="utf-8"))).validate(document)
    assert document["block_definitions"] and document["block_references"] and document["relationships"]
    assert len(document["entities"]) == 4
    assert document["views"][0]["view_type"] == "plan"
    assert not document["views"][0]["classification_ambiguous"]
    original = output.read_bytes()
    duplicate = json.loads(await server.export(operation="cad_document", data={"path": str(output)}))
    assert not duplicate["ok"] and output.read_bytes() == original
