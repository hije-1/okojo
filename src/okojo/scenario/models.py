"""Typed record shapes for the synthetic scenario.

Plain dataclasses so the generator stays dependency-light. Each corresponds to
one output table; field names follow generic public column conventions for
exchange / AML data, so downstream connectors feel realistic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Account:
    uid: int
    entity_name: str
    entity_type: str          # "individual" | "company"
    role_in_ring: str         # e.g. "ultimate_controller", "shell_trading", "noise"
    residence_country: str
    nationality_country: str
    kyc_doc_id: str
    registration_date: str
    vip_level: str
    prior_review_count: int
    account_status: str       # "active" | "retain_monitor" | "offboarded"
    internal_tag: Optional[str] = None   # the internal "do-not-block" account red herring


@dataclass
class KycDoc:
    kyc_doc_id: str
    doc_type: str
    holder_name: str
    holder_dob: str
    issuing_country: str


@dataclass
class DeviceLink:
    device_fingerprint: str
    uid: int


@dataclass
class IpLog:
    uid: int
    real_ip: str
    geolocation: str
    is_vpn: bool
    timestamp: str


@dataclass
class Address:
    address: str
    network: str              # "TRX" | "EVM"
    controller_uid: Optional[int]   # ground truth (None = external / unknown)
    label: str               # "" | "IRGC-STYLE-SYNTHETIC" | "non-custodial-hop" | ...
    is_sanctioned_synthetic: bool


@dataclass
class GasFund:
    funder_address: str
    funded_address: str


@dataclass
class Transaction:
    tx_id: str
    from_ref: str            # a uid (as "uid:...") or an address
    to_ref: str
    amount_usdt: float
    network: str
    timestamp: str
    remark: str
    is_structured_round_number: bool
    direction: str           # "deposit" | "withdrawal" | "onchain"


@dataclass
class SdnEntry:
    """A synthetic sanctions-watchlist entry (the Tell Miner's fuzzy-match target).

    Fully fabricated. Some aliases are deliberate transliteration variants of ring
    members' names, so a fuzzy matcher flags the account while an exact-match
    screen would miss it; others are decoys that must not match (precision)."""

    sdn_id: str
    primary_name: str
    aliases: str              # ';'-separated alias strings
    program: str              # synthetic sanctions program label
    entity_type: str          # "individual" | "company"


@dataclass
class Rfi:
    rfi_id: str
    uid: int
    question: str
    response_text: str
    claims: list = field(default_factory=list)   # list[dict]: {claim_id, text, ground_truth}


@dataclass
class RegistryRecord:
    """A synthetic corporate-registry officer appointment (OSINT substrate).

    Fabricated: company numbers, officer names, and every date derive from
    personas the generator already created, so no new identity is introduced.
    Supports the RFI Contradiction-Checker's registry probe - notably two
    entities an RFI calls unrelated sharing one director over an overlapping
    window. ``company_uid`` / ``officer_uid`` are the scenario's ground-truth
    join keys, the same convention as ``Address.controller_uid``."""

    registry_id: str
    company_number: str
    company_name: str
    jurisdiction: str
    incorporation_date: str
    officer_name: str
    officer_role: str
    appointed_date: str
    resigned_date: str        # "" == currently serving
    company_uid: int
    officer_uid: int


@dataclass
class Designation:
    """A synthetic OFAC-style designation (the remediation sweep's trigger input).

    Fully fabricated: the designated name is a transliteration-style variant of
    a generated persona, the addresses are generated or fixed non-ledger
    literals, and the program label is the synthetic one used throughout.
    ``designated_addresses`` is ';'-joined for the CSV, mirroring
    ``SdnEntry.aliases``."""

    designation_id: str
    designated_name: str
    program: str              # synthetic sanctions program label
    entity_type: str          # "individual" | "company"
    designated_addresses: str  # ';'-separated on-chain addresses
    designation_date: str
    # Phase 8 Part I-B: which list this came from and when. ``source_regime``
    # keys the published ``list_source_registry`` (sweep_config); ``list_type``
    # is national_ct | sdn_style | un_style; ``obligation_vs_signal`` records
    # whether an entry binds our synthetic exchange (obligation) or is a
    # timestamped risk signal only (signal); ``listed_since`` is the ISO date
    # the source list first carried the entry (== designation_date for domestic
    # sdn_style entries; earlier than it for a foreign lead-time plant).
    source_regime: str
    list_type: str            # "national_ct" | "sdn_style" | "un_style"
    obligation_vs_signal: str  # "obligation" | "signal"
    listed_since: str          # ISO date the source list first carried this entry


@dataclass
class WarehouseHold:
    """Sanctions hold status in the analytics warehouse (the feed-fed copy).

    One of two mock systems the sweep reconciles; drift between this table and
    the admin system of record is the planted data-integrity gap."""

    uid: int
    hold_status: str          # "blocked" | "no_hold"
    as_of_date: str           # date the feed last updated this row
    feed_batch_id: str


@dataclass
class AdminHold:
    """Sanctions hold status in the operational admin system (system of record)."""

    uid: int
    hold_status: str          # "blocked" | "no_hold"
    status_date: str          # date of the last status action
    actioned_by: str
    case_ref: str             # "" == no associated ops case


@dataclass
class PriorRfi:
    """An earlier RFI answer from the same subject.

    Kept in its own table so the RFI under review (``rfi.csv``) stays exactly as
    it is. Carries no ground-truth label: a prior answer is *evidence* the
    contradiction checker tests against, never an answer key."""

    rfi_id: str
    uid: int
    asked_date: str
    question: str
    response_text: str
    claims: list = field(default_factory=list)   # list[dict]: {claim_id, text}
