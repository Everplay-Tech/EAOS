import pytest
from httpx import AsyncClient

from matrix.models import Msg


@pytest.mark.real_http
@pytest.mark.asyncio
async def test_tls_roundtrip_with_auth_header(mesh_server, tls_materials, agent_state):
    payload = Msg(origin="suite", target="osteon", intent="draft", input={"goal": "test"})

    async with AsyncClient(base_url=mesh_server, verify=tls_materials.ca_path) as client:
        response = await client.post(
            "/osteon/draft",
            json=payload.model_dump(),
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert agent_state["authorization"] == "Bearer secret-token"


@pytest.mark.real_http
@pytest.mark.asyncio
async def test_error_propagation(mesh_server, tls_materials):
    payload = Msg(origin="suite", target="osteon", intent="error", input={})

    async with AsyncClient(base_url=mesh_server, verify=tls_materials.ca_path) as client:
        response = await client.post("/osteon/error", json=payload.model_dump())

    assert response.status_code == 418
    assert response.json() == {"detail": "brew failure", "id": payload.id}
