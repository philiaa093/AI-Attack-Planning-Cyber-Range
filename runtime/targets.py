"""Fixed, harmless vulnerability-family lab targets."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from urllib.parse import parse_qs, urlsplit

TARGETS = {
    "lab-sqli-001": "SQLI",
    "lab-xss-001": "XSS",
    "lab-path-001": "PATH_TRAVERSAL",
    "lab-clean-001": None,
}

_FIXED_SQL_ROWS = [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]
_FIXED_FILES = {"public.txt": "safe fixture", "readme.txt": "local lab fixture"}


@dataclass(frozen=True)
class Observation:
    status: int
    body: dict[str, object]


class Target:
    def __init__(self, target_id: str) -> None:
        if target_id not in TARGETS:
            raise ValueError("unknown target")
        self.target_id = target_id
        self.reset_count = 0

    @property
    def family(self) -> str | None:
        return TARGETS[self.target_id]

    def reset(self) -> Observation:
        self.reset_count += 1
        return self.observe("reset")

    def health(self) -> Observation:
        return Observation(200, {
            "status": "ok", "target_id": self.target_id, "family": self.family,
            "reset_count": self.reset_count,
        })

    def observe(self, action: str) -> Observation:
        if action == "reset":
            return Observation(200, {"status": "reset", "target_id": self.target_id, "reset_count": self.reset_count})
        if action == "health":
            return self.health()
        if action not in {"ACTION-WEB-001", "ACTION-WEB-002", "ACTION-WEB-003"}:
            return Observation(400, {"status": "invalid_action"})
        expected = {"ACTION-WEB-001": "SQLI", "ACTION-WEB-002": "XSS", "ACTION-WEB-003": "PATH_TRAVERSAL"}[action]
        vulnerable = self.family == expected
        evidence = {
            "status": "detected" if vulnerable else "not_detected",
            "target_id": self.target_id,
            "action_id": action,
            "family": expected,
            "fixture": _fixture(expected) if vulnerable else "clean-control",
            "vulnerable": vulnerable,
        }
        return Observation(200, evidence)


def _fixture(family: str) -> dict[str, object]:
    if family == "SQLI":
        return {"query": "id=1 OR 1=1", "rows": _FIXED_SQL_ROWS, "row_count": len(_FIXED_SQL_ROWS)}
    if family == "XSS":
        marker = "<b>lab-xss-marker</b>"
        return {"input": marker, "rendered_html": marker, "escaped_html": escape(marker)}
    return {"requested": "../public.txt", "served_file": "public.txt", "content": _FIXED_FILES["public.txt"]}


def route(target: Target, method: str, raw_path: str) -> Observation:
    path = urlsplit(raw_path).path
    if method == "GET" and path == "/health":
        return target.health()
    if method == "POST" and path == "/reset":
        return target.reset()
    if method == "POST" and path == "/action":
        values = parse_qs(urlsplit(raw_path).query, keep_blank_values=True)
        action = values.get("action", [""])[0]
        return target.observe(action)
    return Observation(404, {"status": "not_found"})
