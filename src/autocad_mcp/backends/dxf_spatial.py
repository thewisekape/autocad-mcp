"""Read-only spatial queries on ezdxf layout entities."""

from __future__ import annotations

import math

from ezdxf import bbox
from ezdxf.math import BoundingBox


def validate_coordinates(**coordinates):
    for name, value in coordinates.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")


def layout_entities(doc, layout_name=None):
    if layout_name is None:
        layout = doc.modelspace()
    else:
        if not isinstance(layout_name, str) or not layout_name:
            raise ValueError("layout must be a nonempty layout name")
        try:
            layout = doc.layouts.get(layout_name)
        except KeyError:
            raise ValueError(f"Layout {layout_name!r} not found") from None
    return ((entity, layout.name) for entity in layout)


class SpatialScan:
    """Track entities that could not be evaluated, including partial results."""

    box_method = "ezdxf_extents"
    iter_layout = staticmethod(layout_entities)

    @staticmethod
    def find_entity(doc, handle):
        return doc.entitydb.get(handle)

    @staticmethod
    def metadata(entity):
        layer = entity.dxf.get("layer", "0") if entity.dxf.is_supported("layer") else None
        return entity.dxf.handle, entity.dxftype(), layer

    @staticmethod
    def extents(entity):
        return bbox.extents([entity])

    @staticmethod
    def is_retryable(error):
        return False

    def __init__(self):
        self.box_count = 0
        self.skipped_count = 0
        self.issues = []

    def boxes(self, entities, entity_type=None, layer=None):
        for name, value in (("entity_type", entity_type), ("layer", layer)):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{name} must be a nonempty string")

        for entity, layout in entities:
            handle, kind, entity_layer = self.metadata(entity)
            if entity_type is not None and kind.casefold() != entity_type.casefold():
                continue
            if layer is not None and (entity_layer is None or entity_layer.casefold() != layer.casefold()):
                continue
            entry = {"handle": handle, "type": kind, "layer": entity_layer, "layout": layout}
            try:
                box = self.extents(entity)
                if not box.has_data or not all(math.isfinite(v) for v in (*box.extmin, *box.extmax)):
                    self._skip(entry, "No finite bounding box available")
                    continue
            except Exception as exc:
                if self.is_retryable(exc):
                    raise
                self._skip(entry, f"{type(exc).__name__}: {exc}")
                continue
            self.box_count += 1
            yield entry, box

    def _skip(self, entry, reason):
        self.skipped_count += 1
        if len(self.issues) < 20:
            self.issues.append({**entry, "reason": reason})

    def diagnostics(self):
        if self.skipped_count and not self.box_count:
            first = self.issues[0]
            raise ValueError(
                f"No bounding box available for {self.skipped_count} candidate(s); "
                f"first issue for {first['type']} {first['handle']}: {first['reason']}"
            )
        return {
            "box_method": self.box_method,
            "candidate_scope": "top_level_layout",
            "status": "partial" if self.skipped_count else "complete",
            "evaluated_count": self.box_count,
            "skipped_count": self.skipped_count,
            "issues": self.issues,
        }


def window_query(doc, x1, y1, x2, y2, *, mode="contains", entity_type=None, layer=None, layout=None, scan=None):
    validate_coordinates(x1=x1, y1=y1, x2=x2, y2=y2)
    if mode not in ("contains", "intersects"):
        raise ValueError("mode must be 'contains' or 'intersects'")
    min_x, max_x = sorted((x1, x2))
    min_y, max_y = sorted((y1, y2))
    scan = scan or SpatialScan()
    matches = []
    for entry, box in scan.boxes(scan.iter_layout(doc, layout), entity_type, layer):
        left, bottom = box.extmin.x, box.extmin.y
        right, top = box.extmax.x, box.extmax.y
        if mode == "contains":
            hit = min_x <= left <= right <= max_x and min_y <= bottom <= top <= max_y
        else:
            hit = left <= max_x and right >= min_x and bottom <= max_y and top >= min_y
        if hit:
            matches.append({**entry, "bbox_min": [left, bottom], "bbox_max": [right, top]})
    return {"matches": matches, "count": len(matches), "mode": mode, "diagnostics": scan.diagnostics()}


def proximity_query(doc, x, y, radius, *, metric="bbox_center", entity_type=None, layer=None, layout=None, scan=None):
    validate_coordinates(x=x, y=y, radius=radius)
    if radius < 0:
        raise ValueError("radius must be non-negative")
    if metric not in ("bbox_center", "bbox_nearest"):
        raise ValueError("metric must be 'bbox_center' or 'bbox_nearest'")
    scan = scan or SpatialScan()
    matches = []
    for entry, box in scan.boxes(scan.iter_layout(doc, layout), entity_type, layer):
        center = box.center
        if metric == "bbox_center":
            distance = math.hypot(center.x - x, center.y - y)
        else:
            dx = max(box.extmin.x - x, x - box.extmax.x, 0)
            dy = max(box.extmin.y - y, y - box.extmax.y, 0)
            distance = math.hypot(dx, dy)
        if distance <= radius:
            matches.append({**entry, "distance": round(distance, 6), "center": [round(center.x, 6), round(center.y, 6)]})
    matches.sort(key=lambda item: item["distance"])
    return {"matches": matches, "count": len(matches), "metric": metric, "diagnostics": scan.diagnostics()}


def bounding_box(doc, entity_id=None, layer=None, *, entity_type=None, layout=None, scan=None):
    scan = scan or SpatialScan()
    if entity_id and layout is None:
        entity = scan.find_entity(doc, entity_id)
        if entity is None:
            raise ValueError(f"Entity {entity_id} not found")
        entities = [(entity, None)]
        # A handle took precedence over the layer argument in the original API.
        layer = None
    else:
        entities = scan.iter_layout(doc, layout)
        if entity_id:
            entities = ((entity, name) for entity, name in entities if scan.metadata(entity)[0] == entity_id)

    box = BoundingBox()
    for _, entity_box in scan.boxes(entities, entity_type, layer):
        box.extend(entity_box)
    diagnostics = scan.diagnostics()
    if not box.has_data:
        raise ValueError("No bounding box data available for the requested scope")
    if entity_id:
        diagnostics["candidate_scope"] = "entity_handle"
    return {
        "min": list(box.extmin),
        "max": list(box.extmax),
        "width": round(box.extmax.x - box.extmin.x, 10),
        "height": round(box.extmax.y - box.extmin.y, 10),
        "diagnostics": diagnostics,
    }
