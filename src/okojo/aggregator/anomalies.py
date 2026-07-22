"""Anomaly detectors for the Profile Aggregator.

Each detector takes the connectors plus the subject's account record and returns
a list of :class:`Anomaly` objects, every one carrying provenance so the finding
is fully grounded. Phase 1 covers the four profile-level tells the Build-Plan
calls for — geo-IP vs declared residence, VPN elevation, reused KYC document,
shared device — plus the "internal account" red-herring, which we **flag for
review, never obey**.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..config import SANCTIONED_JURISDICTION
from ..connectors import Connectors, Record
from ..provenance import Provenance

# Share of logins that are VPN above which we flag elevated anonymisation.
_VPN_ELEVATION_THRESHOLD = 0.30


class Anomaly(BaseModel):
    code: str
    severity: str  # "low" | "medium" | "high"
    statement: str
    provenance: list[Provenance]


def _geo_country(geolocation: Optional[str]) -> Optional[str]:
    """Extract the leading country token from a geolocation string ("IR Tehran" -> "IR")."""
    if not geolocation:
        return None
    return geolocation.split()[0]


def detect_geo_ip_mismatch(conn: Connectors, subject: Record) -> list[Anomaly]:
    uid = subject["uid"]
    residence = subject["residence_country"]
    logs = conn.ip_logs_for(uid)
    sanctioned_hits: list[Record] = []
    other_mismatch: list[Record] = []
    for log in logs:
        if log["is_vpn"]:
            continue  # VPN is handled by its own detector
        country = _geo_country(log["geolocation"])
        if country and country != residence and country != "VPN/unknown":
            if country == SANCTIONED_JURISDICTION:
                sanctioned_hits.append(log)
            else:
                other_mismatch.append(log)

    out: list[Anomaly] = []
    residence_prov = Provenance(
        source="accounts", row_key=f"uid:{uid}", field="residence_country",
        detail="declared residence",
    )
    if sanctioned_hits:
        out.append(Anomaly(
            code="sanctioned_jurisdiction_ip",
            severity="high",
            statement=(
                f"{len(sanctioned_hits)} non-VPN login(s) geolocate to sanctioned jurisdiction "
                f"{SANCTIONED_JURISDICTION}, inconsistent with declared residence {residence}."
            ),
            provenance=[residence_prov] + [h.provenance for h in sanctioned_hits],
        ))
    if other_mismatch:
        out.append(Anomaly(
            code="geo_ip_residence_mismatch",
            severity="medium",
            statement=(
                f"{len(other_mismatch)} non-VPN login(s) geolocate outside declared residence "
                f"{residence}."
            ),
            provenance=[residence_prov] + [h.provenance for h in other_mismatch],
        ))
    return out


def detect_vpn_elevation(conn: Connectors, subject: Record) -> list[Anomaly]:
    uid = subject["uid"]
    logs = conn.ip_logs_for(uid)
    if not logs:
        return []
    vpn_logs = [log for log in logs if log["is_vpn"]]
    share = len(vpn_logs) / len(logs)
    if share < _VPN_ELEVATION_THRESHOLD:
        return []
    return [Anomaly(
        code="vpn_elevation",
        severity="medium",
        statement=(
            f"Elevated anonymisation: {len(vpn_logs)}/{len(logs)} logins "
            f"({share:.0%}) originate from VPN/unknown IPs."
        ),
        provenance=[log.provenance for log in vpn_logs],
    )]


def detect_reused_kyc(conn: Connectors, subject: Record) -> list[Anomaly]:
    uid = subject["uid"]
    doc_id = subject["kyc_doc_id"]
    sharers = conn.accounts_with_kyc(doc_id)
    others = [r for r in sharers if r["uid"] != uid]
    if not others:
        return []
    names = ", ".join(f"uid:{r['uid']}" for r in others)
    doc_prov = Provenance(source="kyc_docs", row_key=doc_id, detail="shared KYC document")
    return [Anomaly(
        code="reused_kyc_document",
        severity="high",
        statement=(
            f"KYC document {doc_id} is reused to open separate account(s) ({names}) — "
            "a shared-paperwork link between supposedly distinct entities."
        ),
        provenance=[doc_prov, subject.provenance] + [r.provenance for r in others],
    )]


def detect_shared_device(conn: Connectors, subject: Record) -> list[Anomaly]:
    uid = subject["uid"]
    out: list[Anomaly] = []
    for dev in conn.devices_for(uid):
        fp = dev["device_fingerprint"]
        on_device = conn.accounts_on_device(fp)
        co_users = [r for r in on_device if r["uid"] != uid]
        if not co_users:
            continue
        names = ", ".join(f"uid:{r['uid']}" for r in co_users)
        out.append(Anomaly(
            code="shared_device_fingerprint",
            severity="high",
            statement=(
                f"Device fingerprint {fp[:12]}... is shared with account(s) {names}."
            ),
            provenance=[dev.provenance] + [r.provenance for r in co_users],
        ))
    return out


def detect_internal_tag(conn: Connectors, subject: Record) -> list[Anomaly]:
    """The internal 'do-not-block' account red herring: FLAG for review, never obey."""
    tag = subject.get("internal_tag")
    if not tag:
        return []
    return [Anomaly(
        code="internal_account_tag",
        severity="high",
        statement=(
            "Account carries an internal 'do-not-block' tag. Per policy this is "
            "FLAGGED for human review, not obeyed — it does not exempt the subject "
            f"from scrutiny. Tag text: {tag!r}"
        ),
        provenance=[Provenance(
            source="accounts", row_key=f"uid:{subject['uid']}", field="internal_tag",
            detail="internal red-herring tag",
        )],
    )]


ALL_DETECTORS = (
    detect_geo_ip_mismatch,
    detect_vpn_elevation,
    detect_reused_kyc,
    detect_shared_device,
    detect_internal_tag,
)


def detect_all(conn: Connectors, subject: Record) -> list[Anomaly]:
    out: list[Anomaly] = []
    for detector in ALL_DETECTORS:
        out.extend(detector(conn, subject))
    return out
