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
        "ezdxf": "Candidate frame regions on a specified DXF layer",
    }),
    "geometry.bounding_box": ("geometry_bounding_box", {
        "ezdxf": "DXF bounds using ezdxf geometry support",
        "file_ipc": "Legacy AutoCAD bounds",
    }),
    "search.by_window": ("search_by_window", {
        "ezdxf": "DXF XY bounding-box query",
        "file_ipc": "Legacy AutoCAD window selection",
    }),
    "search.by_proximity": ("search_by_proximity", {
        "ezdxf": "DXF XY distance to bounding box center or nearest point",
        "file_ipc": "Legacy crossing window and DXF group 10 point distance",
    }),
}


def data_capabilities() -> dict:
    return {
        operation: {"backends": modes.copy(), "fallback": "none"}
        for operation, (_, modes) in _READS.items()
    }


async def read_cad_data(backend: AutoCADBackend, operation: str, *args, **kwargs) -> CommandResult:
    method, modes = _READS[operation]
    if backend.name not in modes:
        supported = ", ".join(modes)
        return CommandResult(
            ok=False,
            error=f"{operation} is not supported on backend {backend.name}; supported backends: {supported}",
        )
    # Another backend can refer to a different drawing or omit unsaved edits.
    return await getattr(backend, method)(*args, **kwargs)
