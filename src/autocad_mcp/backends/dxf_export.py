"""Safe AutoCAD DXF conversion and verification against source layout objects."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from typing import Any

import ezdxf

try:
    from pywintypes import com_error
except ImportError:
    _TRANSIENT_READY_ERRORS = (AttributeError,)
else:
    _TRANSIENT_READY_ERRORS = (AttributeError, com_error)

# Autodesk ActiveX API History, 2013 and 2018 (AcSaveAsType).
VERSIONS = {"AC1027": 61, "AC1032": 65}
VERSION_ALIASES = {"R2013": "AC1027", "R2018": "AC1032"}

COM_TYPES = {
    "AcDbArc": "ARC",
    "AcDbBlockReference": "INSERT",
    "AcDbMInsertBlock": "INSERT",
    "AcDbCircle": "CIRCLE",
    "AcDbEllipse": "ELLIPSE",
    "AcDbHatch": "HATCH",
    "AcDbLeader": "LEADER",
    "AcDbLine": "LINE",
    "AcDbMLeader": "MULTILEADER",
    "AcDbMText": "MTEXT",
    "AcDbPoint": "POINT",
    "AcDbPolyline": "LWPOLYLINE",
    "AcDb2dPolyline": "POLYLINE",
    "AcDb3dPolyline": "POLYLINE",
    "AcDbSpline": "SPLINE",
    "AcDbTable": "ACAD_TABLE",
    "AcDbText": "TEXT",
    "AcDbRegion": "REGION",
    "AcDbWipeout": "WIPEOUT",
    "AcDbViewport": "VIEWPORT",
}


def canonical_version(version: str) -> str:
    version = version.upper().strip()
    return VERSION_ALIASES.get(version, version)


def com_entity_type(object_name: str) -> str | None:
    if object_name.endswith("Dimension") and object_name.startswith("AcDb"):
        return "DIMENSION"
    return COM_TYPES.get(object_name)


def wait_until_idle(state: Any, phase: str, timeout: float = 8.0, *, probe=None) -> Any:
    deadline = monotonic() + timeout
    last_error = None
    while True:
        try:
            if state.IsQuiescent:
                return probe() if probe is not None else None
        except _TRANSIENT_READY_ERRORS as exc:
            last_error = exc
        if monotonic() >= deadline:
            raise TimeoutError(f"AutoCAD did not become ready {phase} within {timeout:g} seconds") from last_error
        sleep(0.2)


def _com_inventory(document: Any) -> tuple[dict[str, dict[str, str]], set[str]]:
    inventory: dict[str, dict[str, str]] = {}
    unchecked: set[str] = set()
    for layout in document.Layouts:
        name = "Model" if layout.ModelType else layout.Name
        entities = inventory.setdefault(name, {})
        for entity in layout.Block:
            object_name = entity.ObjectName
            entity_type = com_entity_type(object_name)
            if entity_type is None:
                unchecked.add(object_name)
            else:
                entities[entity.Handle.upper()] = entity_type
    return inventory, unchecked


def _verify_dxf(path: Path, source: dict, unchecked: set[str], version: str) -> dict:
    output = ezdxf.readfile(path)
    target = {
        layout.name: {
            entity.dxf.handle.upper(): entity.dxftype()
            for entity in layout
            if entity.dxf.handle
        }
        for layout in output.layouts
    }
    missing = []
    mismatched = []
    for layout, entities in source.items():
        for handle, expected_type in entities.items():
            actual_type = target.get(layout, {}).get(handle)
            if actual_type is None:
                missing.append({"layout": layout, "handle": handle, "type": expected_type})
            elif actual_type != expected_type:
                mismatched.append({
                    "layout": layout,
                    "handle": handle,
                    "expected_type": expected_type,
                    "actual_type": actual_type,
                })
    extra = [] if unchecked else [
        {"layout": layout, "handle": handle, "type": kind}
        for layout, entities in target.items() for handle, kind in entities.items()
        if handle not in source.get(layout, {})
    ]
    return {
        "status": "failed" if missing or mismatched or extra or output.dxfversion != version else "passed",
        "requested_version": version,
        "actual_version": output.dxfversion,
        "checked_entities": sum(map(len, source.values())),
        "missing": missing,
        "type_mismatches": mismatched,
        "unexpected_entities": extra,
        "unchecked_source_types": sorted(unchecked),
        "scope": "Layout entity identity and type by handle. Block contents, external references, "
                 "entity properties, and table cell fidelity require separate validation.",
    }


def export_saved_dwg(document: Any, app: Any, path: str, version: str) -> dict:
    """Export a saved DWG via a temporary copy and publish only a verified DXF."""
    version = canonical_version(version)
    if version not in VERSIONS:
        raise ValueError("Supported AutoCAD DXF versions are R2013/AC1027 and R2018/AC1032")
    destination = Path(path).resolve()
    if destination.suffix.lower() != ".dxf":
        raise ValueError("DXF destination must end in .dxf")
    if destination.exists():
        raise FileExistsError(f"DXF destination already exists: {destination}")
    if not document.Saved:
        raise ValueError("Save pending drawing changes before exporting to DXF")
    source = Path(document.FullName)
    if source.suffix.lower() != ".dwg" or not source.is_file():
        raise ValueError("AutoCAD DXF export requires a saved local DWG")

    state = app.GetAcadState()
    wait_until_idle(state, "before export")
    inventory, unchecked = _com_inventory(document)
    active = app.ActiveDocument
    active_path = active.FullName
    with TemporaryDirectory(prefix=".cad-mcp-dxf-", dir=destination.parent) as stage_dir:
        stage = Path(stage_dir)
        source_copy = stage / source.name
        exported = stage / destination.name
        shutil.copyfile(source, source_copy)
        copied_document = app.Documents.Open(str(source_copy))
        try:
            save_as = wait_until_idle(state, "after opening the export copy", probe=lambda: copied_document.SaveAs)
            save_as(str(exported), VERSIONS[version])
        finally:
            try:
                close = wait_until_idle(state, "before closing the export copy", probe=lambda: copied_document.Close)
                close(False)
            finally:
                restored_path = wait_until_idle(
                    state, "after closing the export copy", probe=lambda: app.ActiveDocument.FullName,
                )
                if restored_path != active_path:
                    active.Activate()
                    wait_until_idle(state, "after restoring the active drawing", probe=lambda: app.Name)

        report = _verify_dxf(exported, inventory, unchecked, version)
        if report["status"] == "passed":
            # Windows rename is atomic on the same volume and refuses existing files.
            # Link also refuses existing files on POSIX, used by offline tests.
            if os.name == "nt":
                exported.rename(destination)
            else:
                os.link(exported, destination)
            return {"saved_dxf": path, "validation": report}
        return {"validation": report}
