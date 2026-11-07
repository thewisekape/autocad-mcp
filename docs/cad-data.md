# CAD data extraction

The server registers 23 MCP tools. The table below covers the data extraction operations in this change. `system(operation="data_capabilities")` reports the read capabilities independently of the active drawing.

| Operation | AutoCAD COM | ezdxf | File IPC |
| --- | --- | --- | --- |
| `query.entity_geometry` | Use `query.entity_properties` for existing geometry fields and annotation details | DXF geometry, coordinate provenance and annotation details | Legacy raw geometry fields |
| `query.block_tree` | Unavailable | Definitions plus layout reference trees and per-instance matrices | Flat definitions |
| `query.tables` | Native layout tables, cells and merge ranges | Unavailable | Unavailable |
| `query.view_regions` | Unavailable | Candidate view regions on an explicit frame layer | Unavailable |
| `geometry.bounding_box` | Unavailable | DXF boxes by handle or layout filters | Legacy AutoCAD bounds |
| `search.by_window` | Unavailable | Containment or intersection of XY bounds | Legacy AutoCAD window selection |
| `search.by_proximity` | Unavailable | XY distance to box center or nearest point | Legacy group 10 point distance after crossing selection |
| `drawing.save_as_dxf` | R2013 / AC1027 by default, or R2018 / AC1032 | Current DXF version | Legacy behavior when version is omitted |
| `export.bom` | Unavailable | Block-reference summary | Block-reference summary |
| `export.entity_data` | Native layout entities | DXF entity fields | Legacy AutoCAD export |

The read router dispatches against the current backend and reports unsupported operations. Automatic cross-backend fallback is disabled until a snapshot can be verified against the active drawing and its saved state. Writes continue to use the selected backend.

## Coordinate and query definitions

- DXF block trees preserve `blocks` and add layout reference trees. Matrix rows use row vectors with translation in the last row. Instance paths distinguish repeated inserts. A plain handle lookup in a block definition returns definition-local geometry and a diagnostic when an instance path is required for WCS.
- DXF layout spatial queries scan top-level entities. `by_window` takes `mode` equal to `contains` (default) or `intersects`, with inclusive XY boundaries. `by_proximity` takes `metric` equal to `bbox_center` (default) or `bbox_nearest`, which is zero inside the box. These operations accept `entity_type`, `layer` and `layout`. `Model` is the default layout. Results describe XY axis-aligned bounding boxes, and some bounds, especially for text and curves, are approximate.
- `query.view_regions` takes `data.frame_layer` and an optional `data.layout`. It looks for axis-aligned, closed, four-vertex lightweight polylines on the specified layer. An explicit title can classify a view. Overlaps and cross-boundary members carry ambiguity markers. The default classification is `unknown`.
- [CADDocument v1](cad-document.v1.schema.json) specifies provenance, coordinates, entity records and view relationships. It separates source facts, computed values and inferences, and distinguishes dimension measurements from display text. Existing MCP responses retain their operation-specific shape. A document-wide export that emits this schema remains separate work.

## Codex MCP configuration

Register the server against the repository path and select a backend for the intended source. Use a separate server name if both configurations should be available. For COM, use the Windows session that can access the running AutoCAD instance.

```toml
[mcp_servers.autocad-dwg]
command = 'G:\CAD-AI\autocad-mcp-unified\.venv\Scripts\python.exe'
args = ['-m', 'autocad_mcp']
env = { AUTOCAD_MCP_BACKEND = 'com', AUTOCAD_MCP_CAD_TYPE = 'autocad' }

[mcp_servers.autocad-dxf]
command = 'G:\CAD-AI\autocad-mcp-unified\.venv\Scripts\python.exe'
args = ['-m', 'autocad_mcp']
env = { AUTOCAD_MCP_BACKEND = 'ezdxf' }
```

Use `uv sync --locked --python 3.11` in the repository to prepare dependencies, then confirm `system(operation="status")` and `system(operation="data_capabilities")` in Codex.

## DWG regression procedure

1. Record the source DWG SHA256 and open a local test copy in AutoCAD. Keep the source copy and all generated data outside Git.
2. Record COM layout counts by entity type, reference Handles, table cells and merge ranges, text samples, dimensions, and reference geometry.
3. Export the test copy with `drawing.save_as_dxf` and `data.version="R2013"` to a new `.dxf` path. Record the validation report. It checks layout-level entity identity and type for supported classes. Confirm block content, text and table fidelity separately.
4. Open the DXF with ezdxf. Compare layout Handles, nested transforms, WCS geometry, dimensions and candidate view regions. Classify discrepancies by conversion loss, expansion or representation change. Compare native TABLE cells through COM where available.
5. Recompute the original SHA256 and record which checks passed, failed or remain unavailable.

## Live validation

AutoCAD 2027 opened a temporary copy of the Autodesk sample `Mechanical - Text and Tables.dwg`. ActiveX read both native tables (17 × 2 and 16 × 2), including all 66 cell strings and 7 merge ranges. R2013 and R2018 both preserved the Handles and types of the 5 checked layout entities (2 tables, 2 block references and 1 MTEXT). The viewport was outside the check. AutoCAD restored the previously active drawing and the source sample's SHA256 matched before and after.

The Jinling Yuehua project DWG was unavailable. The sample run verifies layout entity identity and the source table read. Nested DWG transformations, DXF table cell fidelity, dimension rendering, and the project-specific geometry and frame grouping still require regression against the project drawing.

AutoCAD documentation covers [the R2013 and R2018 format codes](https://help.autodesk.com/cloudhelp/2027/ENU/OARX-RefGuide/files/OARX-RefGuide-AcApDocument__SaveFormat.html), [the SaveAs method](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-ActiveX-Reference/files/GUID-ED0D0B02-25FC-4ED2-9DEE-2B0C9AA9416A.htm), and [idle state checks](https://help.autodesk.com/cloudhelp/2023/KOR/AutoCAD-ActiveX-Reference/files/GUID-7537010D-4A81-48CA-BF03-86AFFF09653D.htm).
