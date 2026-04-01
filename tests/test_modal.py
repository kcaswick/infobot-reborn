"""Tests for Modal runtime configuration precedence helpers."""

from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class _FakeImage:
    def pip_install_from_pyproject(self, **_kwargs: object) -> _FakeImage:
        return self

    def copy_local_dir(self, *_args: object, **_kwargs: object) -> _FakeImage:
        return self


class _FakeImageFactory:
    @staticmethod
    def debian_slim(**_kwargs: object) -> _FakeImage:
        return _FakeImage()


class _FakeVolumeFactory:
    @staticmethod
    def from_name(*_args: object, **_kwargs: object) -> object:
        return object()


class _FakeSecretFactory:
    @staticmethod
    def from_name(*_args: object, **_kwargs: object) -> object:
        return object()


class _FakeApp:
    def __init__(self, **_kwargs: object) -> None:
        pass

    def function(self, **_kwargs: object):
        def decorator(func):
            return func

        return decorator

    def cls(self, **_kwargs: object):
        def decorator(cls):
            return cls

        return decorator

    def local_entrypoint(self):
        def decorator(func):
            return func

        return decorator


def _identity_decorator():
    def decorator(func):
        return func

    return decorator


def _load_modal_globals() -> dict[str, Any]:
    fake_modal = types.SimpleNamespace(
        App=_FakeApp,
        Volume=_FakeVolumeFactory,
        Image=_FakeImageFactory,
        Secret=_FakeSecretFactory,
        asgi_app=_identity_decorator,
        enter=_identity_decorator,
        method=_identity_decorator,
    )
    with patch.dict(sys.modules, {"modal": fake_modal}):
        modal_path = Path(__file__).resolve().parents[1] / "src" / "modal.py"
        return runpy.run_path(str(modal_path))


_MODAL_GLOBALS: dict[str, Any] = _load_modal_globals()

resolve_runtime_config = cast(Any, _MODAL_GLOBALS["resolve_runtime_config"])
DEFAULT_LLM_BASE_URL = cast(str, _MODAL_GLOBALS["DEFAULT_LLM_BASE_URL"])
DEFAULT_LLM_MODEL = cast(str, _MODAL_GLOBALS["DEFAULT_LLM_MODEL"])
DEFAULT_LOG_LEVEL = cast(str, _MODAL_GLOBALS["DEFAULT_LOG_LEVEL"])
DEFAULT_DATABASE_PATH = Path(cast(str, _MODAL_GLOBALS["DEFAULT_DATABASE_PATH"]))
APP_CONFIG_PREFIX = cast(str, _MODAL_GLOBALS["APP_CONFIG_PREFIX"])
RuntimeServiceCache = cast(Any, _MODAL_GLOBALS["RuntimeServiceCache"])
RuntimeConfig = cast(Any, _MODAL_GLOBALS["RuntimeConfig"])
DiscordInteractionType = cast(Any, _MODAL_GLOBALS["DiscordInteractionType"])
DiscordResponseType = cast(Any, _MODAL_GLOBALS["DiscordResponseType"])
web_app_factory = cast(Any, _MODAL_GLOBALS["web_app"])
authenticate = cast(Any, _MODAL_GLOBALS["authenticate"])
_configure_logging = cast(Any, _MODAL_GLOBALS["_configure_logging"])
ModalInteractionWorker = cast(Any, _MODAL_GLOBALS["ModalInteractionWorker"])
register_commands = cast(Any, _MODAL_GLOBALS["register_commands"])


class _FakeAiohttpResponse:
    """Minimal async response/context manager for register_commands tests."""

    def __init__(
        self,
        payload: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self._payload = payload
        self._error = error

    async def __aenter__(self) -> _FakeAiohttpResponse:
        return self

    async def __aexit__(
        self,
        _exc_type: object,
        _exc: object,
        _tb: object,
    ) -> bool:
        return False

    def raise_for_status(self) -> None:
        """Raise the configured error, if any."""
        if self._error is not None:
            raise self._error

    async def json(self) -> object:
        """Return the configured JSON payload."""
        return self._payload


class _FakeAiohttpModule:
    """Tiny aiohttp stub for exercising register_commands branches."""

    def __init__(self, responses: dict[str, list[_FakeAiohttpResponse]]) -> None:
        self._responses = {method: list(items) for method, items in responses.items()}
        self.calls: list[dict[str, object]] = []
        self.connector_kwargs: dict[str, object] | None = None
        self.session_connector: object | None = None

        outer = self

        class TCPConnector:
            def __init__(self, **kwargs: object) -> None:
                outer.connector_kwargs = dict(kwargs)
                self.limit = kwargs.get("limit")
                self.limit_per_host = kwargs.get("limit_per_host")

        class ClientTimeout:
            def __init__(self, *, total: float | None = None) -> None:
                self.total = total

        class ClientSession:
            def __init__(self, *, connector: object | None = None, **_kwargs: object):
                outer.session_connector = connector

            async def __aenter__(self) -> ClientSession:
                return self

            async def __aexit__(
                self,
                _exc_type: object,
                _exc: object,
                _tb: object,
            ) -> bool:
                return False

            def _request(
                self,
                method: str,
                url: str,
                *,
                headers: dict[str, str] | None = None,
                json: dict[str, object] | None = None,
                timeout: object | None = None,
            ) -> _FakeAiohttpResponse:
                outer.calls.append(
                    {
                        "method": method,
                        "url": url,
                        "headers": headers,
                        "json": json,
                        "timeout": timeout,
                    }
                )
                response_queue = outer._responses.setdefault(method, [])
                if not response_queue:
                    raise AssertionError(f"Missing fake aiohttp response for {method}")
                return response_queue.pop(0)

            def get(
                self,
                url: str,
                *,
                headers: dict[str, str] | None = None,
                timeout: object | None = None,
            ) -> _FakeAiohttpResponse:
                return self._request("GET", url, headers=headers, timeout=timeout)

            def patch(
                self,
                url: str,
                *,
                headers: dict[str, str] | None = None,
                json: dict[str, object] | None = None,
                timeout: object | None = None,
            ) -> _FakeAiohttpResponse:
                return self._request(
                    "PATCH",
                    url,
                    headers=headers,
                    json=json,
                    timeout=timeout,
                )

            def post(
                self,
                url: str,
                *,
                headers: dict[str, str] | None = None,
                json: dict[str, object] | None = None,
                timeout: object | None = None,
            ) -> _FakeAiohttpResponse:
                return self._request(
                    "POST",
                    url,
                    headers=headers,
                    json=json,
                    timeout=timeout,
                )

        self.TCPConnector = TCPConnector
        self.ClientTimeout = ClientTimeout
        self.ClientSession = ClientSession


def test_resolve_runtime_config_uses_defaults() -> None:
    """Defaults should be used when neither secret nor env values are set."""
    config = resolve_runtime_config({})

    assert config.llm_base_url == DEFAULT_LLM_BASE_URL
    assert config.llm_model == DEFAULT_LLM_MODEL
    assert config.log_level == DEFAULT_LOG_LEVEL
    assert config.database_path == DEFAULT_DATABASE_PATH


def test_resolve_runtime_config_uses_legacy_env_fallback() -> None:
    """Legacy env keys should be honored when app-config secret keys are absent."""
    config = resolve_runtime_config(
        {
            "LLM_BASE_URL": "http://env.example/v1",
            "LLM_MODEL": "env-model",
            "LOG_LEVEL": "debug",
            "DATABASE_PATH": "/tmp/env.db",
        }
    )

    assert config.llm_base_url == "http://env.example/v1"
    assert config.llm_model == "env-model"
    assert config.log_level == "DEBUG"
    assert config.database_path == Path("/tmp/env.db")


def test_resolve_runtime_config_prefers_app_config_namespace() -> None:
    """Secret-style APP_CONFIG_ keys should override legacy env keys."""
    config = resolve_runtime_config(
        {
            f"{APP_CONFIG_PREFIX}LLM_BASE_URL": "http://secret.example/v1",
            "LLM_BASE_URL": "http://env.example/v1",
            f"{APP_CONFIG_PREFIX}LLM_MODEL": "secret-model",
            "LLM_MODEL": "env-model",
            f"{APP_CONFIG_PREFIX}LOG_LEVEL": "warning",
            "LOG_LEVEL": "debug",
            f"{APP_CONFIG_PREFIX}DATABASE_PATH": "/tmp/secret.db",
            "DATABASE_PATH": "/tmp/env.db",
        }
    )

    assert config.llm_base_url == "http://secret.example/v1"
    assert config.llm_model == "secret-model"
    assert config.log_level == "WARNING"
    assert config.database_path == Path("/tmp/secret.db")


def test_resolve_runtime_config_blank_secret_value_falls_back() -> None:
    """Blank APP_CONFIG values should not block fallback to legacy env values."""
    config = resolve_runtime_config(
        {
            f"{APP_CONFIG_PREFIX}LLM_BASE_URL": "   ",
            "LLM_BASE_URL": "http://env.example/v1",
            f"{APP_CONFIG_PREFIX}LLM_MODEL": "",
            "LLM_MODEL": "env-model",
            f"{APP_CONFIG_PREFIX}LOG_LEVEL": "   ",
            "LOG_LEVEL": "error",
            f"{APP_CONFIG_PREFIX}DATABASE_PATH": "   ",
            "DATABASE_PATH": "/tmp/env.db",
        }
    )

    assert config.llm_base_url == "http://env.example/v1"
    assert config.llm_model == "env-model"
    assert config.log_level == "ERROR"
    assert config.database_path == Path("/tmp/env.db")


def test_resolve_runtime_config_invalid_log_level_uses_default() -> None:
    """Invalid log levels should be normalized to the default."""
    config = resolve_runtime_config({"LOG_LEVEL": "not-a-level"})

    assert config.log_level == DEFAULT_LOG_LEVEL


def test_runtime_service_cache_reuses_service_for_same_config() -> None:
    """Same runtime tuple should reuse one cached service instance."""
    calls: list[tuple[str, str]] = []

    def fake_factory(llm_base_url: str, llm_model: str) -> object:
        calls.append((llm_base_url, llm_model))
        return object()

    cache = RuntimeServiceCache(llm_factory=fake_factory)
    first = cache.get_llm_service("http://llm.local/v1", "model-a")
    second = cache.get_llm_service("http://llm.local/v1", "model-a")

    assert first is second
    assert calls == [("http://llm.local/v1", "model-a")]


def test_runtime_service_cache_separates_services_per_runtime_tuple() -> None:
    """Different runtime tuples should produce separate cached services."""
    calls: list[tuple[str, str]] = []

    def fake_factory(llm_base_url: str, llm_model: str) -> object:
        calls.append((llm_base_url, llm_model))
        return object()

    cache = RuntimeServiceCache(llm_factory=fake_factory)
    first = cache.get_llm_service("http://llm.local/v1", "model-a")
    second = cache.get_llm_service("http://llm.local/v1", "model-b")

    assert first is not second
    assert calls == [
        ("http://llm.local/v1", "model-a"),
        ("http://llm.local/v1", "model-b"),
    ]


def test_webhook_ping_returns_pong(monkeypatch: Any) -> None:
    """Webhook PING interactions should still return Discord PONG responses."""
    web_app_globals = web_app_factory.__globals__
    monkeypatch.setitem(
        web_app_globals,
        "authenticate",
        lambda _headers, _body: None,
    )

    app = web_app_factory()
    client = TestClient(app)
    response = client.post(
        "/interactions",
        json={"type": DiscordInteractionType.PING.value},
    )

    assert response.status_code == 200
    assert response.json() == {"type": DiscordResponseType.PONG.value}


def test_webhook_command_returns_deferred_and_spawns_worker(monkeypatch: Any) -> None:
    """Command interactions should still defer immediately and spawn background work."""
    spawn_calls: list[dict[str, str]] = []

    runtime_config = RuntimeConfig(
        llm_base_url="http://runtime.example/v1",
        llm_model="runtime-model",
        log_level="DEBUG",
        database_path=Path("/tmp/runtime.db"),
    )

    def fake_spawn(**kwargs: str) -> None:
        spawn_calls.append(kwargs)

    fake_worker = SimpleNamespace(
        process_and_reply=SimpleNamespace(spawn=fake_spawn),
    )

    web_app_globals = web_app_factory.__globals__
    monkeypatch.setitem(
        web_app_globals,
        "authenticate",
        lambda _headers, _body: None,
    )
    monkeypatch.setitem(
        web_app_globals,
        "resolve_runtime_config",
        lambda: runtime_config,
    )
    monkeypatch.setitem(web_app_globals, "modal_worker", fake_worker)

    app = web_app_factory()
    client = TestClient(app)
    response = client.post(
        "/interactions",
        json={
            "type": DiscordInteractionType.APPLICATION_COMMAND.value,
            "application_id": "app-123",
            "token": "token-abc",
            "data": {
                "name": "ask",
                "options": [{"name": "question", "value": "What is python?"}],
            },
            "member": {"user": {"username": "alice"}},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "type": DiscordResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE.value
    }
    assert len(spawn_calls) == 1
    assert spawn_calls[0] == {
        "content": "What is python?",
        "username": "alice",
        "app_id": "app-123",
        "interaction_token": "token-abc",
        "llm_base_url": "http://runtime.example/v1",
        "llm_model": "runtime-model",
        "log_level": "DEBUG",
        "database_path": "/tmp/runtime.db",
    }


@pytest.mark.asyncio
async def test_process_and_reply_uses_runtime_database_path(
    monkeypatch: Any,
) -> None:
    """Worker DB connections should honor the resolved runtime database path."""

    captured: dict[str, Any] = {}

    class FakeDatabaseConnection:
        def __init__(self, path: Path) -> None:
            captured["db_path"] = path

        async def connect(self) -> None:
            captured["connected"] = True

        async def close(self) -> None:
            captured["closed"] = True

    async def fake_initialize_schema(_db: object) -> None:
        captured["schema_initialized"] = True

    class FakeMessageHandler:
        def __init__(self, db: object, llm_service: object) -> None:
            captured["handler_args"] = (db, llm_service)

        async def handle_message(self, content: str, username: str) -> str:
            captured["message"] = (content, username)
            return "Processed"

    async def fake_send_to_discord(
        payload: dict[str, str],
        app_id: str,
        interaction_token: str,
    ) -> None:
        captured["discord"] = (payload, app_id, interaction_token)

    worker = ModalInteractionWorker()
    worker._services = SimpleNamespace(
        get_llm_service=lambda llm_base_url, llm_model: (llm_base_url, llm_model)
    )

    method_globals = worker.process_and_reply.__globals__
    monkeypatch.setitem(method_globals, "send_to_discord", fake_send_to_discord)

    fake_db_module = types.SimpleNamespace(
        DatabaseConnection=FakeDatabaseConnection,
        initialize_schema=fake_initialize_schema,
    )
    fake_message_handler_module = types.SimpleNamespace(
        MessageHandler=FakeMessageHandler,
    )

    with patch.dict(
        sys.modules,
        {
            "infobot.db": fake_db_module,
            "infobot.message_handler": fake_message_handler_module,
        },
    ):
        await worker.process_and_reply(
            content="What is python?",
            username="alice",
            app_id="app-123",
            interaction_token="token-abc",
            llm_base_url="http://runtime.example/v1",
            llm_model="runtime-model",
            log_level="DEBUG",
            database_path="/tmp/runtime.db",
        )

    assert captured["db_path"] == Path("/tmp/runtime.db")
    assert captured["connected"] is True
    assert captured["schema_initialized"] is True
    assert captured["message"] == ("What is python?", "alice")
    assert captured["discord"] == (
        {"content": "Processed"},
        "app-123",
        "token-abc",
    )
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_register_commands_skips_existing_commands_without_force(
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Existing commands should be reported and skipped when force is false."""
    fake_aiohttp = _FakeAiohttpModule(
        {
            "GET": [
                _FakeAiohttpResponse(
                    [
                        {"id": "ask-id", "name": "ask"},
                        {"id": "teach-id", "name": "teach"},
                    ]
                )
            ]
        }
    )
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-123")
    monkeypatch.setenv("DISCORD_CLIENT_ID", "client-456")

    with patch.dict(sys.modules, {"aiohttp": fake_aiohttp}):
        await register_commands(force=False)

    captured = capsys.readouterr()
    assert fake_aiohttp.connector_kwargs == {"limit": 1, "limit_per_host": 1}
    assert getattr(fake_aiohttp.session_connector, "limit", None) == 1
    assert getattr(fake_aiohttp.session_connector, "limit_per_host", None) == 1
    assert [call["method"] for call in fake_aiohttp.calls] == ["GET"]
    assert fake_aiohttp.calls[0]["url"] == (
        "https://discord.com/api/v10/applications/client-456/commands"
    )
    assert getattr(fake_aiohttp.calls[0]["timeout"], "total", None) == 10
    assert "Command 'ask' already exists" in captured.out
    assert "Command 'teach' already exists" in captured.out
    assert "All commands registered successfully!" in captured.out


@pytest.mark.asyncio
async def test_register_commands_force_updates_existing_commands(
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Force mode should PATCH existing commands instead of skipping them."""
    fake_aiohttp = _FakeAiohttpModule(
        {
            "GET": [
                _FakeAiohttpResponse(
                    [
                        {"id": "ask-id", "name": "ask"},
                        {"id": "teach-id", "name": "teach"},
                    ]
                )
            ],
            "PATCH": [_FakeAiohttpResponse(), _FakeAiohttpResponse()],
        }
    )
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-123")
    monkeypatch.setenv("DISCORD_CLIENT_ID", "client-456")

    with patch.dict(sys.modules, {"aiohttp": fake_aiohttp}):
        await register_commands(force=True)

    captured = capsys.readouterr()
    assert [call["method"] for call in fake_aiohttp.calls] == [
        "GET",
        "PATCH",
        "PATCH",
    ]
    assert fake_aiohttp.calls[1]["url"].endswith("/commands/ask-id")
    assert fake_aiohttp.calls[1]["json"] == {
        "name": "ask",
        "description": "Ask the bot a question",
        "options": [
            {
                "name": "question",
                "description": "Your question",
                "type": 3,
                "required": True,
            }
        ],
    }
    assert fake_aiohttp.calls[2]["url"].endswith("/commands/teach-id")
    assert fake_aiohttp.calls[2]["json"] == {
        "name": "teach",
        "description": "Teach the bot a new factoid",
        "options": [
            {
                "name": "factoid",
                "description": "The factoid to teach (format: 'key is value')",
                "type": 3,
                "required": True,
            }
        ],
    }
    assert all(
        getattr(call["timeout"], "total", None) == 10
        for call in fake_aiohttp.calls
    )
    assert "Command 'ask' registered" in captured.out
    assert "Command 'teach' registered" in captured.out


@pytest.mark.asyncio
async def test_register_commands_creates_missing_commands(
    monkeypatch: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing commands should be created with POST requests."""
    fake_aiohttp = _FakeAiohttpModule(
        {
            "GET": [_FakeAiohttpResponse([])],
            "POST": [_FakeAiohttpResponse(), _FakeAiohttpResponse()],
        }
    )
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-123")
    monkeypatch.setenv("DISCORD_CLIENT_ID", "client-456")

    with patch.dict(sys.modules, {"aiohttp": fake_aiohttp}):
        await register_commands(force=False)

    captured = capsys.readouterr()
    assert [call["method"] for call in fake_aiohttp.calls] == [
        "GET",
        "POST",
        "POST",
    ]
    assert fake_aiohttp.calls[1]["url"] == (
        "https://discord.com/api/v10/applications/client-456/commands"
    )
    assert fake_aiohttp.calls[1]["json"] == {
        "name": "ask",
        "description": "Ask the bot a question",
        "options": [
            {
                "name": "question",
                "description": "Your question",
                "type": 3,
                "required": True,
            }
        ],
    }
    assert fake_aiohttp.calls[2]["json"] == {
        "name": "teach",
        "description": "Teach the bot a new factoid",
        "options": [
            {
                "name": "factoid",
                "description": "The factoid to teach (format: 'key is value')",
                "type": 3,
                "required": True,
            }
        ],
    }
    assert "Command 'ask' registered" in captured.out
    assert "Command 'teach' registered" in captured.out


@pytest.mark.asyncio
async def test_register_commands_propagates_http_errors(
    monkeypatch: Any,
) -> None:
    """HTTP failures should propagate instead of being swallowed."""
    fake_aiohttp = _FakeAiohttpModule(
        {
            "GET": [_FakeAiohttpResponse([])],
            "POST": [_FakeAiohttpResponse(error=RuntimeError("discord boom"))],
        }
    )
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token-123")
    monkeypatch.setenv("DISCORD_CLIENT_ID", "client-456")

    with patch.dict(sys.modules, {"aiohttp": fake_aiohttp}):
        with pytest.raises(RuntimeError, match="discord boom"):
            await register_commands(force=False)

    assert [call["method"] for call in fake_aiohttp.calls] == ["GET", "POST"]


def test_authenticate_malformed_signature_hex_returns_401(monkeypatch: Any) -> None:
    """Malformed hex in client signature header should raise 401, not 500 (bd-qc8)."""
    from fastapi.exceptions import HTTPException

    # Valid 32-byte public key hex so server config is fine
    valid_pubkey = "a" * 64
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", valid_pubkey)

    headers = {
        "x-signature-ed25519": "not-valid-hex!@#$",
        "x-signature-timestamp": "1234567890",
    }

    with pytest.raises(HTTPException) as exc_info:
        authenticate(headers, b'{"type":1}')

    assert exc_info.value.status_code == 401
    assert "Malformed signature hex" in exc_info.value.detail


def test_authenticate_malformed_public_key_hex_returns_500(
    monkeypatch: Any,
) -> None:
    """Misconfigured DISCORD_PUBLIC_KEY (bad hex) should raise 500."""
    from fastapi.exceptions import HTTPException

    monkeypatch.setenv("DISCORD_PUBLIC_KEY", "not-valid-hex!!")

    headers = {
        "x-signature-ed25519": "aa" * 64,
        "x-signature-timestamp": "1234567890",
    }

    with pytest.raises(HTTPException) as exc_info:
        authenticate(headers, b'{"type":1}')

    assert exc_info.value.status_code == 500
    assert "misconfigured" in exc_info.value.detail.lower()


def test_authenticate_invalid_public_key_bytes_returns_500(
    monkeypatch: Any,
) -> None:
    """Wrong-length public key bytes should still be treated as misconfigured."""
    from fastapi.exceptions import HTTPException

    monkeypatch.setenv("DISCORD_PUBLIC_KEY", "aa" * 31)

    headers = {
        "x-signature-ed25519": "aa" * 64,
        "x-signature-timestamp": "1234567890",
    }

    with pytest.raises(HTTPException) as exc_info:
        authenticate(headers, b'{"type":1}')

    assert exc_info.value.status_code == 500
    assert "misconfigured" in exc_info.value.detail.lower()


def test_authenticate_unexpected_verify_key_error_propagates(
    monkeypatch: Any,
) -> None:
    """Unexpected VerifyKey failures should not be relabeled as misconfiguration."""
    import nacl.signing

    monkeypatch.setenv("DISCORD_PUBLIC_KEY", "aa" * 32)

    class ExplodingVerifyKey:
        def __init__(self, _public_key: bytes) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(nacl.signing, "VerifyKey", ExplodingVerifyKey)

    headers = {
        "x-signature-ed25519": "aa" * 64,
        "x-signature-timestamp": "1234567890",
    }

    with pytest.raises(RuntimeError, match="boom"):
        authenticate(headers, b'{"type":1}')


def _make_noauth_client(monkeypatch: Any) -> TestClient:
    """Build a TestClient with authentication disabled."""
    web_app_globals = web_app_factory.__globals__
    monkeypatch.setitem(
        web_app_globals,
        "authenticate",
        lambda _headers, _body: None,
    )
    return TestClient(web_app_factory())


def test_webhook_rejects_oversized_body(monkeypatch: Any) -> None:
    """Bodies exceeding 256 KiB should be rejected with 413."""
    client = _make_noauth_client(monkeypatch)
    oversized = b"x" * (256 * 1024 + 1)
    response = client.post(
        "/interactions",
        content=oversized,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_webhook_rejects_non_utf8_body(monkeypatch: Any) -> None:
    """Non-UTF-8 bytes should be rejected with 400."""
    client = _make_noauth_client(monkeypatch)
    response = client.post(
        "/interactions",
        content=b"\x80\x81\x82",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert "UTF-8" in response.json()["detail"]


def test_webhook_rejects_malformed_json(monkeypatch: Any) -> None:
    """Invalid JSON should be rejected with 400."""
    client = _make_noauth_client(monkeypatch)
    response = client.post(
        "/interactions",
        content=b"{not json at all}",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert "JSON" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [b"[]", b'"hi"', b"123", b"true", b"null"],
)
def test_webhook_rejects_non_object_json_root(
    monkeypatch: Any,
    payload: bytes,
) -> None:
    """Valid JSON values that are not objects should return 400."""
    client = _make_noauth_client(monkeypatch)
    response = client.post(
        "/interactions",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert "json object" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        (
            {
                "type": DiscordInteractionType.APPLICATION_COMMAND.value,
                "application_id": "app-123",
                "token": "token-abc",
                "data": [],
                "member": {"user": {"username": "alice"}},
            },
            "command data must be a json object",
        ),
        (
            {
                "type": DiscordInteractionType.APPLICATION_COMMAND.value,
                "application_id": "app-123",
                "token": "token-abc",
                "data": "oops",
                "member": {"user": {"username": "alice"}},
            },
            "command data must be a json object",
        ),
        (
            {
                "type": DiscordInteractionType.APPLICATION_COMMAND.value,
                "application_id": "app-123",
                "token": "token-abc",
                "data": None,
                "member": {"user": {"username": "alice"}},
            },
            "command data must be a json object",
        ),
        (
            {
                "type": DiscordInteractionType.APPLICATION_COMMAND.value,
                "application_id": "app-123",
                "token": "token-abc",
                "data": {"name": "ask", "options": "oops"},
                "member": {"user": {"username": "alice"}},
            },
            "command options must be a json array",
        ),
        (
            {
                "type": DiscordInteractionType.APPLICATION_COMMAND.value,
                "application_id": "app-123",
                "token": "token-abc",
                "data": {"name": "ask", "options": ["oops"]},
                "member": {"user": {"username": "alice"}},
            },
            "command options must contain json objects",
        ),
        (
            {
                "type": DiscordInteractionType.APPLICATION_COMMAND.value,
                "application_id": "app-123",
                "token": "token-abc",
                "data": {"name": "ask", "options": [{"name": "question", "value": []}]},
                "member": {"user": {"username": "alice"}},
            },
            "command option value must be a json string",
        ),
        (
            {
                "type": DiscordInteractionType.APPLICATION_COMMAND.value,
                "application_id": "app-123",
                "token": "token-abc",
                "data": {
                    "name": "ask",
                    "options": [{"name": "question", "value": "Hi"}],
                },
                "member": [],
            },
            "interaction member must be a json object",
        ),
        (
            {
                "type": DiscordInteractionType.APPLICATION_COMMAND.value,
                "application_id": "app-123",
                "token": "token-abc",
                "data": {
                    "name": "ask",
                    "options": [{"name": "question", "value": "Hi"}],
                },
                "member": {"user": "oops"},
            },
            "interaction member user must be a json object",
        ),
        (
            {
                "type": DiscordInteractionType.APPLICATION_COMMAND.value,
                "application_id": "app-123",
                "token": "token-abc",
                "data": {
                    "name": "ask",
                    "options": [{"name": "question", "value": "Hi"}],
                },
                "user": "oops",
            },
            "interaction user must be a json object",
        ),
    ],
)
def test_webhook_rejects_malformed_command_payload_shapes(
    monkeypatch: Any,
    payload: dict[str, object],
    detail: str,
) -> None:
    """Malformed nested command payload shapes should return 400."""
    client = _make_noauth_client(monkeypatch)
    response = client.post("/interactions", json=payload)
    assert response.status_code == 400
    assert detail in response.json()["detail"].lower()


def test_webhook_command_missing_app_id_returns_400(
    monkeypatch: Any,
) -> None:
    """Command interaction missing application_id should return 400."""
    client = _make_noauth_client(monkeypatch)
    response = client.post(
        "/interactions",
        json={
            "type": DiscordInteractionType.APPLICATION_COMMAND.value,
            "token": "token-abc",
            "data": {
                "name": "ask",
                "options": [{"name": "question", "value": "Hi"}],
            },
            "member": {"user": {"username": "alice"}},
        },
    )
    assert response.status_code == 400
    assert "required interaction fields" in response.json()["detail"].lower()


def test_configure_logging_updates_level_on_subsequent_calls() -> None:
    """Repeated _configure_logging calls must change the root logger level.

    Regression: logging.basicConfig is a no-op after first invocation,
    so per-request log level changes had no effect (bd-2ts).
    """
    import logging as _logging

    _configure_logging("WARNING")
    assert _logging.getLogger().level == _logging.WARNING

    _configure_logging("DEBUG")
    assert _logging.getLogger().level == _logging.DEBUG

    # Restore to INFO to avoid polluting other tests
    _configure_logging("INFO")
    assert _logging.getLogger().level == _logging.INFO


def test_webhook_command_missing_token_returns_400(
    monkeypatch: Any,
) -> None:
    """Command interaction missing token should return 400."""
    client = _make_noauth_client(monkeypatch)
    response = client.post(
        "/interactions",
        json={
            "type": DiscordInteractionType.APPLICATION_COMMAND.value,
            "application_id": "app-123",
            "data": {
                "name": "ask",
                "options": [{"name": "question", "value": "Hi"}],
            },
            "member": {"user": {"username": "alice"}},
        },
    )
    assert response.status_code == 400
    assert "required interaction fields" in response.json()["detail"].lower()


def test_webhook_command_blank_option_value_returns_user_error(
    monkeypatch: Any,
) -> None:
    """Whitespace-only command values should reuse the existing user-facing error."""
    spawn_calls: list[dict[str, str]] = []

    def fake_spawn(**kwargs: str) -> None:
        spawn_calls.append(kwargs)

    fake_worker = SimpleNamespace(
        process_and_reply=SimpleNamespace(spawn=fake_spawn),
    )

    web_app_globals = web_app_factory.__globals__
    monkeypatch.setitem(
        web_app_globals,
        "authenticate",
        lambda _headers, _body: None,
    )
    monkeypatch.setitem(web_app_globals, "modal_worker", fake_worker)

    client = TestClient(web_app_factory())
    response = client.post(
        "/interactions",
        json={
            "type": DiscordInteractionType.APPLICATION_COMMAND.value,
            "application_id": "app-123",
            "token": "token-abc",
            "data": {
                "name": "ask",
                "options": [{"name": "question", "value": "   \n\t  "}],
            },
            "member": {"user": {"username": "alice"}},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "type": DiscordResponseType.CHANNEL_MESSAGE_WITH_SOURCE.value,
        "data": {"content": "Please provide input for this command."},
    }
    assert spawn_calls == []
