"""Dispatch CAD data reads against the current drawing's backend."""

from autocad_mcp.backends.base import AutoCADBackend, CommandResult


_READS = {
    "query.entity_geometry": ("query_entity_geometry", {
        "ezdxf": "DXF geometry by handle",
        "file_ipc": "Legacy entity fields from the active drawing",
    }),
    "query.block_tree": ("query_block_tree", {
        "ezdxf": "DXF block structure",
        "file_ipc": "Legacy flat block definitions",
    }),
    "query.tables": ("query_tables", {
        "com": "Native table cells and merge ranges where available",
    }),
    "query.view_regions": ("query_view_regions", {
        "ezdxf": "Named drawing frames or rectangles on a selected DXF layer",
    }),
    "geometry.bounding_box": ("geometry_bounding_box", {
        "com": "Native AutoCAD WCS bounding boxes",
        "ezdxf": "DXF bounds using ezdxf geometry support",
        "file_ipc": "Legacy AutoCAD bounds",
    }),
    "search.by_window": ("search_by_window", {
        "com": "Native AutoCAD XY bounding-box query",
        "ezdxf": "DXF XY bounding-box query",
        "file_ipc": "Legacy AutoCAD window selection",
    }),
    "search.by_proximity": ("search_by_proximity", {
        "com": "Native AutoCAD XY bounding-box distance query",
        "ezdxf": "DXF XY distance to bounding box center or nearest point",
        "file_ipc": "Legacy crossing window and DXF group 10 point distance",
    }),
}

_SNAPSHOT_READS = {"query.entity_geometry", "query.block_tree", "query.view_regions"}


def data_capabilities() -> dict:
    capabilities = {
        operation: {"backends": modes.copy(), "fallback": (
            "com_to_verified_r2013_snapshot" if operation in _SNAPSHOT_READS else "none"
        )}
        for operation, (_, modes) in _READS.items()
    }
    capabilities["export.cad_document"] = {
        "backends": {"ezdxf": "CADDocument v1", "com": "CADDocument v1 with native tables"},
        "fallback": "com_to_verified_r2013_snapshot",
    }
    return capabilities


async def read_cad_data(backend: AutoCADBackend, operation: str, *args, **kwargs) -> CommandResult:
    method, modes = _READS[operation]
    if backend.name == "com" and operation in _SNAPSHOT_READS:
        from autocad_mcp.data_snapshot import verified_dxf_snapshot

        try:
            async with verified_dxf_snapshot(backend, verify_block_references=operation != "query.view_regions") as (offline, provenance):
                result = await getattr(offline, method)(*args, **kwargs)
                if result.ok:
                    result.payload["provenance"] = provenance
                return result
        except Exception as exc:
            return CommandResult(ok=False, error=f"{operation} DXF fallback failed: {exc}")
    if backend.name not in modes:
        supported = ", ".join(modes)
        return CommandResult(
            ok=False,
            error=f"{operation} is not supported on backend {backend.name}; supported backends: {supported}",
        )
    return await getattr(backend, method)(*args, **kwargs)
