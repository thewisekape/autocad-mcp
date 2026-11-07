"""Build a short-lived DXF snapshot of the saved drawing bound to COM."""

from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from autocad_mcp.backends.dxf_export import export_saved_dwg, wait_until_idle
from autocad_mcp.backends.ezdxf_backend import EzdxfBackend


def file_sha256(path):
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@asynccontextmanager
async def verified_dxf_snapshot(backend, *, verify_block_references=False):
    if backend._cad_type != "autocad" or backend._app is None or backend._doc is None:
        raise ValueError("A connected Autodesk AutoCAD drawing is required for DXF fallback")
    app, doc = backend._app, backend._doc
    state = app.GetAcadState()
    name = wait_until_idle(state, "before preparing a DXF snapshot", probe=lambda: doc.FullName)
    source = Path(name)
    if not doc.Saved or source.suffix.lower() != ".dwg" or not source.is_file():
        raise ValueError("DXF fallback requires a saved local DWG with no pending changes")
    before = file_sha256(source)
    block_references = None
    if verify_block_references:
        block_references = {
            (block.Name.casefold(), ent.Handle.upper(), ent.Name.casefold())
            for block in doc.Blocks if not block.IsLayout
            for ent in block if ent.ObjectName in ("AcDbBlockReference", "AcDbMInsertBlock")
        }

    with TemporaryDirectory(prefix="autocad-mcp-snapshot-") as folder:
        path = Path(folder) / "snapshot.dxf"
        report = export_saved_dwg(doc, app, str(path), "R2013")["validation"]
        if report["status"] != "passed" or report["unchecked_source_types"]:
            raise ValueError(f"DXF snapshot did not verify all layout entities: {report}")
        wait_until_idle(state, "after preparing a DXF snapshot", probe=lambda: doc.Layouts.Count)
        if backend._doc is not doc or doc.FullName != name or not doc.Saved or file_sha256(source) != before:
            raise ValueError("Source drawing changed while preparing the DXF snapshot")

        offline = EzdxfBackend()
        opened = await offline.drawing_open(str(path))
        if not opened.ok:
            raise ValueError(f"DXF snapshot could not be opened: {opened.error}")
        if block_references is not None:
            converted = {
                (block.name.casefold(), ent.dxf.handle.upper(), ent.dxf.name.casefold())
                for block in offline._doc.blocks if not block.block_record.is_any_layout
                for ent in block.query("INSERT")
            }
            if converted != block_references:
                raise ValueError("DXF snapshot changed block-definition references")
        offline._doc.filename = str(source)
        yield offline, {
            "source_file": str(source), "source_sha256": before,
            "backend": "ezdxf", "extraction_method": "validated_r2013_snapshot",
            "checked_layout_entities": report["checked_entities"],
            "checked_nested_references": len(block_references) if block_references is not None else None,
        }
