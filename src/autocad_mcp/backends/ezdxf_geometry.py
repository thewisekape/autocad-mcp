"""Additional geometry and coordinate provenance for DXF entities."""

import math

from ezdxf import DXFError, bbox
from ezdxf.entities import DXFGraphic
from ezdxf.math import Vec3, arc_angle_span_deg, ellipse_param_span

BOUNDED_TYPES = {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "ELLIPSE", "SPLINE"}


def polyline_segments(entity, segment_length):
    if entity.dxftype() == "LWPOLYLINE":
        points = [Vec3(x, y, 0) for x, y in entity.vertices()]
        bulges = [value for (value,) in entity.get_points("b")]
        closed = entity.closed
    elif entity.is_2d_polyline or entity.is_3d_polyline:
        if entity.dxf.flags & 6:
            raise ValueError("Curve-fit POLYLINE segment measurements are unavailable")
        points = list(entity.points())
        bulges = [vertex.dxf.bulge if entity.is_2d_polyline else 0.0 for vertex in entity.vertices]
        closed = entity.is_closed
    else:
        raise ValueError("Mesh POLYLINE segment measurements are unavailable")
    following = points[1:] + points[:1] if closed and len(points) > 1 else points[1:]
    return [segment_length(p.x, p.y, q.x, q.y, bulge) if bulge else p.distance(q)
            for p, q, bulge in zip(points, following, bulges)]


def polyline_area(entity):
    if entity.dxftype() == "LWPOLYLINE":
        if not entity.closed:
            raise ValueError("Polyline is not closed; area undefined")
        vertices = list(entity.get_points("xyb"))
    else:
        if not entity.is_2d_polyline or entity.dxf.flags & 6:
            raise ValueError("Area requires a planar, non-curve-fit POLYLINE")
        if not entity.is_closed:
            raise ValueError("Polyline is not closed; area undefined")
        vertices = [(v.dxf.location.x, v.dxf.location.y, v.dxf.bulge) for v in entity.vertices]
    if len(vertices) < 2:
        return 0.0
    ox, oy, _ = vertices[0]
    terms = []
    for (x1, y1, bulge), (x2, y2, _) in zip(vertices, vertices[1:] + vertices[:1]):
        terms.append(((x1 - ox) * (y2 - oy) - (y1 - oy) * (x2 - ox)) / 2)
        if bulge:
            chord2 = (x2 - x1) ** 2 + (y2 - y1) ** 2
            if abs(bulge) < 1e-5:
                terms.append(chord2 * bulge / 3)
            else:
                angle = 4 * math.atan(bulge)
                radius2 = chord2 * (bulge + 1 / bulge) ** 2 / 16
                terms.append(radius2 * (angle - math.sin(angle)) / 2)
    return abs(math.fsum(terms))


def ellipse_length(entity):
    start = entity.dxf.start_param
    span = ellipse_param_span(start, entity.dxf.end_param)
    major = entity.dxf.major_axis.magnitude
    minor = major * entity.dxf.ratio
    steps = 512
    step = span / steps

    def speed(parameter):
        return math.hypot(major * math.sin(parameter), minor * math.cos(parameter))

    interior = math.fsum((4 if i % 2 else 2) * speed(start + i * step) for i in range(1, steps))
    return step / 3 * (speed(start) + interior + speed(start + span))


def _polyline_length(points, bulges, closed, segment_length):
    if len(points) < 2:
        return 0.0
    following = points[1:] + points[:1] if closed else points[1:]
    return sum(
        segment_length(p.x, p.y, q.x, q.y, bulge) if bulge else p.distance(q)
        for p, q, bulge in zip(points, following, bulges)
    )


def _polyline_geometry(entity, segment_length):
    warnings = []
    if entity.dxftype() == "LWPOLYLINE":
        points = [Vec3(x, y, entity.dxf.elevation) for x, y in entity.vertices()]
        bulges = [point[0] for point in entity.get_points("b")]
        wcs = entity.vertices_in_wcs()
        closed = entity.closed
        is_ocs = True
    elif entity.is_2d_polyline or entity.is_3d_polyline:
        bulges = (
            [vertex.dxf.bulge for vertex in entity.vertices]
            if entity.is_2d_polyline else [0.0] * len(entity.vertices)
        )
        wcs = entity.points_in_wcs()
        points = list(entity.points())
        closed = entity.is_closed
        is_ocs = entity.is_2d_polyline
        if is_ocs:
            elevation = entity.dxf.elevation.z
            points = [Vec3(point.x, point.y, elevation) for point in points]
        if entity.dxf.flags & 6:
            warnings.append("curve_fit_polyline_length_unavailable")
    else:
        return {"length": None}, ["mesh_polyline_length_unavailable"]

    data = {
        "vertices_in_owner": [list(point) for point in wcs],
        "bulges": bulges,
        "length": None if warnings else _polyline_length(points, bulges, closed, segment_length),
    }
    if is_ocs:
        data["vertices_ocs"] = [list(point) for point in points]
        data["extrusion"] = list(entity.dxf.extrusion)
    return data, warnings


def extend_entity_geometry(entity, geometry, segment_length):
    if not isinstance(entity, DXFGraphic):
        return

    owner = entity.get_layout()
    in_layout = owner is not None and owner.block_record.is_any_layout
    dtype = entity.dxftype()
    warnings = []
    owner_space = None
    if owner is not None:
        owner_space = "WCS" if in_layout else "block_definition"
    coordinates = {"owner_space": owner_space}
    geometry.update({
        "source_file": entity.doc.filename if entity.doc is not None else None,
        "layer": entity.dxf.layer,
        "layout": owner.name if in_layout else None,
        "parent_block": owner.name if owner is not None and not in_layout else None,
        "coordinates": coordinates,
    })
    if owner is None:
        warnings.append("entity_owner_unavailable")
    elif not in_layout:
        warnings.append("block_instance_path_required_for_layout_wcs")

    if dtype == "LINE":
        geometry["length"] = entity.dxf.start.distance(entity.dxf.end)
    elif dtype in {"ARC", "CIRCLE"}:
        coordinates["center_in_owner"] = list(entity.ocs().to_wcs(entity.dxf.center))
        coordinates["extrusion"] = list(entity.dxf.extrusion)
        sweep = arc_angle_span_deg(entity.dxf.start_angle, entity.dxf.end_angle) if dtype == "ARC" else 360.0
        geometry["arc_length"] = math.radians(sweep) * entity.dxf.radius
        geometry["length"] = geometry["arc_length"]
    elif dtype in {"LWPOLYLINE", "POLYLINE"}:
        data, polyline_warnings = _polyline_geometry(entity, segment_length)
        geometry["length"] = data.pop("length")
        coordinates.update(data)
        warnings.extend(polyline_warnings)
    elif dtype == "ELLIPSE":
        coordinates["extrusion"] = list(entity.dxf.extrusion)
    elif dtype == "SPLINE":
        geometry.pop("info", None)
        geometry.update({
            "degree": entity.dxf.degree,
            "flags": entity.dxf.flags,
            "control_points": [list(point) for point in entity.control_points],
            "fit_points": [list(point) for point in entity.fit_points],
            "knots": list(entity.knots),
            "weights": list(entity.weights),
        })
    elif dtype == "INSERT":
        coordinates["insertion_point_in_owner"] = list(entity.ocs().to_wcs(entity.dxf.insert))
        coordinates["extrusion"] = list(entity.dxf.extrusion)
        block = entity.block()
        if block is None:
            warnings.append("missing_block_definition")
        else:
            matrix = entity.matrix44()
            if all(math.isfinite(value) for value in matrix):
                geometry["local_transform"] = [list(row) for row in matrix.rows()]
            else:
                warnings.append("invalid_transform")
        if entity.mcount > 1:
            warnings.append("use_block_tree_for_minsert_instances")

    if dtype in BOUNDED_TYPES:
        geometry["bounding_box"] = None
        try:
            bounds = bbox.extents([entity])
        except (ArithmeticError, DXFError, ValueError):
            warnings.append("bounding_box_unavailable")
        else:
            if bounds.has_data and all(
                math.isfinite(value) for point in (bounds.extmin, bounds.extmax) for value in point
            ):
                geometry["bounding_box"] = {
                    "min": list(bounds.extmin),
                    "max": list(bounds.extmax),
                    "space": coordinates["owner_space"],
                    "approximate": dtype != "LINE",
                }
            else:
                warnings.append("bounding_box_unavailable")
    geometry.setdefault("warnings", []).extend(warnings)
