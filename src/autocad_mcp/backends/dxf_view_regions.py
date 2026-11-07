"""Find candidate drawing view regions using explicit DXF frame layers."""

from __future__ import annotations

import math
import re
from itertools import pairwise

from ezdxf import bbox

from autocad_mcp.backends.dxf_spatial import SpatialScan, layout_entities


_TITLE_TYPES = {
    "plan": "plan",
    "plan view": "plan",
    "平面图": "plan",
    "俯视图": "plan",
    "elevation": "elevation",
    "elevation view": "elevation",
    "立面图": "elevation",
    "正视图": "elevation",
    "侧视图": "elevation",
    "section": "section",
    "section view": "section",
    "剖面图": "section",
    "剖视图": "section",
}

_FRAME_NAME = re.compile(r"图框|(?:^|[^a-z])(?:title[ _-]*block|sheet[ _-]*(?:frame|border)|drawing[ _-]*border)(?:$|[^a-z])", re.I)
_TITLE_SUFFIX = re.compile(r"(平面图|俯视图|立面图|正视图|侧视图|剖面图|剖视图)$")


def _frame_bounds(entity):
    if entity.dxftype() != "LWPOLYLINE" or not entity.closed or len(entity) != 4:
        return None
    if any(bulge for (bulge,) in entity.get_points("b")):
        return None
    points = list(entity.vertices_in_wcs())
    if not all(math.isfinite(value) for point in points for value in point):
        return None
    left, right = min(p.x for p in points), max(p.x for p in points)
    bottom, top = min(p.y for p in points), max(p.y for p in points)
    span = min(right - left, top - bottom)
    if span <= 0:
        return None
    tolerance = span * 1e-9
    if any(abs(point.z - points[0].z) > tolerance for point in points):
        return None
    corners = set()
    for first, second in pairwise([*points, points[0]]):
        same_x = abs(first.x - second.x) <= tolerance
        same_y = abs(first.y - second.y) <= tolerance
        if same_x == same_y:
            return None
        if min(abs(first.x - left), abs(first.x - right)) > tolerance:
            return None
        if min(abs(first.y - bottom), abs(first.y - top)) > tolerance:
            return None
        corners.add((abs(first.x - left) <= tolerance, abs(first.y - bottom) <= tolerance))
    return (left, bottom, right, top) if len(corners) == 4 else None


def _contains(outer, inner):
    return outer[0] <= inner[0] <= inner[2] <= outer[2] and outer[1] <= inner[1] <= inner[3] <= outer[3]


def _intersects(a, b):
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def _title(entity):
    if entity.dxftype() not in ("TEXT", "MTEXT"):
        return None
    text = entity.plain_text()
    normalized = re.sub(r"\s+", " ", text).strip().casefold()
    title_type = _TITLE_TYPES.get(normalized)
    if not title_type and len(normalized) <= 40 and "\n" not in text:
        match = _TITLE_SUFFIX.search(normalized)
        if match:
            title_type = _TITLE_TYPES[match.group()]
    if title_type:
        return {"handle": entity.dxf.handle, "text": text, "view_type": title_type}
    return None


def _named_frame(entity):
    if entity.dxftype() != "INSERT" or not _FRAME_NAME.search(entity.dxf.name):
        return None
    box = bbox.extents([entity])
    if not box.has_data:
        return None
    bounds = (box.extmin.x, box.extmin.y, box.extmax.x, box.extmax.y)
    if all(math.isfinite(value) for value in bounds) and bounds[0] < bounds[2] and bounds[1] < bounds[3]:
        return bounds
    return None


def view_regions(doc, frame_layer=None, *, layout=None):
    """Group top-level entities by frame bounds and infer type from explicit titles."""
    if frame_layer is not None and (not isinstance(frame_layer, str) or not frame_layer):
        raise ValueError("frame_layer must be a nonempty layer name")
    entities = list(layout_entities(doc, layout))
    frames = {}
    frame_layers = {}
    evidence = "named_frame_reference" if frame_layer is None else "explicit_frame_layer"
    for entity, name in entities:
        if frame_layer is None:
            bounds = _named_frame(entity)
        elif entity.dxftype() == "LWPOLYLINE" and entity.dxf.layer.casefold() == frame_layer.casefold():
            bounds = _frame_bounds(entity)
        else:
            continue
        if bounds:
            frames[entity.dxf.handle] = (bounds, name)
            frame_layers[entity.dxf.handle] = entity.dxf.layer

    regions = {
        handle: {
            "frame_handle": handle,
            "frame_layer": frame_layers[handle],
            "frame_evidence": evidence,
            "layout": name,
            "bbox_min": list(bounds[:2]),
            "bbox_max": list(bounds[2:]),
            "view_type": "unknown",
            "classification_method": "explicit_title",
            "members": [],
            "titles": [],
            "overlapping_frames": [],
        }
        for handle, (bounds, name) in frames.items()
    }
    for handle, (bounds, _) in frames.items():
        regions[handle]["overlapping_frames"] = [
            other for other, (other_bounds, _) in frames.items()
            if other != handle
            and max(bounds[0], other_bounds[0]) < min(bounds[2], other_bounds[2])
            and max(bounds[1], other_bounds[1]) < min(bounds[3], other_bounds[3])
        ]

    scan = SpatialScan()
    if frames:
        members = {entity.dxf.handle: (entity, name) for entity, name in entities if entity.dxf.handle not in frames}
        for item, box in scan.boxes(members.values()):
            bounds = (box.extmin.x, box.extmin.y, box.extmax.x, box.extmax.y)
            intersecting = [
                (handle, _contains(frame, bounds)) for handle, (frame, _) in frames.items()
                if _intersects(frame, bounds)
            ]
            for handle, contained in intersecting:
                ambiguous = not contained or len(intersecting) > 1
                regions[handle]["members"].append({
                    **item,
                    "relation": "contained" if contained else "crosses_boundary",
                    "ambiguous": ambiguous,
                })
                if not ambiguous:
                    title = _title(members[item["handle"]][0])
                    if title:
                        regions[handle]["titles"].append(title)

    for region in regions.values():
        title_types = {title["view_type"] for title in region["titles"]}
        if len(title_types) == 1:
            region["view_type"] = next(iter(title_types))
        region["classification_ambiguous"] = len(title_types) > 1
        region["boundary_ambiguous"] = bool(region["overlapping_frames"]) or any(
            member["ambiguous"] for member in region["members"]
        )
        region["ambiguous"] = region["classification_ambiguous"] or region["boundary_ambiguous"]
    return {"regions": list(regions.values()), "count": len(regions), "diagnostics": scan.diagnostics()}
