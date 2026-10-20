import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.transcription import api, deepgram
from app.transcription.provider import ProviderError, TranscriptEvent, get_provider


class FakeConnection:
    def __init__(self):
        self.events = asyncio.Queue()
        self.audio = []
        self.closed = False
        self.finished = False
        self.fail = False

    async def send_audio(self, pcm):
        if self.fail:
            raise RuntimeError("sensitive upstream error")
        self.audio.append(pcm)
        await self.events.put(TranscriptEvent(0, "Example interim", False))
        await self.events.put(TranscriptEvent(0, "Example final.", True))

    async def receive(self):
        return await self.events.get()

    async def keepalive(self):
        pass

    async def finish(self):
        self.finished = True
        await self.events.put(TranscriptEvent(1000, "Last words.", True))
        # Blocked provider reads are cancelled by the bounded final flush.

    async def close(self):
        self.closed = True


@pytest.fixture
def streaming(client, monkeypatch):
    connection = FakeConnection()

    class Provider:
        async def connect(self):
            return connection

    monkeypatch.setattr(api, "session_valid", lambda app, token: token == "a" * 43)
    monkeypatch.setattr(api, "get_provider", lambda settings: Provider())
    return SimpleNamespace(client=client, connection=connection)


def open_stream(setup, source="system", **kwargs):
    return setup.client.websocket_connect(
        "/api/transcription/stream?source=" + source,
        headers={"Authorization": "Bearer " + "a" * 43, **kwargs},
    )


@pytest.mark.parametrize("source", ["system", "microphone"])
def test_ready_audio_interim_final_and_cleanup(streaming, source):
    with open_stream(streaming, source) as socket:
        assert socket.receive_json() == {"type": "ready", "source": source}
        socket.send_bytes(bytes(640))
        interim, final = socket.receive_json(), socket.receive_json()
        assert interim["source"] == final["source"] == source
        assert interim["segment"] == final["segment"] == 0
        assert interim["final"] is False and final["final"] is True
        assert interim["text"] == "Example interim" and final["text"] == "Example final."
        socket.send_text('{"type":"finish"}')
        assert socket.receive_json()["text"] == "Last words."
        assert socket.receive_json() == {"type": "done"}
    assert streaming.connection.closed and streaming.connection.finished
    assert streaming.connection.audio == [bytes(640)]


def test_authentication_required_without_browser_cookie_fallback(streaming):
    with streaming.client.websocket_connect("/api/transcription/stream?source=system") as socket:
        event = socket.receive_json()
        assert event["type"] == "error" and event["retryable"] is False
    assert not streaming.connection.audio


def test_revoked_session_does_not_open_provider(streaming, monkeypatch):
    monkeypatch.setattr(api, "session_valid", lambda app, token: False)
    with open_stream(streaming) as socket:
        assert "revoked" in socket.receive_json()["message"]
    assert not streaming.connection.audio


def test_browser_origin_rejected(streaming):
    with open_stream(streaming, Origin="http://127.0.0.1:5173") as socket:
        assert socket.receive_json()["type"] == "error"


def test_invalid_source_rejected(streaming):
    with open_stream(streaming, "other") as socket:
        assert socket.receive_json()["message"] == "Invalid transcription source."


@pytest.mark.parametrize("packet", [b"", b"a", bytes(6402)])
def test_invalid_audio_rejected(streaming, packet):
    with open_stream(streaming) as socket:
        socket.receive_json()
        socket.send_bytes(packet)
        event = socket.receive_json()
        assert event["type"] == "error" and event["retryable"] is False
    assert streaming.connection.closed


def test_upstream_error_is_sanitized(streaming):
    streaming.connection.fail = True
    with open_stream(streaming) as socket:
        socket.receive_json()
        socket.send_bytes(bytes(640))
        event = socket.receive_json()
        assert event["retryable"] is True
        assert "sensitive" not in json.dumps(event)


def test_disconnect_closes_provider(streaming):
    with open_stream(streaming) as socket:
        socket.receive_json()
    assert streaming.connection.closed


def test_missing_configuration_without_external_requests(client, monkeypatch):
    monkeypatch.setattr(api, "session_valid", lambda app, token: True)
    with client.websocket_connect(
        "/api/transcription/stream?source=system", headers={"Authorization": "Bearer " + "a" * 43}
    ) as socket:
        event = socket.receive_json()
        assert "GEMINI_API_KEY" in event["message"] and event["retryable"] is False


def test_normalization_handles_provider_metadata_empty_final_and_invalid_values():
    payload = {
        "type": "Results",
        "start": 0.32,
        "is_final": False,
        "channel": {"alternatives": [{"transcript": " example "}]},
    }
    event = deepgram.parse_event(json.dumps(payload))
    assert event == TranscriptEvent(320, "example", False)
    payload["is_final"] = True
    payload["channel"]["alternatives"][0]["transcript"] = ""
    assert deepgram.parse_event(json.dumps(payload)).final
    assert deepgram.parse_event('{"type":"Metadata"}') is None
    payload["start"] = -1
    with pytest.raises(ProviderError):
        deepgram.parse_event(json.dumps(payload))


def test_provider_wire_configuration_is_private_and_streaming(settings, monkeypatch):
    settings = settings.model_copy(
        update={
            "transcription_provider": "deepgram",
            "deepgram_api_key": SecretStr("test-only-provider-key"),
        }
    )
    captured = {}

    class Socket:
        async def close(self):
            pass

    async def connect(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Socket()

    monkeypatch.setattr(deepgram, "connect", connect)
    connection = asyncio.run(get_provider(settings).connect())
    assert "interim_results=true" in captured["url"] and "mip_opt_out=true" in captured["url"]
    assert "sample_rate=16000" in captured["url"] and "channels=1" in captured["url"]
    assert "test-only-provider-key" not in captured["url"]
    assert captured["logger"].propagate is False
    asyncio.run(connection.close())


def test_live_stream_rechecks_session_and_revokes_access(streaming, monkeypatch):
    checks = iter([True, False])
    monkeypatch.setattr(api, "session_valid", lambda app, token: next(checks))
    monkeypatch.setattr(api, "KEEPALIVE_SECONDS", 0.01)
    monkeypatch.setattr(api, "AUTH_RECHECK_SECONDS", 0)
    with open_stream(streaming) as socket:
        assert socket.receive_json()["type"] == "ready"
        event = socket.receive_json()
        assert "revoked" in event["message"] and not event["retryable"]
    assert streaming.connection.closed
