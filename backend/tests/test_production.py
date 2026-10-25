"""Production origin and user-id auth wiring."""

from pathlib import Path

import pytest
import test_unified as sessions
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from tandem import config

ORIGIN = "https://filmocracy.party"


@pytest.fixture
def sqlite_setup(tmp_path, monkeypatch):
    yield from sessions.setup.__wrapped__(tmp_path, monkeypatch)


@pytest.fixture
def production_client(sqlite_setup, monkeypatch):
    factory, _, _ = sqlite_setup
    monkeypatch.setenv("FRONTEND_ORIGINS", ORIGIN)
    monkeypatch.setattr(config, "DEV_AUTH", False)
    app = factory()
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        yield client


def test_production_origin_and_user_id_wiring(production_client):
    client = production_client
    preflight = client.options(
        "/sessions",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ORIGIN
    bad = client.options(
        "/sessions",
        headers={
            "Origin": "https://unrelated.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert bad.status_code == 400 and "access-control-allow-origin" not in bad.headers
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer not an id"}).status_code == 401
    assert client.get("/me", headers={"Authorization": f"Bearer {'x' * 65}"}).status_code == 401
    response = client.get("/me", headers={"Authorization": "Bearer host", "Origin": ORIGIN})
    assert response.status_code == 200 and response.json()["user"] == "host"
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_production_socket_origin_auth_and_session_ownership(production_client):
    client = production_client
    made = client.post(
        "/sessions", headers={"Authorization": "Bearer host"}, json={"display_name": "TV"}
    )
    assert made.status_code == 200
    sid = made.json()["session_id"]
    path = f"/sessions/{sid}/ws"
    with client.websocket_connect(path, headers={"Origin": ORIGIN}) as ws:
        ws.send_json({"type": "auth", "token": "host"})
        assert ws.receive_json()["state"]["session"]["host_user_id"] == "host"
    for token, code in [("not an id", 4401), ("other", 4403)]:
        with client.websocket_connect(path, headers={"Origin": ORIGIN}) as ws:
            ws.send_json({"type": "auth", "token": token})
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == code
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path, headers={"Origin": "https://unrelated.example"}):
            pass
    assert (
        client.get(f"/sessions/{sid}", headers={"Authorization": "Bearer other"}).status_code
        == 404
    )


def test_railway_refuses_fake_encoder(sqlite_setup, monkeypatch):
    factory, _, _ = sqlite_setup
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "production-simulation")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "/data")
    monkeypatch.setattr(config, "DATA_DIR", Path("/data"))
    monkeypatch.setattr(config, "DEV_AUTH", False)
    monkeypatch.setattr(config, "FAKE_ENCODER", True)
    with pytest.raises(RuntimeError, match="TANDEM_FAKE_ENCODER"):
        with TestClient(factory()):
            pass
