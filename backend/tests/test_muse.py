"""Unified screenshot uploads through the real Muse SDK using a mocked provider transport."""

import asyncio
import base64
import io
import json

import httpx
import pytest
import test_unified as session_tests
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from PIL import Image
from tandem import config, grid, vision


@pytest.fixture
def muse_setup(tmp_path, monkeypatch):
    yield from session_tests.setup.__wrapped__(tmp_path, monkeypatch)


def screenshot():
    image = Image.new("RGB", (194, 129), "white")
    colors = ["red", "green", "blue", "purple", "orange", "brown"]
    for i, color in enumerate(colors):
        image.paste(color, (65 * (i % 3), 65 * (i // 3), 65 * (i % 3) + 64, 65 * (i // 3) + 64))
    data = io.BytesIO()
    image.save(data, "PNG")
    return data.getvalue()


def completion(content):
    return {
        "id": "test",
        "object": "chat.completion",
        "created": 1,
        "model": "muse-spark-1.3",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
    }


def provider(monkeypatch, handler):
    clients = []

    def client():
        value = AsyncOpenAI(
            api_key="test-only",
            base_url=config.MUSE_BASE_URL,
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        clients.append(value)
        return value

    monkeypatch.setenv("MUSE_API_KEY", "test-only")
    monkeypatch.setattr(vision, "_client", client)
    return clients


def test_unified_upload_splits_tiles_and_uses_muse_contract(muse_setup, monkeypatch):
    factory, store, _ = muse_setup
    requests = []
    data = screenshot()
    assert len(grid.split_explore(data)) == 6

    def reply(request):
        assert str(request.url) == "https://api.meta.ai/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "muse-spark-1.3"
        assert body["reasoning_effort"] == "low" and body["max_tokens"] == 4096
        assert body["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "feed_tags", "schema": vision.SCHEMA},
        }
        message = body["messages"][0]
        assert message["role"] == "user"
        uri = message["content"][0]["image_url"]["url"]
        assert uri.startswith("data:image/png;base64,")
        assert Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).size == (64, 64)
        requests.append(True)
        result = {"is_ad_or_noise": len(requests) == 1, "tags": [{"tag": "cozy", "weight": 0.8}]}
        return httpx.Response(200, json=completion(json.dumps(result)))

    clients = provider(monkeypatch, reply)
    with TestClient(factory()) as c:
        response = c.post(
            "/feeds",
            headers={"Authorization": "Bearer a"},
            files={"files": ("explore.png", data, "image/png")},
        )
        assert response.status_code == 200
        out = response.json()
        assert len(requests) == 6 and out["dropped_as_noise"] == 1
        assert out["tags"] == {"cozy": 0.8}
        assert store.get_feed(out["feed_id"])["user"] == "a"
        assert c.get("/health").json()["vision"] is True
    assert all(client.is_closed() for client in clients)


@pytest.mark.parametrize(
    "content",
    ['```json\n{"is_ad_or_noise":false,"tags":[]}\n```', "not json", '{"tags":null}', "[]"],
)
def test_provider_reply_parsing_and_default_reasoning_omission(monkeypatch, content):
    monkeypatch.setattr(config, "MUSE_REASONING", "")

    def reply(request):
        assert "reasoning_effort" not in json.loads(request.content)
        return httpx.Response(200, json=completion(content))

    clients = provider(monkeypatch, reply)
    result = asyncio.run(vision.read_screenshots([(b"synthetic", "image/png")]))
    assert result == ([(False, {})] if content.startswith("```") else [(True, {})])
    assert all(client.is_closed() for client in clients)


def test_missing_muse_key_reports_configuration_and_manual_tags_still_work(muse_setup, monkeypatch):
    factory, _, _ = muse_setup
    monkeypatch.delenv("MUSE_API_KEY", raising=False)
    monkeypatch.setenv("LLAMA_API_KEY", "old-name-is-not-used")
    with TestClient(factory()) as c:
        headers = {"Authorization": "Bearer a"}
        response = c.post(
            "/feeds", headers=headers, files={"files": ("plain.png", b"plain", "image/png")}
        )
        assert response.status_code == 503 and "MUSE_API_KEY" in response.json()["detail"]
        assert c.post("/feeds", headers=headers, data={"tags": '{"cozy":1}'}).status_code == 200


def test_provider_failure_is_retryable_and_does_not_create_feed(muse_setup, monkeypatch):
    factory, store, _ = muse_setup

    def unavailable(request):
        return httpx.Response(503, json={"error": {"message": "provider unavailable"}})

    provider(monkeypatch, unavailable)
    with TestClient(factory()) as c:
        response = c.post(
            "/feeds",
            headers={"Authorization": "Bearer a"},
            files={"files": ("plain.png", b"plain", "image/png")},
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "Muse vision unavailable; retry or send tags instead"
        assert store.latest_feed("a") is None
