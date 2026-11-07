"""File-based IPC backend for AutoCAD LT.

Protocol:
1. Python writes JSON command to C:/temp/autocad_mcp_cmd_{request_id}.json
2. Python types the fixed string "(c:mcp-dispatch)" + Enter
3. LISP reads cmd, dispatches via command map, writes result to
   C:/temp/autocad_mcp_result_{request_id}.json
4. Python polls for result file (100ms intervals, 10s timeout)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import structlog

from autocad_mcp.backends.base import AutoCADBackend, BackendCapabilities, CommandResult
from autocad_mcp.config import IPC_DIR, IPC_TIMEOUT, LISP_DIR

log = structlog.get_logger()

# IPC settings
POLL_INTERVAL = 0.1  # seconds
TIMEOUT = IPC_TIMEOUT  # seconds (configurable via AUTOCAD_MCP_IPC_TIMEOUT)
STALE_THRESHOLD = 60.0  # clean up files older than this


def find_autocad_window() -> int | None:
    """Find the AutoCAD LT window handle by checking window titles."""
    if sys.platform != "win32":
        return None
    try:
        import win32gui

        windows: list[int] = []

        def callback(hwnd, result):
            if win32gui.IsWindowVisible(hwnd):
                text = win32gui.GetWindowText(hwnd).lower()
                if "autocad" in text and ("drawing" in text or ".dwg" in text):
                    result.append(hwnd)
            return True

        win32gui.EnumWindows(callback, windows)
        return windows[0] if windows else None
    except ImportError:
        return None


class FileIPCBackend(AutoCADBackend):
    """File-based IPC with AutoCAD LT via mcp_dispatch.lsp."""

    def __init__(self):
        self._hwnd: int | None = None
        self._command_hwnd: int | None = None
        self._ipc_dir = Path(IPC_DIR)
        self._screenshot_provider = None
        self._lock = asyncio.Lock()  # Single in-flight command

    @property
    def name(self) -> str:
        return "file_ipc"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            can_read_drawing=True,
            can_modify_entities=True,
            can_create_entities=True,
            can_screenshot=True,
            can_save=True,
            can_plot_pdf=True,
            can_zoom=True,
            can_query_entities=True,
            can_file_operations=True,
            can_undo=True,
        )

    async def initialize(self) -> CommandResult:
        """Find AutoCAD window and verify dispatcher is loaded."""
        self._hwnd = find_autocad_window()
        if not self._hwnd:
            return CommandResult(ok=False, error="AutoCAD LT window not found")

        # Set up screenshot provider
        try:
            from autocad_mcp.screenshot import Win32ScreenshotProvider

            self._screenshot_provider = Win32ScreenshotProvider(self._hwnd)
        except Exception:
            pass

        # Find command-line child edit control for focus-free dispatch
        self._command_hwnd = self._find_command_line_hwnd()
        log.info("command_line_hwnd", hwnd=self._command_hwnd)

        # Ensure IPC directory exists
        self._ipc_dir.mkdir(parents=True, exist_ok=True)

        # Clean up stale IPC files
        self._cleanup_stale_files()

        # Ping the dispatcher to verify it's loaded
        result = await self._dispatch("ping", {})
        if not result.ok:
            lisp_path = str(LISP_DIR / "mcp_dispatch.lsp").replace("\\", "/")
            return CommandResult(
                ok=False,
                error=(
                    "AutoCAD LT detected but mcp_dispatch.lsp not loaded.\n"
                    f'In AutoCAD command line, type:\n  (load "{lisp_path}")\n'
                    "Or add lisp-code/ to trusted paths for auto-loading."
                ),
            )

        return CommandResult(ok=True, payload={"backend": "file_ipc", "hwnd": self._hwnd})

    async def status(self) -> CommandResult:
        info = {
            "backend": "file_ipc",
            "hwnd": self._hwnd,
            "ipc_dir": str(self._ipc_dir),
            "capabilities": {k: v for k, v in self.capabilities.__dict__.items()},
        }
        return CommandResult(ok=True, payload=info)

    # --- IPC dispatch ---

    async def _dispatch(self, command: str, params: dict, timeout: float | None = None) -> CommandResult:
        """Send a command via file IPC and wait for result.

        On timeout, auto-reinitializes (re-detects AutoCAD window) and retries once.
        This handles AutoCAD restarts where the window handle becomes stale.
        """
        async with self._lock:
            result = await self._dispatch_unlocked(command, params, timeout=timeout)
            if not result.ok and result.error and "Timeout" in result.error:
                old_hwnd = self._hwnd
                new_hwnd = find_autocad_window()
                if new_hwnd and new_hwnd != old_hwnd:
                    log.info("auto_reinit", old_hwnd=old_hwnd, new_hwnd=new_hwnd)
                    self._hwnd = new_hwnd
                    self._command_hwnd = self._find_command_line_hwnd()
                    if self._screenshot_provider:
                        try:
                            from autocad_mcp.screenshot import Win32ScreenshotProvider
                            self._screenshot_provider = Win32ScreenshotProvider(self._hwnd)
                        except Exception:
                            pass
                    self._cleanup_stale_files()
                    result = await self._dispatch_unlocked(command, params, timeout=timeout)
            return result

    async def _dispatch_unlocked(self, command: str, params: dict, timeout: float | None = None) -> CommandResult:
        """Core IPC logic (must be called under _lock)."""
        effective_timeout = timeout if timeout is not None else TIMEOUT
        request_id = uuid.uuid4().hex[:12]
        cmd_file = self._ipc_dir / f"autocad_mcp_cmd_{request_id}.json"
        result_file = self._ipc_dir / f"autocad_mcp_result_{request_id}.json"
        tmp_file = cmd_file.with_suffix(".tmp")

        try:
            # Strip None values — the simple LISP JSON parser can't handle null
            clean_params = {k: v for k, v in params.items() if v is not None}
            # Atomic write: write to .tmp, then rename
            payload = {
                "request_id": request_id,
                "command": command,
                "params": clean_params,
                "ts": time.time(),
            }
            tmp_file.write_text(json.dumps(payload), encoding="utf-8")
            tmp_file.rename(cmd_file)

            # Type the fixed dispatch trigger
            self._type_dispatch_trigger()

            # Poll for result
            deadline = time.time() + effective_timeout
            while time.time() < deadline:
                if result_file.exists():
                    try:
                        # AutoCAD LISP writes files in Windows-1252 encoding;
                        # try UTF-8 first (covers ASCII), fall back to cp1252
                        try:
                            text = result_file.read_text(encoding="utf-8")
                        except UnicodeDecodeError:
                            text = result_file.read_text(encoding="cp1252")
                        data = json.loads(text)
                        # Verify request_id matches
                        if data.get("request_id") == request_id:
                            return CommandResult(
                                ok=data.get("ok", False),
                                payload=data.get("payload"),
                                error=data.get("error"),
                            )
                    except (json.JSONDecodeError, OSError):
                        pass  # File may be partially written, retry
                await asyncio.sleep(POLL_INTERVAL)

            return CommandResult(ok=False, error=f"Timeout waiting for result (request_id={request_id})")

        finally:
            # Cleanup
            for f in (cmd_file, result_file, tmp_file):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass

    def _find_command_line_hwnd(self) -> int | None:
        """Find AutoCAD's MDIClient child window for command routing."""
        if sys.platform != "win32" or not self._hwnd:
            return None
        try:
            import win32gui

            mdi_client: list[int] = []

            def cb(child_hwnd, _):
                if win32gui.GetClassName(child_hwnd) == "MDIClient":
                    mdi_client.append(child_hwnd)
                    return False  # stop enumeration
                return True

            win32gui.EnumChildWindows(self._hwnd, cb, None)
            return mdi_client[0] if mdi_client else None
        except Exception:
            return None

    def _type_dispatch_trigger(self):
        """Post '(c:mcp-dispatch)' + Enter via WM_CHAR to MDIClient — no focus steal.

        Sends ESC keystrokes first to cancel any stale pending command
        (e.g. from a previous timeout leaving AutoCAD in a command prompt).
        """
        try:
            import ctypes

            WM_CHAR = 0x0102
            WM_KEYDOWN = 0x0100
            WM_KEYUP = 0x0101
            VK_ESCAPE = 0x1B
            target = self._command_hwnd or self._hwnd
            post = ctypes.windll.user32.PostMessageW

            # Cancel any pending command (2x ESC for nested commands)
            for _ in range(2):
                post(target, WM_KEYDOWN, VK_ESCAPE, 0)
                post(target, WM_KEYUP, VK_ESCAPE, 0)
            time.sleep(0.05)

            for ch in "(c:mcp-dispatch)":
                post(target, WM_CHAR, ord(ch), 0)
            # Enter = carriage return
            post(target, WM_CHAR, 0x0D, 0)
            time.sleep(0.05)
        except Exception as e:
            log.error("dispatch_trigger_failed", error=str(e))

    def _cleanup_stale_files(self):
        """Remove stale IPC files from previous sessions."""
        try:
            now = time.time()
            for pattern in ("autocad_mcp_*.json", "autocad_mcp_*.tmp", "autocad_mcp_lisp_*.lsp"):
                for f in self._ipc_dir.glob(pattern):
                    if now - f.stat().st_mtime > STALE_THRESHOLD:
                        f.unlink(missing_ok=True)
        except OSError:
            pass

    # --- Drawing management ---

    async def drawing_info(self) -> CommandResult:
        return await self._dispatch("drawing-info", {})

    async def drawing_save(self, path: str | None = None) -> CommandResult:
        return await self._dispatch("drawing-save", {"path": path})

    async def drawing_save_as_dxf(
        self, path: str, version: str | None = None,
    ) -> CommandResult:
        if version is not None:
            return CommandResult(ok=False, error="File IPC does not support selecting a DXF version")
        destination = Path(path)
        if destination.suffix.lower() != ".dxf" or destination.exists():
            return CommandResult(ok=False, error="Choose a new destination with a .dxf extension")
        return await self._dispatch("drawing-save-as-dxf", {"path": path})

    async def drawing_create(self, name: str | None = None) -> CommandResult:
        return await self._dispatch("drawing-create", {"name": name})

    async def drawing_purge(self) -> CommandResult:
        return await self._dispatch("drawing-purge", {})

    async def drawing_plot_pdf(self, path: str) -> CommandResult:
        return await self._dispatch("drawing-plot-pdf", {"path": path})

    async def drawing_get_variables(self, names: list[str] | None = None) -> CommandResult:
        if names:
            # Strip $ prefix for AutoCAD compatibility (ezdxf uses $ACADVER, AutoCAD uses ACADVER)
            clean_names = [n.lstrip("$") for n in names]
            names_str = ";".join(clean_names)
        else:
            names_str = ""
        return await self._dispatch("drawing-get-variables", {"names_str": names_str})

    async def drawing_open(self, path: str) -> CommandResult:
        return await self._dispatch("drawing-open", {"path": path})

    # --- Undo / Redo ---

    async def undo(self) -> CommandResult:
        return await self._dispatch("undo", {})

    async def redo(self) -> CommandResult:
        return await self._dispatch("redo", {})

    # --- Freehand LISP execution ---

    async def execute_lisp(self, code: str) -> CommandResult:
        """Execute arbitrary AutoLISP code via temp file.

        File persists for session; cleaned up by _cleanup_stale_files().
        """
        request_id = uuid.uuid4().hex[:12]
        code_file = self._ipc_dir / f"autocad_mcp_lisp_{request_id}.lsp"
        code_file.write_text(code, encoding="utf-8")
        return await self._dispatch("execute-lisp", {
            "code_file": str(code_file).replace("\\", "/")
        })

    # --- Entity operations ---

    async def create_line(self, x1, y1, x2, y2, layer=None) -> CommandResult:
        return await self._dispatch("create-line", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "layer": layer})

    async def create_circle(self, cx, cy, radius, layer=None) -> CommandResult:
        return await self._dispatch("create-circle", {"cx": cx, "cy": cy, "radius": radius, "layer": layer})

    async def create_polyline(self, points, closed=False, layer=None) -> CommandResult:
        pts_str = ";".join(f"{p[0]},{p[1]}" for p in points)
        return await self._dispatch("create-polyline", {
            "points_str": pts_str, "closed": "1" if closed else "0", "layer": layer
        })

    async def create_rectangle(self, x1, y1, x2, y2, layer=None) -> CommandResult:
        return await self._dispatch("create-rectangle", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "layer": layer})

    async def create_arc(self, cx, cy, radius, start_angle, end_angle, layer=None) -> CommandResult:
        return await self._dispatch("create-arc", {"cx": cx, "cy": cy, "radius": radius, "start_angle": start_angle, "end_angle": end_angle, "layer": layer})

    async def create_ellipse(self, cx, cy, major_x, major_y, ratio, layer=None) -> CommandResult:
        return await self._dispatch("create-ellipse", {"cx": cx, "cy": cy, "major_x": major_x, "major_y": major_y, "ratio": ratio, "layer": layer})

    async def create_mtext(self, x, y, width, text, height=2.5, layer=None) -> CommandResult:
        return await self._dispatch("create-mtext", {"x": x, "y": y, "width": width, "text": text, "height": height, "layer": layer})

    async def create_hatch(self, entity_id, pattern="ANSI31") -> CommandResult:
        return await self._dispatch("create-hatch", {"entity_id": entity_id, "pattern": pattern})

    async def entity_list(self, layer=None) -> CommandResult:
        return await self._dispatch("entity-list", {"layer": layer})

    async def entity_count(self, layer=None) -> CommandResult:
        return await self._dispatch("entity-count", {"layer": layer})

    async def entity_get(self, entity_id) -> CommandResult:
        return await self._dispatch("entity-get", {"entity_id": entity_id})

    async def entity_erase(self, entity_id) -> CommandResult:
        return await self._dispatch("entity-erase", {"entity_id": entity_id})

    async def entity_copy(self, entity_id, dx, dy) -> CommandResult:
        return await self._dispatch("entity-copy", {"entity_id": entity_id, "dx": dx, "dy": dy})

    async def entity_move(self, entity_id, dx, dy) -> CommandResult:
        return await self._dispatch("entity-move", {"entity_id": entity_id, "dx": dx, "dy": dy})

    async def entity_rotate(self, entity_id, cx, cy, angle) -> CommandResult:
        return await self._dispatch("entity-rotate", {"entity_id": entity_id, "cx": cx, "cy": cy, "angle": angle})

    async def entity_scale(self, entity_id, cx, cy, factor) -> CommandResult:
        return await self._dispatch("entity-scale", {"entity_id": entity_id, "cx": cx, "cy": cy, "factor": factor})

    async def entity_mirror(self, entity_id, x1, y1, x2, y2) -> CommandResult:
        return await self._dispatch("entity-mirror", {"entity_id": entity_id, "x1": x1, "y1": y1, "x2": x2, "y2": y2})

    async def entity_offset(self, entity_id, distance) -> CommandResult:
        return await self._dispatch("entity-offset", {"entity_id": entity_id, "distance": distance})

    async def entity_array(self, entity_id, rows, cols, row_dist, col_dist) -> CommandResult:
        return await self._dispatch("entity-array", {"entity_id": entity_id, "rows": rows, "cols": cols, "row_dist": row_dist, "col_dist": col_dist})

    async def entity_fillet(self, entity_id1, entity_id2, radius) -> CommandResult:
        return await self._dispatch("entity-fillet", {"id1": entity_id1, "id2": entity_id2, "radius": radius})

    async def entity_chamfer(self, entity_id1, entity_id2, dist1, dist2) -> CommandResult:
        return await self._dispatch("entity-chamfer", {"id1": entity_id1, "id2": entity_id2, "dist1": dist1, "dist2": dist2})

    # --- Layer operations ---

    async def layer_list(self) -> CommandResult:
        return await self._dispatch("layer-list", {})

    async def layer_create(self, name, color="white", linetype="CONTINUOUS") -> CommandResult:
        return await self._dispatch("layer-create", {"name": name, "color": color, "linetype": linetype})

    async def layer_set_current(self, name) -> CommandResult:
        return await self._dispatch("layer-set-current", {"name": name})

    async def layer_set_properties(self, name, color=None, linetype=None, lineweight=None) -> CommandResult:
        return await self._dispatch("layer-set-properties", {"name": name, "color": color, "linetype": linetype, "lineweight": lineweight})

    async def layer_freeze(self, name) -> CommandResult:
        return await self._dispatch("layer-freeze", {"name": name})

    async def layer_thaw(self, name) -> CommandResult:
        return await self._dispatch("layer-thaw", {"name": name})

    async def layer_lock(self, name) -> CommandResult:
        return await self._dispatch("layer-lock", {"name": name})

    async def layer_unlock(self, name) -> CommandResult:
        return await self._dispatch("layer-unlock", {"name": name})

    # --- Block operations ---

    async def block_list(self) -> CommandResult:
        return await self._dispatch("block-list", {})

    async def block_insert(self, name, x, y, scale=1.0, rotation=0.0, block_id=None) -> CommandResult:
        return await self._dispatch("block-insert", {"name": name, "x": x, "y": y, "scale": scale, "rotation": rotation, "block_id": block_id})

    async def block_insert_with_attributes(self, name, x, y, scale=1.0, rotation=0.0, attributes=None) -> CommandResult:
        return await self._dispatch("block-insert-with-attributes", {"name": name, "x": x, "y": y, "scale": scale, "rotation": rotation, "attributes": attributes or {}})

    async def block_get_attributes(self, entity_id) -> CommandResult:
        return await self._dispatch("block-get-attributes", {"entity_id": entity_id})

    async def block_update_attribute(self, entity_id, tag, value) -> CommandResult:
        return await self._dispatch("block-update-attribute", {"entity_id": entity_id, "tag": tag, "value": value})

    async def block_define(self, name, entities) -> CommandResult:
        return await self._dispatch("block-define", {"name": name, "entities": entities})

    # --- Annotation ---

    async def create_text(self, x, y, text, height=2.5, rotation=0.0, layer=None) -> CommandResult:
        return await self._dispatch("create-text", {"x": x, "y": y, "text": text, "height": height, "rotation": rotation, "layer": layer})

    async def create_dimension_linear(self, x1, y1, x2, y2, dim_x, dim_y) -> CommandResult:
        return await self._dispatch("create-dimension-linear", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "dim_x": dim_x, "dim_y": dim_y})

    async def create_dimension_aligned(self, x1, y1, x2, y2, offset) -> CommandResult:
        return await self._dispatch("create-dimension-aligned", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "offset": offset})

    async def create_dimension_angular(self, cx, cy, x1, y1, x2, y2) -> CommandResult:
        return await self._dispatch("create-dimension-angular", {"cx": cx, "cy": cy, "x1": x1, "y1": y1, "x2": x2, "y2": y2})

    async def create_dimension_radius(self, cx, cy, radius, angle) -> CommandResult:
        return await self._dispatch("create-dimension-radius", {"cx": cx, "cy": cy, "radius": radius, "angle": angle})

    async def create_leader(self, points, text) -> CommandResult:
        pts_str = ";".join(f"{p[0]},{p[1]}" for p in points)
        return await self._dispatch("create-leader", {"points_str": pts_str, "text": text})

    # --- P&ID ---

    async def pid_setup_layers(self) -> CommandResult:
        return await self._dispatch("pid-setup-layers", {})

    async def pid_insert_symbol(self, category, symbol, x, y, scale=1.0, rotation=0.0) -> CommandResult:
        return await self._dispatch("pid-insert-symbol", {"category": category, "symbol": symbol, "x": x, "y": y, "scale": scale, "rotation": rotation})

    async def pid_list_symbols(self, category) -> CommandResult:
        return await self._dispatch("pid-list-symbols", {"category": category})

    async def pid_draw_process_line(self, x1, y1, x2, y2) -> CommandResult:
        return await self._dispatch("pid-draw-process-line", {"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    async def pid_connect_equipment(self, x1, y1, x2, y2) -> CommandResult:
        return await self._dispatch("pid-connect-equipment", {"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    async def pid_add_flow_arrow(self, x, y, rotation=0.0) -> CommandResult:
        return await self._dispatch("pid-add-flow-arrow", {"x": x, "y": y, "rotation": rotation})

    async def pid_add_equipment_tag(self, x, y, tag, description="") -> CommandResult:
        return await self._dispatch("pid-add-equipment-tag", {"x": x, "y": y, "tag": tag, "description": description})

    async def pid_add_line_number(self, x, y, line_num, spec) -> CommandResult:
        return await self._dispatch("pid-add-line-number", {"x": x, "y": y, "line_num": line_num, "spec": spec})

    async def pid_insert_valve(self, x, y, valve_type, rotation=0.0, attributes=None) -> CommandResult:
        return await self._dispatch("pid-insert-valve", {"x": x, "y": y, "valve_type": valve_type, "rotation": rotation, "attributes": attributes or {}})

    async def pid_insert_instrument(self, x, y, instrument_type, rotation=0.0, tag_id="", range_value="") -> CommandResult:
        return await self._dispatch("pid-insert-instrument", {"x": x, "y": y, "instrument_type": instrument_type, "rotation": rotation, "tag_id": tag_id, "range_value": range_value})

    async def pid_insert_pump(self, x, y, pump_type, rotation=0.0, attributes=None) -> CommandResult:
        return await self._dispatch("pid-insert-pump", {"x": x, "y": y, "pump_type": pump_type, "rotation": rotation, "attributes": attributes or {}})

    async def pid_insert_tank(self, x, y, tank_type, scale=1.0, attributes=None) -> CommandResult:
        return await self._dispatch("pid-insert-tank", {"x": x, "y": y, "tank_type": tank_type, "scale": scale, "attributes": attributes or {}})

    # --- Query operations ---
    # TODO: Implement LISP commands for query-entity-properties, query-entity-geometry,
    # query-drawing-summary, query-layer-summary in mcp_dispatch.lsp

    async def query_entity_properties(self, entity_id) -> CommandResult:
        return await self._dispatch("query-entity-properties", {"entity_id": entity_id})

    async def query_entity_geometry(self, entity_id) -> CommandResult:
        return await self._dispatch("query-entity-geometry", {"entity_id": entity_id})

    async def query_drawing_summary(self) -> CommandResult:
        return await self._dispatch("query-drawing-summary", {})

    async def query_layer_summary(self, layer) -> CommandResult:
        return await self._dispatch("query-layer-summary", {"layer": layer})

    # --- Search operations ---
    # TODO: Implement LISP commands for search-text, search-by-attribute,
    # search-by-window, search-by-proximity, search-by-type-and-layer in mcp_dispatch.lsp

    async def search_text(self, pattern, case_sensitive=False) -> CommandResult:
        return await self._dispatch("search-text", {
            "pattern": pattern,
            "case_sensitive": "1" if case_sensitive else "0",
        })

    async def search_by_attribute(self, tag=None, value=None) -> CommandResult:
        return await self._dispatch("search-by-attribute", {"tag": tag, "value": value})

    async def search_by_window(self, x1, y1, x2, y2) -> CommandResult:
        return await self._dispatch("search-by-window", {"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    async def search_by_proximity(self, x, y, radius) -> CommandResult:
        return await self._dispatch("search-by-proximity", {"x": x, "y": y, "radius": radius})

    async def search_by_type_and_layer(self, entity_type=None, layer=None, color=None) -> CommandResult:
        return await self._dispatch("search-by-type-and-layer", {
            "entity_type": entity_type,
            "layer": layer,
            "color": color,
        })

    # --- Geometry operations ---
    # TODO: Implement LISP commands for geometry-distance, geometry-length,
    # geometry-area, geometry-bounding-box, geometry-polyline-info in mcp_dispatch.lsp

    async def geometry_distance(self, x1, y1, x2, y2) -> CommandResult:
        return await self._dispatch("geometry-distance", {"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    async def geometry_length(self, entity_id) -> CommandResult:
        return await self._dispatch("geometry-length", {"entity_id": entity_id})

    async def geometry_area(self, entity_id) -> CommandResult:
        return await self._dispatch("geometry-area", {"entity_id": entity_id})

    async def geometry_bounding_box(self, entity_id=None, layer=None) -> CommandResult:
        return await self._dispatch("geometry-bounding-box", {"entity_id": entity_id, "layer": layer})

    async def geometry_polyline_info(self, entity_id) -> CommandResult:
        return await self._dispatch("geometry-polyline-info", {"entity_id": entity_id})

    # --- Bulk operations ---
    # TODO: Implement LISP commands for bulk-set-property, bulk-erase in mcp_dispatch.lsp

    async def bulk_set_property(self, handles, property_name, value) -> CommandResult:
        handles_str = ";".join(handles)
        return await self._dispatch("bulk-set-property", {
            "handles_str": handles_str,
            "property_name": property_name,
            "value": value,
        })

    async def bulk_erase(self, handles) -> CommandResult:
        handles_str = ";".join(handles)
        return await self._dispatch("bulk-erase", {"handles_str": handles_str})

    # --- Export ---
    # TODO: Implement LISP command for export-entity-data in mcp_dispatch.lsp

    async def export_entity_data(self, layer=None, entity_type=None) -> CommandResult:
        return await self._dispatch("export-entity-data", {"layer": layer, "entity_type": entity_type})

    # --- Select / Filter ---

    async def select_filter(self, entity_type=None, layer=None, color=None,
                            x1=None, y1=None, x2=None, y2=None) -> CommandResult:
        return await self._dispatch("select-filter", {
            "entity_type": entity_type, "layer": layer, "color": color,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        })

    async def bulk_move(self, handles, dx, dy) -> CommandResult:
        return await self._dispatch("bulk-move", {
            "handles_str": ";".join(handles), "dx": dx, "dy": dy,
        })

    async def bulk_copy(self, handles, dx, dy) -> CommandResult:
        return await self._dispatch("bulk-copy", {
            "handles_str": ";".join(handles), "dx": dx, "dy": dy,
        })

    async def find_replace_text(self, find, replace, layer=None) -> CommandResult:
        return await self._dispatch("find-replace-text", {
            "find": find, "replace": replace, "layer": layer,
        })

    # --- Entity Modification ---

    async def entity_set_property(self, entity_id, property_name, value) -> CommandResult:
        return await self._dispatch("entity-set-property", {
            "entity_id": entity_id, "property_name": property_name, "value": value,
        })

    async def entity_set_text(self, entity_id, text) -> CommandResult:
        return await self._dispatch("entity-set-text", {
            "entity_id": entity_id, "text": text,
        })

    # --- View Enhancements ---

    async def zoom_center(self, x, y, height) -> CommandResult:
        return await self._dispatch("zoom-center", {"x": x, "y": y, "height": height})

    async def layer_visibility(self, name, visible) -> CommandResult:
        return await self._dispatch("layer-visibility", {
            "name": name, "visible": "1" if visible else "0",
        })

    # --- Validate ---

    async def validate_layer_standards(self, allowed_layers) -> CommandResult:
        return await self._dispatch("validate-layer-standards", {
            "allowed_layers": ";".join(allowed_layers),
        })

    async def validate_duplicates(self, tolerance=0.001) -> CommandResult:
        return await self._dispatch("validate-duplicates", {"tolerance": tolerance})

    async def validate_zero_length(self) -> CommandResult:
        return await self._dispatch("validate-zero-length", {})

    async def validate_qc_report(self, allowed_layers=None) -> CommandResult:
        params = {}
        if allowed_layers:
            params["allowed_layers"] = ";".join(allowed_layers)
        return await self._dispatch("validate-qc-report", params)

    # --- Export / Reporting ---

    async def export_bom(self, block_names=None) -> CommandResult:
        params = {}
        if block_names:
            params["block_names"] = ";".join(block_names)
        return await self._dispatch("export-bom", params)

    async def export_data_extract(self, entity_type=None, layer=None, properties=None) -> CommandResult:
        params = {"entity_type": entity_type, "layer": layer}
        if properties:
            params["properties"] = ";".join(properties)
        return await self._dispatch("export-data-extract", params)

    async def export_layer_report(self) -> CommandResult:
        return await self._dispatch("export-layer-report", {})

    async def export_block_count(self) -> CommandResult:
        return await self._dispatch("export-block-count", {})

    async def export_drawing_statistics(self) -> CommandResult:
        return await self._dispatch("export-drawing-statistics", {})

    # --- Extended Query ---

    async def query_text_styles(self) -> CommandResult:
        return await self._dispatch("query-text-styles", {})

    async def query_dimension_styles(self) -> CommandResult:
        return await self._dispatch("query-dimension-styles", {})

    async def query_linetypes(self) -> CommandResult:
        return await self._dispatch("query-linetypes", {})

    async def query_block_tree(self) -> CommandResult:
        return await self._dispatch("query-block-tree", {})

    async def query_drawing_metadata(self) -> CommandResult:
        return await self._dispatch("query-drawing-metadata", {})

    # --- Extended Search ---

    async def search_by_block_name(self, block_name) -> CommandResult:
        return await self._dispatch("search-by-block-name", {"block_name": block_name})

    async def search_by_handle_list(self, handles) -> CommandResult:
        return await self._dispatch("search-by-handle-list", {"handles_str": ";".join(handles)})

    # --- Equipment Find / Inspect ---

    async def equipment_find(self, pattern, case_sensitive=False, search_scope="all",
                             zoom_to_first=True, zoom_height=600.0, max_results=50) -> CommandResult:
        return await self._dispatch("equipment-find", {
            "pattern": pattern,
            "case_sensitive": "1" if case_sensitive else "0",
            "search_scope": search_scope,
            "zoom_to_first": "1" if zoom_to_first else "0",
            "zoom_height": zoom_height,
            "max_results": max_results,
        }, timeout=60.0)

    async def equipment_inspect(self, x, y, view_width=600.0, view_height=600.0,
                                infer_center=True, handle=None) -> CommandResult:
        return await self._dispatch("equipment-inspect", {
            "x": x, "y": y,
            "view_width": view_width, "view_height": view_height,
            "infer_center": "1" if infer_center else "0",
            "handle": handle,
        }, timeout=30.0)

    # --- Deep Text Search ---

    async def find_text(self, pattern, case_sensitive=False, max_results=50,
                        zoom_to_first=True, zoom_height=600.0) -> CommandResult:
        return await self._dispatch("find-text", {
            "pattern": pattern,
            "case_sensitive": "1" if case_sensitive else "0",
            "max_results": max_results,
            "zoom_to_first": "1" if zoom_to_first else "0",
            "zoom_height": zoom_height,
        }, timeout=120.0)

    # --- Equipment Tag Placement ---

    async def place_equipment_tag(self, cx, cy, cz=0.0, tag="", cube_size=24.0,
                                  direction="right", text_height=8.0) -> CommandResult:
        return await self._dispatch("place-equipment-tag", {
            "cx": cx, "cy": cy, "cz": cz,
            "tag": tag, "cube_size": cube_size,
            "direction": direction, "text_height": text_height,
        }, timeout=30.0)

    async def batch_find_and_tag(self, tags, cube_size=24.0, direction="right",
                                  text_height=8.0) -> CommandResult:
        return await self._dispatch("batch-find-and-tag", {
            "tags": ";".join(tags),
            "cube_size": cube_size,
            "direction": direction,
            "text_height": text_height,
        }, timeout=300.0)

    # --- Extended Entity ---

    async def entity_explode(self, entity_id) -> CommandResult:
        return await self._dispatch("entity-explode", {"entity_id": entity_id})

    async def entity_join(self, entity_ids) -> CommandResult:
        return await self._dispatch("entity-join", {"entity_ids": ";".join(entity_ids)})

    async def entity_extend(self, entity_id, boundary_id) -> CommandResult:
        return await self._dispatch("entity-extend", {"entity_id": entity_id, "boundary_id": boundary_id})

    async def entity_trim(self, entity_id, boundary_id) -> CommandResult:
        return await self._dispatch("entity-trim", {"entity_id": entity_id, "boundary_id": boundary_id})

    async def entity_break_at(self, entity_id, x, y) -> CommandResult:
        return await self._dispatch("entity-break-at", {"entity_id": entity_id, "x": x, "y": y})

    # --- Extended Validate ---

    async def validate_text_standards(self, allowed_styles=None, allowed_heights=None) -> CommandResult:
        params = {}
        if allowed_styles: params["allowed_styles"] = ";".join(allowed_styles)
        if allowed_heights: params["allowed_heights"] = ";".join(str(h) for h in allowed_heights)
        return await self._dispatch("validate-text-standards", params)

    async def validate_orphaned_entities(self) -> CommandResult:
        return await self._dispatch("validate-orphaned-entities", {})

    async def validate_attribute_completeness(self, required_tags=None) -> CommandResult:
        params = {}
        if required_tags: params["required_tags"] = ";".join(required_tags)
        return await self._dispatch("validate-attribute-completeness", params)

    async def validate_connectivity(self, layer=None, tolerance=0.01) -> CommandResult:
        return await self._dispatch("validate-connectivity", {"layer": layer, "tolerance": tolerance})

    # --- Extended Select ---

    async def find_replace_attribute(self, tag, find, replace) -> CommandResult:
        return await self._dispatch("find-replace-attribute", {"tag": tag, "find": find, "replace": replace})

    async def layer_rename(self, old_name, new_name) -> CommandResult:
        return await self._dispatch("layer-rename", {"old_name": old_name, "new_name": new_name})

    async def layer_merge(self, source_layer, target_layer) -> CommandResult:
        return await self._dispatch("layer-merge", {"source_layer": source_layer, "target_layer": target_layer})

    # --- Enhanced View ---

    async def zoom_scale(self, factor) -> CommandResult:
        return await self._dispatch("zoom-scale", {"factor": factor})

    async def pan(self, dx, dy) -> CommandResult:
        return await self._dispatch("pan", {"dx": dx, "dy": dy})

    # --- Enhanced Drawing ---

    async def drawing_audit(self, fix=False) -> CommandResult:
        return await self._dispatch("drawing-audit", {"fix": "1" if fix else "0"})

    async def drawing_units(self, units=None) -> CommandResult:
        params = {}
        if units is not None: params["units"] = units
        return await self._dispatch("drawing-units", params)

    async def drawing_limits(self, x1=None, y1=None, x2=None, y2=None) -> CommandResult:
        return await self._dispatch("drawing-limits", {"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    async def drawing_wblock(self, handles, path) -> CommandResult:
        return await self._dispatch("drawing-wblock", {"handles_str": ";".join(handles), "path": path})

    # --- XREF ---

    async def xref_list(self) -> CommandResult:
        return await self._dispatch("xref-list", {})

    async def xref_attach(self, path, x=0, y=0, scale=1.0, overlay=False) -> CommandResult:
        return await self._dispatch("xref-attach", {"path": path, "x": x, "y": y, "scale": scale, "overlay": "1" if overlay else "0"})

    async def xref_detach(self, name) -> CommandResult:
        return await self._dispatch("xref-detach", {"name": name})

    async def xref_reload(self, name) -> CommandResult:
        return await self._dispatch("xref-reload", {"name": name})

    async def xref_bind(self, name, insert=False) -> CommandResult:
        return await self._dispatch("xref-bind", {"name": name, "insert": "1" if insert else "0"})

    async def xref_path_update(self, name, new_path) -> CommandResult:
        return await self._dispatch("xref-path-update", {"name": name, "new_path": new_path})

    async def xref_query_entities(self, name, entity_type=None, layer=None) -> CommandResult:
        return await self._dispatch("xref-query-entities", {"name": name, "entity_type": entity_type, "layer": layer})

    # --- Layout ---

    async def layout_list(self) -> CommandResult:
        return await self._dispatch("layout-list", {})

    async def layout_create(self, name) -> CommandResult:
        return await self._dispatch("layout-create", {"name": name})

    async def layout_switch(self, name) -> CommandResult:
        return await self._dispatch("layout-switch", {"name": name})

    async def layout_delete(self, name) -> CommandResult:
        return await self._dispatch("layout-delete", {"name": name})

    async def layout_viewport_create(self, x, y, width, height, scale=1.0) -> CommandResult:
        return await self._dispatch("layout-viewport-create", {"x": x, "y": y, "width": width, "height": height, "scale": scale})

    async def layout_viewport_set_scale(self, viewport_id, scale) -> CommandResult:
        return await self._dispatch("layout-viewport-set-scale", {"viewport_id": viewport_id, "scale": scale})

    async def layout_viewport_lock(self, viewport_id, lock=True) -> CommandResult:
        return await self._dispatch("layout-viewport-lock", {"viewport_id": viewport_id, "lock": "1" if lock else "0"})

    async def layout_page_setup(self, name, paper_size=None, orientation=None) -> CommandResult:
        return await self._dispatch("layout-page-setup", {"name": name, "paper_size": paper_size, "orientation": orientation})

    async def layout_titleblock_fill(self, layout_name, attributes=None) -> CommandResult:
        # Serialize attributes dict as key=value pairs separated by |
        attrs_str = None
        if attributes:
            attrs_str = "|".join(f"{k}={v}" for k, v in attributes.items())
        return await self._dispatch("layout-titleblock-fill", {"layout_name": layout_name, "attributes_str": attrs_str})

    async def layout_batch_plot(self, layouts=None, output_path=None) -> CommandResult:
        params = {"output_path": output_path}
        if layouts: params["layouts_str"] = ";".join(layouts)
        return await self._dispatch("layout-batch-plot", params)

    # --- Electrical ---
    # Electrical operations that need AutoCAD are dispatched to LISP
    # Pure calculation operations are handled in the backend directly

    async def electrical_nec_lookup(self, table, parameters=None) -> CommandResult:
        params = {"table": table}
        if parameters:
            params.update(parameters)
        return await self._dispatch("electrical-nec-lookup", params)

    async def electrical_voltage_drop(self, voltage, current, wire_gauge, length, phase=1, power_factor=1.0) -> CommandResult:
        return await self._dispatch("electrical-voltage-drop", {
            "voltage": voltage, "current": current, "wire_gauge": wire_gauge,
            "length": length, "phase": int(phase), "power_factor": power_factor,
        })

    async def electrical_conduit_fill(self, conduit_size, conduit_type, wire_gauges=None) -> CommandResult:
        params = {"conduit_size": conduit_size, "conduit_type": conduit_type}
        if wire_gauges: params["wire_gauges"] = ";".join(wire_gauges)
        return await self._dispatch("electrical-conduit-fill", params)

    async def electrical_load_calc(self, devices=None) -> CommandResult:
        params = {}
        if devices:
            total_watts = sum(d.get("watts", 0) for d in devices)
            voltage = devices[0].get("voltage", 120) if devices else 120
            pf = devices[0].get("power_factor", 1.0) if devices else 1.0
            params = {"total_watts": total_watts, "voltage": voltage, "power_factor": pf}
        return await self._dispatch("electrical-load-calc", params)

    async def electrical_symbol_insert(self, symbol_type, x, y, scale=1.0, rotation=0.0, layer=None) -> CommandResult:
        return await self._dispatch("electrical-symbol-insert", {
            "symbol_type": symbol_type, "x": x, "y": y,
            "scale": scale, "rotation": rotation, "layer": layer,
        })

    async def electrical_circuit_trace(self, start_entity, layer=None) -> CommandResult:
        return await self._dispatch("electrical-circuit-trace", {"start_entity": start_entity, "layer": layer})

    async def electrical_panel_schedule_gen(self, panel_block, x=0, y=0) -> CommandResult:
        return await self._dispatch("electrical-panel-schedule-gen", {"panel_block": panel_block, "x": x, "y": y})

    async def electrical_wire_number_assign(self, layer, prefix="W", start_num=1) -> CommandResult:
        return await self._dispatch("electrical-wire-number-assign", {"layer": layer, "prefix": prefix, "start_num": start_num})

    # --- MagiCAD ---

    async def magicad_status(self) -> CommandResult:
        return await self._dispatch("magicad-status", {})

    async def magicad_run(self, command: str, args: str | None = None) -> CommandResult:
        params = {"command": command}
        if args:
            params["args"] = args
        return await self._dispatch("magicad-run", params, timeout=30)

    async def magicad_update_drawing(self, flags: str | None = None) -> CommandResult:
        params = {}
        if flags:
            params["flags"] = flags
        return await self._dispatch("magicad-update-drawing", params, timeout=60)

    async def magicad_cleanup(self, options: str | None = None) -> CommandResult:
        params = {}
        if options:
            params["options"] = options
        return await self._dispatch("magicad-cleanup", params, timeout=60)

    async def magicad_ifc_export(self, mode: str = "current") -> CommandResult:
        return await self._dispatch("magicad-ifc-export", {"mode": mode}, timeout=120)

    async def magicad_view_mode(self, mode: str, type: str = "D") -> CommandResult:
        return await self._dispatch("magicad-view-mode", {"mode": mode, "type": type})

    async def magicad_change_storey(self, storey: str) -> CommandResult:
        return await self._dispatch("magicad-change-storey", {"storey": storey})

    async def magicad_section_update(self) -> CommandResult:
        return await self._dispatch("magicad-section-update", {}, timeout=60)

    async def magicad_fix_errors(self) -> CommandResult:
        return await self._dispatch("magicad-fix-errors", {}, timeout=30)

    async def magicad_show_all(self) -> CommandResult:
        return await self._dispatch("magicad-show-all", {})

    async def magicad_clear_garbage(self) -> CommandResult:
        return await self._dispatch("magicad-clear-garbage", {})

    async def magicad_disconnect_project(self) -> CommandResult:
        return await self._dispatch("magicad-disconnect-project", {})

    async def magicad_list_commands(self) -> CommandResult:
        return await self._dispatch("magicad-list-commands", {}, timeout=30)

    async def magicad_project_info(self) -> CommandResult:
        result = await self._dispatch("magicad-project-info", {})
        if not result.ok or not result.payload:
            return result
        # Enrich with file-system search for .qpd/.epj project files
        import pathlib
        data = result.payload if isinstance(result.payload, dict) else {}
        dwgprefix = data.get("dwgprefix", "")
        if dwgprefix:
            p = pathlib.Path(dwgprefix)
            project_files: list[str] = []
            for _ in range(5):  # walk up 5 levels
                for ext in ("*.qpd", "*.epj", "*.mep", "*.mrd"):
                    project_files.extend(str(f) for f in p.glob(ext))
                p = p.parent
            if project_files:
                data["project_files"] = project_files
        return CommandResult(ok=True, payload=data)

    # --- View ---

    async def zoom_extents(self) -> CommandResult:
        return await self._dispatch("zoom-extents", {})

    async def zoom_window(self, x1, y1, x2, y2) -> CommandResult:
        return await self._dispatch("zoom-window", {"x1": x1, "y1": y1, "x2": x2, "y2": y2})

    async def get_screenshot(self) -> CommandResult:
        if self._screenshot_provider:
            data = self._screenshot_provider.capture()
            if data:
                return CommandResult(ok=True, payload=data)
        return CommandResult(ok=False, error="Screenshot capture failed")
