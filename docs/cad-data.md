# CAD data extraction

The server registers 23 MCP tools. The table below covers the data extraction operations in this change. `system(operation="data_capabilities")` reports the read capabilities independently of the active drawing.

| Operation | AutoCAD COM | ezdxf | File IPC |
| --- | --- | --- | --- |
| `query.entity_geometry` | Verified DXF snapshot | DXF geometry, coordinate provenance and annotation details | Legacy raw geometry fields |
| `query.block_tree` | Verified DXF snapshot | Definitions plus layout reference trees and per-instance matrices | Flat definitions |
| `query.tables` | Native layout tables, cells and merge ranges | Unavailable | Unavailable |
| `query.view_regions` | Verified DXF snapshot | Named frame blocks or rectangles on a selected layer | Unavailable |
| `geometry.bounding_box` | Native WCS bounds | DXF boxes by handle or layout filters | Legacy AutoCAD bounds |
| `search.by_window` | Containment or intersection of native XY bounds | Containment or intersection of XY bounds | Legacy AutoCAD window selection |
| `search.by_proximity` | Distance to native XY box center or nearest point | XY distance to box center or nearest point | Legacy group 10 point distance after crossing selection |
| `drawing.save_as_dxf` | R2013 / AC1027 by default, or R2018 / AC1032 | Current DXF version | Legacy behavior when version is omitted |
| `export.bom` | Unavailable | Block-reference summary | Block-reference summary |
| `export.entity_data` | Native layout entities | DXF entity fields | Legacy AutoCAD export |
| `export.cad_document` | Verified DXF snapshot with native tables | CADDocument v1 | Unavailable |

For the marked COM reads, the server converts a temporary copy of the saved DWG. The R2013 snapshot must match every layout entity by Handle and type. Block and document extraction also check nested references. A stable SHA256 and saved state are required. Unsupported entities or validation failures produce an explicit error. The server removes the temporary snapshot after the read. Rendering and external references require separate verification.

## Coordinate and query definitions

- DXF block trees preserve `blocks` and add layout reference trees. Matrix rows use row vectors with translation in the last row. Instance paths distinguish repeated inserts. A plain handle lookup in a block definition returns definition-local geometry and a diagnostic when an instance path is required for WCS.
- COM and DXF spatial queries scan top-level entities. Window queries support containment and intersection with inclusive XY boundaries. Proximity queries support distance to the box center or nearest point. The options include entity type, layer and layout. Model is the default layout. COM uses native WCS bounds and retries busy calls briefly. Some DXF bounds, especially for text and curves, are approximate. [AutoCAD GetBoundingBox reference](https://help.autodesk.com/cloudhelp/2025/CHS/AutoCAD-LT-ActiveX-Reference/files/GUID-A20C361C-BBF0-4EAB-8BE7-709154CEEE09.htm)
- Query view regions with an optional layout and frame layer. The default finds named drawing-frame blocks and uses explicit titles. A specified layer selects closed rectangular polylines. Insufficient or conflicting titles yield unknown. Title ambiguity and cross-boundary membership are reported separately.
- The cad_document export operation emits [CADDocument v1](cad-document.v1.schema.json). Pass a new JSON path in data.path to write a file, or omit it to return the document. The document includes layout and block-definition entities, instance paths, dimensions, annotations, tables, views and relationships. COM supplies native table cells. Direct DXF reads provide best-effort cell strings.

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

Project-drawing regression results are stored separately. Layout identity checks, native table extraction and snapshot reads cover the documented scope. Rendering and full object fidelity require separate checks.

AutoCAD documentation covers [the R2013 and R2018 format codes](https://help.autodesk.com/cloudhelp/2027/ENU/OARX-RefGuide/files/OARX-RefGuide-AcApDocument__SaveFormat.html), [the SaveAs method](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-ActiveX-Reference/files/GUID-ED0D0B02-25FC-4ED2-9DEE-2B0C9AA9416A.htm), and [idle state checks](https://help.autodesk.com/cloudhelp/2023/KOR/AutoCAD-ActiveX-Reference/files/GUID-7537010D-4A81-48CA-BF03-86AFFF09653D.htm).
