"""Pluggable model and decision-source adapter contracts."""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from .models import build_decisions, get_model


@runtime_checkable
class DecisionAdapter(Protocol):
    """Normalize an external model version into auditable decisions."""

    adapter_id: str

    def describe(self) -> dict[str, Any]: ...

    def decisions(self) -> pd.DataFrame: ...


@dataclass(frozen=True)
class ReferenceModelAdapter:
    """Adapter for ChaosHire's deterministic transparent fixtures."""

    model_id: str
    adapter_id: str = "reference-model"

    def describe(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "model_id": self.model_id,
            "mode": "local_scoring",
            "deterministic": True,
        }

    def decisions(self) -> pd.DataFrame:
        return build_decisions(get_model(self.model_id))


@dataclass(frozen=True)
class CallableDecisionAdapter:
    """Safe integration point for an in-process production decision provider."""

    model_id: str
    provider: Callable[[], pd.DataFrame]
    adapter_id: str = "callable-decisions"

    def describe(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "model_id": self.model_id,
            "mode": "provided_decisions",
            "deterministic": False,
        }

    def decisions(self) -> pd.DataFrame:
        frame = self.provider()
        required = {"accepted"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(
                f"Adapter output is missing required columns: {', '.join(sorted(missing))}."
            )
        return frame.copy()


@dataclass(frozen=True)
class RemoteDecisionAdapter:
    """Authenticated HTTP connector for an operator-configured decision API.

    The URL and the *name* of the credential environment variable come from
    operator configuration (``CHAOSHIRE_REMOTE_MODELS``), never from request
    input, so exposing the connector adds no SSRF surface to the public API.
    ``transport`` is an httpx transport override used by tests.
    """

    model_id: str
    url: str
    api_key_env: str | None = None
    timeout_seconds: float = 30.0
    transport: Any = None
    adapter_id: str = "remote-http"

    def describe(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_id,
            "model_id": self.model_id,
            "mode": "remote_http",
            "url": self.url,
            "authenticated": self.api_key_env is not None,
            "deterministic": False,
        }

    def decisions(self) -> pd.DataFrame:
        try:
            import httpx
        except ImportError as error:  # pragma: no cover - httpx is a declared runtime dep
            raise RuntimeError(
                "The remote connector requires httpx; install requirements.txt."
            ) from error
        if not self.url.startswith(("https://", "http://")):
            raise ValueError(f"Remote connector URL must be http(s): {self.url!r}")
        headers = {"Accept": "application/json"}
        if self.api_key_env:
            api_key = os.environ.get(self.api_key_env, "").strip()
            if not api_key:
                raise ValueError(
                    f"Remote connector '{self.model_id}' is missing API key env '{self.api_key_env}'."
                )
            headers["Authorization"] = f"Bearer {api_key}"
        with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
            response = client.get(self.url, headers=headers)
        response.raise_for_status()
        return normalise_remote_decisions(response.json(), model_id=self.model_id)


FAVOURABLE_VALUES = {"1", "true", "yes", "y", "accept", "accepted"}


def normalise_remote_decisions(payload: Any, model_id: str) -> pd.DataFrame:
    """Normalise a remote JSON payload into the DecisionAdapter contract."""
    rows = payload.get("decisions") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Remote model '{model_id}' returned no decision rows.")
    frame = pd.DataFrame(rows)
    if "accepted" not in frame.columns:
        raise ValueError(f"Remote model '{model_id}' payload is missing the 'accepted' field.")

    def as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in FAVOURABLE_VALUES

    frame["accepted"] = frame["accepted"].map(as_bool)
    return frame


def remote_adapters_from_env() -> list[RemoteDecisionAdapter]:
    """Parse the operator-configured connector list (``CHAOSHIRE_REMOTE_MODELS``).

    Expected shape: a JSON list of objects with ``model_id``, ``url``, optional
    ``api_key_env`` and optional ``timeout_seconds``.
    """
    raw = os.environ.get("CHAOSHIRE_REMOTE_MODELS", "").strip()
    if not raw:
        return []
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"CHAOSHIRE_REMOTE_MODELS is not valid JSON: {error}") from error
    if not isinstance(entries, list):
        raise ValueError("CHAOSHIRE_REMOTE_MODELS must be a JSON list of connector objects.")
    adapters: list[RemoteDecisionAdapter] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("model_id") or not entry.get("url"):
            raise ValueError("Each connector needs 'model_id' and 'url'.")
        url = str(entry["url"])
        if not url.startswith(("https://", "http://")):
            raise ValueError(f"Connector URL must be http(s): {url!r}")
        adapters.append(
            RemoteDecisionAdapter(
                model_id=str(entry["model_id"]),
                url=url,
                api_key_env=entry.get("api_key_env"),
                timeout_seconds=float(entry.get("timeout_seconds", 30.0)),
            )
        )
    return adapters


def find_remote_adapter(model_id: str) -> RemoteDecisionAdapter | None:
    """Return the operator-configured connector for ``model_id``, if any."""
    for adapter in remote_adapters_from_env():
        if adapter.model_id == model_id:
            return adapter
    return None


def adapter_catalog() -> dict[str, Any]:
    """Document supported integration modes without making unsafe outbound requests."""
    try:
        configured = [adapter.model_id for adapter in remote_adapters_from_env()]
        remote_status = "configured" if configured else "library"
    except ValueError:
        configured = []
        remote_status = "misconfigured"
    return {
        "contract": "DecisionAdapter.describe() + DecisionAdapter.decisions()",
        "required_normalized_columns": ["accepted"],
        "recommended_columns": ["candidate_id", "qualified", "protected attributes"],
        "adapters": [
            {
                "id": "reference-model",
                "status": "available",
                "use": "Transparent deterministic LegacyCorp and MeritFirst fixtures.",
            },
            {
                "id": "csv-decisions",
                "status": "available",
                "use": "Configurable outcome export through POST /api/upload.",
            },
            {
                "id": "callable-decisions",
                "status": "library",
                "use": "In-process integration for a versioned production decision provider.",
            },
            {
                "id": "remote-http",
                "status": remote_status,
                "use": (
                    "Authenticated HTTP connector for operator-configured remote "
                    "decision APIs (POST /api/connectors/audit)."
                ),
                "configured_models": configured,
            },
        ],
        "security_note": "ChaosHire consumes decisions; it does not require model weights or execute uploaded code.",
    }
