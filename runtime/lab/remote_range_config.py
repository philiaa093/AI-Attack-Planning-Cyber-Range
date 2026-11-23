"""Closed, secret-free configuration for a remote GNS3/vSphere range."""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from runtime.lab.enterprise_range.topology import ENTERPRISE_TARGETS
from runtime.lab.range_provider import RangeProviderError


_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
_TOP_LEVEL_KEYS = frozenset({
    "schema_version",
    "configuration_id",
    "control_token_env",
    "gns3",
    "vsphere",
    "targets",
})
_GNS3_KEYS = frozenset({"base_url", "project_id", "username_env", "password_env"})
_VSPHERE_KEYS = frozenset({"base_url", "api_release", "username_env", "password_env"})
_TARGET_KEYS = frozenset({"data_url", "control_url", "gns3_node_id", "vsphere_vm_id"})


@dataclass(frozen=True)
class GNS3RemoteConfig:
    base_url: str
    project_id: str
    username_env: str
    password_env: str


@dataclass(frozen=True)
class VSphereRemoteConfig:
    base_url: str
    api_release: str
    username_env: str
    password_env: str


@dataclass(frozen=True)
class RemoteTargetConfig:
    data_url: str
    control_url: str
    gns3_node_id: str
    vsphere_vm_id: str


@dataclass(frozen=True)
class RemoteRangeConfig:
    schema_version: int
    configuration_id: str
    control_token_env: str
    gns3: GNS3RemoteConfig
    vsphere: VSphereRemoteConfig
    targets: Mapping[str, RemoteTargetConfig]

    def resolve_control_token(self, environ: Mapping[str, str] | None = None) -> str:
        token = _read_secret(self.control_token_env, environ)
        if len(token) < 32:
            raise RangeProviderError(
                "REMOTE_CONTROL_TOKEN_INVALID",
                "Management control token must contain at least 32 characters",
            )
        return token


def _reject_unknown_keys(value: Mapping[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise RangeProviderError(
            "REMOTE_CONFIG_UNKNOWN_FIELD",
            f"Unknown {label} fields: {', '.join(unknown)}",
        )


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise RangeProviderError("REMOTE_CONFIG_INVALID", f"{label} must be a non-empty bounded string")
    return value


def _require_env_name(value: Any, label: str) -> str:
    name = _require_string(value, label)
    if not _ENV_NAME.fullmatch(name):
        raise RangeProviderError("REMOTE_CONFIG_INVALID_ENV_REF", f"{label} is not a valid environment reference")
    return name


def _require_https_url(value: Any, label: str) -> str:
    url = _require_string(value, label).rstrip("/")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RangeProviderError(
            "REMOTE_CONFIG_INSECURE_URL",
            f"{label} must be an HTTPS URL without userinfo, query, or fragment",
        )
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        address = None
    if address is not None and not (
        address.is_private or address.is_loopback or address.is_link_local
    ):
        raise RangeProviderError(
            "REMOTE_CONFIG_PUBLIC_IP_DENIED",
            f"{label} must not use a public IP literal",
        )
    return url


def _read_secret(name: str, environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    value = source.get(name, "")
    if not value:
        raise RangeProviderError("REMOTE_SECRET_MISSING", f"Required environment secret is missing: {name}")
    return value


def resolve_basic_credentials(
    username_env: str,
    password_env: str,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    return _read_secret(username_env, environ), _read_secret(password_env, environ)


def load_remote_range_config(path: str | Path) -> RemoteRangeConfig:
    config_path = Path(path).resolve()
    try:
        if config_path.stat().st_size > 262_144:
            raise RangeProviderError("REMOTE_CONFIG_TOO_LARGE", "Remote range config exceeds 256 KiB")
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except RangeProviderError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise RangeProviderError("REMOTE_CONFIG_READ_FAILED", type(exc).__name__) from exc
    return parse_remote_range_config(raw)


def parse_remote_range_config(raw: Any) -> RemoteRangeConfig:
    if not isinstance(raw, dict):
        raise RangeProviderError("REMOTE_CONFIG_INVALID", "Remote range config must be an object")
    _reject_unknown_keys(raw, _TOP_LEVEL_KEYS, "top-level")
    if raw.get("schema_version") != 1:
        raise RangeProviderError("REMOTE_CONFIG_VERSION_UNSUPPORTED", "schema_version must be 1")

    configuration_id = _require_string(raw.get("configuration_id"), "configuration_id")
    control_token_env = _require_env_name(raw.get("control_token_env"), "control_token_env")

    gns3_raw = raw.get("gns3")
    if not isinstance(gns3_raw, dict):
        raise RangeProviderError("REMOTE_CONFIG_INVALID", "gns3 must be an object")
    _reject_unknown_keys(gns3_raw, _GNS3_KEYS, "gns3")
    gns3 = GNS3RemoteConfig(
        base_url=_require_https_url(gns3_raw.get("base_url"), "gns3.base_url"),
        project_id=_require_string(gns3_raw.get("project_id"), "gns3.project_id"),
        username_env=_require_env_name(gns3_raw.get("username_env"), "gns3.username_env"),
        password_env=_require_env_name(gns3_raw.get("password_env"), "gns3.password_env"),
    )

    vsphere_raw = raw.get("vsphere")
    if not isinstance(vsphere_raw, dict):
        raise RangeProviderError("REMOTE_CONFIG_INVALID", "vsphere must be an object")
    _reject_unknown_keys(vsphere_raw, _VSPHERE_KEYS, "vsphere")
    vsphere = VSphereRemoteConfig(
        base_url=_require_https_url(vsphere_raw.get("base_url"), "vsphere.base_url"),
        api_release=_require_string(vsphere_raw.get("api_release"), "vsphere.api_release"),
        username_env=_require_env_name(vsphere_raw.get("username_env"), "vsphere.username_env"),
        password_env=_require_env_name(vsphere_raw.get("password_env"), "vsphere.password_env"),
    )

    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, dict):
        raise RangeProviderError("REMOTE_CONFIG_INVALID", "targets must be an object")
    expected_targets = frozenset(ENTERPRISE_TARGETS)
    if frozenset(targets_raw) != expected_targets:
        raise RangeProviderError(
            "REMOTE_CONFIG_TARGET_SET_MISMATCH",
            "targets must exactly match the canonical enterprise target IDs",
        )
    targets: dict[str, RemoteTargetConfig] = {}
    for target_id in sorted(expected_targets):
        target_raw = targets_raw[target_id]
        if not isinstance(target_raw, dict):
            raise RangeProviderError("REMOTE_CONFIG_INVALID", f"targets.{target_id} must be an object")
        _reject_unknown_keys(target_raw, _TARGET_KEYS, f"targets.{target_id}")
        targets[target_id] = RemoteTargetConfig(
            data_url=_require_https_url(target_raw.get("data_url"), f"targets.{target_id}.data_url"),
            control_url=_require_https_url(target_raw.get("control_url"), f"targets.{target_id}.control_url"),
            gns3_node_id=_require_string(target_raw.get("gns3_node_id"), f"targets.{target_id}.gns3_node_id"),
            vsphere_vm_id=_require_string(target_raw.get("vsphere_vm_id"), f"targets.{target_id}.vsphere_vm_id"),
        )

    unique_fields = {
        "data_url": [target.data_url for target in targets.values()],
        "control_url": [target.control_url for target in targets.values()],
        "gns3_node_id": [target.gns3_node_id for target in targets.values()],
        "vsphere_vm_id": [target.vsphere_vm_id for target in targets.values()],
    }
    duplicates = sorted(
        field_name
        for field_name, values in unique_fields.items()
        if len(values) != len(set(values))
    )
    if duplicates:
        raise RangeProviderError(
            "REMOTE_CONFIG_DUPLICATE_BINDING",
            "Remote targets require unique bindings for: " + ", ".join(duplicates),
        )

    return RemoteRangeConfig(
        schema_version=1,
        configuration_id=configuration_id,
        control_token_env=control_token_env,
        gns3=gns3,
        vsphere=vsphere,
        targets=targets,
    )
