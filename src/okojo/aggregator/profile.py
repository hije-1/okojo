"""Profile Aggregator — a unified, anomaly-flagged subject timeline.

Stands in for an investigator clicking across a dozen dashboards: it pulls the
subject's account/KYC facts, logins, and transactions from the mock systems into
one time-ordered, provenance-carrying timeline, and attaches the anomalies the
detectors surface. Output is a schema-validated :class:`ProfileTimeline`.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..connectors import Connectors, Record
from ..provenance import Provenance
from .anomalies import Anomaly, detect_all


class TimelineEvent(BaseModel):
    timestamp: str
    kind: str
    description: str
    provenance: list[Provenance]


class ProfileTimeline(BaseModel):
    subject_uid: int
    subject_name: str
    entity_type: str
    residence_country: str
    account_status: str
    prior_review_count: int
    internal_tag: Optional[str] = None
    events: list[TimelineEvent]
    anomalies: list[Anomaly]

    def anomaly_codes(self) -> list[str]:
        return [a.code for a in self.anomalies]


def _registration_event(subject: Record) -> TimelineEvent:
    return TimelineEvent(
        timestamp=str(subject["registration_date"]),
        kind="account_registration",
        description=(
            f"Account opened: {subject['entity_name']} "
            f"({subject['entity_type']}, residence {subject['residence_country']}, "
            f"KYC {subject['kyc_doc_id']})."
        ),
        provenance=[subject.provenance],
    )


def _login_events(conn: Connectors, uid: int) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for log in conn.ip_logs_for(uid):
        vpn = " via VPN/unknown" if log["is_vpn"] else ""
        events.append(TimelineEvent(
            timestamp=str(log["timestamp"]),
            kind="ip_login",
            description=f"Login from {log['geolocation']} ({log['real_ip']}){vpn}.",
            provenance=[log.provenance],
        ))
    return events


def _transaction_events(conn: Connectors, subject: Record) -> list[TimelineEvent]:
    uid = subject["uid"]
    # Transactions referencing the subject directly, plus any of its controlled addresses.
    refs = {f"uid:{uid}"}
    for addr in conn.addresses_for(uid):
        refs.add(addr["address"])

    seen: set[str] = set()
    events: list[TimelineEvent] = []
    for ref in refs:
        for tx in conn.transactions_touching(ref):
            if tx["tx_id"] in seen:
                continue
            seen.add(tx["tx_id"])
            remark = f' — remark: "{tx["remark"]}"' if tx.get("remark") else ""
            structured = " [structured round-number]" if tx["is_structured_round_number"] else ""
            events.append(TimelineEvent(
                timestamp=str(tx["timestamp"]),
                kind=f"transaction_{tx['direction']}",
                description=(
                    f"{tx['direction'].title()} {tx['amount_usdt']:,.2f} USDT "
                    f"{tx['from_ref']} → {tx['to_ref']}{structured}{remark}."
                ),
                provenance=[tx.provenance],
            ))
    return events


def build_profile(conn: Connectors, subject_uid: int) -> ProfileTimeline:
    """Assemble the unified, anomaly-flagged timeline for one subject."""
    subject = conn.get_account(subject_uid)
    if subject is None:
        raise ValueError(f"No account with uid {subject_uid}")

    events: list[TimelineEvent] = [_registration_event(subject)]
    events.extend(_login_events(conn, subject_uid))
    events.extend(_transaction_events(conn, subject))
    # Chronological order (ISO strings sort lexicographically; a bare date sorts
    # before same-day datetimes, which is the intended ordering).
    events.sort(key=lambda e: e.timestamp)

    anomalies = detect_all(conn, subject)

    return ProfileTimeline(
        subject_uid=subject_uid,
        subject_name=subject["entity_name"],
        entity_type=subject["entity_type"],
        residence_country=subject["residence_country"],
        account_status=subject["account_status"],
        prior_review_count=int(subject["prior_review_count"]),
        internal_tag=subject.get("internal_tag"),
        events=events,
        anomalies=anomalies,
    )
