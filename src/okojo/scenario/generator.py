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
from datetime import datetime, timedelta
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
    DeviceLink,
    GasFund,
    IpLog,
    KycDoc,
    Rfi,
    SdnEntry,
    Transaction,
)

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

    # ---- RFI with ground-truth contradictions ---------------------------- #
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
                "contradicted_by": [
                    "reused KYC document links the two entities",
                    "shared device-fingerprint match between the accounts",
                    "common controller (KINGPIN) until recent transfer date",
                ],
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
                "contradicted_by": [
                    "downstream exposure to synthetic IRGC-style sanctioned addresses",
                    "structured just-under round-number transfers",
                    "gas-funded 'non-custodial' hops controlled by the same party",
                ],
            },
        ],
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
    accounts_by_uid = {a.uid: a for a in accounts}
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

    # RFI: flatten claims to JSON string for the CSV, and keep a rich JSON too
    pd.DataFrame(
        [{"rfi_id": rfi.rfi_id, "uid": rfi.uid, "question": rfi.question,
          "response_text": rfi.response_text, "claims_json": json.dumps(rfi.claims)}]
    ).to_csv(out_dir / "rfi.csv", index=False)

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
    }
    return summary
