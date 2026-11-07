"""Read structured native AutoCAD table data via the ActiveX table interface."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def read_table(
    table: Any,
    layout: str,
    source_file: str,
    cell_merge: Callable[[Any, int, int], tuple[int, int, int, int] | None],
) -> dict:
    rows, columns = table.Rows, table.Columns
    warnings = []
    cells = []
    ranges: set[tuple[int, int, int, int]] = set()
    merge_available = True

    for row in range(rows):
        texts = []
        for col in range(columns):
            try:
                value = table.GetText(row, col)
                if not isinstance(value, str):
                    raise TypeError("Expected a COM string")
                texts.append(value)
            except Exception:
                texts.append(None)
                warnings.append(f"Cell text unavailable at ({row}, {col})")
            if merge_available:
                try:
                    bounds = cell_merge(table, row, col)
                    if bounds is not None:
                        ranges.add(bounds)
                except Exception:
                    warnings.append("Cell merge information unavailable")
                    merge_available = False
        cells.append(texts)

    def optional_property(name: str, convert: Callable) -> Any:
        try:
            return convert(getattr(table, name))
        except Exception:
            warnings.append(f"Table property unavailable: {name}")
            return None

    return {
        "handle": table.Handle,
        "layer": table.Layer,
        "layout": layout,
        "source_file": source_file,
        "rows": rows,
        "columns": columns,
        "insertion_point": optional_property("InsertionPoint", list),
        "style": optional_property("StyleName", str),
        "cells": cells,
        "merged_ranges": [
            {"min_row": min_row, "max_row": max_row, "min_col": min_col, "max_col": max_col}
            for min_row, max_row, min_col, max_col in sorted(ranges)
        ] if merge_available else None,
        "validation_status": "partial" if warnings else "complete",
        "warnings": warnings,
    }
