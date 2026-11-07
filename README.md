# AutoCAD MCP Server v5.0 — Unified

A unified MCP (Model Context Protocol) server for AutoCAD that combines three backend strategies into a single, extensible package.

## Three Backends

| Backend | Connection | Requirements | Multi-CAD | Platform |
|---------|-----------|-------------|-----------|----------|
| **File IPC** | AutoLISP dispatcher + Win32 PostMessage | AutoCAD LT 2024+ | No | Windows |
| **COM** | Windows COM automation | AutoCAD 2018+ / ZWCAD / GstarCAD / BricsCAD | Yes | Windows |
| **ezdxf** | Headless DXF generation | None (pure Python) | N/A | Any |

## 23 MCP Tools

| # | Tool | Operations | Description |
|---|------|-----------|-------------|
| 1 | `drawing` | create, open, save, save_as_dxf, info, purge, plot_pdf, undo, redo, audit, units, limits, wblock | File/drawing management |
| 2 | `entity` | create_line/circle/polyline/rectangle/arc/ellipse/mtext/hatch, list, count, get, copy, move, rotate, scale, mirror, offset, array, fillet, chamfer, erase, explode, join, extend, trim, break_at | Entity CRUD + modification |
| 3 | `layer` | list, create, set_current, set_properties, freeze, thaw, lock, unlock | Layer management |
| 4 | `block` | list, insert, insert_with_attributes, get_attributes, update_attribute, define | Block operations |
| 5 | `annotation` | create_text, create_dimension_linear/aligned/angular/radius, create_leader | Text, dimensions, leaders |
| 6 | `pid` | setup_layers, insert_symbol, list_symbols, draw_process_line, connect_equipment, insert_valve/instrument/pump/tank | P&ID engineering |
| 7 | `view` | zoom_extents, zoom_window, zoom_center, pan, zoom_scale, screenshot, layer_visibility | Viewport control |
| 8 | `system` | status, health, runtime, init, execute_lisp, data_capabilities | Server management |
| 9 | `query` | entity_properties, entity_geometry, drawing_summary, layer_summary, text_styles, dimension_styles, linetypes, block_tree, drawing_metadata, tables, view_regions | Read-only queries |
| 10 | `search` | text, by_attribute, by_window, by_proximity, by_type_and_layer, by_block_name, by_handle_list, equipment_find, equipment_inspect, find_text, batch_find_and_tag | Find operations |
| 11 | `geometry` | distance, length, area, bounding_box, polyline_info | Measurements |
| 12 | `select` | filter, bulk_move, bulk_copy, bulk_erase, bulk_set_property, find_replace_text, find_replace_attribute, layer_rename, layer_merge | Bulk operations |
| 13 | `modify` | set_property, set_text | Property changes |
| 14 | `validate` | layer_standards, text_standards, orphaned_entities, attribute_completeness, connectivity, duplicates, zero_length, qc_report | QC checks |
| 15 | `export` | entity_data, bom, data_extract, layer_report, block_count, drawing_statistics, cad_document | Data export |
| 16 | `xref` | list, attach, detach, reload, bind, path_update, query_entities | External references |
| 17 | `layout` | list, create, switch, delete, viewport_create, viewport_set_scale, viewport_lock, page_setup, titleblock_fill, batch_plot | Layouts & viewports |
| 18 | `electrical` | nec_lookup, voltage_drop, conduit_fill, load_calc, symbol_insert, circuit_trace, panel_schedule_gen, wire_number_assign | NEC calculations |
| 19 | `connection` | connect, disconnect, status, list_supported, switch_backend | Multi-CAD connection management |
| 20 | `batch` | draw_lines, draw_circles, draw_rectangles, draw_polylines, draw_texts | Batch drawing (60-70% fewer API calls) |
| 21 | `nlp` | parse + execute natural language commands | Natural language CAD commands (EN/SV) |
| 22 | `excel_export` | full_export, selected_export | Export to Excel spreadsheets |
| 23 | `magicad` | status, list_commands, run, update_drawing, project_info, and other MagiCAD operations | MEP integration |

## Quick Start

### Installation

```bash
cd autocad-mcp

# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

### Configuration

Set the backend via environment variable:

```bash
# Auto-detect (default): tries File IPC -> COM -> ezdxf
set AUTOCAD_MCP_BACKEND=auto

# Force specific backend
set AUTOCAD_MCP_BACKEND=file_ipc   # AutoLISP-based (AutoCAD LT)
set AUTOCAD_MCP_BACKEND=com        # COM automation (full AutoCAD + alternatives)
set AUTOCAD_MCP_BACKEND=ezdxf      # Headless DXF (no AutoCAD needed)

# For COM backend: select which CAD
set AUTOCAD_MCP_CAD_TYPE=autocad   # or zwcad, gcad, bricscad
```

### Claude Desktop / Claude Code Configuration

Add to your MCP configuration:

```json
{
  "mcpServers": {
    "autocad": {
      "command": "uv",
      "args": ["--directory", "/path/to/autocad-mcp", "run", "python", "-m", "autocad_mcp"],
      "env": {
        "AUTOCAD_MCP_BACKEND": "auto"
      }
    }
  }
}
```

### File IPC Backend Setup

For AutoCAD LT, load the LISP dispatcher:

1. Open AutoCAD LT
2. In the command line, type: `(load "/path/to/autocad-mcp/lisp-code/mcp_dispatch.lsp")`
3. The MCP server will automatically detect the running AutoCAD instance

## Architecture

For CAD data extraction, see the [backend compatibility matrix and validation guide](docs/cad-data.md).

```
MCP Client (Claude Desktop, Claude Code, Cursor, etc.)
    |
    +---> Python MCP Server (stdio transport)
           |
           +-> File IPC Backend --> JSON files + Win32 PostMessage --> AutoLISP --> AutoCAD LT
           |
           +-> COM Backend --> win32com.client --> AutoCAD / ZWCAD / GstarCAD / BricsCAD
           |
           +-> ezdxf Backend --> In-memory DXF (headless, cross-platform)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOCAD_MCP_BACKEND` | `auto` | Backend: `auto`, `file_ipc`, `com`, `ezdxf` |
| `AUTOCAD_MCP_CAD_TYPE` | `autocad` | COM target: `autocad`, `zwcad`, `gcad`, `bricscad` |
| `AUTOCAD_MCP_IPC_DIR` | `C:/temp` | File IPC working directory |
| `AUTOCAD_MCP_IPC_TIMEOUT` | `30` | IPC timeout in seconds (1-300) |
| `AUTOCAD_MCP_ONLY_TEXT` | `false` | Disable screenshots (text-only) |

## Dependencies

- Python 3.10+
- `mcp[cli]` -- MCP protocol framework
- `ezdxf` -- DXF read/write
- `matplotlib` + `Pillow` -- Screenshot rendering
- `structlog` -- Structured logging
- `pywin32` -- Windows COM + Win32 API (Windows only)
- `openpyxl` -- Excel export

## Credits

Built by combining the best of:
- [puran-water/autocad-mcp](https://github.com/puran-water/autocad-mcp) -- Dual backend architecture, File IPC, execute_lisp
- [ngk0/autocad-mcp](https://github.com/ngk0/autocad-mcp) -- 19 tool categories, xref/layout/electrical, 232 tests
- [AnCode666/multiCAD-mcp](https://github.com/AnCode666/multiCAD-mcp) -- COM multi-CAD support, batch operations, NLP, Excel export

## License

Copyright 2026 Nordiska Brand AB

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for details.
