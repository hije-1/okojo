"""Designation parsing (fail-closed) and designated-name screening.

``parse_designation`` is the sweep's input boundary and it ships closed: the
pasted payload is validated strictly (unknown fields rejected, every field
typed and constrained) BEFORE anything else happens, and ``designation_id`` —
which later names a filesystem directory — must match a fixed shape before any
path is derived from it. A malformed paste is a clean rejection: nothing is
written, no partial audit chain exists, because parsing is a pure function
that touches no disk. This boundary may face untrusted input in a later phase;
it is built for that now.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from rapidfuzz import fuzz

from ..connectors import Connectors, Record
from ..provenance import Provenance
from . import NAME_MATCH_THRESHOLD

# The only designation-id shape the sweep accepts, validated before any path
# is touched. Uppercase-letters/digits/hyphens only — no separators, no dots,
# nothing a filesystem could interpret.
DESIGNATION_ID_PATTERN = r"^[A-Z]{3}-\d{4}-\d{4}$"


class DesignationParseError(ValueError):
    """A designation payload was rejected. Nothing was written anywhere."""


class Designation(BaseModel):
    """A validated synthetic designation — the sweep's trigger input."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    designation_id: str = Field(pattern=DESIGNATION_ID_PATTERN)
    designated_name: str = Field(min_length=1)
    program: str = Field(min_length=1)
    entity_type: Literal["individual", "company"]
    designated_addresses: list[str] = Field(min_length=1)
    designation_date: str

    @field_validator("designated_addresses")
    @classmethod
    def _addresses_well_formed(cls, v: list[str]) -> list[str]:
        for addr in v:
            if not addr or not addr.strip() or addr != addr.strip():
                raise ValueError("designated address must be a non-empty token")
            if any(ch.isspace() for ch in addr) or ";" in addr:
                raise ValueError("designated address must not contain whitespace or ';'")
        return v

    @field_validator("designation_date")
    @classmethod
    def _date_is_iso(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"designation_date must be an ISO date: {v!r}") from exc
        return v


def parse_designation(raw: Union[str, dict]) -> Designation:
    """Parse a pasted designation (JSON text or an already-decoded mapping).

    Fail-closed: any malformed payload — invalid JSON, a non-object, unknown
    fields, an empty address list, an id that is not exactly the published
    shape — raises :class:`DesignationParseError`. Pure function: no file,
    directory, or audit record exists until a designation has fully validated.
    """
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DesignationParseError(f"designation payload is not valid JSON: {exc}") from exc
    else:
        data = raw
    if not isinstance(data, dict):
        raise DesignationParseError("designation payload must be a JSON object")
    try:
        return Designation(**data)
    except ValidationError as exc:
        raise DesignationParseError(f"designation payload rejected: {exc}") from exc


def designation_from_record(rec: Record) -> Designation:
    """Build a validated :class:`Designation` from a ``designations`` table row.

    The CSV row goes through exactly the same model as a pasted payload — one
    validation boundary, not two.
    """
    return parse_designation({
        "designation_id": str(rec["designation_id"]),
        "designated_name": str(rec["designated_name"]),
        "program": str(rec["program"]),
        "entity_type": str(rec["entity_type"]),
        "designated_addresses": str(rec["designated_addresses"]).split(";"),
        "designation_date": str(rec["designation_date"]),
    })


class DesignationNameMatch(BaseModel):
    """An account whose registered name resembles the designated name."""

    uid: int
    entity_name: str
    score: float
    provenance: list[Provenance]


def match_designated_name(
    conn: Connectors,
    designation: Designation,
    threshold: int = NAME_MATCH_THRESHOLD,
) -> list[DesignationNameMatch]:
    """Fuzzy-screen every account name against the designated name.

    The same evasion pattern the SDN screener defeats: an account opened under
    a transliteration variant of a designated name slides past an exact-match
    screen. Each hit is grounded in the account row it screens. Ordered by uid.
    """
    hits: list[DesignationNameMatch] = []
    for acct in conn.all_accounts():
        s = fuzz.WRatio(str(acct["entity_name"]), designation.designated_name)
        if s >= threshold:
            hits.append(DesignationNameMatch(
                uid=int(acct["uid"]),
                entity_name=str(acct["entity_name"]),
                score=round(float(s), 1),
                provenance=[acct.provenance],
            ))
    return sorted(hits, key=lambda h: h.uid)
