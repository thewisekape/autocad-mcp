"""AutoCAD ActiveX WCS bounds with the shared spatial query rules."""

import asyncio
from time import monotonic

from ezdxf.math import BoundingBox

from autocad_mcp.backends.base import CommandResult
from autocad_mcp.backends.dxf_export import com_entity_type
from autocad_mcp.backends.dxf_spatial import SpatialScan


def is_busy(error):
    code = getattr(error, "hresult", None)
    return isinstance(code, int) and code & 0xFFFFFFFF in (0x80010001, 0x8001010A)


class COMScan(SpatialScan):
    box_method = "autocad_get_bounding_box"
    is_retryable = staticmethod(is_busy)

    @staticmethod
    def iter_layout(doc, layout_name):
        if layout_name is None:
            return ((entity, "Model") for entity in doc.ModelSpace)
        if not isinstance(layout_name, str) or not layout_name:
            raise ValueError("layout must be a nonempty layout name")
        for layout in doc.Layouts:
            name = "Model" if layout.ModelType else layout.Name
            if name.casefold() == layout_name.casefold():
                return ((entity, name) for entity in layout.Block)
        raise ValueError(f"Layout {layout_name!r} not found")

    @staticmethod
    def find_entity(doc, handle):
        return doc.HandleToObject(handle)

    @staticmethod
    def metadata(entity):
        name = entity.ObjectName
        return entity.Handle, com_entity_type(name) or name, entity.Layer

    @staticmethod
    def extents(entity):
        import pythoncom
        import win32com.client

        dispatch = win32com.client.dynamic.DumbDispatch(entity._oleobj_)
        minimum, maximum = (
            win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None)
            for _ in range(2)
        )
        dispatch.GetBoundingBox(minimum, maximum)
        return BoundingBox((minimum.value, maximum.value))


async def run_spatial(app, doc, operation, *args, retry_timeout=3.0, **options):
    if app is None or doc is None:
        return CommandResult(ok=False, error="No AutoCAD drawing is connected")
    deadline = monotonic() + retry_timeout
    retries = 0
    while True:
        try:
            if app.GetAcadState().IsQuiescent:
                payload = operation(doc, *args, scan=COMScan(), **options)
                payload["diagnostics"]["busy_retries"] = retries
                return CommandResult(ok=True, payload=payload)
        except Exception as exc:
            if not is_busy(exc):
                return CommandResult(ok=False, error=f"AutoCAD spatial query failed: {exc}")
        if monotonic() >= deadline:
            return CommandResult(ok=False, error=f"AutoCAD busy after {retries} spatial retries ({retry_timeout:g}s limit)")
        retries += 1
        await asyncio.sleep(min(0.2, max(0, deadline - monotonic())))
