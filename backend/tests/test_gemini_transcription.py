import asyncio
import base64
import json
from collections import deque

import pytest
from pydantic import SecretStr

from app.transcription import deepgram, gemini
from app.transcription.provider import ProviderError, get_provider


class Socket:
    def __init__(self, events=()):
        self.events = deque(events)
        self.sent = []
        self.closed = False

    async def send(self, value):
        self.sent.append(json.loads(value))

    async def recv(self):
        return json.dumps(self.events.popleft())

    async def ping(self):
        pass

    async def close(self):
        self.closed = True


def run(awaitable):
    return asyncio.run(awaitable)


def test_gemini_default_setup_and_no_deepgram(settings, monkeypatch):
    assert settings.transcription_provider == "gemini"
    assert settings.gemini_transcribe_model == "gemini-3.5-transcribe-live"
    settings.gemini_api_key = SecretStr("fake-test-only")
    socket = Socket([{"setupComplete": {}}])
    captured = {}

    async def connect(url, **kwargs):
        captured.update(url=url, **kwargs)
        return socket

    async def forbidden(*args, **kwargs):
        pytest.fail("Deepgram must remain dormant")

    monkeypatch.setattr(gemini, "connect", connect)
    monkeypatch.setattr(deepgram, "connect", forbidden)
    connection = run(get_provider(settings).connect())
    assert isinstance(connection, gemini.GeminiConnection)
    setup = socket.sent[0]["setup"]
    assert setup["model"] == "models/gemini-3.5-transcribe-live"
    assert setup["generationConfig"]["responseModalities"] == ["TEXT"]
    assert setup["inputAudioTranscription"]["mode"] == "VERBATIM"
    assert "Salesforce" in setup["inputAudioTranscription"]["customVocabulary"]
    assert captured["max_queue"] == 8 and not captured["logger"].propagate
    run(connection.close())
    assert socket.closed


def test_interim_final_and_fragmented_finals_have_stable_distinct_identity():
    socket = Socket(
        [
            {"serverContent": {"interimInputTranscription": {"text": "Tell me"}}},
            {
                "serverContent": {
                    "interimInputTranscription": {"text": "Tell me about an integration"}
                }
            },
            {"serverContent": {"inputTranscription": {"text": "Tell me about an integration."}}},
            {"serverContent": {"inputTranscription": {"text": "And challenges you faced."}}},
        ]
    )
    connection = gemini.GeminiConnection(socket)
    events = [run(connection.receive()) for _ in range(4)]
    assert events[0].segment == events[1].segment == events[2].segment
    assert events[3].segment > events[2].segment
    assert [event.final for event in events] == [False, False, True, True]
    assert events[3].text == "And challenges you faced."


def test_both_sources_have_independent_provider_state():
    system = gemini.GeminiConnection(Socket())
    mic = gemini.GeminiConnection(Socket())
    system.normalize({"serverContent": {"interimInputTranscription": {"text": "Them"}}})
    mic.normalize({"serverContent": {"inputTranscription": {"text": "You"}}})
    assert system.events[0].text == "Them" and not system.events[0].final
    assert mic.events[0].text == "You" and mic.events[0].final
    assert system.segment is not None and mic.segment is None


def test_batched_pcm_flush_and_cleanup():
    socket = Socket()
    connection = gemini.GeminiConnection(socket)
    for _ in range(6):
        run(connection.send_audio(bytes(640)))
    assert len(socket.sent) == 1
    audio = socket.sent[0]["realtimeInput"]["audio"]
    assert audio["mimeType"] == "audio/pcm;rate=16000"
    assert base64.b64decode(audio["data"]) == bytes(3200)
    run(connection.finish())
    assert base64.b64decode(socket.sent[1]["realtimeInput"]["audio"]["data"]) == bytes(640)
    assert socket.sent[-1] == {"realtimeInput": {"audioStreamEnd": True}}
    run(connection.close())
    assert not connection.pending and not connection.events and socket.closed


@pytest.mark.parametrize(
    "payload",
    ["bad", "[]", '{"serverContent":[]}', '{"serverContent":{"inputTranscription":{"text":4}}}'],
)
def test_malformed_event_is_sanitized(payload):
    connection = gemini.GeminiConnection(Socket())
    with pytest.raises(ProviderError, match="malformed"):
        connection.normalize(gemini.decode(payload))


@pytest.mark.parametrize("code", [401, 403, 429])
def test_auth_quota_do_not_reconnect_or_fallback(code):
    with pytest.raises(ProviderError) as problem:
        gemini.decode(json.dumps({"error": {"code": code, "message": "private upstream content"}}))
    assert not problem.value.retryable
    assert "private" not in str(problem.value)


def test_renewal_and_goaway_request_reconnect_without_audio_replay():
    connection = gemini.GeminiConnection(Socket())
    connection.began -= 600
    with pytest.raises(ProviderError) as problem:
        run(connection.keepalive())
    assert problem.value.retryable
    with pytest.raises(ProviderError):
        connection.normalize({"goAway": {"timeLeft": "2s"}})
    run(connection.close())
    replacement = gemini.GeminiConnection(Socket())
    assert not replacement.pending and not replacement.events


def test_setup_failure_closes_socket_and_never_leaks_provider_text(settings, monkeypatch):
    settings.gemini_api_key = SecretStr("fake-test-only")
    socket = Socket([{"error": {"code": 429, "message": "private"}}])

    async def connect(*args, **kwargs):
        return socket

    monkeypatch.setattr(gemini, "connect", connect)
    with pytest.raises(ProviderError) as problem:
        run(get_provider(settings).connect())
    assert socket.closed and not problem.value.retryable
    assert "private" not in str(problem.value)


def test_network_failure_is_retryable_without_fallback(settings, monkeypatch):
    settings.gemini_api_key = SecretStr("fake-test-only")

    async def connect(*args, **kwargs):
        raise OSError("private")

    monkeypatch.setattr(gemini, "connect", connect)
    with pytest.raises(ProviderError) as problem:
        run(get_provider(settings).connect())
    assert problem.value.retryable and "private" not in str(problem.value)


@pytest.mark.parametrize("source", ["system", "microphone"])
def test_gemini_selected_through_authenticated_relay(client, settings, monkeypatch, source):
    from app.transcription import api

    settings.gemini_api_key = SecretStr("fake-test-only")
    events = asyncio.Queue()
    instances = []

    class LiveSocket(Socket):
        async def send(self, value):
            await super().send(value)
            message = self.sent[-1]
            if "setup" in message:
                await events.put({"setupComplete": {}})
            elif "audio" in message.get("realtimeInput", {}):
                await events.put(
                    {"serverContent": {"interimInputTranscription": {"text": "Example"}}}
                )
                await events.put(
                    {"serverContent": {"inputTranscription": {"text": "Example final."}}}
                )

        async def recv(self):
            return json.dumps(await events.get())

    async def connect(*args, **kwargs):
        socket = LiveSocket()
        instances.append(socket)
        return socket

    async def forbidden(*args, **kwargs):
        pytest.fail("Deepgram connection during Gemini session")

    monkeypatch.setattr(gemini, "connect", connect)
    monkeypatch.setattr(deepgram, "connect", forbidden)
    monkeypatch.setattr(api, "session_valid", lambda app, token: True)
    with client.websocket_connect(
        "/api/transcription/stream?source=" + source,
        headers={"Authorization": "Bearer " + "a" * 43},
    ) as socket:
        assert socket.receive_json() == {"type": "ready", "source": source}
        socket.send_bytes(bytes(3200))
        interim, final = socket.receive_json(), socket.receive_json()
        assert interim["source"] == final["source"] == source
        assert interim["segment"] == final["segment"]
        assert not interim["final"] and final["final"]
    assert len(instances) == 1 and instances[0].closed


def test_setup_timeout_closes_connection(settings, monkeypatch):
    settings.gemini_api_key = SecretStr("fake-test-only")

    class TimedOut(Socket):
        async def recv(self):
            raise TimeoutError()

    socket = TimedOut()

    async def connect(*args, **kwargs):
        return socket

    monkeypatch.setattr(gemini, "connect", connect)
    with pytest.raises(ProviderError) as problem:
        run(get_provider(settings).connect())
    assert problem.value.retryable and socket.closed


def test_disconnect_is_retryable_but_policy_close_is_terminal():
    from websockets.exceptions import ConnectionClosedError
    from websockets.frames import Close

    class Disconnected(Socket):
        def __init__(self, code):
            super().__init__()
            self.code = code

        async def recv(self):
            raise ConnectionClosedError(Close(self.code, "private"), None)

    for code, retryable in [(1011, True), (1008, False)]:
        connection = gemini.GeminiConnection(Disconnected(code))
        with pytest.raises(ProviderError) as problem:
            run(connection.receive())
        assert problem.value.retryable is retryable
        assert "private" not in str(problem.value)


def test_same_message_partial_and_final_are_both_delivered():
    connection = gemini.GeminiConnection(
        Socket(
            [
                {
                    "serverContent": {
                        "interimInputTranscription": {"text": "How did you"},
                        "inputTranscription": {"text": "How did you handle the migration?"},
                    }
                }
            ]
        )
    )
    partial = run(connection.receive())
    final = run(connection.receive())
    assert partial.segment == final.segment and not partial.final and final.final


def test_normal_close_during_finish_uses_existing_relay_flush_path():
    from websockets.exceptions import ConnectionClosedOK
    from websockets.frames import Close

    class Closed(Socket):
        async def recv(self):
            raise ConnectionClosedOK(Close(1000, ""), Close(1000, ""), True)

    connection = gemini.GeminiConnection(Closed())
    run(connection.finish())
    with pytest.raises(ConnectionClosedOK):
        run(connection.receive())


def test_cancellation_during_setup_closes_upstream(settings, monkeypatch):
    settings.gemini_api_key = SecretStr("fake-test-only")

    class Cancelled(Socket):
        async def recv(self):
            raise asyncio.CancelledError()

    socket = Cancelled()

    async def connect(*args, **kwargs):
        return socket

    monkeypatch.setattr(gemini, "connect", connect)
    with pytest.raises(asyncio.CancelledError):
        run(get_provider(settings).connect())
    assert socket.closed
