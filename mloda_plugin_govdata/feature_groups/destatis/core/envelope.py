"""GENESIS reply shapes (typed from the pinned OpenAPI spec where it types them) and the status mapping.

Three JSON shapes exist: the nested envelope (``Ident``, ``Status`` object, ``Parameter``, ``Object``
or ``List`` or neither, ``Copyright``), the flat ``logincheck`` reply (``Status`` is a string), and a
flat top-level status (``Code``, ``Content``, ``Type``) that the ``data`` and ``metadata`` services
send with HTTP 401 or 404. Each has its own model; the HTTP status is inspected next to the body.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import (
    GenesisAuthError,
    GenesisBackendError,
    GenesisEmptySelection,
    GenesisJobAccepted,
    GenesisMaintenance,
    GenesisResultTooLarge,
    GenesisUnknownEnvelope,
    GenesisUnknownTable,
)
from .redact import CREDENTIAL_KEYS, REDACTED

# Status codes. "documented": Anwenderdokumentation v5.1 examples; "observed": live on 2026-08-16;
# "pystatis": recorded by that client's maintainers, not observed here yet (re-pin from a capture).
CODE_OK = 0  # documented
CODE_GENERIC_ERROR = 2  # observed: backend outage and wrong credentials share it, the text decides
CODE_NOT_AUTHORIZED = 15  # observed (HTTP 401): credential headers missing or not recognized
CODE_PARAMETER_ADJUSTED = 22  # documented (Warnung): a parameter was corrected, the request ran
CODE_TABLE_NOT_FOUND = 90  # pystatis
CODE_RESULT_TOO_LARGE = 98  # pystatis
CODE_NO_OBJECTS = 104  # documented (Information): no objects for the selection

# Lower-cased Content substrings.
TEXT_BACKEND_ERROR = "unerwarteten systemfehlers"  # observed
TEXT_BAD_CREDENTIALS: tuple[str, ...] = (
    "nutzernamen bzw.",  # observed: wrong user or password
    "geben sie ihr passwort ein",  # observed: an unknown token (for example from the other host)
    "zugangsdaten nicht erkannt",  # observed with code 15
)
TEXT_JOB_ACCEPTED = "bearbeitungsauftrag wurde erstellt"  # pystatis
TEXT_TOO_LARGE = "zu groß"  # pystatis
LOGINCHECK_OK = "erfolgreich an- und abgemeldet"  # documented and observed
GUEST_USERNAME = "GAST"

_ZIP_MAGIC = b"PK\x03\x04"


def _none_to_empty(value: object) -> object:
    return "" if value is None else value


class GenesisStatus(BaseModel):
    """Spec ``Status``; ``Type`` is compared case-insensitively (``ERROR`` observed, ``Error`` documented)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    code: int = Field(alias="Code")
    content: str = Field(default="", alias="Content")
    type: str = Field(default="", alias="Type")

    @field_validator("content", "type", mode="before")
    @classmethod
    def _text(cls, value: object) -> object:
        return _none_to_empty(value)

    @property
    def is_error(self) -> bool:
        return self.type.lower() in {"error", "fehler"}

    @property
    def is_warning(self) -> bool:
        return self.type.lower() in {"warning", "warnung"}

    def as_dict(self) -> dict[str, Any]:
        return {"Code": self.code, "Content": self.content, "Type": self.type}


class GenesisIdent(BaseModel):
    """Spec ``Ident``: which service and method answered."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    service: str = Field(default="", alias="Service")
    method: str = Field(default="", alias="Method")

    @field_validator("service", "method", mode="before")
    @classmethod
    def _text(cls, value: object) -> object:
        return _none_to_empty(value)


class GenesisEnvelope(BaseModel):
    """The nested JSON reply. ``parameter`` drops ``username`` and ``password`` at parse time."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    ident: GenesisIdent | None = Field(default=None, alias="Ident")
    status: GenesisStatus = Field(alias="Status")
    parameter: dict[str, Any] = Field(default_factory=dict, alias="Parameter")
    data: dict[str, Any] | None = Field(default=None, alias="Object")
    entries: list[Any] | None = Field(default=None, alias="List")
    copyright: str | None = Field(default=None, alias="Copyright")

    @field_validator("parameter", mode="before")
    @classmethod
    def _strip_credentials(cls, value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("Parameter must be an object")  # noqa: TRY004  (pydantic turns ValueError into a validation error)
        return {str(k): v for k, v in value.items() if str(k).lower() not in CREDENTIAL_KEYS}


class LoginCheckReply(BaseModel):
    """``helloworld/logincheck``: flat, ``Status`` is a string. Repr redacts the echoed username."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    status: str = Field(default="", alias="Status")
    username: str = Field(default="", alias="Username")

    @field_validator("status", "username", mode="before")
    @classmethod
    def _text(cls, value: object) -> object:
        return _none_to_empty(value)

    @property
    def is_guest(self) -> bool:
        return self.username.strip().upper() == GUEST_USERNAME

    @property
    def is_success(self) -> bool:
        return LOGINCHECK_OK in self.status.lower() and not self.is_guest

    def __repr_args__(self) -> Iterator[tuple[str | None, Any]]:
        yield "status", self.status
        yield "username", (GUEST_USERNAME if self.is_guest else REDACTED)


class HelloWorldReply(BaseModel):
    """``helloworld/whoami``: only the request's User-Agent comes back."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    user_agent: str = Field(default="", alias="User-Agent")


JsonReply = GenesisEnvelope | LoginCheckReply | HelloWorldReply | GenesisStatus


def parse_json_reply(payload: Any) -> JsonReply:
    """Pick the model by keys; a flat ``Code``/``Content``/``Type`` body parses as a bare ``GenesisStatus``."""
    if not isinstance(payload, dict):
        raise GenesisUnknownEnvelope(f"GENESIS reply is not a JSON object: {type(payload).__name__}")
    status = payload.get("Status")
    if isinstance(status, dict):
        return GenesisEnvelope.model_validate(payload)
    if isinstance(status, str):
        return LoginCheckReply.model_validate(payload)
    if "Code" in payload and "Content" in payload:
        return GenesisStatus.model_validate(payload)
    if "User-Agent" in payload:
        return HelloWorldReply.model_validate(payload)
    raise GenesisUnknownEnvelope(f"Unknown GENESIS reply shape with keys {sorted(map(str, payload))!r}")


def raise_for_status_block(
    status: GenesisStatus, *, http_status: int | None = None, endpoint: str | None = None
) -> None:
    """Map a status block to a typed exception; code 0 and the parameter-adjusted warning pass."""
    text = status.content.lower()
    details: dict[str, Any] = {"endpoint": endpoint, "http_status": http_status, "status_block": status.as_dict()}
    if TEXT_BACKEND_ERROR in text:
        raise GenesisBackendError(
            f"GENESIS backend error: {status.content} The host returns this during outages and, as observed, "
            "for guest or wrong credentials. Retry later; if it persists, check the credentials in the web UI.",
            **details,
        )
    if status.code == CODE_NOT_AUTHORIZED or any(marker in text for marker in TEXT_BAD_CREDENTIALS):
        raise GenesisAuthError(
            f"GENESIS rejected the credentials or found none in the request headers: {status.content} "
            "Registrations are per host; a token from another GENESIS installation is not valid here.",
            **details,
        )
    if TEXT_JOB_ACCEPTED in text:
        raise GenesisJobAccepted(f"GENESIS queued a background job instead of a table: {status.content}", **details)
    if status.code == CODE_RESULT_TOO_LARGE or TEXT_TOO_LARGE in text:
        raise GenesisResultTooLarge(f"GENESIS result too large for a direct download: {status.content}", **details)
    if status.code == CODE_TABLE_NOT_FOUND:
        raise GenesisUnknownTable(f"GENESIS does not know the table: {status.content}", **details)
    if status.code == CODE_NO_OBJECTS:
        raise GenesisEmptySelection(f"GENESIS found no objects for the selection: {status.content}", **details)
    if status.code in (CODE_OK, CODE_PARAMETER_ADJUSTED) and not status.is_error:
        return
    raise GenesisUnknownEnvelope(f"Unknown GENESIS status block {status.as_dict()!r} (HTTP {http_status})", **details)


def raise_for_logincheck(
    reply: LoginCheckReply, *, http_status: int | None = None, endpoint: str | None = None
) -> None:
    """Success text plus a real username passes; ``GAST`` is an auth failure even next to the success text."""
    text = reply.status.lower()
    details: dict[str, Any] = {
        "endpoint": endpoint,
        "http_status": http_status,
        "status_block": {"Status": reply.status},
    }
    if TEXT_BACKEND_ERROR in text:
        raise GenesisBackendError(
            f"GENESIS backend error on logincheck: {reply.status} Retry later; if it persists, check the "
            "credentials in the web UI.",
            **details,
        )
    if reply.is_guest:
        raise GenesisAuthError(
            f"logincheck ran as guest (Username {GUEST_USERNAME}): the credential headers were not sent or not "
            f"recognized. Server text: {reply.status}",
            **details,
        )
    if any(marker in text for marker in TEXT_BAD_CREDENTIALS):
        raise GenesisAuthError(
            f"GENESIS rejected the credentials: {reply.status} Registrations are per host; a token from another "
            "GENESIS installation is not valid here.",
            **details,
        )
    if LOGINCHECK_OK in text:
        return
    raise GenesisUnknownEnvelope(f"Unknown logincheck status {reply.status!r} (HTTP {http_status})", **details)


@dataclass(frozen=True)
class InspectedReply:
    """What came back: a zip payload (``reply`` is None, ``body`` holds it) or a parsed, status-checked JSON reply."""

    kind: Literal["zip", "json"]
    http_status: int
    content_type: str
    reply: JsonReply | None
    body: bytes


def _looks_like_html(content_type: str, body: bytes) -> bool:
    return "html" in content_type or body.lstrip()[:1] == b"<"


def inspect_response(response: httpx.Response, endpoint: str | None = None) -> InspectedReply:
    """Classify by content type and body, parse JSON into its model, and raise the mapped exception."""
    content_type = response.headers.get("content-type", "").lower()
    body = response.content
    http_status = response.status_code
    if body[: len(_ZIP_MAGIC)] == _ZIP_MAGIC:
        return InspectedReply(kind="zip", http_status=http_status, content_type=content_type, reply=None, body=body)
    if _looks_like_html(content_type, body):
        raise GenesisMaintenance(
            f"GENESIS answered with an HTML page instead of JSON (HTTP {http_status}, {content_type or 'no content type'}); "
            "the host is likely in maintenance or returned an error page. Retry later.",
            endpoint=endpoint,
            http_status=http_status,
        )
    try:
        payload = json.loads(body)
    except ValueError:
        raise GenesisUnknownEnvelope(
            f"GENESIS reply is neither a zip nor JSON (HTTP {http_status}, {content_type or 'no content type'}): "
            f"{body[:200]!r}",
            endpoint=endpoint,
            http_status=http_status,
        ) from None
    reply = parse_json_reply(payload)
    if isinstance(reply, GenesisEnvelope):
        raise_for_status_block(reply.status, http_status=http_status, endpoint=endpoint)
    elif isinstance(reply, GenesisStatus):
        raise_for_status_block(reply, http_status=http_status, endpoint=endpoint)
    elif isinstance(reply, LoginCheckReply):
        raise_for_logincheck(reply, http_status=http_status, endpoint=endpoint)
    if http_status >= 400:
        raise GenesisUnknownEnvelope(
            f"GENESIS answered HTTP {http_status} with a status block this client does not map",
            endpoint=endpoint,
            http_status=http_status,
        )
    return InspectedReply(kind="json", http_status=http_status, content_type=content_type, reply=reply, body=body)
