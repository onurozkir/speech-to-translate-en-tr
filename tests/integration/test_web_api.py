import pytest
from fastapi.testclient import TestClient
from teams_translator.config.loader import load_config
from teams_translator.streaming.orchestrator import MeetingOrchestrator
from teams_translator.web.server import create_app


def test_web_api_endpoints():
    config = load_config()
    orchestrator = MeetingOrchestrator(config=config, use_mocks=True)
    app = create_app(orchestrator)
    client = TestClient(app)

    # Test status endpoint
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "system" in data
    assert "error" in data

    # Test devices endpoint
    res = client.get("/api/devices")
    assert res.status_code == 200
    assert "devices" in res.json()
    for device in res.json()["devices"]:
        assert "stable_id" in device
        assert "host_api" in device
        assert "max_input_channels" in device
        assert "roles" in device

    res = client.get("/api/audio/diagnostics")
    assert res.status_code == 200
    diagnostics = res.json()
    assert "resolved" in diagnostics
    assert "outgoing" in diagnostics
    assert "incoming" in diagnostics

    # Test profiles endpoint
    res = client.get("/api/profiles")
    assert res.status_code == 200
    profiles = res.json()["profiles"]
    assert len(profiles) >= 1
    assert "target_languages" in profiles[0]

    # Test switch voice and language endpoints
    res = client.post("/api/meeting/switch_voice", json={"profile_id": profiles[0]["id"]})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res = client.post("/api/meeting/switch_language", json={"target_language": "fr"})
    assert res.status_code == 200
    assert res.json()["target_language"] == "fr"

    res = client.post("/api/meeting/switch_language", json={"target_language": "unsupported"})
    assert res.status_code == 400
