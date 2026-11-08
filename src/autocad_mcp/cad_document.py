"""Assemble and optionally save the CADDocument v1 interchange format."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from ezdxf import DXFError
from ezdxf.entities.acad_table import read_acad_table_content

from autocad_mcp.backends.base import CommandResult
from autocad_mcp.data_snapshot import file_sha256, verified_dxf_snapshot


def source_ref(path, handle, layout=None, nested_path=None, instance_id=None):
    result = {"file": path, "handle": handle, "layout": layout, "nested_path": nested_path or []}
    if instance_id is not None:
        result["instance_id"] = instance_id
    return result


def observation(method, warnings=(), kind="source_fact"):
    return {"kind": kind, "extraction_method": method,
            "validation_status": "partial" if warnings else "unverified", "warnings": list(warnings)}


def entity_record(source, entity_type, layer, coordinate_system, data, method, warnings=(), kind="source_fact"):
    return {"source": source, "entity_type": entity_type, "layer": layer, "coordinate_system": coordinate_system,
            "data": data, **observation(method, warnings, kind)}


def dxf_table(entity):
    try:
        cells = read_acad_table_content(entity)
    except (AttributeError, ValueError, TypeError, KeyError, DXFError):
        return {"cells": None}, ["DXF table cell strings unavailable"]
    return {"cells": cells, "merged_ranges": None}, ["DXF cell strings are best effort; merge information requires AutoCAD COM"]


async def build_document(backend, file, method, native_tables=None, frame_layer=None):
    doc = backend._doc
    path = file["path"]
    layouts = list(doc.layouts)
    definitions = [block for block in doc.blocks if not block.block_record.is_any_layout]
    output = {"schema_version": "1.0.0", "file": file, "layouts": [layout.name for layout in layouts],
              "layers": [layer.dxf.name for layer in doc.layers], "entities": [], "block_definitions": [],
              "block_references": [], "dimensions": [], "annotations": [], "tables": [], "views": [], "relationships": []}
    native_tables = {table["handle"]: table for table in native_tables or []}

    for container in (*layouts, *definitions):
        in_layout = container.block_record.is_any_layout
        layout_name = container.name if in_layout else None
        for entity in container:
            handle, kind = entity.dxf.handle, entity.dxftype()
            if not handle:
                continue
            layer = entity.dxf.get("layer", None) if entity.dxf.is_supported("layer") else None
            source = source_ref(path, handle, layout_name)
            geometry = await backend.query_entity_geometry(handle)
            data = geometry.payload.copy() if geometry.ok else {}
            warnings = list(data.get("warnings", ()))
            if "info" in data:
                warnings.append(data["info"])
            if not geometry.ok:
                warnings.append(geometry.error)
            if not in_layout:
                data.setdefault("parent_block", container.name)
            coordinate_system = "WCS" if in_layout else "block_local"
            if kind == "ACAD_TABLE":
                native = native_tables.get(handle)
                if native is not None:
                    data, warnings = {**native, "source_file": path}, native["warnings"]
                else:
                    table, warnings = dxf_table(entity)
                    data.update(table)
                record = entity_record(source, kind, layer, coordinate_system, data, "autocad_com" if native is not None else method, warnings)
                output["tables"].append(record)
            else:
                annotation = data.get("annotation")
                if annotation:
                    warnings.extend(annotation.get("warnings", ()))
                record = entity_record(source, kind, layer, coordinate_system, data, method, warnings)
                if kind == "DIMENSION":
                    record["measurement"] = (annotation or {}).get("measurement")
                    record["display_text"] = (annotation or {}).get("display_value")
                    output["dimensions"].append(record)
                elif kind in ("TEXT", "MTEXT"):
                    output["annotations"].append(record)
            output["entities"].append(record)

    tree_result = await backend.query_block_tree()
    if not tree_result.ok:
        raise ValueError(f"Block structure could not be extracted: {tree_result.error}")
    tree = tree_result.payload
    for block in tree["blocks"]:
        if block["kind"] == "LayoutDefinition":
            continue
        source = source_ref(path, block["handle"])
        output["block_definitions"].append(entity_record(source, "BLOCK_DEFINITION", None, "block_local", block, method))

    pending = [(node, None) for layout in tree["layouts"] for node in reversed(layout["references"])]
    while pending:
        node, parent = pending.pop()
        source = source_ref(path, node["handle"], node["layout"], node["nested_path"], node["id"])
        data = {key: value for key, value in node.items() if key != "children"}
        output["block_references"].append(entity_record(source, "INSERT", node["layer"], "WCS", data, method, node["warnings"], "computed"))
        targets = [("nested_in", parent)]
        if node["definition_handle"]:
            targets.append(("references_definition", source_ref(path, node["definition_handle"])))
        output["relationships"].extend(
            {"from": source, "to": target, "relationship_type": kind, **observation(method)}
            for kind, target in targets if target is not None
        )
        pending.extend((child, source) for child in reversed(node["children"]))
    if tree["warnings"]:
        output["warnings"] = tree["warnings"]

    for layout in layouts:
        views = await backend.query_view_regions(frame_layer, layout=layout.name)
        if not views.ok:
            output.setdefault("warnings", []).append(views.error)
            continue
        for region in views.payload["regions"]:
            members = [{**source_ref(path, item["handle"], layout.name),
                        "relation": item["relation"], "ambiguous": item["ambiguous"]} for item in region["members"]]
            output["views"].append({"id": f"{layout.name}/{region['frame_handle']}", "view_type": region["view_type"],
                                    "frame": source_ref(path, region["frame_handle"], layout.name),
                                    "bbox_min": region["bbox_min"], "bbox_max": region["bbox_max"],
                                    "titles": [{**title, "source": source_ref(path, title["handle"], layout.name)}
                                               for title in region["titles"]],
                                    "members": members, "ambiguous": region["ambiguous"],
                                    "frame_evidence": region["frame_evidence"],
                                    "classification_ambiguous": region["classification_ambiguous"],
                                    "boundary_ambiguous": region["boundary_ambiguous"],
                                    **observation("view_region_rules", ["Ambiguous view grouping"] if region["ambiguous"] else [], "inferred")})
    return output


def write_document(output, destination):
    with TemporaryDirectory(prefix=".cad-document-", dir=destination.parent) as directory:
        staged = Path(directory) / "document.json"
        with staged.open("w", encoding="utf-8") as stream:
            json.dump(output, stream, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        if os.name == "nt":
            staged.rename(destination)
        else:
            os.link(staged, destination)


async def export_cad_document(backend, *, path=None, frame_layer=None):
    try:
        destination = Path(path).resolve() if path is not None else None
        if destination is not None and (destination.suffix.lower() != ".json" or destination.exists()):
            raise ValueError("Choose a new .json output path")
        if backend.name == "ezdxf" and backend._doc is not None:
            doc = backend._doc
            file = {"path": str(doc.filename or "unsaved.dxf"), "format": "DXF", "dxf_version": doc.dxfversion}
            output = await build_document(backend, file, "ezdxf", frame_layer=frame_layer)
        elif backend.name == "com":
            async with verified_dxf_snapshot(backend, verify_block_references=True) as (offline, provenance):
                native = await backend.query_tables()
                if not native.ok:
                    raise ValueError(f"Native table extraction failed: {native.error}")
                source = Path(provenance["source_file"])
                if not backend._doc.Saved or file_sha256(source) != provenance["source_sha256"]:
                    raise ValueError("Source drawing changed during document extraction")
                file = {"path": str(source), "format": "DWG", "sha256": provenance["source_sha256"],
                        "dxf_version": offline._doc.dxfversion}
                output = await build_document(offline, file, provenance["extraction_method"], native.payload["tables"], frame_layer)
                output["provenance"] = provenance
        else:
            raise ValueError("Open a DXF with ezdxf or connect a saved DWG in AutoCAD COM first")
        if destination is None:
            return CommandResult(ok=True, payload=output)
        write_document(output, destination)
        return CommandResult(ok=True, payload={"path": str(destination), "schema_version": output["schema_version"],
                                               "entities": len(output["entities"]), "views": len(output["views"])})
    except (TypeError, ValueError, OSError) as exc:
        return CommandResult(ok=False, error=f"CADDocument export failed: {exc}")
