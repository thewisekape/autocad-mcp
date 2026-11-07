from pathlib import Path
from types import SimpleNamespace

import ezdxf
import pytest

from autocad_mcp.backends.com_backend import COMBackend
from autocad_mcp.backends.dxf_export import export_saved_dwg
from autocad_mcp.backends.ezdxf_backend import EzdxfBackend


def fake_drawing(tmp_path, source_type="AcDbLine"):
    dwg = tmp_path / "source.dwg"
    dwg.write_bytes(b"source drawing")
    events = []
    export = ezdxf.new("R2013")
    handle = export.modelspace().add_line((0, 0), (1, 2)).dxf.handle
    model = SimpleNamespace(
        Name="Model",
        ModelType=True,
        Block=[SimpleNamespace(ObjectName=source_type, Handle=handle)],
    )

    def save_as(path, enum):
        events.append(("save", enum))
        export.saveas(path)

    def open_copy(path):
        copy = Path(path)
        assert copy != dwg
        assert copy.read_bytes() == dwg.read_bytes()
        events.append(("open", copy))
        return SimpleNamespace(
            FullName=str(copy), SaveAs=save_as, Close=lambda save: events.append(("close", save)),
        )

    source = SimpleNamespace(
        FullName=str(dwg),
        Saved=True,
        Layouts=[model],
        Activate=lambda: events.append(("restore",)),
    )
    app = SimpleNamespace(
        ActiveDocument=source, Documents=SimpleNamespace(Open=open_copy),
        GetAcadState=lambda: SimpleNamespace(IsQuiescent=True),
    )
    return source, app, events


def test_export_uses_verified_2013_copy(tmp_path):
    source, app, events = fake_drawing(tmp_path)
    out = tmp_path / "result.dxf"
    result = export_saved_dwg(source, app, str(out), "R2013")
    assert result["validation"]["status"] == "passed"
    assert result["validation"]["checked_entities"] == 1
    assert ezdxf.readfile(out).dxfversion == "AC1027"
    assert Path(source.FullName).read_bytes() == b"source drawing"
    assert events[1:] == [("save", 61), ("close", False)]
    assert not events[0][1].exists()


def test_rejects_type_conversion_without_publishing_output(tmp_path):
    source, app, events = fake_drawing(tmp_path, "AcDbTable")
    out = tmp_path / "result.dxf"
    result = export_saved_dwg(source, app, str(out), "AC1027")
    assert result["validation"]["status"] == "failed"
    assert result["validation"]["type_mismatches"][0]["expected_type"] == "ACAD_TABLE"
    assert not out.exists()
    assert not events[0][1].exists()


def test_export_refuses_original_or_existing_output(tmp_path):
    source, app, events = fake_drawing(tmp_path)
    out = tmp_path / "existing.dxf"
    out.write_bytes(b"existing")
    with pytest.raises(ValueError, match=r"\.dxf"):
        export_saved_dwg(source, app, source.FullName, "AC1027")
    with pytest.raises(FileExistsError):
        export_saved_dwg(source, app, str(out), "AC1027")
    assert out.read_bytes() == b"existing"
    assert not events


def test_export_refuses_unsaved_source(tmp_path):
    source, app, events = fake_drawing(tmp_path)
    source.Saved = False
    with pytest.raises(ValueError, match="pending drawing changes"):
        export_saved_dwg(source, app, str(tmp_path / "result.dxf"), "AC1027")
    assert not events


def test_wait_until_idle_retries_busy_and_bounds_the_wait(monkeypatch):
    from autocad_mcp.backends import dxf_export

    attempts = iter([False, True])
    state = type("State", (), {"IsQuiescent": property(lambda _: next(attempts))})()
    monkeypatch.setattr(dxf_export, "sleep", lambda _: None)
    assert dxf_export.wait_until_idle(state, "before export", probe=lambda: "ready") == "ready"

    with pytest.raises(TimeoutError, match="before export"):
        dxf_export.wait_until_idle(SimpleNamespace(IsQuiescent=False), "before export", timeout=0)


async def test_ezdxf_explicit_current_version(tmp_path):
    backend = EzdxfBackend()
    await backend.initialize()
    path = str(tmp_path / "result.dxf")
    assert not (await backend.drawing_save_as_dxf(path, "R2018")).ok
    assert (await backend.drawing_save_as_dxf(path, "R2013")).ok
    assert ezdxf.readfile(path).dxfversion == "AC1027"


async def test_com_table_partial_cells_and_unique_merge(monkeypatch):
    backend = COMBackend()

    def read_cell(row, col):
        if (row, col) == (1, 1):
            raise RuntimeError("Unreadable cell")
        return [["中文", ""], ["A", ""]][row][col]

    table = SimpleNamespace(
        ObjectName="AcDbTable", Handle="AC", Layer="TABLES", Rows=2, Columns=2,
        InsertionPoint=(12, 34, 0), StyleName="Report", GetText=read_cell,
    )
    backend._app = SimpleNamespace(Name="AutoCAD")
    backend._doc = SimpleNamespace(
        FullName="sample.dwg",
        Layouts=[SimpleNamespace(Name="Layout1", Block=[table])],
    )
    backend._msp = []
    monkeypatch.setattr(backend, "_read_table_merge", lambda _, row, col: (0, 0, 0, 1) if row == 0 else None)
    result = await backend.query_tables("layout1", "ac")
    assert result.ok
    assert result.payload["count"] == 1
    row = result.payload["tables"][0]
    assert row["cells"] == [["中文", ""], ["A", None]]
    assert row["merged_ranges"] == [{"min_row": 0, "max_row": 0, "min_col": 0, "max_col": 1}]
    assert row["insertion_point"] == [12, 34, 0]
    assert row["validation_status"] == "partial"
    assert not (await backend.query_tables("missing-layout")).ok
    assert not (await backend.query_tables("layout1", "not-a-handle")).ok

def test_mtext_keeps_control_codes_and_normalized_text():
    from autocad_mcp.backends.annotation_data import extract_dxf_annotation

    doc = ezdxf.new("R2013")
    raw = r"{\C1;Red} text\PNext line"
    entity = doc.modelspace().add_mtext(raw)
    annotation = extract_dxf_annotation(entity)["annotation"]
    assert annotation["raw_text"] == raw
    assert annotation["normalized_text"] == "Red text\nNext line"


def test_dimension_style_override_keeps_measurement_separate():
    from autocad_mcp.backends.annotation_data import extract_dxf_annotation

    doc = ezdxf.new("R2013")
    style = doc.dimstyles.new("Example", dxfattribs={"dimlfac": 1.5, "dimscale": 2})
    dim = doc.modelspace().add_aligned_dim(
        (0, 0), (4, 0), 2, dimstyle=style.dxf.name, override={"dimlfac": 2.5},
    )
    dim.commit()
    dim.dimension.dxf.actual_measurement = 4.0
    annotation = extract_dxf_annotation(dim.dimension)["annotation"]
    assert annotation["style_settings"]["dimlfac"] == 2.5
    assert annotation["style_settings"]["dimscale"] == 2
    assert annotation["style_overrides"]["dimlfac"] == 2.5
    assert annotation["measurement"] == 4
    assert annotation["display_value"] is None
