"""Geo-triangulation wiring for the remediation sweep (Phase 8 Part III U1b).

The store-touching adapter between the connectors and the pure ``geo`` collectors:
it builds a :class:`~okojo.geo.TerritoryProfile` from the ``territory_profile``
sibling, gathers the region's exclusive carriers, and assembles one dossier per
account — keeping those the one-signal rule surfaces. The signal logic itself
lives in ``geo`` (pure, store-independent); this module only fetches rows and
feeds them in, so the two stay cleanly separated.
"""

from __future__ import annotations

from typing import Optional

from ..connectors import Connectors
from ..geo import GeoDossier, TerritoryProfile, assemble_dossier
from .designation import Designation


def _split(v: object) -> list[str]:
    """A ';'-joined sibling cell as a clean list (robust to None / NaN)."""
    if v is None:
        return []
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return []
    return [t for t in s.split(";") if t]


def territory_profile(conn: Connectors, designation: Designation) -> Optional[TerritoryProfile]:
    """Build the :class:`TerritoryProfile` a territory designation triangulates
    against, or ``None`` if no profile row exists for it."""
    rec = conn.territory_profile_for(designation.designation_id)
    if rec is None:
        return None
    return TerritoryProfile(
        territory_code=str(rec["territory_code"]),
        territory_label=str(rec["territory_label"]),
        country_code=str(rec["country_code"]),
        ip_tokens=_split(rec["ip_tokens"]),
        phone_prefixes=_split(rec["phone_prefixes"]),
        timezones=_split(rec["timezones"]),
    )


def run_geo_triangulation(conn: Connectors, designation: Designation) -> list[GeoDossier]:
    """Triangulate every account against the designated territory and return the
    dossiers the one-signal rule surfaces, ordered by uid.

    Returns ``[]`` when the designation carries no territory profile (so a
    non-territory designation, or a territory row that is somehow absent, adds
    nothing). Deterministic and read-only."""
    territory = territory_profile(conn, designation)
    if territory is None:
        return []
    carriers = {str(r["carrier"]) for r in conn.exclusive_carriers_for(territory.territory_code)}
    reference_date = designation.designation_date

    surfaced: list[GeoDossier] = []
    for acct in conn.all_accounts():
        uid = int(acct["uid"])
        kyc = conn.get_kyc(str(acct["kyc_doc_id"]))
        dossier = assemble_dossier(
            uid, str(acct["entity_name"]),
            territory=territory, reference_date=reference_date,
            ip_records=conn.ip_logs_for(uid),
            phone_records=conn.phone_registrations_for(uid),
            kyc_doc_records=[kyc] if kyc is not None else [],
            account_record=acct,
            timezone_records=conn.device_timezones_for(uid),
            validity_records=conn.kyc_artifact_validity_for(uid),
            exclusive_carriers=carriers,
        )
        if dossier.surfaced:
            surfaced.append(dossier)
    return sorted(surfaced, key=lambda d: d.uid)
