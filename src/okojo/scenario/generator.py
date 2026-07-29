"""Deterministic synthetic-scenario generator for Okojo.

Builds a fabricated oil / sanctions-evasion network that is *pattern-faithful*
to the behaviours seen in real crypto-exchange investigations, but contains no
real identities, addresses, or documents. Everything derives from ``SEED`` so
the dataset regenerates identically.

Planted patterns (each is also recorded in ``ground_truth.json`` so downstream
capabilities can be scored):

  * a cross-border ring of shell trading companies with an ultimate controller
    who hides behind family- and employee-cutout directors;
  * the *same KYC document* reused to open "separate" entities;
  * shared devices (``device_fingerprint``) across supposedly unrelated accounts;
  * logins from a sanctioned jurisdiction interleaved with VPN IPs;
  * structured, just-under round-number transfers and bidirectional near-equal
    flows through non-custodial hops toward synthetic "IRGC-style" addresses;
  * gas-funding links that betray control of a "non-custodial" wallet;
  * withdrawal remarks that name the true controller of an address;
  * a licensed-trust intermediary whose polished RFI answers are contradicted
    by the device / flow / KYC evidence (ground-truth "lies");
  * a recidivist account that cleared several prior "retain & monitor" reviews;
  * a "DON'T block — internal account" tag planted as a red herring.

Usage:
    from okojo.scenario import generate_scenario
    summary = generate_scenario()          # writes CSVs + ground_truth.json
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

try:  # prefer the real Faker (see requirements.txt); fall back if unavailable
    from faker import Faker
except ModuleNotFoundError:  # pragma: no cover
    from ._fakelite import FakeLite as Faker

from ..config import (
    RING_JURISDICTIONS,
    SANCTIONED_CITY,
    SANCTIONED_JURISDICTION,
    SEED,
    SIM_END,
    SIM_START,
    STRUCTURED_AMOUNT,
    SYNTHETIC_DIR,
)
from .models import (
    Account,
    Address,
    AdminHold,
    BeneficialOwnership,
    Designation,
    DesignationIdentifier,
    DeviceLink,
    GasFund,
    IpLog,
    KycArtifact,
    KycDoc,
    KycIdentityAttribute,
    OfficerAppointment,
    PriorRfi,
    RegistryRecord,
    Relationship,
    RelationshipAssertion,
    Rfi,
    SdnEntry,
    StaffRegister,
    Transaction,
    WarehouseHold,
)

# The onboarding artifacts the synthetic world holds on file, per entity type —
# the DATA plane of the KYC-completeness check (Slice S3). Deliberately kept
# INDEPENDENT of the sweep's required-artifact POLICY (``sweep_config()``'s
# ``required_artifacts``): the generator plants what is on file, the sweep
# decides what is required, so removing an artifact from the standard changes
# what counts as a gap without touching a single generated row. The literals
# happen to mirror the standard so that a clean account satisfies it exactly;
# the 5b eval asserts the policy-independence directly.
_KYC_EMITTED_ARTIFACTS = {
    "individual": ["government_id", "proof_of_address"],
    "company": ["certificate_of_incorporation", "beneficial_ownership"],
}

_BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_HEX = "0123456789abcdef"


# --------------------------------------------------------------------------- #
# small deterministic helpers
# --------------------------------------------------------------------------- #
def _tron_addr(rng: random.Random) -> str:
    return "T" + "".join(rng.choice(_BASE58) for _ in range(33))


def _evm_addr(rng: random.Random) -> str:
    return "0x" + "".join(rng.choice(_HEX) for _ in range(40))


def _device_fp(rng: random.Random) -> str:
    return "".join(rng.choice(_HEX) for _ in range(40))


def _rand_ts(rng: random.Random) -> str:
    span = (SIM_END - SIM_START).days
    day = SIM_START + timedelta(days=rng.randint(0, span))
    dt = datetime(day.year, day.month, day.day, rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59))
    return dt.isoformat()


def _vpn_ip(rng: random.Random) -> str:
    # RFC-5737 TEST-NET-3 — guaranteed non-routable / synthetic.
    return f"203.0.113.{rng.randint(1, 254)}"


def _tehran_ip(rng: random.Random) -> str:
    # RFC-5737 TEST-NET-2 — synthetic; stands in for a sanctioned-jurisdiction IP.
    return f"198.51.100.{rng.randint(1, 254)}"


_VOWEL_SWAP = {"a": "e", "e": "i", "i": "o", "o": "u", "u": "a"}


def _alias_variant(name: str) -> str:
    """A deterministic transliteration-style variant of a name.

    Swaps the first vowel in the last whitespace token, yielding a near-duplicate
    (~90% similar) that a fuzzy matcher catches but an exact-match sanctions
    screen would miss — the evasion pattern the Tell Miner is built to defeat.
    """
    parts = name.split()
    if not parts:
        return name
    chars = list(parts[-1])
    for i, ch in enumerate(chars):
        if ch.lower() in _VOWEL_SWAP:
            repl = _VOWEL_SWAP[ch.lower()]
            chars[i] = repl.upper() if ch.isupper() else repl
            break
    parts[-1] = "".join(chars)
    return " ".join(parts)


def _uids_with_sanctioned_exposure(
    txs: list, address_controllers: dict[str, int], sanctioned_addrs: list[str], candidate_uids: list[int]
) -> list[int]:
    """UIDs whose funds can reach a synthetic sanctioned endpoint by directed flow.

    Derived purely from already-generated data (no RNG draws), so the label stays
    in sync with the planted scenario and does not perturb determinism. A uid is
    "exposed" if a value-transaction path leads from a wallet it controls, or from
    a transaction it sends, to any synthetic sanctioned address. This is the
    definitional answer key for the On-chain Risk Scorer — deliberately a plain
    reachability truth, independent of any scorer heuristics (hop caps, amount
    weighting) so the eval is not tautological.
    """
    from collections import deque

    adj: dict[str, set[str]] = {}

    def _link(a: str, b: str) -> None:
        adj.setdefault(a, set()).add(b)

    for t in txs:
        _link(t.from_ref, t.to_ref)
    for addr, uid in address_controllers.items():
        _link(f"uid:{uid}", addr)  # a controller can move its own wallet's funds

    sanctioned = set(sanctioned_addrs)

    def _reaches(start: str) -> bool:
        seen = {start}
        dq = deque(adj.get(start, ()))
        while dq:
            node = dq.popleft()
            if node in sanctioned:
                return True
            if node in seen:
                continue
            seen.add(node)
            dq.extend(adj.get(node, ()))
        return False

    return sorted(u for u in candidate_uids if _reaches(f"uid:{u}"))


def _designation_exposure(
    txs: list, address_controllers: dict[str, int], designated_addrs: list[str], candidate_uids: list[int]
) -> tuple[list[int], dict[int, int], list[int]]:
    """Per-uid exposure to a set of designated addresses, with hop distance.

    The distance-recording sibling of :func:`_uids_with_sanctioned_exposure`,
    over the same ``{transaction, controls}`` edge semantics — gas-funding links
    are deliberately NOT flow edges, so they can never fabricate exposure. Like
    its sibling this is a definitional answer key computed from already-generated
    data (zero RNG draws), independent of any sweep-engine heuristics so the
    Phase-8 eval is not tautological.

    ``hops`` = the minimum number of *transaction* edges on a directed path from
    the subject (its uid node or any wallet it controls, all at distance 0) to a
    designated address; 0 therefore means the subject controls a designated
    address outright. ``direct`` <=> hops <= 1: the subject controls a designated
    address, or a single transaction of its lands on one.

    Returns ``(exposed_uids sorted, {uid: hops}, direct_uids sorted)``.
    """
    from collections import deque

    adj: dict[str, list[str]] = {}
    for t in txs:
        adj.setdefault(t.from_ref, []).append(t.to_ref)
    controlled: dict[int, list[str]] = {}
    for addr, uid in address_controllers.items():
        controlled.setdefault(uid, []).append(addr)
    designated = set(designated_addrs)

    hops: dict[int, int] = {}
    for uid in candidate_uids:
        start = [f"uid:{uid}"] + controlled.get(uid, [])
        if any(node in designated for node in start):
            hops[uid] = 0
            continue
        dist = {node: 0 for node in start}
        dq = deque(start)
        found: Optional[int] = None
        while dq and found is None:
            node = dq.popleft()
            for nb in adj.get(node, ()):
                if nb in designated:
                    found = dist[node] + 1  # BFS pops in distance order -> minimal
                    break
                if nb not in dist:
                    dist[nb] = dist[node] + 1
                    dq.append(nb)
        if found is not None:
            hops[uid] = found

    exposed = sorted(hops)
    direct = sorted(u for u, h in hops.items() if h <= 1)
    return exposed, hops, direct


# --------------------------------------------------------------------------- #
# the ring specification (structure is fixed; names/ids are generated)
# --------------------------------------------------------------------------- #
# (key, entity_type, role_in_ring, jurisdiction)
_RING_SPEC = [
    ("KINGPIN", "individual", "ultimate_controller", "AE"),
    ("SIBLING", "individual", "family_cutout_director", "AE"),
    ("EMPLOYEE", "individual", "employee_cutout", "TR"),
    ("TRUST", "company", "licensed_trust_intermediary", "HK"),
    ("SHELL_AE", "company", "shell_trading", "AE"),
    ("SHELL_TR", "company", "shell_trading", "TR"),
    ("SHELL_HK", "company", "shell_trading", "HK"),
    ("SHELL_NZ", "company", "shell_trading", "NZ"),
    ("SHELL_CN", "company", "shell_trading", "CN"),
    ("PRIVILEGED", "company", "privileged_internal_redherring", "AE"),
    ("RECIDIVIST", "individual", "recidivist_mule", "HK"),
]

_NOISE_ACCOUNTS = 12  # ordinary users so the ring isn't trivially separable


# --------------------------------------------------------------------------- #
# Which evidence rebuts which RFI claim — ONE definition, three consumers.
#
# Consumed by (a) the claim's ``contradicted_by`` prose in ``rfi.csv``, (b)
# ``ground_truth["rfi_claim_key"]``'s ``expected_sources`` (the eval's answer
# key), and (c) which Phase-5 checkers are expected to fire. A guard test asserts
# all three agree, so they can never silently drift apart again.
#
# They HAD drifted: C2 originally cited reused-KYC and shared-device rebuttals
# that were never planted (the reused-KYC pairs are SIBLING/SHELL_AE and
# EMPLOYEE/EMPLOYEE-2; no shared device pairs the trust with SHELL_NZ). Neither
# could be planted without adding rows to the frozen accounts/devices tables, so
# C2 is re-based onto three sources that exist: the corporate registry's common
# director, the subject's own prior RFI answer, and the layering flows that
# already run between the two entities.
#
# Ordered lists of (source_key, prose_note) — never a set, so ordering is stable
# across platforms and hash seeds. The C4 notes are byte-for-byte the originals:
# C4's rebuttals were always substantiated by planted data and are unchanged.
_RFI_CLAIM_SOURCES: dict[str, list[tuple[str, str]]] = {
    "C1": [
        ("device", "shared device_fingerprint between the trust and accounts it "
                   "transacts with, undercutting fully segregated custody"),
    ],
    "C2": [
        ("registry", "corporate registry shows a common director across the two "
                     "entities over an overlapping appointment window"),
        ("prior_rfi", "the subject's own earlier RFI answer describes a management "
                      "services agreement with the same entity"),
        ("onchain", "bidirectional near-equal transfers between the two entities' "
                    "controller wallets"),
    ],
    "C3": [],
    "C4": [
        ("onchain", "downstream exposure to synthetic IRGC-style sanctioned addresses"),
        ("onchain", "structured just-under round-number transfers"),
        ("onchain", "gas-funded 'non-custodial' hops controlled by the same party"),
    ],
}

# Expected adjudication per claim. ``contradicted`` is the eval's positive class;
# ``qualified`` and ``unverifiable`` are correct non-positive outcomes.
_RFI_CLAIM_VERDICTS: dict[str, str] = {
    "C1": "qualified",
    "C2": "contradicted",
    "C3": "unverifiable",
    "C4": "contradicted",
}

_RFI_CLAIM_ORDER = ["C1", "C2", "C3", "C4"]


def _sources_for(claim_id: str) -> list[str]:
    """Distinct source keys for a claim, sorted — the eval's expected_sources."""
    return sorted({key for key, _ in _RFI_CLAIM_SOURCES[claim_id]})


def _notes_for(claim_id: str) -> list[str]:
    """The claim's ``contradicted_by`` prose, in declaration order."""
    return [note for _, note in _RFI_CLAIM_SOURCES[claim_id]]


# Corporate-registry appointments: (company_key, officer_key, role, resigned_date).
# An explicit ordered list — the planted fact is the first two rows, where the
# licensed trust and SHELL_NZ (which the RFI calls unrelated) share one director.
_REGISTRY_SPEC = [
    ("TRUST", "KINGPIN", "director", ""),
    ("SHELL_NZ", "KINGPIN", "director", SIM_END.isoformat()),
    ("SHELL_AE", "SIBLING", "director", ""),
    ("SHELL_TR", "EMPLOYEE", "director", ""),
    ("SHELL_HK", "SIBLING", "director", ""),
    ("SHELL_CN", "EMPLOYEE", "director", ""),
    ("PRIVILEGED", "SIBLING", "director", ""),
]


# Fixed literal TRX-shaped addresses for the decoy designation (Phase 8's
# false-positive probe). Deliberately NOT drawn from the address generator and
# never written to addresses.csv: they touch nothing in the ledger, so the
# expected exposure for the decoy is exactly the empty set. Base58 (no 0/O/I/l),
# "T" + 33 chars, matching the real generated TRX-style addresses in shape only.
_DECOY_DESIGNATION_ADDRS = [
    "TDecoyDesignationAddrAAAAAAAAAAAAA",
    "TDecoyDesignationAddrBBBBBBBBBBBBB",
]


# ---- Phase 8 Part II (T1): identity-resolution variant-screen plants -------- #
# INVENTED, plausible romanization personas — NO source-document provenance.
# Each designated name is ONE published romanization of an underlying name; the
# matching customer opened under a DIFFERENT published romanization, so an
# exact-match (and even a single-script fuzzy) screen misses it while the variant
# layer bridges it via cited equivalence classes. A same-surname decoy whose
# first name is OUTSIDE the equivalence class must NOT match (discrimination).
# These accounts are non-transacting and carry no holds, no KYC-artifact rows,
# and no staff rows — so every legacy + Part-I-B scorecard stays byte-identical
# (the customers move only accounts.csv / kyc_docs.csv; verified by test). Built
# RNG-free below the generator boundary. Fields:
#   (designation_id, family, designated_name, customer_name, decoy_name, country)
# ``country`` is deliberately AE — a jurisdiction ALREADY present across the
# existing accounts — so these additive personas introduce NO new jurisdiction
# into the shared EntityBackbone. The variant screen resolves on NAME, never
# residence; a new jurisdiction (e.g. RU) would add a jurisdiction corroborator
# that shifts unrelated cases' advisory matching (a legacy scorecard), which the
# additive-only rule forbids. AE keeps every legacy scorecard byte-identical.
_IDENTITY_PLANTS = [
    ("DES-2026-0005", "cyrillic", "Yevgeniy Zhukovskiy",
     "Evgenii Zhukovsky", "Dmitri Zhukovsky", "AE"),
    ("DES-2026-0006", "arabic", "Muhammad Al-Sayigh",
     "Mohammed El-Sayegh", "Khalid El-Sayegh", "AE"),
]

# ---- Phase 8 Part II (T2): corroboration name-COLLISION plant --------------- #
# A third foreign name-only designation whose published-romanization variant
# ("Alexander Volkoff") matches an EXISTING-looking customer who is NOT the
# designated party — same Cyrillic name family, different individual. The
# variant screen (correctly) surfaces the collision; corroboration on DOB +
# nationality + document number DISMISSES it with the reason recorded. This is
# the sanctions-screening false positive the corroboration step exists to
# remove. NOT a member of identity_variant_matches (the designation does NOT
# refer to this customer), so the T1 variant-screen answer key and scorecard are
# untouched. INVENTED names; AE jurisdiction (no new jurisdiction introduced).
#   (designation_id, family, designated_name, customer_name, country)
_CORROBORATION_COLLISION = (
    "DES-2026-0007", "cyrillic", "Aleksandr Volkov", "Alexander Volkoff", "AE")

# The identifiers the FOREIGN list published for each identity designation's
# designated party (designation_identifiers.csv), and the DEFINITIONAL
# corroboration outcome the scenario is built to realize. decide_corroboration
# recomputes the outcome from the KYC-vs-identifier comparison, so the eval is a
# real check, never circular. A "" field == the list published no such
# identifier (a name-only listing) — read as UNKNOWN, never a mismatch.
#   did: (dob, nationality, doc_type, doc_number, outcome, mismatched_fields)
_DESIGNATION_IDENTIFIER_DATA = {
    # true hit: document number matches (and DOB + nationality match too).
    "DES-2026-0005": ("1984-05-14", "AE", "PASSPORT", "P-AE-550014",
                      "corroborated_true_hit", []),
    # needs human: nationality matches, but the list published no DOB and no
    # document number — nothing confirms and nothing disqualifies.
    "DES-2026-0006": ("", "AE", "", "",
                      "possible_match_needs_human", []),
    # dismissed: a same-name collision — DOB, nationality, and document number
    # all differ from the designated party. The reason is recorded.
    "DES-2026-0007": ("1970-03-22", "RU", "PASSPORT", "P-RU-778120",
                      "name_only_dismissed",
                      ["date of birth", "nationality", "document number"]),
}

# The matched customer's KYC identity attributes (kyc_identity_attributes.csv),
# keyed by the designation their name matches. dob mirrors the customer's KYC
# document; document numbers are distinct per customer (only DES-0005's equals
# its designation's, giving the decisive true-hit corroboration).
_CORROBORATION_CUSTOMER_KYC = {
    "DES-2026-0005": ("PASSPORT", "P-AE-550014"),
    "DES-2026-0006": ("PASSPORT", "P-AE-660021"),
    "DES-2026-0007": ("PASSPORT", "P-AE-770033"),
}

# ---- Phase 8 Part II (T3): beneficial-owner + officer walk plants ----------- #
# Hung off the DES-2026-0005 resolved true-hit (the corroborated Zhukovsky
# customer) — the walk runs from a party the screen matched AND corroboration did
# not dismiss. All accounts here are NEW, non-transacting company/officer
# personas appended AFTER every per-account loop, so holds / KYC-artifacts /
# staff tables stay byte-identical. Company names are DISTINCT from every
# designated name, so the variant screen never spuriously matches them. RNG-free.
# INVENTED names (no source provenance). The party's uid is resolved at gen time.
_T3_PARTY_DID = "DES-2026-0005"
# Two companies the party beneficially owns: one AT/above the 0.50 control
# threshold (propagates), one below (does NOT — the discrimination trap).
#   (key, company_name, ownership_pct, as_of_date)
# Names are INVENTED and deliberately token-distinctive: none of their >=4-char
# tokens collide with any transaction-remark word, so the case tell miner's
# distinctive-token set is unpolluted and every case scorecard stays byte-identical
# (a generic token like "Trade" would match the "trade" remark — the additive-name
# landmine, verified against the remark corpus before use).
_T3_COMPANIES = [
    ("CO_PROP", "Halcyon Nominees Ltd", 0.60, "2024-04-01"),
    ("CO_BELOW", "Verdanova Estates Ltd", 0.30, "2024-04-01"),
]
# The fictitious executive: a name-only officer of record whose INVENTED name
# matches no account and no KYC holder — no resolvable identity footprint.
_T3_FICTITIOUS_OFFICER = "Reinhardt Voss"
# The incoming post-designation director: a NEW footprinted officer persona whose
# appointment postdates the designation (the control-change trap). Appointed
# 2026-02-15 — 16 days after the 2026-01-30 designation date.
_T3_POST_OFFICER = ("POST_DIRECTOR", "Dana Krieg")
_T3_POST_APPOINTED = "2026-02-15"

# ---- Phase 8 Part II (T4): proximity-ring plants ---------------------------- #
# Relatives/associates of the DES-2026-0005 resolved party (Evgenii Zhukovsky),
# surfaced for REVIEW (never exposure, never asserted kinship). NEW, non-
# transacting individual personas appended after every per-account loop; INVENTED,
# token-distinctive names (no remark collision). Each demonstrates a distinct
# primary signal, plus the two binding traps:
#   * a DORMANT relative (offboarded) surfaces as loudly as an active one;
#   * an ACTIVE unrelated stranger is NOT surfaced (dormancy is not weighted).
# The existing DES-0005 same-surname decoy (Dmitri Zhukovsky) is ALSO surfaced by
# the shared-surname signal — the T1 variant-decoy (correctly not a name-variant
# MATCH to the designation) is a legitimate proximity associate under the DISTINCT
# proximity layer; the two layers do different jobs.
#   (key, name, account_status, signal)
_T4_RING = [
    ("REL_DORMANT", "Sofia Zhukovsky", "offboarded", "shared_surname+relationship"),
    ("REL_CROSSHOLD", "Petra Novak", "active", "kyc_document_cross_holding"),
    ("STRANGER", "James Miller", "active", "none"),
]


def generate_scenario(out_dir: Optional[Path] = None, seed: int = SEED) -> dict:
    """Generate the synthetic scenario and write it to ``out_dir``.

    Returns a summary dict (counts + output path)."""
    out_dir = Path(out_dir) if out_dir else SYNTHETIC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed)

    accounts: list[Account] = []
    kyc_docs: dict[str, KycDoc] = {}
    key_to_uid: dict[str, int] = {}
    next_uid = 500_000_000

    def _new_kyc(country: str) -> KycDoc:
        doc = KycDoc(
            kyc_doc_id=f"KYC-{len(kyc_docs) + 1:04d}",
            doc_type=rng.choice(["PASSPORT", "ID_CARD", "DRIVING_LICENSE"]),
            holder_name=fake.name(),
            holder_dob=fake.date_of_birth(minimum_age=25, maximum_age=65).isoformat(),
            issuing_country=country,
        )
        kyc_docs[doc.kyc_doc_id] = doc
        return doc

    # ---- ring accounts ---------------------------------------------------- #
    for key, etype, role, jur in _RING_SPEC:
        uid = next_uid
        next_uid += 1
        key_to_uid[key] = uid
        name = fake.company() if etype == "company" else fake.name()
        kyc = _new_kyc(jur)
        accounts.append(
            Account(
                uid=uid,
                entity_name=name,
                entity_type=etype,
                role_in_ring=role,
                residence_country=jur,
                nationality_country=jur if etype == "company" else rng.choice(RING_JURISDICTIONS),
                kyc_doc_id=kyc.kyc_doc_id,
                registration_date=_rand_ts(rng)[:10],
                vip_level=rng.choice(["VIP2", "VIP3", "VIP4"]) if role != "noise" else "Regular",
                prior_review_count=5 if role == "recidivist_mule" else rng.randint(0, 1),
                account_status="retain_monitor" if role == "recidivist_mule" else "active",
                internal_tag="Internal account. Contact operations team lead."
                if role == "privileged_internal_redherring"
                else None,
            )
        )

    # ---- reused-KYC-document pattern -------------------------------------- #
    # The SHELL_AE company account is opened with the SIBLING's KYC document,
    # and a second EMPLOYEE account reuses the EMPLOYEE's document. These are
    # the "separate entities, same paperwork" tells.
    reused_kyc: dict[str, list[int]] = {}
    sibling_kyc = next(a.kyc_doc_id for a in accounts if key_to_uid["SIBLING"] == a.uid)
    for a in accounts:
        if a.uid == key_to_uid["SHELL_AE"]:
            a.kyc_doc_id = sibling_kyc
    reused_kyc[sibling_kyc] = [key_to_uid["SIBLING"], key_to_uid["SHELL_AE"]]

    employee_kyc = next(a.kyc_doc_id for a in accounts if key_to_uid["EMPLOYEE"] == a.uid)
    emp2_uid = next_uid
    next_uid += 1
    accounts.append(
        Account(
            uid=emp2_uid,
            entity_name=fake.name(),
            entity_type="individual",
            role_in_ring="employee_cutout",
            residence_country="TR",
            nationality_country="TR",
            kyc_doc_id=employee_kyc,
            registration_date=_rand_ts(rng)[:10],
            vip_level="VIP1",
            prior_review_count=0,
            account_status="active",
        )
    )
    reused_kyc[employee_kyc] = [key_to_uid["EMPLOYEE"], emp2_uid]

    # ---- noise accounts --------------------------------------------------- #
    for _ in range(_NOISE_ACCOUNTS):
        uid = next_uid
        next_uid += 1
        jur = rng.choice(["US", "GB", "DE", "SG", "BR", "ZA"])
        kyc = _new_kyc(jur)
        accounts.append(
            Account(
                uid=uid,
                entity_name=fake.name(),
                entity_type="individual",
                role_in_ring="noise",
                residence_country=jur,
                nationality_country=jur,
                kyc_doc_id=kyc.kyc_doc_id,
                registration_date=_rand_ts(rng)[:10],
                vip_level="Regular",
                prior_review_count=0,
                account_status="active",
            )
        )

    ring_uids = [key_to_uid[k] for k, *_ in _RING_SPEC] + [emp2_uid]

    # ---- shared-device pattern ------------------------------------------- #
    device_links: list[DeviceLink] = []
    shared_devices: dict[str, list[int]] = {}

    def _share(uids: list[int]) -> str:
        fv = _device_fp(rng)
        for u in uids:
            device_links.append(DeviceLink(device_fingerprint=fv, uid=u))
        shared_devices[fv] = uids
        return fv

    _share([key_to_uid["KINGPIN"], key_to_uid["EMPLOYEE"], key_to_uid["TRUST"]])
    _share([key_to_uid["SHELL_AE"], key_to_uid["SHELL_TR"], key_to_uid["PRIVILEGED"]])
    _share([key_to_uid["TRUST"], key_to_uid["SHELL_HK"]])
    _share([key_to_uid["EMPLOYEE"], emp2_uid, key_to_uid["RECIDIVIST"]])
    # every account also gets its own unique device
    for a in accounts:
        device_links.append(DeviceLink(device_fingerprint=_device_fp(rng), uid=a.uid))

    # ---- IP logs (sanctioned-jurisdiction leakage) ----------------------- #
    ip_logs: list[IpLog] = []
    leak_uids = {key_to_uid["TRUST"], key_to_uid["SHELL_HK"], key_to_uid["KINGPIN"]}
    for a in accounts:
        n = rng.randint(4, 9)
        for _ in range(n):
            if a.uid in leak_uids and rng.random() < 0.4:
                ip_logs.append(IpLog(a.uid, _tehran_ip(rng), f"{SANCTIONED_JURISDICTION} {SANCTIONED_CITY}", False, _rand_ts(rng)))
            elif a.role_in_ring != "noise" and rng.random() < 0.5:
                ip_logs.append(IpLog(a.uid, _vpn_ip(rng), "VPN/unknown", True, _rand_ts(rng)))
            else:
                ip_logs.append(IpLog(a.uid, f"{rng.randint(11,220)}.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}", a.residence_country, False, _rand_ts(rng)))

    # ---- addresses, controllers, sanctions ------------------------------- #
    addresses: list[Address] = []
    address_controllers: dict[str, int] = {}

    # 3 synthetic "IRGC-style" sanctioned endpoint addresses (no controller uid)
    sanctioned_addrs: list[str] = []
    for _ in range(3):
        addr = _tron_addr(rng)
        addresses.append(Address(addr, "TRX", None, "IRGC-STYLE-SYNTHETIC", True))
        sanctioned_addrs.append(addr)

    # controller addresses for key ring members
    controller_addr: dict[str, str] = {}
    for key in ["KINGPIN", "EMPLOYEE", "TRUST", "SHELL_AE", "SHELL_TR", "SHELL_HK", "SHELL_NZ", "SHELL_CN"]:
        addr = _tron_addr(rng)
        controller_addr[key] = addr
        addresses.append(Address(addr, "TRX", key_to_uid[key], "controller-wallet", False))
        address_controllers[addr] = key_to_uid[key]

    # non-custodial layering hops (controlled by KINGPIN in ground truth,
    # but presented as "non-custodial" in the RFI)
    hop_addrs: list[str] = []
    for _ in range(4):
        addr = _tron_addr(rng)
        hop_addrs.append(addr)
        addresses.append(Address(addr, "TRX", key_to_uid["KINGPIN"], "non-custodial-hop", False))
        address_controllers[addr] = key_to_uid["KINGPIN"]

    # ---- gas-funding pattern --------------------------------------------- #
    # KINGPIN's wallet funds the gas of the "non-custodial" hops — the tell.
    gas_funds: list[GasFund] = [GasFund(controller_addr["KINGPIN"], h) for h in hop_addrs]

    # ---- transactions ----------------------------------------------------- #
    txs: list[Transaction] = []
    structured_tx_ids: list[str] = []
    betraying_remarks: list[dict] = []
    tx_counter = 0

    def _tx(from_ref, to_ref, amount, remark, direction, structured=False) -> Transaction:
        nonlocal tx_counter
        tx_counter += 1
        t = Transaction(
            tx_id=f"SIMTX{tx_counter:06d}",
            from_ref=from_ref,
            to_ref=to_ref,
            amount_usdt=round(amount, 2),
            network="TRX",
            timestamp=_rand_ts(rng),
            remark=remark,
            is_structured_round_number=structured,
            direction=direction,
        )
        txs.append(t)
        return t

    emp_nick = "Old " + accounts[[a.uid for a in accounts].index(key_to_uid["EMPLOYEE"])].entity_name.split()[0]

    # shells push structured round numbers up to the trust, then to hops, then
    # to the sanctioned endpoints — with a few betraying remarks along the way.
    for key in ["SHELL_AE", "SHELL_TR", "SHELL_HK", "SHELL_NZ", "SHELL_CN"]:
        for _ in range(rng.randint(2, 4)):
            _tx(f"uid:{key_to_uid[key]}", controller_addr["TRUST"], STRUCTURED_AMOUNT, "trade settlement", "withdrawal", structured=True)
            structured_tx_ids.append(txs[-1].tx_id)

    # trust -> non-custodial hops (KINGPIN-controlled), one remark betrays control
    for i, h in enumerate(hop_addrs):
        remark = "aggregation wallet" if i == 0 else ("client custody" if i == 1 else "")
        t = _tx(controller_addr["TRUST"], h, rng.uniform(3.0e6, 9.0e6), remark, "onchain")
        if i == 0:
            betraying_remarks.append({"tx_id": t.tx_id, "address": h, "reveals": "aggregation wallet — not a client address", "controller_uid": key_to_uid["KINGPIN"]})

    # employee funds a hop and labels it with the controller's nickname (betrayal)
    t = _tx(f"uid:{key_to_uid['EMPLOYEE']}", hop_addrs[1], 27_000_000, f"{emp_nick} wallet", "withdrawal")
    betraying_remarks.append({"tx_id": t.tx_id, "address": hop_addrs[1], "reveals": f'remark "{emp_nick} wallet" names the true controller', "controller_uid": key_to_uid["EMPLOYEE"]})

    # an "aggregation fee - partner share" remark (an off-book fee-skim tell)
    t = _tx(f"uid:{key_to_uid['RECIDIVIST']}", controller_addr["SHELL_CN"], 4_850_000, "aggregation fee - partner share", "withdrawal")
    betraying_remarks.append({"tx_id": t.tx_id, "address": controller_addr["SHELL_CN"], "reveals": "remark references an off-book aggregation fee-share arrangement", "controller_uid": key_to_uid["RECIDIVIST"]})

    # hops -> sanctioned endpoints (direct sanctioned exposure)
    sanctioned_exposure_tx_ids: list[str] = []
    sanctioned_exposure_addresses: list[str] = []
    for h in hop_addrs:
        t = _tx(h, rng.choice(sanctioned_addrs), rng.uniform(2.0e6, 8.0e6), "", "onchain")
        sanctioned_exposure_tx_ids.append(t.tx_id)
        sanctioned_exposure_addresses.append(h)

    # bidirectional near-equal flows between trust and a shell (layering tell)
    layering_tx_ids: list[str] = []
    for _ in range(3):
        amt = rng.uniform(1.0e6, 2.0e6)
        t1 = _tx(controller_addr["TRUST"], controller_addr["SHELL_NZ"], amt, "internal transfer", "onchain")
        t2 = _tx(controller_addr["SHELL_NZ"], controller_addr["TRUST"], amt * rng.uniform(0.985, 0.999), "internal transfer", "onchain")
        layering_tx_ids.extend([t1.tx_id, t2.tx_id])

    # noise transactions
    noise_uids = [a.uid for a in accounts if a.role_in_ring == "noise"]
    for _ in range(30):
        _tx(f"uid:{rng.choice(noise_uids)}", _tron_addr(rng), rng.uniform(50, 5000), rng.choice(["", "savings", "payment", "trade"]), rng.choice(["deposit", "withdrawal"]))

    # ---- registration-date coherence pass (RNG-free) ---------------------- #
    # registration_date was drawn independently of the activity above, which
    # could place logins and transactions BEFORE the account existed — an
    # impossibility a chronological view surfaces immediately. Clamp each
    # incoherent account's registration to 30 days before its first observed
    # activity (logins, exchange-leg transactions, and transactions touching
    # its controlled addresses). Derived entirely from values already drawn —
    # no new rng draw, so ordering stays deterministic — and already-coherent
    # draws are left untouched. Runs BEFORE the registry and prior-RFI
    # sections below, which derive their dates from these corrected values.
    first_activity: dict[int, str] = {}

    def _earlier_activity(uid: int, ts: str) -> None:
        cur = first_activity.get(uid)
        if cur is None or ts < cur:
            first_activity[uid] = ts

    for log in ip_logs:
        _earlier_activity(log.uid, log.timestamp)
    for t in txs:
        for ref in (t.from_ref, t.to_ref):
            if ref.startswith("uid:"):
                _earlier_activity(int(ref[4:]), t.timestamp)
            elif ref in address_controllers:
                _earlier_activity(address_controllers[ref], t.timestamp)
    for a in accounts:
        first = first_activity.get(a.uid)
        if first is not None and a.registration_date > first[:10]:
            opened = datetime.fromisoformat(first[:10]) - timedelta(days=30)
            a.registration_date = opened.date().isoformat()

    # ---- RFI with ground-truth contradictions ---------------------------- #
    # Everything from here on is RNG-FREE: it derives from data already drawn
    # above, so the pre-existing tables regenerate byte-identically.
    accounts_by_uid = {a.uid: a for a in accounts}
    shell_nz_name = accounts[[a.uid for a in accounts].index(key_to_uid["SHELL_NZ"])].entity_name
    rfi = Rfi(
        rfi_id="SIM-RFI-0001",
        uid=key_to_uid["TRUST"],
        question=(
            "Please explain your relationship to the following addresses and to "
            f"{shell_nz_name}, and the source of the transacted funds."
        ),
        response_text=(
            "All listed addresses are our own licensed-trust custody wallets, fully "
            f"segregated per client. {shell_nz_name} is a separate legal entity with no "
            "ownership or management relationship to us. We communicate only through our "
            "regulated platform, never Telegram or WhatsApp. Client funds derive solely "
            "from lawful bitumen and petroleum trade settlement, and every client passed "
            "full KYC/AML due diligence."
        ),
        claims=[
            {
                "claim_id": "C1",
                "text": "The addresses are our own licensed-trust custody wallets, fully segregated.",
                "ground_truth": "partly_true_but_omits_control",
            },
            {
                "claim_id": "C2",
                "text": f"{shell_nz_name} is a separate legal entity with no ownership or management relationship.",
                "ground_truth": "false",
                "contradicted_by": _notes_for("C2"),
            },
            {
                "claim_id": "C3",
                "text": "We communicate only through our regulated platform, never Telegram/WhatsApp.",
                "ground_truth": "unverifiable",
            },
            {
                "claim_id": "C4",
                "text": "Client funds derive solely from lawful bitumen/petroleum trade settlement.",
                "ground_truth": "false",
                "contradicted_by": _notes_for("C4"),
            },
        ],
    )

    # ---- corporate-registry OSINT (contradiction substrate) --------------- #
    # Built from the ordered _REGISTRY_SPEC over personas/jurisdictions/dates
    # already generated: no new identity, no PII, and no rng draw. The planted
    # fact is the shared director across the trust and SHELL_NZ, which the RFI
    # asserts are unrelated.
    registry: list[RegistryRecord] = []
    for i, (company_key, officer_key, role, resigned) in enumerate(_REGISTRY_SPEC, start=1):
        company = accounts_by_uid[key_to_uid[company_key]]
        officer = accounts_by_uid[key_to_uid[officer_key]]
        registry.append(RegistryRecord(
            registry_id=f"REG-{i:04d}",
            company_number=f"{company.residence_country}-{company.uid}",
            company_name=company.entity_name,
            jurisdiction=company.residence_country,
            incorporation_date=company.registration_date,
            officer_name=officer.entity_name,
            officer_role=role,
            appointed_date=company.registration_date,
            resigned_date=resigned,
            company_uid=company.uid,
            officer_uid=officer.uid,
        ))

    # ---- the subject's own PRIOR RFI answer ------------------------------- #
    # Kept in its own table so rfi.csv (the RFI under review) is untouched. The
    # earlier answer concedes exactly the relationship the current answer denies.
    # Asked 30 days after the later of the two incorporations, so the earlier
    # answer cannot reference an entity that did not yet exist. Derived from the
    # generated registration dates (deterministic, no rng), not a fixed offset.
    _prior_rfi_date = max(
        datetime.fromisoformat(accounts_by_uid[key_to_uid["TRUST"]].registration_date),
        datetime.fromisoformat(accounts_by_uid[key_to_uid["SHELL_NZ"]].registration_date),
    ) + timedelta(days=30)

    prior_rfi = PriorRfi(
        rfi_id="SIM-RFI-0000",
        uid=key_to_uid["TRUST"],
        asked_date=_prior_rfi_date.date().isoformat(),
        question=(
            "Please describe the services you provide to counterparties on this "
            "platform and any corporate relationships arising from them."
        ),
        response_text=(
            f"We act as settlement agent for {shell_nz_name} under a management "
            "services agreement, and one of our directors also sits on its board. "
            "Onboarding and payment instructions for that relationship are handled "
            "from our office."
        ),
        claims=[{
            "claim_id": "P1",
            "text": (
                f"We act as settlement agent for {shell_nz_name} under a management "
                "services agreement and share a director with it."
            ),
        }],
    )

    # ---- derived Phase-2 labels (no RNG; stay in sync by construction) ---- #
    # Answer keys for the On-chain Risk Scorer + network sanctioned-exposure eval,
    # the IP-leak detector, and the layering detector. Computed from the data
    # already planted above, so the CSVs remain byte-identical.
    sanctioned_exposure_uids = _uids_with_sanctioned_exposure(
        txs, address_controllers, sanctioned_addrs, [a.uid for a in accounts]
    )
    sanctioned_ip_leak_uids = sorted(leak_uids)

    # ---- synthetic SDN / alias watchlist (Tell Miner fuzzy-match target) -- #
    # Watchlisted ring members carry an alias that is a transliteration variant of
    # their registered name (evasion of exact-match screening); decoys must not
    # match any account. Built from already-generated names — no RNG, no CSV drift.
    sdn_entries: list[SdnEntry] = []
    sdn_alias_matches: list[dict] = []
    for sdn_id, key in [("SDN-0001", "KINGPIN"), ("SDN-0002", "RECIDIVIST")]:
        acct = accounts_by_uid[key_to_uid[key]]
        variant = _alias_variant(acct.entity_name)
        sdn_entries.append(SdnEntry(
            sdn_id=sdn_id, primary_name=variant, aliases=variant,
            program="SYNTHETIC-IRGC-STYLE", entity_type="individual",
        ))
        sdn_alias_matches.append({"uid": acct.uid, "sdn_id": sdn_id, "watchlist_name": variant})
    # decoys — themed but unrelated to the ring (precision / false-positive test)
    sdn_entries.append(SdnEntry("SDN-0003", "Bandar Petrochemical Front",
                                "Bandar Petrochemical Front;BPF Trading", "SYNTHETIC-IRGC-STYLE", "company"))
    sdn_entries.append(SdnEntry("SDN-0004", "Reza Oil Logistics",
                                "Reza Oil Logistics;ROL Shipping", "SYNTHETIC-IRGC-STYLE", "company"))

    # ---- designations (Phase 8: the remediation sweep's trigger input) ---- #
    # RNG-free: names and addresses derive from personas and wallets already
    # generated above. The live designation targets SHELL_NZ's controller
    # wallet plus one KINGPIN-controlled "non-custodial" hop, so the exposed
    # set is deliberately DIFFERENT from the legacy sanctioned_exposure_uids
    # key — a sweep that replays the Phase-2 answer key fails the eval.
    designation_date = (SIM_END + timedelta(days=30)).isoformat()
    # Both Part-I designations are DOMESTIC sdn_style/obligation entries. Per
    # Part I-B ruling IB-B their listed_since == designation_date exactly: the
    # lead-time gap is a property ONLY of the foreign plant (S2), so no
    # accidental domestic "window" can ever exist (asserted by test).
    designations = [
        Designation(
            designation_id="DES-2026-0001",
            designated_name=_alias_variant(shell_nz_name),
            program="SYNTHETIC-IRGC-STYLE",
            entity_type="company",
            designated_addresses=";".join([controller_addr["SHELL_NZ"], hop_addrs[2]]),
            designation_date=designation_date,
            source_regime="SYN-DOMESTIC-OFAC",
            list_type="sdn_style",
            obligation_vs_signal="obligation",
            listed_since=designation_date,
        ),
        # The decoy: same name as the SDN-0003 precision decoy (pinned equal by
        # test, not by reference, to keep this section purely additive) plus two
        # fixed non-ledger addresses. Expected exposure: the empty set.
        Designation(
            designation_id="DES-2026-0002",
            designated_name="Bandar Petrochemical Front",
            program="SYNTHETIC-IRGC-STYLE",
            entity_type="company",
            designated_addresses=";".join(_DECOY_DESIGNATION_ADDRS),
            designation_date=designation_date,
            source_regime="SYN-DOMESTIC-OFAC",
            list_type="sdn_style",
            obligation_vs_signal="obligation",
            listed_since=designation_date,
        ),
        # ---- Part I-B: two FOREIGN national-CT plants (signal, not obligation) #
        # A foreign national-list entry is a timestamped RISK SIGNAL, never a
        # legal effect binding this synthetic exchange. designation_date is the
        # common sweep reference date; listed_since is when the FOREIGN list
        # first carried the entry, so the lead-time window is [listed_since,
        # designation_date] — positive for a foreign plant, zero for domestic.
        #
        # 3a LEAD-TIME (chain-traced, TIME axis): a transliteration variant of
        # KINGPIN's name (IB-B) over an existing KINGPIN-controlled hop wallet
        # (hop_addrs[0] — distinct from the domestic designation's hop_addrs[2],
        # no legacy-CSV change). The foreign list flagged this network on
        # 2024-01-30; the domestic designation is 2026-01-30 — so the sweep can
        # measure the money that moved while ONLY the foreign list knew.
        Designation(
            designation_id="DES-2026-0003",
            designated_name=_alias_variant(accounts_by_uid[key_to_uid["KINGPIN"]].entity_name),
            program="SYNTHETIC-NCT-STYLE",
            entity_type="individual",
            designated_addresses=hop_addrs[0],
            designation_date=designation_date,
            source_regime="SYN-FOREIGN-NCT",
            list_type="national_ct",
            obligation_vs_signal="signal",
            listed_since="2024-01-30",
        ),
        # 3b GRANULARITY (name-only, DEPTH axis): a transliteration variant of
        # SIBLING's name with NO wallet and NO domestic designation — permitted
        # empty-address path (national_ct + signal). Surfaced by the name screen
        # as a review-tier identity row, proving foreign-list coverage is
        # ADDITIVE, not duplicative (SIBLING is never in a domestic exposure set).
        Designation(
            designation_id="DES-2026-0004",
            designated_name=_alias_variant(accounts_by_uid[key_to_uid["SIBLING"]].entity_name),
            program="SYNTHETIC-NCT-STYLE",
            entity_type="individual",
            designated_addresses="",
            designation_date=designation_date,
            source_regime="SYN-FOREIGN-NCT",
            list_type="national_ct",
            obligation_vs_signal="signal",
            listed_since="2025-03-01",
        ),
        # ---- Part II (T1): two foreign name-only plants for VARIANT screening #
        # Each designated_name is a published romanization of an underlying name;
        # a customer opened under a DIFFERENT published romanization (planted in
        # accounts.csv below the boundary) is caught by the variant layer but
        # MISSED by the direct screen. national_ct/signal + empty addresses (the
        # S1 name-only rule): no wallet, no exposure — surfaced purely by the
        # variant name screen. listed_since == designation_date (not a lead-time
        # plant; these exercise cross-romanization matching, not cross-list
        # timing). Distinguished from the S2 foreign plants only by membership in
        # the identity_variant_matches key (the fixtures/tests scope on that).
        *[
            Designation(
                designation_id=did,
                designated_name=desig_name,
                program="SYNTHETIC-NCT-STYLE",
                entity_type="individual",
                designated_addresses="",
                designation_date=designation_date,
                source_regime="SYN-FOREIGN-NCT",
                list_type="national_ct",
                obligation_vs_signal="signal",
                listed_since=designation_date,
            )
            for did, _family, desig_name, _cust, _decoy, _country in _IDENTITY_PLANTS
        ],
        # ---- Part II (T2): the corroboration name-COLLISION plant ---------- #
        # Same national_ct/signal/name-only shape as the T1 identity plants; its
        # variant screen surfaces a customer whose KYC identity attributes do NOT
        # corroborate the designated party (a same-name collision), so the
        # corroboration decision dismisses it with the reason recorded. Not in
        # identity_variant_matches (does not refer to that customer).
        Designation(
            designation_id=_CORROBORATION_COLLISION[0],
            designated_name=_CORROBORATION_COLLISION[2],
            program="SYNTHETIC-NCT-STYLE",
            entity_type="individual",
            designated_addresses="",
            designation_date=designation_date,
            source_regime="SYN-FOREIGN-NCT",
            list_type="national_ct",
            obligation_vs_signal="signal",
            listed_since=designation_date,
        ),
    ]

    # ---- sanctions-hold mock systems (warehouse feed vs. admin record) ---- #
    # Full per-account coverage in BOTH systems, so reconciliation is a real
    # comparison rather than a presence check. Two gaps are planted, one in
    # each drift direction, both on accounts the live designation exposes.
    # Every hold action predates the designation: these are legacy screening
    # actions, and the gaps are pre-existing sync failures that the sweep
    # SURFACES — the designation triggers the look, not the holds.
    baseline_date = (SIM_END + timedelta(days=1)).isoformat()
    warehouse_holds: list[WarehouseHold] = []
    admin_holds: list[AdminHold] = []
    for a in accounts:
        if a.uid == key_to_uid["TRUST"]:
            # missed_sync_block: ops blocked it; the warehouse feed never synced.
            warehouse_holds.append(WarehouseHold(a.uid, "no_hold", baseline_date, "WH-FEED-0001"))
            admin_holds.append(AdminHold(
                a.uid, "blocked", (SIM_END + timedelta(days=14)).isoformat(),
                "sanctions_ops", "OPS-HOLD-0001",
            ))
        elif a.uid == key_to_uid["SHELL_TR"]:
            # unrecorded_unblock: the hold synced to the warehouse, then was
            # quietly released in admin; the release never synced back.
            warehouse_holds.append(WarehouseHold(
                a.uid, "blocked", (SIM_END + timedelta(days=7)).isoformat(), "WH-FEED-0002",
            ))
            admin_holds.append(AdminHold(
                a.uid, "no_hold", (SIM_END + timedelta(days=21)).isoformat(),
                "sanctions_ops", "OPS-REL-0002",
            ))
        else:
            warehouse_holds.append(WarehouseHold(a.uid, "no_hold", baseline_date, "WH-FEED-0001"))
            admin_holds.append(AdminHold(a.uid, "no_hold", baseline_date, "baseline_load", ""))

    block_status_gaps = [
        {"uid": key_to_uid["TRUST"], "warehouse_status": "no_hold",
         "admin_status": "blocked", "gap_type": "missed_sync_block"},
        {"uid": key_to_uid["SHELL_TR"], "warehouse_status": "blocked",
         "admin_status": "no_hold", "gap_type": "unrecorded_unblock"},
    ]

    # ---- KYC artifacts on file (Part I-B S3: the completeness data plane) --- #
    # Full per-account coverage: one row per (account, artifact) for the
    # artifacts the entity type carries. Every artifact is on file (present) with
    # exactly ONE planted gap — the ultimate controller (KINGPIN) is missing a
    # proof-of-address. KINGPIN is the only exposed INDIVIDUAL (proof-of-address
    # is an individual artifact; the exposed shells/trust are companies), so the
    # gap is maximally test-separable from the insider (EMPLOYEE) and granularity
    # (SIBLING) beats — the ultimate controller onboarded without a POA on file.
    kyc_artifacts: list[KycArtifact] = []
    for a in accounts:
        for art in _KYC_EMITTED_ARTIFACTS[a.entity_type]:
            present = not (a.uid == key_to_uid["KINGPIN"] and art == "proof_of_address")
            kyc_artifacts.append(KycArtifact(uid=a.uid, artifact_type=art, present=present))

    # ---- staff-account register (Part I-B S3: the insider-linkage data plane) #
    # The employee-account register an exchange keeps for conflict-of-interest
    # monitoring. EMPLOYEE (the staff cutout) is on it; a second, ordinary staff
    # member (a noise account with no ring linkage) is also on it, so the insider
    # flag must require BOTH register membership AND a device overlap into the
    # exposed network — register membership alone never produces a worksheet row.
    # Detection reads THIS table only, never role_in_ring. onboarded_date reuses
    # the account's own (coherent) registration date.
    noise_uids = sorted(a.uid for a in accounts if a.role_in_ring == "noise")
    staff_register: list[StaffRegister] = [
        StaffRegister(
            staff_id="EMP-0001", uid=key_to_uid["EMPLOYEE"], department="Operations",
            employment_status="active",
            onboarded_date=accounts_by_uid[key_to_uid["EMPLOYEE"]].registration_date,
        ),
        StaffRegister(
            staff_id="EMP-0002", uid=noise_uids[0], department="Customer Support",
            employment_status="active",
            onboarded_date=accounts_by_uid[noise_uids[0]].registration_date,
        ),
    ]
    staff_uids = {s.uid for s in staff_register}

    # ---- derived Phase-8 designation labels (no RNG; in sync by construction) #
    all_uids = [a.uid for a in accounts]

    def _split_addrs(joined: str) -> list[str]:
        # A name-only (empty) address list round-trips as "" — split to [], not
        # [""], so the exposure walk sees no address rather than a bogus empty one.
        return joined.split(";") if joined else []

    des_exposed: dict[str, list[int]] = {}
    des_hops: dict[str, dict[str, int]] = {}
    des_direct: dict[str, list[int]] = {}
    des_adjacent: dict[str, list[int]] = {}
    for d in designations:
        exposed, hops, direct = _designation_exposure(
            txs, address_controllers, _split_addrs(d.designated_addresses), all_uids
        )
        des_exposed[d.designation_id] = exposed
        des_hops[d.designation_id] = {str(u): hops[u] for u in sorted(hops)}
        des_direct[d.designation_id] = direct
        # Adjacency: non-flow linkage (shared device / reused KYC) to an exposed
        # uid. A review-only list, disjoint from exposure by construction — the
        # same discipline as the scorer's gas_only_link (linkage is never flow).
        exposed_set = set(exposed)
        adjacent: set[int] = set()
        for group in list(shared_devices.values()) + list(reused_kyc.values()):
            if any(u in exposed_set for u in group):
                adjacent.update(u for u in group if u not in exposed_set)
        des_adjacent[d.designation_id] = sorted(adjacent)

    # ---- Part I-B cross-list early warning (no RNG) ---------------------- #
    # Lead-time window = [listed_since, designation_date]: positive only for a
    # foreign plant; zero for domestic (listed_since == designation_date, IB-B).
    #
    # In-window exposure measures the MONEY THAT MOVED while only the foreign
    # list knew — i.e. transaction flow, not control. Control of a designated
    # wallet is a timeless fact (hops == 0) that would survive even a zero-length
    # window, so it is deliberately EXCLUDED here: in-window exposure is the set
    # of accounts FLOW-exposed (hops >= 1) using only transactions dated inside
    # the window. All of 3a's downstream flow falls inside its 731-day window, so
    # its in-window flow set is its full set of flow-exposed counterparties; the
    # domestic windows are single instants with no in-window transactions, so
    # their in-window flow sets are empty — the cross-list contrast.
    designation_lead_time_window: dict[str, dict] = {}
    designation_exposure_in_window: dict[str, dict] = {}
    for d in designations:
        lead_days = (date.fromisoformat(d.designation_date)
                     - date.fromisoformat(d.listed_since)).days
        designation_lead_time_window[d.designation_id] = {
            "listed_since": d.listed_since,
            "designation_date": d.designation_date,
            "lead_days": lead_days,
        }
        addrs = _split_addrs(d.designated_addresses)
        in_window_txs = [
            t for t in txs
            if d.listed_since <= t.timestamp[:10] <= d.designation_date
        ]
        _, in_hops, _ = _designation_exposure(
            in_window_txs, address_controllers, addrs, all_uids
        )
        flow_uids = sorted(u for u, h in in_hops.items() if h >= 1)
        # Direct inflow that landed on a designated wallet inside the window —
        # the value the foreign list's lead time let move onto the designated
        # address before the domestic designation acted.
        designated = set(addrs)
        direct_inflow = round(sum(
            float(t.amount_usdt) for t in in_window_txs if t.to_ref in designated
        ), 2)
        designation_exposure_in_window[d.designation_id] = {
            "flow_uids": flow_uids,
            "direct_inflow_usdt": direct_inflow,
        }

    # Name matches are definitional: a designated name IS a transliteration
    # variant of a registered persona name (SHELL_NZ for the domestic live;
    # KINGPIN for 3a; SIBLING for 3b), so an exact-match screen misses it. The
    # decoy name was built to match no account (the SDN-0003 precision probe).
    designation_name_match_uids = {
        "DES-2026-0001": [key_to_uid["SHELL_NZ"]],
        "DES-2026-0002": [],
        "DES-2026-0003": [key_to_uid["KINGPIN"]],
        "DES-2026-0004": [key_to_uid["SIBLING"]],
        # The Part-II identity plants are DIRECT-screen misses by construction
        # (the customer opened under a different romanization) — the direct name
        # screen finds nothing; the variant layer is what recovers them, and its
        # answer key is ``identity_variant_matches`` below.
        **{did: [] for did, *_ in _IDENTITY_PLANTS},
    }
    # The FOREIGN-list name matches specifically — 3a's variant resolves to the
    # already-exposed KINGPIN (so it adds no new worksheet row), while 3b's
    # variant resolves to SIBLING, who has NO wallet and NO domestic designation
    # and is therefore surfaced ONLY by the name screen (additive, not
    # duplicative — proven absent from every domestic exposure set by test).
    foreign_name_match_uids = {
        "DES-2026-0003": [key_to_uid["KINGPIN"]],
        "DES-2026-0004": [key_to_uid["SIBLING"]],
    }

    # ---- Part I-B S3: pre/post-designation exposure timing (no RNG) ------- #
    # For each exposed account, WHEN did its exposure-driving flow occur relative
    # to the designation date? Control of a designated wallet (hops == 0) is a
    # TIMELESS fact — no transaction dates it — the same discipline that excludes
    # hops-0 from the in-window key. Flow exposure (hops >= 1) is
    # post-designation iff a driving path uses a transaction dated AFTER the
    # designation date (the categorically worse fact); otherwise pre-designation.
    # In this scenario every transaction predates every designation_date, so all
    # flow exposure is pre-designation (legacy exposure the designation surfaces)
    # — computed here, never assumed, so a future post-dated plant flips it.
    designation_exposure_timing: dict[str, dict[str, str]] = {}
    for d in designations:
        addrs = _split_addrs(d.designated_addresses)
        hops_map = {int(u): h for u, h in des_hops[d.designation_id].items()}
        post_txs = [t for t in txs if t.timestamp[:10] > d.designation_date]
        _, post_hops, _ = _designation_exposure(post_txs, address_controllers, addrs, all_uids)
        timing: dict[str, str] = {}
        for uid in des_exposed[d.designation_id]:
            if hops_map[uid] == 0:
                timing[str(uid)] = "timeless_control"
            elif post_hops.get(uid, 0) >= 1:
                timing[str(uid)] = "post_designation"
            else:
                timing[str(uid)] = "pre_designation"
        designation_exposure_timing[d.designation_id] = timing

    # ---- Part I-B S3: KYC completeness + insider-linkage answer keys ------ #
    # KYC gaps: required-and-absent artifacts per account, from the DATA plane
    # (kyc_artifacts) against the emitted-artifact list (which mirrors the sweep
    # standard). Exactly one: KINGPIN missing proof_of_address.
    kyc_present = {(k.uid, k.artifact_type): k.present for k in kyc_artifacts}
    kyc_artifact_gaps = {
        str(a.uid): sorted(
            art for art in _KYC_EMITTED_ARTIFACTS[a.entity_type]
            if not kyc_present[(a.uid, art)]
        )
        for a in accounts
    }
    kyc_artifact_gaps = {u: gaps for u, gaps in kyc_artifact_gaps.items() if gaps}

    # Insider linkage: staff-register accounts that ALSO overlap a device with
    # the live domestic designation's exposed set. EMPLOYEE qualifies (staff +
    # shared device with KINGPIN/TRUST); the ordinary staffer does not (no ring
    # device). Derived from the register + device graph — never role_in_ring.
    live_did = next(d.designation_id for d in designations
                    if d.list_type == "sdn_style" and des_exposed[d.designation_id])
    live_exposed_set = set(des_exposed[live_did])
    device_adjacent = {
        u for grp in shared_devices.values() if set(grp) & live_exposed_set
        for u in grp if u not in live_exposed_set
    }
    insider_linkage_uids = sorted(staff_uids & device_adjacent)

    # ---- Part II (T1): identity-resolution personas (RNG-free, additive) --- #
    # Appended AFTER every per-account loop above (holds, KYC artifacts, staff
    # register, and every legacy/Part-I-B answer key), so those tables and keys
    # never see these accounts and regenerate byte-identically. The customers
    # move only accounts.csv (+ their own kyc_docs.csv rows); they carry no
    # transactions, no holds, no KYC artifacts, and no staff membership. Each
    # customer opened under a DIFFERENT published romanization than its foreign
    # designation, so the direct name screen misses it and the variant layer must
    # recover it; the same-surname decoy (first name outside the equivalence
    # class) must never be matched. All names are INVENTED (no source provenance).
    # ``identity_variant_matches`` is the DEFINITIONAL answer key (which customer
    # each designated name refers to, by construction) — NOT the screen's output,
    # so the eval is a real recovery test, never circular.
    identity_variant_matches: dict[str, list[int]] = {}
    identity_variant_decoy_uids: list[int] = []
    identity_customer_uid: dict[str, int] = {}   # did -> matched customer uid
    identity_decoy_uid: dict[str, int] = {}      # did -> same-surname decoy uid (T4)
    # (uid, dob, nationality, doc_type, doc_number) for every identity subject —
    # the substrate for kyc_identity_attributes.csv (Part II T2).
    identity_subject_attrs: list[tuple[int, str, str, str, str]] = []
    for did, _family, _desig_name, cust_name, decoy_name, country in _IDENTITY_PLANTS:
        cust_uid = next_uid
        next_uid += 1
        cust_doc = KycDoc(
            kyc_doc_id=f"KYC-{len(kyc_docs) + 1:04d}", doc_type="PASSPORT",
            holder_name=cust_name, holder_dob="1984-05-14", issuing_country=country,
        )
        kyc_docs[cust_doc.kyc_doc_id] = cust_doc
        accounts.append(Account(
            uid=cust_uid, entity_name=cust_name, entity_type="individual",
            role_in_ring="identity_review_subject", residence_country=country,
            nationality_country=country, kyc_doc_id=cust_doc.kyc_doc_id,
            registration_date="2023-06-15", vip_level="Regular",
            prior_review_count=0, account_status="active",
        ))
        cust_doc_type, cust_doc_number = _CORROBORATION_CUSTOMER_KYC[did]
        identity_subject_attrs.append(
            (cust_uid, "1984-05-14", country, cust_doc_type, cust_doc_number))
        decoy_uid = next_uid
        next_uid += 1
        decoy_doc = KycDoc(
            kyc_doc_id=f"KYC-{len(kyc_docs) + 1:04d}", doc_type="PASSPORT",
            holder_name=decoy_name, holder_dob="1979-11-02", issuing_country=country,
        )
        kyc_docs[decoy_doc.kyc_doc_id] = decoy_doc
        accounts.append(Account(
            uid=decoy_uid, entity_name=decoy_name, entity_type="individual",
            role_in_ring="identity_review_subject", residence_country=country,
            nationality_country=country, kyc_doc_id=decoy_doc.kyc_doc_id,
            registration_date="2023-06-15", vip_level="Regular",
            prior_review_count=0, account_status="active",
        ))
        # A decoy never reaches corroboration (its name is not a match); it
        # carries an attribute row only for full identity-subject coverage.
        identity_subject_attrs.append(
            (decoy_uid, "1979-11-02", country, "PASSPORT", f"P-{country}-DEC{decoy_uid}"))
        identity_variant_matches[did] = [cust_uid]
        identity_customer_uid[did] = cust_uid
        identity_variant_decoy_uids.append(decoy_uid)
        identity_decoy_uid[did] = decoy_uid
    identity_variant_decoy_uids = sorted(identity_variant_decoy_uids)

    # ---- Part II (T2): the corroboration name-COLLISION customer ----------- #
    # Alexander Volkoff — a same-name-family customer the DES-0007 variant screen
    # surfaces but corroboration DISMISSES (a different individual). Additive:
    # accounts.csv + kyc_docs.csv only; not in identity_variant_matches.
    col_did, _col_family, _col_desig, col_cust_name, col_country = _CORROBORATION_COLLISION
    collision_uid = next_uid
    next_uid += 1
    col_doc = KycDoc(
        kyc_doc_id=f"KYC-{len(kyc_docs) + 1:04d}", doc_type="PASSPORT",
        holder_name=col_cust_name, holder_dob="1984-05-14", issuing_country=col_country,
    )
    kyc_docs[col_doc.kyc_doc_id] = col_doc
    accounts.append(Account(
        uid=collision_uid, entity_name=col_cust_name, entity_type="individual",
        role_in_ring="identity_review_subject", residence_country=col_country,
        nationality_country=col_country, kyc_doc_id=col_doc.kyc_doc_id,
        registration_date="2023-06-15", vip_level="Regular",
        prior_review_count=0, account_status="active",
    ))
    identity_customer_uid[col_did] = collision_uid
    col_doc_type, col_doc_number = _CORROBORATION_CUSTOMER_KYC[col_did]
    identity_subject_attrs.append(
        (collision_uid, "1984-05-14", col_country, col_doc_type, col_doc_number))

    # ---- Part II (T3): beneficial-owner + officer walk personas + tables --- #
    # NEW company + officer personas hung off the DES-2026-0005 resolved party,
    # appended here (after every per-account loop) so holds / KYC-artifacts /
    # staff tables stay byte-identical. Company names are DISTINCT from every
    # designated name, so the variant screen never spuriously matches them.
    # beneficial_ownership.csv + officer_appointments.csv are NEW sibling tables
    # (registry.csv byte-identical). All RNG-free; INVENTED names.
    from ..identity import OWNERSHIP_CONTROL_THRESHOLD
    t3_party_uid = identity_customer_uid[_T3_PARTY_DID]
    t3_company_uid: dict[str, int] = {}
    for key, cname, _pct, _asof in _T3_COMPANIES:
        cuid = next_uid
        next_uid += 1
        cdoc = KycDoc(
            kyc_doc_id=f"KYC-{len(kyc_docs) + 1:04d}", doc_type="ID_CARD",
            holder_name=cname, holder_dob="", issuing_country="AE",
        )
        kyc_docs[cdoc.kyc_doc_id] = cdoc
        accounts.append(Account(
            uid=cuid, entity_name=cname, entity_type="company",
            role_in_ring="ownership_review_subject", residence_country="AE",
            nationality_country="AE", kyc_doc_id=cdoc.kyc_doc_id,
            registration_date="2023-06-15", vip_level="Regular",
            prior_review_count=0, account_status="active",
        ))
        t3_company_uid[key] = cuid
    # The incoming post-designation director (a NEW footprinted officer persona).
    _post_key, post_name = _T3_POST_OFFICER
    post_officer_uid = next_uid
    next_uid += 1
    post_doc = KycDoc(
        kyc_doc_id=f"KYC-{len(kyc_docs) + 1:04d}", doc_type="PASSPORT",
        holder_name=post_name, holder_dob="1981-09-30", issuing_country="AE",
    )
    kyc_docs[post_doc.kyc_doc_id] = post_doc
    accounts.append(Account(
        uid=post_officer_uid, entity_name=post_name, entity_type="individual",
        role_in_ring="ownership_review_subject", residence_country="AE",
        nationality_country="AE", kyc_doc_id=post_doc.kyc_doc_id,
        registration_date="2023-06-15", vip_level="Regular",
        prior_review_count=0, account_status="active",
    ))

    co_prop = t3_company_uid["CO_PROP"]
    party_name = next(a.entity_name for a in accounts if a.uid == t3_party_uid)
    beneficial_ownership = [
        BeneficialOwnership(owner_uid=t3_party_uid, company_uid=t3_company_uid[key],
                            ownership_pct=pct, as_of_date=asof)
        for key, _cname, pct, asof in _T3_COMPANIES
    ]
    # Officer appointments on CO_PROP. Four rows realize the two detectors and
    # their discrimination cases (dates vs the 2026-01-30 designation date):
    #  OFF-0001 real footprint, pre-designation      -> neither flag
    #  OFF-0002 name-only INVENTED, no footprint      -> FICTITIOUS EXECUTIVE
    #  OFF-0003 footprinted, appointed post-designation -> POST-DESIGNATION CONTROL CHANGE
    #  OFF-0004 name-only but its name resolves to an account -> has footprint (NOT fictitious)
    officer_appointments = [
        OfficerAppointment(
            appointment_id="OFF-2026-0001", company_uid=co_prop,
            officer_uid=str(t3_party_uid), officer_name=party_name,
            role="director", appointed_date="2024-05-10", resigned_date="",
        ),
        OfficerAppointment(
            appointment_id="OFF-2026-0002", company_uid=co_prop,
            officer_uid="", officer_name=_T3_FICTITIOUS_OFFICER,
            role="director", appointed_date="2024-08-01", resigned_date="",
        ),
        OfficerAppointment(
            appointment_id="OFF-2026-0003", company_uid=co_prop,
            officer_uid=str(post_officer_uid), officer_name=post_name,
            role="director", appointed_date=_T3_POST_APPOINTED, resigned_date="",
        ),
        OfficerAppointment(
            appointment_id="OFF-2026-0004", company_uid=co_prop,
            officer_uid="", officer_name=party_name,
            role="secretary", appointed_date="2024-06-01", resigned_date="",
        ),
    ]
    # DEFINITIONAL T3 answer keys — the intended dispositions, recomputed
    # independently by walk_ownership from the two tables, so the eval is a real
    # check, never circular. Propagation is gated by OWNERSHIP_CONTROL_THRESHOLD.
    ownership_propagated_uids = sorted(
        t3_company_uid[key] for key, _c, pct, _a in _T3_COMPANIES
        if pct >= OWNERSHIP_CONTROL_THRESHOLD)
    fictitious_executive_flags = ["OFF-2026-0002"]
    post_designation_control_changes = ["OFF-2026-0003"]

    # ---- Part II (T4): proximity-ring personas + tables + answer key ------- #
    # Relatives/associates of the DES-2026-0005 resolved party, appended here
    # (after every per-account loop) so all hold/KYC/staff tables stay byte-
    # identical. relationships.csv + relationship_assertions.csv are NEW sibling
    # tables (remark/registry surfaces byte-identical). All RNG-free.
    t4_party_uid = identity_customer_uid[_T3_PARTY_DID]
    t4_ring_uid: dict[str, int] = {}
    for key, name, status, _signal in _T4_RING:
        ruid = next_uid
        next_uid += 1
        rdoc = KycDoc(
            kyc_doc_id=f"KYC-{len(kyc_docs) + 1:04d}", doc_type="PASSPORT",
            holder_name=name, holder_dob="1986-02-20", issuing_country="AE",
        )
        kyc_docs[rdoc.kyc_doc_id] = rdoc
        accounts.append(Account(
            uid=ruid, entity_name=name, entity_type="individual",
            role_in_ring="proximity_review_subject", residence_country="AE",
            nationality_country="AE", kyc_doc_id=rdoc.kyc_doc_id,
            registration_date="2023-06-15", vip_level="Regular",
            prior_review_count=0, account_status=status,
        ))
        t4_ring_uid[key] = ruid
    sofia_uid = t4_ring_uid["REL_DORMANT"]
    petra_uid = t4_ring_uid["REL_CROSSHOLD"]
    # Declared-relationship metadata + relationship-asserting artifacts. The
    # dormant relative carries a declared sibling relationship AND a relationship
    # remark; the cross-holding associate carries a KYC-document cross-holding.
    relationships = [
        Relationship(uid_a=t4_party_uid, uid_b=sofia_uid, declared_relationship="sibling"),
    ]
    relationship_assertions = [
        RelationshipAssertion(
            assertion_id="RA-2026-0001", subject_uid=t4_party_uid, related_uid=sofia_uid,
            assertion_type="relationship_remark",
            detail="an account remark refers to the two as family members",
        ),
        RelationshipAssertion(
            assertion_id="RA-2026-0002", subject_uid=t4_party_uid, related_uid=petra_uid,
            assertion_type="kyc_document_cross_holding",
            detail="a copy of the designated party's identity document is held in "
                   "this account's onboarding file",
        ),
    ]
    # DEFINITIONAL proximity answer key, per designation with a resolved
    # INDIVIDUAL party that has surname/relationship associates. DES-0005: the two
    # planted relatives PLUS the existing same-surname decoy (Dmitri Zhukovsky);
    # the active STRANGER (James Miller) is deliberately EXCLUDED. DES-0006: the
    # El-Sayegh surname decoy (Khalid), surfaced for its resolved needs-human
    # party. build_proximity_ring recomputes both, so the eval is a real check.
    proximity_ring_uids = {
        _T3_PARTY_DID: sorted([sofia_uid, petra_uid,
                               identity_decoy_uid[_T3_PARTY_DID]]),
        "DES-2026-0006": [identity_decoy_uid["DES-2026-0006"]],
    }

    # ---- Part II (T2): the two new corroboration tables + answer keys ------ #
    # designation_identifiers.csv: what the FOREIGN list published for each
    # identity designation's designated party. kyc_identity_attributes.csv: the
    # matched customer's identity attributes (the shared substrate T4 reuses).
    designation_identifiers = [
        DesignationIdentifier(
            designation_id=did, dob=dob, nationality=nat,
            doc_type=doc_type, doc_number=doc_number,
        )
        for did, (dob, nat, doc_type, doc_number, _outcome, _reason)
        in _DESIGNATION_IDENTIFIER_DATA.items()
    ]
    kyc_identity_attributes = [
        KycIdentityAttribute(
            uid=uid, dob=dob, nationality=nat,
            address=f"{nat} (synthetic address on file)",
            email=f"subject{uid}@example.invalid",
            doc_type=doc_type, doc_number=doc_number,
        )
        for (uid, dob, nat, doc_type, doc_number) in sorted(identity_subject_attrs)
    ]
    # DEFINITIONAL corroboration answer key: the outcome each matched customer
    # SHOULD resolve to, and — for the dismissal — the mismatched identifier
    # fields recorded as the reason. decide_corroboration recomputes the outcome
    # independently from the attributes, so the eval is a real check.
    corroboration_outcomes = {
        did: {str(identity_customer_uid[did]): data[4]}
        for did, data in _DESIGNATION_IDENTIFIER_DATA.items()
    }
    corroboration_dismissal_reasons = {
        did: data[5]
        for did, data in _DESIGNATION_IDENTIFIER_DATA.items()
        if data[4] == "name_only_dismissed"
    }
    # Part II (T5a) identity-review RFI answer key: the candidates corroboration
    # could neither confirm nor dismiss (possible_match_needs_human) — the only
    # outcome that earns a subject-facing identity-verification request. A true
    # hit is already resolved and a dismissal is a cleared collision, so neither
    # is contacted. Derived from the SAME definitional corroboration classification
    # (no new plant, no CSV change); draft_identity_review_rfis recomputes it.
    identity_review_rfi_uids = {
        did: [str(identity_customer_uid[did])]
        for did, data in _DESIGNATION_IDENTIFIER_DATA.items()
        if data[4] == "possible_match_needs_human"
    }

    # ---- assemble ground truth ------------------------------------------- #
    ground_truth = {
        "readme": "Fabricated data. Labels below are the answer key for scoring Okojo's capabilities.",
        "ultimate_controller_uid": key_to_uid["KINGPIN"],
        "network_member_uids": sorted(ring_uids),
        "privileged_redherring_uid": key_to_uid["PRIVILEGED"],
        "recidivist_uids": [key_to_uid["RECIDIVIST"]],
        "reused_kyc_docs": {k: sorted(v) for k, v in reused_kyc.items()},
        "shared_devices": {k: sorted(v) for k, v in shared_devices.items()},
        "sanctioned_addresses_synthetic": sorted(sanctioned_addrs),
        "address_controllers": {k: address_controllers[k] for k in sorted(address_controllers)},
        "gas_funding_tells": [asdict(g) for g in gas_funds],
        "betraying_remarks": betraying_remarks,
        "structured_transfer_tx_ids": structured_tx_ids,
        "sanctioned_exposure_uids": sanctioned_exposure_uids,
        "sanctioned_exposure_addresses": sorted(set(sanctioned_exposure_addresses)),
        "sanctioned_exposure_tx_ids": sanctioned_exposure_tx_ids,
        "sanctioned_ip_leak_uids": sanctioned_ip_leak_uids,
        "layering_tx_ids": layering_tx_ids,
        "sdn_alias_matches": sdn_alias_matches,
        "rfi_lies": [
            {"rfi_id": rfi.rfi_id, "claim_id": c["claim_id"], "text": c["text"], "contradicted_by": c["contradicted_by"]}
            for c in rfi.claims
            if c["ground_truth"] == "false"
        ],
        # Per-claim answer key for the RFI Contradiction-Checker. Covers ALL four
        # claims, not just the declared lies, so every adjudication branch has a
        # gold value: ``contradicted`` is the eval's positive class, while
        # ``qualified`` and ``unverifiable`` are correct non-positive outcomes
        # (flagging either as a contradiction is the false positive to catch).
        # ``expected_sources`` comes from the same _RFI_CLAIM_SOURCES map that
        # produces each claim's ``contradicted_by`` prose.
        "rfi_claim_key": [
            {
                "rfi_id": rfi.rfi_id,
                "claim_id": cid,
                "verdict": _RFI_CLAIM_VERDICTS[cid],
                "expected_sources": _sources_for(cid),
            }
            for cid in _RFI_CLAIM_ORDER
        ],
        "prior_rfi_ids": [prior_rfi.rfi_id],
        "registry_shared_officer_uids": sorted({
            key_to_uid["TRUST"], key_to_uid["SHELL_NZ"],
        }),
        # Phase-8 designation answer keys. Exposure/hops/direct come from
        # _designation_exposure (the distance-recording sibling of the legacy
        # exposure key, same flow-edge semantics); adjacency is review-only and
        # disjoint from exposure; the gap list is the reconciliation answer key.
        "designations": [
            {**asdict(d), "designated_addresses": _split_addrs(d.designated_addresses)}
            for d in designations
        ],
        "designation_exposed_uids": des_exposed,
        "designation_direct_uids": des_direct,
        "designation_exposure_hops": des_hops,
        "designation_adjacent_uids": des_adjacent,
        "designation_name_match_uids": designation_name_match_uids,
        "block_status_gaps": block_status_gaps,
        # Part I-B cross-list early warning: the lead-time window per designation
        # (zero for domestic, ~2yr for the 3a foreign plant), the in-window
        # exposure set (money that moved while only the foreign list knew), and
        # the foreign-list name matches (3a -> KINGPIN already exposed; 3b ->
        # SIBLING, name-only and additive).
        "designation_lead_time_window": designation_lead_time_window,
        "designation_exposure_in_window": designation_exposure_in_window,
        "foreign_name_match_uids": foreign_name_match_uids,
        # Part I-B S3 worksheet flags: WHEN exposure-driving flow occurred vs the
        # designation date (control is timeless); the required-and-absent KYC
        # artifacts per account; and the staff accounts whose device overlap into
        # the exposed network makes them insider-linkage flags.
        "designation_exposure_timing": designation_exposure_timing,
        "kyc_artifact_gaps": kyc_artifact_gaps,
        "insider_linkage_uids": insider_linkage_uids,
        # Part II (T1) variant-name-screen answer keys. ``identity_variant_matches``
        # is the customer each foreign name-only designation refers to (recovered
        # ONLY via the transliteration variant layer, missed by the direct
        # screen); ``identity_variant_decoy_uids`` are same-surname accounts that
        # must NEVER be matched (discrimination). Definitional, not screen output.
        "identity_variant_matches": identity_variant_matches,
        "identity_variant_decoy_uids": identity_variant_decoy_uids,
        # Part II (T2) corroboration answer keys. ``corroboration_outcomes`` is
        # the definitional disposition each name/variant-matched customer should
        # resolve to (per designation, keyed by str uid); DES-0007 is the
        # name-COLLISION case whose customer is dismissed. ``corroboration_
        # dismissal_reasons`` records the mismatched identifier fields for every
        # dismissal. decide_corroboration recomputes both from the two new
        # identity tables, so the eval is a real check, never circular.
        "corroboration_outcomes": corroboration_outcomes,
        "corroboration_dismissal_reasons": corroboration_dismissal_reasons,
        # Part II (T5a) identity-review RFI answer key: per designation, the
        # candidate uid(s) that earn a subject-facing identity-verification
        # request — exactly the possible_match_needs_human candidates.
        "identity_review_rfi_uids": identity_review_rfi_uids,
        # Part II (T3) beneficial-owner + officer walk answer keys, all hung off
        # the DES-2026-0005 resolved party. ``ownership_propagated_uids`` are the
        # companies owned at/above OWNERSHIP_CONTROL_THRESHOLD (review-tier
        # "owned/controlled by a designated party"; the below-threshold company
        # is excluded — the discrimination trap). ``fictitious_executive_flags``
        # is the name-only officer with no resolvable identity footprint;
        # ``post_designation_control_changes`` is the appointment dated after the
        # designation. All recomputed independently by walk_ownership.
        "ownership_propagated_uids": ownership_propagated_uids,
        "fictitious_executive_flags": fictitious_executive_flags,
        "post_designation_control_changes": post_designation_control_changes,
        # Part II (T4) proximity-ring answer key: per designation with a resolved
        # individual party, the relatives/associates surfaced for REVIEW (never
        # exposure). DES-0005 carries the two planted relatives plus the existing
        # same-surname decoy; the active stranger is excluded (dormancy is not
        # weighted). build_proximity_ring recomputes it independently.
        "proximity_ring_uids": proximity_ring_uids,
    }

    # ---- write outputs ---------------------------------------------------- #
    def _write(name: str, rows: list) -> None:
        pd.DataFrame([asdict(r) for r in rows]).to_csv(out_dir / name, index=False)

    _write("accounts.csv", accounts)
    _write("kyc_docs.csv", list(kyc_docs.values()))
    _write("devices.csv", device_links)
    _write("ip_logs.csv", ip_logs)
    _write("addresses.csv", addresses)
    _write("gas_funding.csv", gas_funds)
    _write("transactions.csv", txs)
    _write("sdn_list.csv", sdn_entries)
    _write("registry.csv", registry)
    _write("designations.csv", designations)
    _write("sanctions_hold_warehouse.csv", warehouse_holds)
    _write("sanctions_hold_admin.csv", admin_holds)
    _write("kyc_artifacts.csv", kyc_artifacts)
    _write("staff_register.csv", staff_register)
    _write("designation_identifiers.csv", designation_identifiers)
    _write("kyc_identity_attributes.csv", kyc_identity_attributes)
    _write("beneficial_ownership.csv", beneficial_ownership)
    _write("officer_appointments.csv", officer_appointments)
    _write("relationships.csv", relationships)
    _write("relationship_assertions.csv", relationship_assertions)

    # RFI: flatten claims to JSON string for the CSV, and keep a rich JSON too
    pd.DataFrame(
        [{"rfi_id": rfi.rfi_id, "uid": rfi.uid, "question": rfi.question,
          "response_text": rfi.response_text, "claims_json": json.dumps(rfi.claims)}]
    ).to_csv(out_dir / "rfi.csv", index=False)

    pd.DataFrame(
        [{"rfi_id": prior_rfi.rfi_id, "uid": prior_rfi.uid,
          "asked_date": prior_rfi.asked_date, "question": prior_rfi.question,
          "response_text": prior_rfi.response_text,
          "claims_json": json.dumps(prior_rfi.claims)}]
    ).to_csv(out_dir / "rfi_prior.csv", index=False)

    (out_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2))

    summary = {
        "output_dir": str(out_dir),
        "accounts": len(accounts),
        "ring_members": len(ring_uids),
        "kyc_docs": len(kyc_docs),
        "reused_kyc_docs": len(reused_kyc),
        "device_links": len(device_links),
        "shared_device_groups": len(shared_devices),
        "ip_logs": len(ip_logs),
        "addresses": len(addresses),
        "sanctioned_addresses": len(sanctioned_addrs),
        "gas_funding_tells": len(gas_funds),
        "transactions": len(txs),
        "structured_transfers": len(structured_tx_ids),
        "sanctioned_exposure_uids": len(sanctioned_exposure_uids),
        "layering_transfers": len(layering_tx_ids),
        "sdn_entries": len(sdn_entries),
        "sdn_alias_matches": len(sdn_alias_matches),
        "betraying_remarks": len(betraying_remarks),
        "rfi_claims": len(rfi.claims),
        "rfi_lies": len(ground_truth["rfi_lies"]),
        "registry_records": len(registry),
        "prior_rfis": 1,
        "designations": len(designations),
        "hold_status_rows": len(warehouse_holds) + len(admin_holds),
        "block_status_gaps": len(block_status_gaps),
        "kyc_artifacts": len(kyc_artifacts),
        "kyc_artifact_gaps": len(kyc_artifact_gaps),
        "staff_register_rows": len(staff_register),
        "insider_linkage_uids": len(insider_linkage_uids),
        "designation_identifiers": len(designation_identifiers),
        "kyc_identity_attributes": len(kyc_identity_attributes),
        "corroboration_dismissals": len(corroboration_dismissal_reasons),
        "beneficial_ownership": len(beneficial_ownership),
        "officer_appointments": len(officer_appointments),
        "ownership_propagated_uids": len(ownership_propagated_uids),
        "relationships": len(relationships),
        "relationship_assertions": len(relationship_assertions),
        "proximity_ring_total": sum(len(v) for v in proximity_ring_uids.values()),
    }
    return summary
