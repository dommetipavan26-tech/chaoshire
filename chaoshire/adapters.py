"""Pluggable model and decision-source adapter contracts."""

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

import pandas as pd

from .decisions import normalise_decisions
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
        return normalise_decisions(self.provider())


def validate_remote_configuration(
    url: str,
    timeout_seconds: float = 30.0,
    api_key_env: str | None = None,
    *,
    allow_http: bool = False,
) -> None:
    """Reject unsafe configuration without including credential-bearing values in errors."""
    if not isinstance(url, str) or len(url) > 2048 or any(c.isspace() for c in url) or "\\" in url:
        raise ValueError("Remote connector URL must be an absolute http(s) URL.")
    try:
        parts = urlsplit(url)
        valid = parts.scheme in {"https", "http"} and bool(parts.hostname) and parts.port != 0
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Remote connector URL must be an absolute http(s) URL.")
    if parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ValueError(
            "Remote connector URL must not contain userinfo, query credentials or fragments."
        )
    if not isinstance(allow_http, bool) or (parts.scheme == "http" and not allow_http):
        raise ValueError(
            "Remote connectors require HTTPS; allow_http=true is an explicit local/private-network opt-in."
        )
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 120
    ):
        raise ValueError("Remote connector timeout_seconds must be finite and in (0, 120].")
    if api_key_env is not None and (
        not isinstance(api_key_env, str)
        or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env) is None
    ):
        raise ValueError("Remote connector api_key_env must be a valid environment-variable name.")


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
    allow_http: bool = False
    max_response_bytes: int = 5_500_000

    def describe(self) -> dict[str, Any]:
        validate_remote_configuration(
            self.url, self.timeout_seconds, self.api_key_env, allow_http=self.allow_http
        )
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
        validate_remote_configuration(
            self.url, self.timeout_seconds, self.api_key_env, allow_http=self.allow_http
        )
        if (
            isinstance(self.max_response_bytes, bool)
            or not isinstance(self.max_response_bytes, int)
            or self.max_response_bytes <= 0
        ):
            raise ValueError("Remote response byte limit must be a positive integer.")
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if self.api_key_env:
            api_key = os.environ.get(self.api_key_env, "").strip()
            if not api_key:
                raise ValueError(
                    f"Remote connector '{self.model_id}' is missing API key env '{self.api_key_env}'."
                )
            headers["Authorization"] = f"Bearer {api_key}"
        body = bytearray()
        with httpx.Client(
            timeout=self.timeout_seconds, transport=self.transport, follow_redirects=False
        ) as client:
            with client.stream("GET", self.url, headers=headers) as response:
                response.raise_for_status()
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ValueError(
                        "Remote responses must use identity encoding for bounded decoding."
                    )
                for chunk in response.iter_bytes(chunk_size=65_536):
                    if len(body) + len(chunk) > self.max_response_bytes:
                        raise ValueError(
                            "Remote decision response exceeds the configured byte limit."
                        )
                    body.extend(chunk)
        return normalise_remote_decisions(json.loads(body), model_id=self.model_id)


def normalise_remote_decisions(payload: Any, model_id: str) -> pd.DataFrame:
    """Normalize both outcome and truth labels before any metric sees the rows."""
    rows = payload.get("decisions") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Remote model '{model_id}' returned no decision rows.")
    if len(rows) > 100_000 or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Remote decisions must be a bounded list of row objects.")
    frame = pd.DataFrame(rows)
    if "accepted" not in frame.columns:
        raise ValueError(f"Remote model '{model_id}' payload is missing the 'accepted' field.")
    return normalise_decisions(frame)


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
        raise ValueError("CHAOSHIRE_REMOTE_MODELS is not valid JSON.") from error
    if not isinstance(entries, list):
        raise ValueError("CHAOSHIRE_REMOTE_MODELS must be a JSON list of connector objects.")
    adapters: list[RemoteDecisionAdapter] = []
    seen: set[str] = set()
    if len(entries) > 100:
        raise ValueError("Configure no more than 100 remote models.")
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("model_id") or not entry.get("url"):
            raise ValueError("Each connector needs 'model_id' and 'url'.")
        model_id = entry["model_id"]
        if (
            not isinstance(model_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}", model_id)
            or model_id in seen
        ):
            raise ValueError("Remote model IDs must be unique, bounded identifiers.")
        seen.add(model_id)
        timeout = entry.get("timeout_seconds", 30.0)
        key_env = entry.get("api_key_env")
        allow_http = entry.get("allow_http", False)
        validate_remote_configuration(entry["url"], timeout, key_env, allow_http=allow_http)
        adapters.append(
            RemoteDecisionAdapter(
                model_id=model_id,
                url=entry["url"],
                api_key_env=key_env,
                timeout_seconds=float(timeout),
                allow_http=allow_http,
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
    from .explain import adapter_catalog_entry

    return {
        "contract": "DecisionAdapter.describe() + DecisionAdapter.decisions()",
        "required_normalized_columns": ["accepted"],
        "recommended_columns": ["candidate_id", "qualified", "protected attributes"],
        "label_contract": "Explicit booleans, numeric 0/1, or documented true/false tokens; missing/unknown/nonfinite labels are rejected.",
        "remote_transport": "HTTPS by default; credential-free URLs; explicit allow_http for private/local endpoints; bounded response bodies.",
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
            adapter_catalog_entry(),
        ],
        "security_note": "ChaosHire consumes decisions; it does not require model weights or execute uploaded code.",
    }
