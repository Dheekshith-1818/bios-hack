import pytest
import httpx
from backend.main import app

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_api_health():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Check landing page
        index_res = await client.get("/")
        assert index_res.status_code == 200
        assert "CivicGuard Autopilot" in index_res.text
        assert "importmap" in index_res.text

        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "CivicGuard Autopilot"

@pytest.mark.anyio
async def test_api_public_config():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/config/public")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "canarySampleWindows" in data

@pytest.mark.anyio
async def test_api_graph_and_state():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res_graph = await client.get("/api/graph")
        assert res_graph.status_code == 200
        g_data = res_graph.json()
        assert "nodes" in g_data
        assert "edges" in g_data

        res_state = await client.get("/api/state")
        assert res_state.status_code == 200
        s_data = res_state.json()
        assert "activeScenario" in s_data
        assert "summaries" in s_data

@pytest.mark.anyio
async def test_api_simulations_controls():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        p_res = await client.post("/api/simulations/pause")
        assert p_res.status_code == 200
        assert p_res.json()["is_paused"] is True

        r_res = await client.post("/api/simulations/resume")
        assert r_res.status_code == 200
        assert r_res.json()["is_paused"] is False

        s_res = await client.post("/api/simulations/speed", json={"speed": 2.5})
        assert s_res.status_code == 200
        assert s_res.json()["speed"] == 2.5

        reset_res = await client.post("/api/simulations/reset")
        assert reset_res.status_code == 200

@pytest.mark.anyio
async def test_api_audit_and_evaluation():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        a_res = await client.get("/api/audit")
        assert a_res.status_code == 200
        assert isinstance(a_res.json(), list)

        v_res = await client.get("/api/audit/verify")
        assert v_res.status_code == 200
        assert "valid" in v_res.json()

        e_res = await client.get("/api/evaluation/latest")
        assert e_res.status_code == 200
        assert "measured" in e_res.json()
        assert "targets" in e_res.json()

@pytest.mark.anyio
async def test_api_auth_lifecycle():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Login with demo SRE lead credentials
        res = await client.post("/api/auth/login", json={"username": "sre_lead", "password": "civicguard2026"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["user"]["role"] == "operator"
        token = data["user"]["token"]

        # 2. Check current user with token
        me_res = await client.get(f"/api/auth/me?token={token}")
        assert me_res.status_code == 200
        assert me_res.json()["authenticated"] is True
        assert me_res.json()["user"]["username"] == "sre_lead"

        # 3. Logout
        logout_res = await client.post(f"/api/auth/logout?token={token}")
        assert logout_res.status_code == 200
        assert logout_res.json()["success"] is True

        # 4. Verify logged out
        me_after = await client.get(f"/api/auth/me?token={token}")
        assert me_after.json()["authenticated"] is False
