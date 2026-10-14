"""Local, session-only model configuration. No provider or agent execution."""
from __future__ import annotations

import ipaddress
import json
import re
import threading
import uuid
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator


LOCAL_ORIGINS = frozenset(
    f"http://{host}:{port}"
    for host in ("localhost", "127.0.0.1")
    for port in (5173, 3000, 8000)
)


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=80)
    protocol: str = Field(pattern=r"^(openai-compatible|anthropic)$")
    model: str = Field(min_length=1, max_length=160)
    endpoint: str = Field(min_length=1, max_length=512)
    api_key: SecretStr = Field(default_factory=lambda: SecretStr(""), max_length=4096)
    clear_key: bool = False

    @field_validator("name", "model")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Invalid text")
        return value

    @field_validator("api_key")
    @classmethod
    def clean_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if raw and (raw != raw.strip() or any(ord(c) < 33 or ord(c) > 126 for c in raw)):
            raise ValueError("Invalid key")
        return value

    @field_validator("endpoint")
    @classmethod
    def clean_endpoint(cls, value: str) -> str:
        value = value.strip()
        if not value.isascii() or any(ord(c) <= 32 for c in value) or "\\" in value:
            raise ValueError("Invalid endpoint")
        parsed = urlsplit(value)
        host = parsed.hostname
        if (not host or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or "?" in value or "#" in value):
            raise ValueError("Endpoint must not contain credentials, query or fragment")
        port = parsed.port  # Reject malformed ports.
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("Invalid port")
        if ":" not in host and not re.fullmatch(r"[a-zA-Z0-9.-]+", host):
            raise ValueError("Invalid host")
        if ":" in host:
            ipaddress.IPv6Address(host)
        local = host.lower() == "localhost" or host in ("127.0.0.1", "::1")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
            raise ValueError("HTTPS required except for loopback")
        if "%" in parsed.path or any(p in (".", "..") for p in parsed.path.split("/")):
            raise ValueError("Invalid path")
        authority = f"[{host.lower()}]" if ":" in host else host.lower()
        if port is not None:
            authority += f":{port}"
        return urlunsplit((parsed.scheme, authority, parsed.path.rstrip("/"), "", ""))


class ProfileStore:
    """Secrets stay in private process memory; only sanitized metadata leaves."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._profiles: dict[str, ProfileInput] = {}

    @staticmethod
    def public(profile_id: str, value: ProfileInput) -> dict:
        return {"id": profile_id, "name": value.name, "protocol": value.protocol,
                "model": value.model, "endpoint": value.endpoint,
                "has_api_key": bool(value.api_key.get_secret_value()),
                "connection_status": "NOT_TESTED"}

    def list_profiles(self) -> list[dict]:
        with self._lock:
            return [self.public(k, v) for k, v in self._profiles.items()]

    def save(self, value: ProfileInput, profile_id: str | None = None) -> dict:
        with self._lock:
            if profile_id is not None and profile_id not in self._profiles:
                raise HTTPException(404, "Model profile not found")
            if profile_id is None and len(self._profiles) >= 20:
                raise HTTPException(409, "Maximum 20 model profiles per session")
            if value.clear_key and value.api_key.get_secret_value():
                raise HTTPException(422, "Choose either replace or remove API key")
            if profile_id and not value.clear_key and not value.api_key.get_secret_value():
                value = value.model_copy(update={"api_key": self._profiles[profile_id].api_key})
            if value.clear_key:
                value = value.model_copy(update={"api_key": SecretStr("")})
            profile_id = profile_id or uuid.uuid4().hex
            self._profiles[profile_id] = value
            return self.public(profile_id, value)

    def remove(self, profile_id: str) -> None:
        with self._lock:
            if profile_id not in self._profiles:
                raise HTTPException(404, "Model profile not found")
            del self._profiles[profile_id]


def _local_request(request: Request, *, mutation: bool) -> None:
    try:
        local = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    host = urlsplit(str(request.url)).hostname
    if not local or host not in ("localhost", "127.0.0.1", "::1"):
        raise HTTPException(403, "Model settings require a local connection")
    origin = request.headers.get("origin")
    if (mutation or origin is not None) and origin not in LOCAL_ORIGINS:
        raise HTTPException(403, "Model settings require a trusted local origin")


async def _input(request: Request) -> ProfileInput:
    _local_request(request, mutation=True)
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
        raise HTTPException(415, "Expected application/json")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384:
            raise HTTPException(413, "Model settings request too large")
    try:
        return ProfileInput.model_validate(json.loads(body))
    except (ValidationError, ValueError, UnicodeError):
        # Do not echo validation errors: they include submitted secrets.
        raise HTTPException(422, "Invalid model settings. Check model, HTTPS endpoint and API key.") from None


def create_router(store: ProfileStore) -> APIRouter:
    router = APIRouter(prefix="/api/model-profiles", tags=["Model configuration"])

    @router.get("")
    async def listing(request: Request, response: Response) -> dict:
        _local_request(request, mutation=False)
        response.headers["Cache-Control"] = "no-store"
        return {"profiles": store.list_profiles(), "storage": "SERVER_SESSION",
                "execution_integration": "NOT_CONNECTED"}

    @router.post("")
    async def create(request: Request, response: Response) -> dict:
        value = await _input(request)
        response.headers["Cache-Control"] = "no-store"
        return store.save(value)

    @router.post("/{profile_id}")
    async def update(profile_id: str, request: Request, response: Response) -> dict:
        value = await _input(request)
        response.headers["Cache-Control"] = "no-store"
        return store.save(value, profile_id)

    @router.post("/{profile_id}/remove")
    async def remove(profile_id: str, request: Request, response: Response) -> dict:
        _local_request(request, mutation=True)
        store.remove(profile_id)
        response.headers["Cache-Control"] = "no-store"
        return {"removed": True}

    return router
