"""Tests for Modal runtime configuration precedence helpers."""

from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch


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
    )
    with patch.dict(sys.modules, {"modal": fake_modal}):
        modal_path = Path(__file__).resolve().parents[1] / "src" / "modal.py"
        return runpy.run_path(str(modal_path))


_MODAL_GLOBALS: dict[str, Any] = _load_modal_globals()

resolve_runtime_config = cast(Any, _MODAL_GLOBALS["resolve_runtime_config"])
DEFAULT_LLM_BASE_URL = cast(str, _MODAL_GLOBALS["DEFAULT_LLM_BASE_URL"])
DEFAULT_LLM_MODEL = cast(str, _MODAL_GLOBALS["DEFAULT_LLM_MODEL"])
DEFAULT_LOG_LEVEL = cast(str, _MODAL_GLOBALS["DEFAULT_LOG_LEVEL"])
APP_CONFIG_PREFIX = cast(str, _MODAL_GLOBALS["APP_CONFIG_PREFIX"])


def test_resolve_runtime_config_uses_defaults() -> None:
    """Defaults should be used when neither secret nor env values are set."""
    config = resolve_runtime_config({})

    assert config.llm_base_url == DEFAULT_LLM_BASE_URL
    assert config.llm_model == DEFAULT_LLM_MODEL
    assert config.log_level == DEFAULT_LOG_LEVEL


def test_resolve_runtime_config_uses_legacy_env_fallback() -> None:
    """Legacy env keys should be honored when app-config secret keys are absent."""
    config = resolve_runtime_config(
        {
            "LLM_BASE_URL": "http://env.example/v1",
            "LLM_MODEL": "env-model",
            "LOG_LEVEL": "debug",
        }
    )

    assert config.llm_base_url == "http://env.example/v1"
    assert config.llm_model == "env-model"
    assert config.log_level == "DEBUG"


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
        }
    )

    assert config.llm_base_url == "http://secret.example/v1"
    assert config.llm_model == "secret-model"
    assert config.log_level == "WARNING"


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
        }
    )

    assert config.llm_base_url == "http://env.example/v1"
    assert config.llm_model == "env-model"
    assert config.log_level == "ERROR"


def test_resolve_runtime_config_invalid_log_level_uses_default() -> None:
    """Invalid log levels should be normalized to the default."""
    config = resolve_runtime_config({"LOG_LEVEL": "not-a-level"})

    assert config.log_level == DEFAULT_LOG_LEVEL
