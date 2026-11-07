"""Read-only DXF block topology and coordinate transforms."""

from math import isfinite

from ezdxf import DXFError
from ezdxf.math import Matrix44

MAX_DEPTH = 64
MAX_REFERENCES = 10_000


def _dynamic_definition(block, doc):
    """Resolve AutoCAD's persisted dynamic-block association where present."""
    record = block.block_record
    if record.has_xdata("AcDbDynamicBlockGUID"):
        return block
    if record.has_xdata("AcDbBlockRepBTag"):
        tags = record.get_xdata("AcDbBlockRepBTag")
        handle = tags.get_first_value(1005, None)
        base = doc.entitydb.get(handle) if handle else None
        if base is not None and base.dxftype() == "BLOCK_RECORD":
            return doc.blocks.get(base.dxf.name)
    return None


def _definition_kind(block, dynamic):
    if block.block.is_xref or block.block.is_xref_overlay:
        return "Xref"
    if block.block_record.is_any_layout:
        return "LayoutDefinition"
    if dynamic is block:
        return "DynamicBlock"
    if block.name.startswith("*"):
        return "AnonymousBlock"
    return "BlockDefinition"


def _insert_matrices(insert, block, parent_matrix):
    if block is None:
        return None, None, None
    local_matrix = insert.matrix44()
    if not all(isfinite(value) for value in local_matrix):
        raise ValueError("INSERT matrix contains non-finite values")
    world_matrix = local_matrix * parent_matrix if parent_matrix is not None else None
    if world_matrix is not None and not all(isfinite(value) for value in world_matrix):
        raise ValueError("Composed INSERT matrix contains non-finite values")
    origin = world_matrix.transform(block.block.dxf.base_point) if world_matrix is not None else None
    if origin is not None and not all(isfinite(value) for value in origin):
        raise ValueError("INSERT origin contains non-finite values")
    return local_matrix, world_matrix, origin


def _matrix_rows(matrix):
    return [list(row) for row in matrix.rows()] if matrix is not None else None


def extract_block_tree(doc, source_file):
    """Return block definitions plus per-layout reference instances.

    Matrix44 uses row vectors, so the child-to-layout transform is the
    child-to-parent transform multiplied by the parent-to-layout transform.
    """
    blocks = []
    definitions = {}
    for block in doc.blocks:
        is_xref = bool(block.block.is_xref or block.block.is_xref_overlay)
        dynamic = _dynamic_definition(block, doc)
        kind = _definition_kind(block, dynamic)
        entry = {
            "name": block.name,
            "is_xref": is_xref,
            "is_anonymous": block.name.startswith("*"),
            "entity_count": len(block),
            "handle": block.block_record.dxf.handle,
            "kind": kind,
            "base_point": list(block.block.dxf.base_point),
            "effective_name": dynamic.name if dynamic is not None else block.name,
            "is_dynamic": dynamic is not None,
        }
        if is_xref:
            entry["xref_path"] = block.block.dxf.xref_path
        attdefs = [
            {"tag": ad.dxf.tag, "prompt": ad.dxf.get("prompt", "")}
            for ad in block.attdefs() if ad.dxf.hasattr("tag")
        ]
        if attdefs:
            entry["attribute_definitions"] = attdefs
        blocks.append(entry)
        definitions[entry["handle"]] = entry

    warnings = []
    remaining = MAX_REFERENCES

    def references(container, layout, parent, parent_matrix, ancestors):
        nonlocal remaining
        nodes = []
        for source in container.query("INSERT"):
            handle = source.dxf.handle
            block = source.block()
            definition_handle = block.block_record.dxf.handle if block is not None else None
            definition = definitions.get(definition_handle, {})
            kind = definition.get("kind")
            grid_size = source.dxf.row_count * source.dxf.column_count
            expand_grid = 1 < grid_size <= MAX_REFERENCES and source.mcount > 1
            instances = source.multi_insert() if expand_grid else (source,)

            for index, insert in enumerate(instances):
                if remaining == 0:
                    return nodes
                remaining -= 1
                path_segment = f"{handle}[{index}]" if expand_grid else handle
                path = parent["nested_path"] + [path_segment] if parent else [path_segment]
                node_id = f"{layout.block_record_handle}/" + "/".join(path)
                node_warnings = []
                local_matrix = world_matrix = world_origin = None
                try:
                    local_matrix, world_matrix, world_origin = _insert_matrices(
                        insert, block, parent_matrix,
                    )
                except (ArithmeticError, DXFError, ValueError):
                    node_warnings.append("invalid_transform")

                node = {
                    "id": node_id,
                    "kind": "NestedBlockReference" if parent else "BlockReference",
                    "handle": handle,
                    "layout": layout.name,
                    "layer": source.dxf.layer,
                    "block_name": source.dxf.name,
                    "definition_handle": definition_handle,
                    "definition_kind": kind,
                    "effective_name": definition.get("effective_name"),
                    "is_dynamic": definition.get("is_dynamic"),
                    "is_xref": definition.get("is_xref"),
                    "parent_id": parent["id"] if parent else None,
                    "parent_block": parent["block_name"] if parent else None,
                    "nested_path": path,
                    "insertion_point_ocs": list(insert.dxf.insert),
                    "insertion_point_wcs": list(world_origin) if world_origin is not None else None,
                    "rotation_degrees": source.dxf.rotation,
                    "scale_factors": [source.dxf.xscale, source.dxf.yscale, source.dxf.zscale],
                    "local_transform": _matrix_rows(local_matrix),
                    "world_transform": _matrix_rows(world_matrix),
                    "attributes": {att.dxf.tag: att.dxf.text for att in source.attribs},
                    "children": [],
                    "warnings": node_warnings,
                }
                if grid_size > MAX_REFERENCES:
                    node_warnings.append("minsert_grid_not_expanded")
                if block is None:
                    node_warnings.append("missing_block_definition")
                elif kind == "Xref":
                    node_warnings.append("xref_contents_not_resolved")
                elif definition_handle in ancestors:
                    node_warnings.append("cyclic_block_reference")
                elif len(path) == MAX_DEPTH:
                    if block.query("INSERT"):
                        node_warnings.append("max_block_depth_reached")
                else:
                    node["children"] = references(
                        block, layout, node, world_matrix, ancestors | {definition_handle},
                    )
                nodes.append(node)
        return nodes

    layouts = []
    for layout in doc.layouts:
        layouts.append({
            "name": layout.name,
            "block_record_handle": layout.block_record_handle,
            "references": references(layout, layout, None, Matrix44(), frozenset()),
        })
    if remaining == 0:
        warnings.append("max_block_references_reached")
    return {
        "blocks": blocks,
        "layouts": layouts,
        "source_file": source_file,
        "matrix_convention": "4x4 row vectors, translation in last row",
        "warnings": warnings,
    }
