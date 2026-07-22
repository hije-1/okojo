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
class Rfi:
    rfi_id: str
    uid: int
    question: str
    response_text: str
    claims: list = field(default_factory=list)   # list[dict]: {claim_id, text, ground_truth}
