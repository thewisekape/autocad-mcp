import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from autocad_mcp.backends.base import CommandResult
from autocad_mcp.data_router import data_capabilities, read_cad_data


class TableBackend:
    name = "com"

    async def query_tables(self, layout=None, entity_id=None):
        return CommandResult(ok=True, payload={"layout": layout, "entity_id": entity_id, "tables": []})


@pytest.mark.asyncio
async def test_table_route_keeps_successful_empty_result():
    result = await read_cad_data(TableBackend(), "query.tables", layout="Model", entity_id="AB")
    assert result.ok
    assert result.payload == {"layout": "Model", "entity_id": "AB", "tables": []}


@pytest.mark.asyncio
async def test_mcp_query_exposes_table_and_dxf_view_operations(monkeypatch):
    from autocad_mcp import client, server
    from autocad_mcp.backends.ezdxf_backend import EzdxfBackend

    monkeypatch.setattr(client, "_backend", TableBackend())
    result = json.loads(await server.query(operation="tables", data={"layout": "Model"}))
    assert result == {"ok": True, "payload": {"layout": "Model", "entity_id": None, "tables": []}}

    backend = EzdxfBackend()
    assert (await backend.initialize()).ok
    monkeypatch.setattr(client, "_backend", backend)
    result = json.loads(await server.query(operation="view_regions", data={"frame_layer": "FRAME"}))
    assert result["ok"] and result["payload"]["regions"] == []


@pytest.mark.asyncio
async def test_table_route_fails_explicitly_on_offline_backend():
    from autocad_mcp.backends.ezdxf_backend import EzdxfBackend

    result = await read_cad_data(EzdxfBackend(), "query.tables")
    assert not result.ok
    assert "supported backends: com" in result.error
    assert data_capabilities()["query.tables"]["fallback"] == "none"


def test_document_schema_keeps_measurement_and_display_text_separate():
    path = Path(__file__).resolve().parents[1] / "docs" / "cad-document.v1.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    dimension = {
        "source": {"file": "fixture.dxf", "handle": "A2", "layout": "Model", "nested_path": []},
        "entity_type": "DIMENSION",
        "layer": "0",
        "coordinate_system": "WCS",
        "data": {},
        "kind": "source_fact",
        "extraction_method": "dxf",
        "validation_status": "partial",
        "measurement": 1.125,
        "display_text": None,
    }
    document = {
        "schema_version": "1.0.0",
        "file": {"path": "fixture.dxf", "format": "DXF"},
        "layouts": ["Model"],
        "entities": [dimension],
    }
    validator.validate(document)
    dimension["confidence"] = 0.8
    with pytest.raises(ValidationError):
        validator.validate(document)
