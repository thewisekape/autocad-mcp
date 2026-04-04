"""Abstract base class for AutoCAD backends + CommandResult envelope."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommandResult:
    """Structured result envelope from backend operations."""

    ok: bool
    payload: Any = None
    error: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            d["payload"] = self.payload
        else:
            d["error"] = self.error
        return d


@dataclass
class BackendCapabilities:
    """Declares what a backend supports."""

    can_read_drawing: bool = False
    can_modify_entities: bool = False
    can_create_entities: bool = True
    can_screenshot: bool = False
    can_save: bool = False
    can_plot_pdf: bool = False
    can_zoom: bool = False
    can_query_entities: bool = False
    can_file_operations: bool = False
    can_undo: bool = False


class AutoCADBackend(ABC):
    """Abstract interface for AutoCAD operation backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier: 'file_ipc' or 'ezdxf'."""

    @property
    @abstractmethod
    def capabilities(self) -> BackendCapabilities:
        """Declare supported operations."""

    @abstractmethod
    async def initialize(self) -> CommandResult:
        """Initialize the backend. Called once at startup."""

    @abstractmethod
    async def status(self) -> CommandResult:
        """Return backend health/status info."""

    # --- Drawing management ---

    async def drawing_info(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def drawing_save(self, path: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def drawing_save_as_dxf(self, path: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def drawing_create(self, name: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def drawing_purge(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def drawing_plot_pdf(self, path: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def drawing_get_variables(self, names: list[str] | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def drawing_open(self, path: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Undo / Redo ---

    async def undo(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def redo(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Freehand LISP execution ---

    async def execute_lisp(self, code: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def setup_lisp(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Entity operations ---

    async def create_line(self, x1: float, y1: float, x2: float, y2: float, layer: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_circle(self, cx: float, cy: float, radius: float, layer: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_polyline(self, points: list[list[float]], closed: bool = False, layer: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_rectangle(self, x1: float, y1: float, x2: float, y2: float, layer: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_arc(self, cx: float, cy: float, radius: float, start_angle: float, end_angle: float, layer: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_ellipse(self, cx: float, cy: float, major_x: float, major_y: float, ratio: float, layer: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_mtext(self, x: float, y: float, width: float, text: str, height: float = 2.5, layer: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_hatch(self, entity_id: str, pattern: str = "ANSI31") -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_list(self, layer: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_count(self, layer: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_get(self, entity_id: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_erase(self, entity_id: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_copy(self, entity_id: str, dx: float, dy: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_move(self, entity_id: str, dx: float, dy: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_rotate(self, entity_id: str, cx: float, cy: float, angle: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_scale(self, entity_id: str, cx: float, cy: float, factor: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_mirror(self, entity_id: str, x1: float, y1: float, x2: float, y2: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_offset(self, entity_id: str, distance: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_array(self, entity_id: str, rows: int, cols: int, row_dist: float, col_dist: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_fillet(self, entity_id1: str, entity_id2: str, radius: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_chamfer(self, entity_id1: str, entity_id2: str, dist1: float, dist2: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Layer operations ---

    async def layer_list(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layer_create(self, name: str, color: str | int = "white", linetype: str = "CONTINUOUS") -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layer_set_current(self, name: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layer_set_properties(self, name: str, color: str | int | None = None, linetype: str | None = None, lineweight: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layer_freeze(self, name: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layer_thaw(self, name: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layer_lock(self, name: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layer_unlock(self, name: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Block operations ---

    async def block_list(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def block_insert(self, name: str, x: float, y: float, scale: float = 1.0, rotation: float = 0.0, block_id: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def block_insert_with_attributes(self, name: str, x: float, y: float, scale: float = 1.0, rotation: float = 0.0, attributes: dict[str, str] | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def block_get_attributes(self, entity_id: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def block_update_attribute(self, entity_id: str, tag: str, value: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def block_define(self, name: str, entities: list[dict]) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Annotation ---

    async def create_text(self, x: float, y: float, text: str, height: float = 2.5, rotation: float = 0.0, layer: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_dimension_linear(self, x1: float, y1: float, x2: float, y2: float, dim_x: float, dim_y: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_dimension_aligned(self, x1: float, y1: float, x2: float, y2: float, offset: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_dimension_angular(self, cx: float, cy: float, x1: float, y1: float, x2: float, y2: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_dimension_radius(self, cx: float, cy: float, radius: float, angle: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def create_leader(self, points: list[list[float]], text: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- P&ID ---

    async def pid_setup_layers(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_insert_symbol(self, category: str, symbol: str, x: float, y: float, scale: float = 1.0, rotation: float = 0.0) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_list_symbols(self, category: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_draw_process_line(self, x1: float, y1: float, x2: float, y2: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_connect_equipment(self, x1: float, y1: float, x2: float, y2: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_add_flow_arrow(self, x: float, y: float, rotation: float = 0.0) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_add_equipment_tag(self, x: float, y: float, tag: str, description: str = "") -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_add_line_number(self, x: float, y: float, line_num: str, spec: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_insert_valve(self, x: float, y: float, valve_type: str, rotation: float = 0.0, attributes: dict[str, str] | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_insert_instrument(self, x: float, y: float, instrument_type: str, rotation: float = 0.0, tag_id: str = "", range_value: str = "") -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_insert_pump(self, x: float, y: float, pump_type: str, rotation: float = 0.0, attributes: dict[str, str] | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pid_insert_tank(self, x: float, y: float, tank_type: str, scale: float = 1.0, attributes: dict[str, str] | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- View ---

    async def zoom_extents(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def zoom_window(self, x1: float, y1: float, x2: float, y2: float) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def get_screenshot(self) -> CommandResult:
        """Return base64 PNG in payload."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Query operations ---

    async def query_entity_properties(self, entity_id: str) -> CommandResult:
        """Get ALL properties of an entity: type, layer, color, linetype, lineweight, and type-specific geometry data."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def query_entity_geometry(self, entity_id: str) -> CommandResult:
        """Get precise geometry: for polylines return all vertices/bulges, for circles return center/radius, for text return content/position/height/style, for blocks return insert point/scale/rotation/attributes."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def query_drawing_summary(self) -> CommandResult:
        """Get entity count by type, by layer, drawing extents, block/style/linetype inventory."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def query_layer_summary(self, layer: str) -> CommandResult:
        """Per-layer stats: entity count by type, bounding box."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Search operations ---

    async def search_text(self, pattern: str, case_sensitive: bool = False) -> CommandResult:
        """Find all TEXT/MTEXT entities containing pattern. Return handle, text content, position, layer."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def search_by_attribute(self, tag: str = None, value: str = None) -> CommandResult:
        """Find INSERT entities with matching attribute tag/value. Return handle, block name, position, all attributes."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def search_by_window(self, x1: float, y1: float, x2: float, y2: float) -> CommandResult:
        """Find all entities within rectangular window. Return handles with type, layer, position."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def search_by_proximity(self, x: float, y: float, radius: float) -> CommandResult:
        """Find all entities within radius of point."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def search_by_type_and_layer(self, entity_type: str = None, layer: str = None, color: int = None) -> CommandResult:
        """Find entities matching type/layer/color filter. Return full property data."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Geometry operations ---

    async def geometry_distance(self, x1: float, y1: float, x2: float, y2: float) -> CommandResult:
        """Calculate distance between two points."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def geometry_length(self, entity_id: str) -> CommandResult:
        """Get total length of line/polyline/arc."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def geometry_area(self, entity_id: str) -> CommandResult:
        """Get area of closed polyline/circle."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def geometry_bounding_box(self, entity_id: str = None, layer: str = None) -> CommandResult:
        """Get axis-aligned bounding box of entity, or all entities on layer."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def geometry_polyline_info(self, entity_id: str) -> CommandResult:
        """Get polyline vertices, bulges, segment lengths, total length, is_closed, area if closed."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Bulk operations ---

    async def bulk_set_property(self, handles: list, property_name: str, value) -> CommandResult:
        """Set property (layer, color, linetype) on multiple entities."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def bulk_erase(self, handles: list) -> CommandResult:
        """Erase multiple entities by handle list."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Export ---

    async def export_entity_data(self, layer: str = None, entity_type: str = None) -> CommandResult:
        """Export filtered entities with ALL properties as structured data."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Select / Filter ---

    async def select_filter(self, entity_type: str = None, layer: str = None,
                            color: int = None, x1: float = None, y1: float = None,
                            x2: float = None, y2: float = None) -> CommandResult:
        """Select entities matching criteria. Returns list of handles."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def bulk_move(self, handles: list, dx: float, dy: float) -> CommandResult:
        """Move multiple entities by delta."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def bulk_copy(self, handles: list, dx: float, dy: float) -> CommandResult:
        """Copy multiple entities by delta offset."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def find_replace_text(self, find: str, replace: str, layer: str = None) -> CommandResult:
        """Find and replace text content in TEXT/MTEXT entities."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Entity Property Modification ---

    async def entity_set_property(self, entity_id: str, property_name: str, value: Any) -> CommandResult:
        """Set a single property on an entity (color, layer, linetype, lineweight)."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_set_text(self, entity_id: str, text: str) -> CommandResult:
        """Update text content of TEXT or MTEXT entity."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- View Enhancements ---

    async def zoom_center(self, x: float, y: float, height: float) -> CommandResult:
        """Zoom to center point with specified view height."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layer_visibility(self, name: str, visible: bool) -> CommandResult:
        """Turn layer on/off."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Validate ---

    async def validate_layer_standards(self, allowed_layers: list[str]) -> CommandResult:
        """Check all entities are on approved layers. Returns violations."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def validate_duplicates(self, tolerance: float = 0.001) -> CommandResult:
        """Find duplicate/overlapping entities."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def validate_zero_length(self) -> CommandResult:
        """Find zero-length lines, zero-area circles."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def validate_qc_report(self, allowed_layers: list[str] = None) -> CommandResult:
        """Run all validation checks and return structured pass/fail report."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Export / Reporting ---

    async def export_bom(self, block_names: list[str] = None) -> CommandResult:
        """Bill of Materials from block insertions with attributes."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def export_data_extract(self, entity_type: str = None, layer: str = None,
                                  properties: list[str] = None) -> CommandResult:
        """Custom data extraction: filter + properties → tabular data."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def export_layer_report(self) -> CommandResult:
        """Layer usage statistics: entity counts, types, extents per layer."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def export_block_count(self) -> CommandResult:
        """Count of each block insertion, optionally grouped by attributes."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def export_drawing_statistics(self) -> CommandResult:
        """Comprehensive drawing stats: entity counts, layer counts, complexity."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Extended Query ---

    async def query_text_styles(self) -> CommandResult:
        """List all text styles with font, height, width factor."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def query_dimension_styles(self) -> CommandResult:
        """List all dimension styles with key properties."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def query_linetypes(self) -> CommandResult:
        """List all loaded linetypes."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def query_block_tree(self) -> CommandResult:
        """Hierarchical block/xref structure with attribute definitions."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def query_drawing_metadata(self) -> CommandResult:
        """Drawing metadata: units, limits, title, author, custom properties."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Extended Search ---

    async def search_by_block_name(self, block_name: str) -> CommandResult:
        """Find all insertions of a specific block."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def search_by_handle_list(self, handles: list[str]) -> CommandResult:
        """Batch-get properties for multiple handles at once."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Equipment Find / Inspect ---

    async def equipment_find(self, pattern: str, case_sensitive: bool = False,
                             search_scope: str = "all", zoom_to_first: bool = True,
                             zoom_height: float = 600.0, max_results: int = 50) -> CommandResult:
        """Deep text search across modelspace, attributes, and block definitions.

        Searches TEXT, MTEXT in modelspace, then attribute values on INSERTs,
        then text inside block definitions (with nested block recursion).
        Optionally zooms to the first result.
        """
        return CommandResult(ok=False, error="Not supported on this backend")

    async def equipment_inspect(self, x: float, y: float, view_width: float = 600.0,
                                view_height: float = 600.0, infer_center: bool = True,
                                handle: str | None = None) -> CommandResult:
        """Zoom to area, find nearby entities, infer equipment center.

        Center inference priority: specific INSERT bbox > largest circle >
        nearest INSERT > text position fallback.
        """
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Deep Text Search ---

    async def find_text(self, pattern: str, case_sensitive: bool = False,
                        max_results: int = 50, zoom_to_first: bool = True,
                        zoom_height: float = 600.0) -> CommandResult:
        """Deep text search across modelspace and all block definitions.

        Searches TEXT, MTEXT, DIMENSION overrides, INSERT ATTRIBs, and text
        inside block definitions (including nested/xref blocks).
        """
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Equipment Tag Placement ---

    async def place_equipment_tag(self, cx: float, cy: float, cz: float = 0.0,
                                  tag: str = "", cube_size: float = 24.0,
                                  direction: str = "right",
                                  text_height: float = 8.0) -> CommandResult:
        """Place a complete equipment tag group: 3D cube + leader + MTEXT label + underline."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def batch_find_and_tag(self, tags: list[str], cube_size: float = 24.0,
                                  direction: str = "right",
                                  text_height: float = 8.0) -> CommandResult:
        """Find multiple tags in drawing and place equipment tag groups at each location.

        Returns placed count, not_found list, and per-tag results with handles.
        """
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Extended Entity ---

    async def entity_explode(self, entity_id: str) -> CommandResult:
        """Explode a block or polyline into component entities."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_join(self, entity_ids: list[str]) -> CommandResult:
        """Join collinear lines or polyline segments."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_extend(self, entity_id: str, boundary_id: str) -> CommandResult:
        """Extend entity to boundary."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_trim(self, entity_id: str, boundary_id: str) -> CommandResult:
        """Trim entity at boundary."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def entity_break_at(self, entity_id: str, x: float, y: float) -> CommandResult:
        """Break entity at a point."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Extended Validate ---

    async def validate_text_standards(self, allowed_styles: list[str] = None,
                                      allowed_heights: list[float] = None) -> CommandResult:
        """Check text styles/heights match standards."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def validate_orphaned_entities(self) -> CommandResult:
        """Find entities on frozen/off layers or outside drawing limits."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def validate_attribute_completeness(self, required_tags: list[str] = None) -> CommandResult:
        """Check all required block attributes are filled."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def validate_connectivity(self, layer: str = None, tolerance: float = 0.01) -> CommandResult:
        """Verify wire/pipe endpoints connect (no dangling ends)."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Extended Select ---

    async def find_replace_attribute(self, tag: str, find: str, replace: str) -> CommandResult:
        """Find and replace in block attribute values."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layer_rename(self, old_name: str, new_name: str) -> CommandResult:
        """Rename layer and update all entity references."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layer_merge(self, source_layer: str, target_layer: str) -> CommandResult:
        """Merge entities from one layer into another."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Enhanced View ---

    async def zoom_scale(self, factor: float) -> CommandResult:
        """Set absolute zoom factor."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def pan(self, dx: float, dy: float) -> CommandResult:
        """Pan view by delta."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Enhanced Drawing ---

    async def drawing_audit(self, fix: bool = False) -> CommandResult:
        """Run drawing audit, optionally fix issues."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def drawing_units(self, units: int = None) -> CommandResult:
        """Get/set drawing units."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def drawing_limits(self, x1: float = None, y1: float = None,
                             x2: float = None, y2: float = None) -> CommandResult:
        """Get/set drawing limits."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def drawing_wblock(self, handles: list[str], path: str) -> CommandResult:
        """Export selection to new DWG."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- XREF ---

    async def xref_list(self) -> CommandResult:
        """List all xrefs with path, type, loaded status."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def xref_attach(self, path: str, x: float = 0, y: float = 0,
                          scale: float = 1.0, overlay: bool = False) -> CommandResult:
        """Attach an external reference."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def xref_detach(self, name: str) -> CommandResult:
        """Detach an external reference."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def xref_reload(self, name: str) -> CommandResult:
        """Reload an external reference."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def xref_bind(self, name: str, insert: bool = False) -> CommandResult:
        """Bind xref into drawing."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def xref_path_update(self, name: str, new_path: str) -> CommandResult:
        """Update xref file path."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def xref_query_entities(self, name: str, entity_type: str = None,
                                  layer: str = None) -> CommandResult:
        """Query entities inside an xref by type/layer."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Layout ---

    async def layout_list(self) -> CommandResult:
        """List all layouts/tabs."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layout_create(self, name: str) -> CommandResult:
        """Create new layout."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layout_switch(self, name: str) -> CommandResult:
        """Switch active layout."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layout_delete(self, name: str) -> CommandResult:
        """Delete layout."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layout_viewport_create(self, x: float, y: float, width: float,
                                     height: float, scale: float = 1.0) -> CommandResult:
        """Create viewport in paper space."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layout_viewport_set_scale(self, viewport_id: str, scale: float) -> CommandResult:
        """Set viewport display scale."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layout_viewport_lock(self, viewport_id: str, lock: bool = True) -> CommandResult:
        """Lock/unlock viewport scale."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layout_page_setup(self, name: str, paper_size: str = None,
                                orientation: str = None) -> CommandResult:
        """Configure paper size and orientation."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layout_titleblock_fill(self, layout_name: str,
                                     attributes: dict[str, str] = None) -> CommandResult:
        """Auto-fill title block attributes in a layout."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def layout_batch_plot(self, layouts: list[str] = None,
                                output_path: str = None) -> CommandResult:
        """Plot multiple layouts to PDF."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Electrical ---

    async def electrical_nec_lookup(self, table: str, parameters: dict = None) -> CommandResult:
        """Look up NEC table values (wire ampacity, conduit fill, etc.)."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def electrical_voltage_drop(self, voltage: float, current: float,
                                      wire_gauge: str, length: float,
                                      phase: int = 1, power_factor: float = 1.0) -> CommandResult:
        """Calculate voltage drop for a circuit."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def electrical_conduit_fill(self, conduit_size: str, conduit_type: str,
                                      wire_gauges: list[str] = None) -> CommandResult:
        """Check conduit fill % against NEC tables."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def electrical_load_calc(self, devices: list[dict] = None) -> CommandResult:
        """Calculate total load per circuit/panel from device ratings."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def electrical_symbol_insert(self, symbol_type: str, x: float, y: float,
                                       scale: float = 1.0, rotation: float = 0.0,
                                       layer: str = None) -> CommandResult:
        """Insert standard electrical symbol."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def electrical_circuit_trace(self, start_entity: str,
                                       layer: str = None) -> CommandResult:
        """Trace a circuit from panel to device via wire connectivity."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def electrical_panel_schedule_gen(self, panel_block: str,
                                            x: float = 0, y: float = 0) -> CommandResult:
        """Generate panel schedule table from circuit data."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def electrical_wire_number_assign(self, layer: str, prefix: str = "W",
                                            start_num: int = 1) -> CommandResult:
        """Auto-assign wire numbers following convention."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- MagiCAD ---

    async def magicad_status(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_run(self, command: str, args: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_update_drawing(self, flags: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_cleanup(self, options: str | None = None) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_ifc_export(self, mode: str = "current") -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_view_mode(self, mode: str, type: str = "D") -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_change_storey(self, storey: str) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_section_update(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_fix_errors(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_show_all(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_clear_garbage(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_disconnect_project(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_list_commands(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    async def magicad_project_info(self) -> CommandResult:
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- COM / Connection Management ---

    async def connect(self, cad_type: str = "autocad") -> CommandResult:
        """Connect to a specific CAD application via COM."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def disconnect(self) -> CommandResult:
        """Disconnect from the current CAD application."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def get_connection_status(self) -> CommandResult:
        """Get connection status for all CAD types."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Batch Drawing Operations ---

    async def batch_draw_lines(self, lines: list[dict]) -> CommandResult:
        """Draw multiple lines in a single batch. Each dict: {x1, y1, x2, y2, layer?, color?}."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def batch_draw_circles(self, circles: list[dict]) -> CommandResult:
        """Draw multiple circles. Each dict: {cx, cy, radius, layer?, color?}."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def batch_draw_rectangles(self, rectangles: list[dict]) -> CommandResult:
        """Draw multiple rectangles. Each dict: {x1, y1, x2, y2, layer?, color?}."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def batch_draw_polylines(self, polylines: list[dict]) -> CommandResult:
        """Draw multiple polylines. Each dict: {points, closed?, layer?, color?}."""
        return CommandResult(ok=False, error="Not supported on this backend")

    async def batch_draw_texts(self, texts: list[dict]) -> CommandResult:
        """Draw multiple text entities. Each dict: {x, y, text, height?, rotation?, layer?}."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- NLP ---

    async def execute_natural_command(self, command: str) -> CommandResult:
        """Parse and execute a natural language drawing command."""
        return CommandResult(ok=False, error="Not supported on this backend")

    # --- Excel Export ---

    async def export_to_excel(self, filename: str = "drawing_data.xlsx",
                               output_dir: str | None = None) -> CommandResult:
        """Export drawing data to an Excel file."""
        return CommandResult(ok=False, error="Not supported on this backend")
