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

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
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
    # NOTE: no min_length here — the empty-address case is legal for exactly one
    # combination (national_ct + signal), enforced by _empty_addresses_only_when
    # below, which needs list_type and obligation_vs_signal in hand.
    designated_addresses: list[str]
    designation_date: str
    # Phase 8 Part I-B: which list, and when (see the dataclass in
    # scenario/models.py for the field semantics).
    source_regime: str = Field(min_length=1)
    list_type: Literal["national_ct", "sdn_style", "un_style"]
    obligation_vs_signal: Literal["obligation", "signal"]
    listed_since: str

    @field_validator("designated_addresses")
    @classmethod
    def _addresses_well_formed(cls, v: list[str]) -> list[str]:
        for addr in v:
            if not addr or not addr.strip() or addr != addr.strip():
                raise ValueError("designated address must be a non-empty token")
            if any(ch.isspace() for ch in addr) or ";" in addr:
                raise ValueError("designated address must not contain whitespace or ';'")
        return v

    @field_validator("designation_date", "listed_since")
    @classmethod
    def _date_is_iso(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"date must be ISO: {v!r}") from exc
        return v

    @model_validator(mode="after")
    def _empty_addresses_only_when_national_ct_signal(self) -> "Designation":
        """An empty address list is permitted IFF this is a national_ct entry
        carrying a signal (never an obligation) — a name-only foreign listing
        with no on-chain identifiers, surfaced by the name screen for identity
        review. Every other combination must carry at least one address, so a
        sdn_style / obligation designation can never arrive addressless and
        silently sweep nothing.
        """
        if not self.designated_addresses:
            if not (self.list_type == "national_ct"
                    and self.obligation_vs_signal == "signal"):
                raise ValueError(
                    "empty designated_addresses permitted only for a "
                    "national_ct + signal entry (name-only foreign listing); "
                    f"got list_type={self.list_type!r}, "
                    f"obligation_vs_signal={self.obligation_vs_signal!r}"
                )
        return self


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
    raw_addrs = str(rec["designated_addresses"])
    # A name-only (empty) address list round-trips through the CSV as the empty
    # string; splitting that yields [""], which the well-formedness check would
    # reject — so map it back to the empty list the model expects.
    addresses = raw_addrs.split(";") if raw_addrs else []
    return parse_designation({
        "designation_id": str(rec["designation_id"]),
        "designated_name": str(rec["designated_name"]),
        "program": str(rec["program"]),
        "entity_type": str(rec["entity_type"]),
        "designated_addresses": addresses,
        "designation_date": str(rec["designation_date"]),
        "source_regime": str(rec["source_regime"]),
        "list_type": str(rec["list_type"]),
        "obligation_vs_signal": str(rec["obligation_vs_signal"]),
        "listed_since": str(rec["listed_since"]),
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
