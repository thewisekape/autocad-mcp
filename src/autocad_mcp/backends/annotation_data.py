"""Annotation source fields and conservative text normalization."""

from __future__ import annotations

from math import degrees
from typing import Any

from ezdxf.lldxf.const import DXFError
from ezdxf.tools.text import plain_mtext, plain_text


# DXF dimension-style values governing measured units and displayed formatting.
STYLE_FIELDS = (
    "dimlfac", "dimscale", "dimdec", "dimlunit", "dimadec", "dimaunit",
    "dimrnd", "dimzin", "dimazin", "dimdsep", "dimpost", "dimalt", "dimaltf",
    "dimaltd", "dimaltu", "dimapost", "dimtol", "dimlim", "dimtp", "dimtm",
)


def extract_dxf_annotation(entity: Any, *, owner_space: str | None = "WCS") -> dict:
    kind = entity.dxftype()
    attrs = entity.dxf
    if kind == "MTEXT":
        return {"annotation": {
            "raw_text": entity.text,
            "normalized_text": entity.plain_text(fast=False),
            "insertion_point": list(attrs.insert),
            "insertion_coordinate_system": owner_space,
            "rotation_degrees": entity.get_rotation(),
            "height": attrs.char_height,
            "style": attrs.style,
            "alignment": {"attachment_point": attrs.attachment_point},
        }}
    if kind == "TEXT":
        return {"annotation": {
            "raw_text": attrs.text,
            "normalized_text": entity.plain_text(),
            "insertion_point": list(attrs.insert),
            "insertion_coordinate_system": "OCS",
            "rotation_degrees": attrs.rotation,
            "height": attrs.height,
            "style": attrs.style,
            "alignment": {"horizontal": attrs.halign, "vertical": attrs.valign},
        }}
    if kind != "DIMENSION":
        return {}

    try:
        style = entity.override()
        settings = {field: style.get(field) for field in STYLE_FIELDS}
        overrides = {field: style.dimstyle_attribs[field] for field in STYLE_FIELDS if field in style.dimstyle_attribs}
    except DXFError:
        settings = {}
        overrides = {}
    return {"annotation": {
        "dimension_type": entity.dimtype,
        "measurement": attrs.get("actual_measurement"),
        "measurement_method": "DXF actual_measurement tag" if attrs.hasattr("actual_measurement") else None,
        "text_override": attrs.text,
        "dimension_style": attrs.dimstyle,
        "style_settings": settings,
        "style_overrides": overrides,
        "definition_coordinate_system": owner_space,
        "definition_points": {
            field: list(attrs.get(field))
            for field in ("defpoint", "defpoint2", "defpoint3", "defpoint4")
            if attrs.hasattr(field)
        },
        "text_position_ocs": list(attrs.text_midpoint) if attrs.hasattr("text_midpoint") else None,
        "display_value": None,
        "warnings": ["Rendered dimension text and associations are unavailable."]
        + (["Dimension style settings are unavailable."] if not settings else []),
    }}


def _com_value(entity: Any, field: str) -> Any:
    try:
        value = getattr(entity, field)
    except Exception:
        return None
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return None


def extract_com_annotation(entity: Any) -> dict:
    kind = entity.ObjectName
    if kind in ("AcDbText", "AcDbMText"):
        raw = _com_value(entity, "TextString")
        mtext = kind == "AcDbMText"
        rotation = _com_value(entity, "Rotation")
        return {"annotation": {
            "raw_text": raw,
            "normalized_text": (plain_mtext(raw) if mtext else plain_text(raw)) if isinstance(raw, str) else None,
            "insertion_point": _com_value(entity, "InsertionPoint"),
            "insertion_coordinate_system": "WCS",
            "rotation_degrees": degrees(rotation) if rotation is not None else None,
            "height": _com_value(entity, "Height"),
            "style": _com_value(entity, "StyleName"),
            "alignment": (
                {"attachment_point": _com_value(entity, "AttachmentPoint")} if mtext
                else {"alignment": _com_value(entity, "Alignment")}
            ),
        }}
    if not (kind.startswith("AcDb") and kind.endswith("Dimension")):
        return {}

    measurement = _com_value(entity, "Measurement")
    return {"annotation": {
        "dimension_type": kind,
        "measurement": measurement,
        "measurement_method": "ActiveX Measurement" if measurement is not None else None,
        "text_override": _com_value(entity, "TextOverride"),
        "dimension_style": _com_value(entity, "StyleName"),
        "style_settings": {
            key: _com_value(entity, field)
            for key, field in {
                "dimlfac": "LinearScaleFactor", "dimscale": "ScaleFactor",
                "dimdec": "PrimaryUnitsPrecision", "dimlunit": "UnitsFormat",
                "dimadec": "TextPrecision", "dimaunit": "AngleFormat",
            }.items()
        },
        "text_position": _com_value(entity, "TextPosition"),
        "display_value": None,
        "warnings": ["Rendered dimension text and associations are unavailable."],
    }}
