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
class KycArtifact:
    """One onboarding artifact on file for an account (Phase 8 Part I-B S3).

    The DATA the world holds — one row per (account, artifact) with a present
    flag — checked by the sweep against the INDEPENDENT required-artifact
    standard published in ``sweep_config()``. The two are deliberately separate:
    this table records what is on file; the policy records what is required, so
    changing the standard changes what counts as a gap without touching the
    data. Full per-account coverage (the Slice-A hold-table pattern); the single
    planted gap is a missing proof-of-address on the ultimate controller."""

    uid: int
    artifact_type: str        # e.g. "government_id" | "proof_of_address"
    present: bool


@dataclass
class StaffRegister:
    """An employee-account entry in the staff register (Phase 8 Part I-B S3).

    Typologically real: exchanges maintain a register of employee-owned accounts
    for conflict-of-interest monitoring. The insider-linkage worksheet flag reads
    THIS register ONLY to identify a staff account — never ``role_in_ring`` or
    any ground-truth key — and fires the severe flag only where staff membership
    coincides with a device overlap into the exposed network."""

    staff_id: str
    uid: int
    department: str
    employment_status: str    # "active" | "former"
    onboarded_date: str


@dataclass
class DesignationIdentifier:
    """The identifying data a sanctions list publishes for a designated party
    (Phase 8 Part II T2).

    Kept in its own sibling table so ``designations.csv`` stays byte-identical
    (Decision R4). A field left empty means the list published no such
    identifier for this entry (a name-only foreign listing) — corroboration
    reads an absent field as UNKNOWN, never as a mismatch. Compared against a
    matched customer's :class:`KycIdentityAttribute` row by the corroboration
    decision to separate a true hit from a same-name collision."""

    designation_id: str
    dob: str                  # ISO date, or "" if the list published none
    nationality: str          # ISO-3166 alpha-2, or ""
    doc_type: str             # e.g. "PASSPORT", or ""
    doc_number: str           # government document number, or ""


@dataclass
class KycIdentityAttribute:
    """A customer's KYC identity attributes for identity resolution (Phase 8
    Part II T2; the shared substrate T4's proximity ring also reads).

    One row per identity-review subject — the corroboration substrate compared
    against a :class:`DesignationIdentifier`. ``address`` / ``email`` are
    synthetic and carried for T4 (shared-attribute proximity signals); T2 uses
    ``dob`` / ``nationality`` / ``doc_number``. A new sibling table (R4), so
    every existing CSV stays byte-identical."""

    uid: int
    dob: str                  # ISO date
    nationality: str          # ISO-3166 alpha-2
    address: str
    email: str
    doc_type: str
    doc_number: str


@dataclass
class BeneficialOwnership:
    """A synthetic KYB beneficial-ownership edge (Phase 8 Part II T3).

    One row per (owner, company) ownership stake. Kept in its own sibling table
    so every existing CSV stays byte-identical (Decision R4). ``ownership_pct`` is
    a fraction in [0, 1]; designation status propagates through this edge to the
    company only at or above the published ``OWNERSHIP_CONTROL_THRESHOLD``
    (majority control, principle level). An ownership edge is a DISTINCT edge
    type: like a gas-funding edge, it can never fabricate on-chain flow exposure
    — it surfaces control/status for review only. ``as_of_date`` dates the stake
    (an ownership change dated after a designation is a control-change signal)."""

    owner_uid: int
    company_uid: int
    ownership_pct: float       # fraction in [0, 1]
    as_of_date: str            # ISO date the stake was recorded


@dataclass
class OfficerAppointment:
    """A synthetic corporate officer appointment (Phase 8 Part II T3).

    A sibling table to ``registry.csv`` (kept byte-identical, R4) carrying the
    officer/operator structure the ownership walk reads. ``officer_uid`` is the
    scenario ground-truth join key when the officer resolves to a customer
    account; a name-only appointment (``officer_uid`` empty, ``officer_name``
    set) is how a company can name an officer with no resolvable identity
    footprint — the FICTITIOUS-EXECUTIVE pattern the walk flags. ``appointed_date``
    dated shortly after a designation is the POST-DESIGNATION CONTROL-CHANGE
    pattern. Both are surfaced for REVIEW; neither ever moves on-chain exposure."""

    appointment_id: str
    company_uid: int
    officer_uid: str           # "" == name-only (no resolvable account)
    officer_name: str
    role: str                  # e.g. "director" | "secretary"
    appointed_date: str        # ISO date
    resigned_date: str         # "" == currently serving


@dataclass
class Relationship:
    """A declared relationship between two customers (Phase 8 Part II T4).

    Declared-relationship metadata on file (e.g. next-of-kin, director-family) —
    a NEW sibling table so every existing surface stays byte-identical (R4). It is
    a *correlational* signal the proximity layer surfaces WITH its evidence; the
    system never asserts kinship as fact. Directed pair ``(uid_a, uid_b)``."""

    uid_a: int
    uid_b: int
    declared_relationship: str    # e.g. "sibling" | "spouse" | "parent"


@dataclass
class RelationshipAssertion:
    """A relationship-asserting artifact between two customers (Phase 8 Part II T4).

    A NEW sibling table (keeps the remark/registry surfaces byte-identical, R4)
    carrying the free-text and document signals the proximity layer reads without
    ever touching ``transactions.remark``: a relationship-asserting remark, or a
    KYC-document cross-holding (one party's identity document on file inside
    another's account). ``assertion_type`` keys which proximity signal it feeds.
    Surfaced as evidence; never an assertion of kinship as fact."""

    assertion_id: str
    subject_uid: int              # the resolved/designated party
    related_uid: int              # the candidate associate
    assertion_type: str           # "relationship_remark" | "kyc_document_cross_holding"
    detail: str


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
