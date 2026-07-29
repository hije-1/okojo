"""Geo-triangulation signal collectors + totality dossier (Phase 8 Part III U1a).

Audit-safe unit tests over CONSTRUCTED fixtures — no scenario, no store, no
generator touch. Each collector is exercised for both a hit and a miss; the VPN
discipline (never location evidence, plus the higher-value slip) and the
staleness modifier (valid vs expired counter-evidence + the dual control-gap
flag) are asserted directly; and the one-signal rule is asserted at the dossier.
"""

from __future__ import annotations

from okojo.connectors import Record
from okojo.geo import (
    GeoDossier,
    TerritoryProfile,
    assemble_dossier,
    collect_counter_evidence,
    collect_declared_residence,
    collect_device_timezone,
    collect_exclusive_carrier,
    collect_ip_geolocation,
    collect_kyc_geography,
    collect_phone_prefix,
    collect_vpn_markers,
    collect_vpn_slip,
)
from okojo.provenance import Provenance


# A fictional territory: code "QZ" inside the fictional country "VN-QZ"? No — keep
# the codes obviously invented and unrelated to any real country/advisory. These
# are TEST fixtures only (the scenario's real invented labels are proposed for PM
# eyeball in U1b, before regeneration).
TERR = TerritoryProfile(
    territory_code="ZZ",
    territory_label="Zerran Free Zone",
    country_code="XQ",
    ip_tokens=["Zerran", "Zerran City"],
    phone_prefixes=["+9995", "+99951"],
    timezones=["Etc/GMT-9"],
)
REF_DATE = "2026-01-30"


def _rec(source: str, row_key: str, **data) -> Record:
    return Record(dict(data), Provenance(source=source, row_key=row_key))


def _ip(ts: str, geo: str, is_vpn: bool, uid: int = 1) -> Record:
    return _rec("ip_logs", f"uid:{uid}@{ts}", uid=uid, real_ip="1.2.3.4",
               geolocation=geo, is_vpn=is_vpn, timestamp=ts)


# --- (a) IP geolocation ------------------------------------------------------


def test_ip_geolocation_hits_non_vpn_territory_ip():
    rows = [_ip("2026-01-10T00:00:00", "Zerran City XQ", False)]
    sigs = collect_ip_geolocation(rows, TERR)
    assert [s.signal_id for s in sigs] == ["ip_geolocation"]
    assert sigs[0].provenance.source == "ip_logs"


def test_ip_geolocation_skips_vpn_and_non_territory():
    rows = [
        _ip("2026-01-10T00:00:00", "Zerran City XQ", True),   # VPN: never location
        _ip("2026-01-11T00:00:00", "Somewhere Else", False),  # not the territory
    ]
    assert collect_ip_geolocation(rows, TERR) == []


# --- (b) phone prefix / (c) exclusive carrier --------------------------------


def test_phone_prefix_hit_and_miss():
    hit = [_rec("phone_registrations", "uid:1", uid=1, phone_prefix="+9995", carrier="Neutral Telecom")]
    miss = [_rec("phone_registrations", "uid:2", uid=2, phone_prefix="+1206", carrier="Neutral Telecom")]
    assert [s.signal_id for s in collect_phone_prefix(hit, TERR)] == ["phone_prefix"]
    assert collect_phone_prefix(miss, TERR) == []


def test_exclusive_carrier_fires_independent_of_prefix():
    # Carrier-only: prefix is NOT a territory prefix, but the carrier is region-exclusive.
    rows = [_rec("phone_registrations", "uid:1", uid=1, phone_prefix="+1206",
                 carrier="Zerran Mobile")]
    carriers = {"Zerran Mobile"}
    assert collect_phone_prefix(rows, TERR) == []          # prefix inconclusive
    sigs = collect_exclusive_carrier(rows, carriers)
    assert [s.signal_id for s in sigs] == ["exclusive_carrier"]
    assert sigs[0].weight_class == "high_value"


def test_exclusive_carrier_miss_for_non_exclusive():
    rows = [_rec("phone_registrations", "uid:1", uid=1, phone_prefix="+1206",
                 carrier="Global Roaming Co")]
    assert collect_exclusive_carrier(rows, {"Zerran Mobile"}) == []


# --- (d) KYC geography / (e) residence / (f) timezone ------------------------


def test_kyc_geography_hit_and_miss():
    hit = [_rec("kyc_docs", "K1", kyc_doc_id="K1", doc_type="national_id",
                issuing_country="ZZ")]
    miss = [_rec("kyc_docs", "K2", kyc_doc_id="K2", doc_type="national_id",
                 issuing_country="AE")]
    assert [s.signal_id for s in collect_kyc_geography(hit, TERR)] == ["kyc_geography"]
    assert collect_kyc_geography(miss, TERR) == []


def test_declared_residence_hit_and_miss_and_none():
    hit = _rec("accounts", "uid:1", uid=1, entity_name="A", residence_country="ZZ")
    miss = _rec("accounts", "uid:2", uid=2, entity_name="B", residence_country="AE")
    assert [s.signal_id for s in collect_declared_residence(hit, TERR)] == ["declared_residence"]
    assert collect_declared_residence(miss, TERR) == []
    assert collect_declared_residence(None, TERR) == []


def test_device_timezone_hit_is_weak_and_miss():
    hit = [_rec("device_timezones", "dev1:uid:1", device_fingerprint="dev1", uid=1,
                timezone="Etc/GMT-9")]
    miss = [_rec("device_timezones", "dev2:uid:2", device_fingerprint="dev2", uid=2,
                 timezone="Europe/London")]
    sigs = collect_device_timezone(hit, TERR)
    assert [s.signal_id for s in sigs] == ["device_timezone"]
    assert sigs[0].weight_class == "weak"
    assert collect_device_timezone(miss, TERR) == []


# --- VPN discipline ----------------------------------------------------------


def test_vpn_markers_recorded_never_as_signal():
    rows = [_ip("2026-01-10T00:00:00", "VPN/unknown", True)]
    markers = collect_vpn_markers(rows)
    assert len(markers) == 1
    # A VPN login yields NO location signal.
    assert collect_ip_geolocation(rows, TERR) == []


def test_vpn_slip_is_higher_value_and_cites_window():
    # Otherwise-continuous VPN, with ONE territory IP bracketed by VPN use.
    rows = [
        _ip("2026-01-01T00:00:00", "VPN/unknown", True),
        _ip("2026-01-05T00:00:00", "Zerran City XQ", False),   # the slip
        _ip("2026-01-09T00:00:00", "VPN/unknown", True),
    ]
    slips = collect_vpn_slip(rows, TERR)
    assert [s.signal_id for s in slips] == ["vpn_slip"]
    assert slips[0].weight_class == "high_value"
    # The slip window (the bracketing VPN timestamps) is cited explicitly.
    assert "2026-01-01T00:00:00" in slips[0].detail
    assert "2026-01-09T00:00:00" in slips[0].detail
    # And the slip is NOT also double-counted as an ordinary IP signal.
    assert collect_ip_geolocation(rows, TERR) == []


def test_territory_ip_not_bracketed_is_ordinary_not_slip():
    # A territory IP AFTER all VPN use is not a slip (no VPN after it).
    rows = [
        _ip("2026-01-01T00:00:00", "VPN/unknown", True),
        _ip("2026-01-09T00:00:00", "Zerran City XQ", False),
    ]
    assert collect_vpn_slip(rows, TERR) == []
    assert [s.signal_id for s in collect_ip_geolocation(rows, TERR)] == ["ip_geolocation"]


# --- staleness modifier + dual control-gap flag ------------------------------


def _validity(atype: str, geo: str, expiry: str) -> Record:
    return _rec("kyc_artifact_validity", f"uid:1:{atype}", uid=1,
                artifact_type=atype, issuing_geography=geo, expiry_date=expiry)


def test_counter_evidence_valid_argues_in_full_no_gap():
    rows = [_validity("residency_card", "AE", "2030-01-01")]  # foreign, still valid
    counter, gaps = collect_counter_evidence(rows, TERR, REF_DATE)
    assert len(counter) == 1
    assert counter[0].staleness == "valid" and counter[0].counterweight == "full"
    assert gaps == []


def test_counter_evidence_expired_is_degraded_and_raises_gap():
    rows = [_validity("residency_card", "AE", "2024-01-01")]  # foreign, expired < REF
    counter, gaps = collect_counter_evidence(rows, TERR, REF_DATE)
    assert counter[0].staleness == "expired" and counter[0].counterweight == "degraded"
    assert [g.gap_type for g in gaps] == ["kyc_refresh_expired"]


def test_counter_evidence_missing_expiry_raises_missing_gap():
    rows = [_validity("residency_card", "AE", "")]
    counter, gaps = collect_counter_evidence(rows, TERR, REF_DATE)
    assert counter == []
    assert [g.gap_type for g in gaps] == ["kyc_refresh_missing"]


def test_document_issued_inside_territory_is_not_counter_evidence():
    rows = [_validity("residency_card", "ZZ", "2024-01-01")]  # inside the territory
    counter, gaps = collect_counter_evidence(rows, TERR, REF_DATE)
    assert counter == [] and gaps == []


def test_non_residency_doc_is_never_counter_evidence():
    rows = [_validity("proof_of_address", "AE", "2024-01-01")]
    counter, gaps = collect_counter_evidence(rows, TERR, REF_DATE)
    assert counter == [] and gaps == []


# --- the totality dossier + one-signal rule ----------------------------------


def _dossier(*, ip=None, phone=None, kyc=None, acct=None, tz=None, validity=None,
             carriers=None) -> GeoDossier:
    return assemble_dossier(
        1, "Test Subject", territory=TERR, reference_date=REF_DATE,
        ip_records=ip or [], phone_records=phone or [], kyc_doc_records=kyc or [],
        account_record=acct, timezone_records=tz or [], validity_records=validity or [],
        exclusive_carriers=carriers or set(),
    )


def test_dossier_clean_account_not_surfaced():
    d = _dossier(ip=[_ip("2026-01-01T00:00:00", "London GB", False)])
    assert d.surfaced is False
    assert d.signal_ids() == []


def test_dossier_single_signal_surfaces():
    d = _dossier(acct=_rec("accounts", "uid:1", uid=1, entity_name="A",
                           residence_country="ZZ"))
    assert d.surfaced is True
    assert d.signal_ids() == ["declared_residence"]


def test_dossier_multi_signal_accumulates():
    d = _dossier(
        ip=[_ip("2026-01-01T00:00:00", "Zerran City XQ", False)],
        phone=[_rec("phone_registrations", "uid:1", uid=1, phone_prefix="+9995",
                    carrier="Zerran Mobile")],
        kyc=[_rec("kyc_docs", "K1", kyc_doc_id="K1", doc_type="national_id",
                  issuing_country="ZZ")],
        acct=_rec("accounts", "uid:1", uid=1, entity_name="A", residence_country="ZZ"),
        carriers={"Zerran Mobile"},
    )
    assert d.surfaced is True
    # ip + phone_prefix + exclusive_carrier + kyc_geography + declared_residence
    assert set(d.signal_ids()) == {
        "ip_geolocation", "phone_prefix", "exclusive_carrier",
        "kyc_geography", "declared_residence",
    }


def test_dossier_vpn_confounded_surfaces_on_other_signal():
    # All IP is VPN (no IP signal), but residence still triangulates; the VPN is a
    # marker, not a location signal.
    d = _dossier(
        ip=[_ip("2026-01-01T00:00:00", "VPN/unknown", True)],
        acct=_rec("accounts", "uid:1", uid=1, entity_name="A", residence_country="ZZ"),
    )
    assert d.surfaced is True
    assert d.signal_ids() == ["declared_residence"]
    assert len(d.vpn_markers) == 1


def test_dossier_ambiguous_traveller_surfaces_on_slip_with_expired_counter_evidence():
    # National onboarded abroad: residence foreign (no residence signal), one
    # VPN-slip territory IP, an EXPIRED foreign residency card. Surfaced by the
    # slip alone; the expired counter-evidence is degraded and raises a gap.
    d = _dossier(
        ip=[
            _ip("2026-01-01T00:00:00", "VPN/unknown", True),
            _ip("2026-01-05T00:00:00", "Zerran City XQ", False),  # slip
            _ip("2026-01-09T00:00:00", "VPN/unknown", True),
        ],
        acct=_rec("accounts", "uid:1", uid=1, entity_name="A", residence_country="AE"),
        validity=[_validity("residency_card", "AE", "2024-01-01")],
    )
    assert d.surfaced is True
    assert d.has_vpn_slip()
    assert d.signal_ids() == ["vpn_slip"]          # the ONLY positive signal
    assert d.counter_evidence[0].counterweight == "degraded"
    assert [g.gap_type for g in d.control_gaps] == ["kyc_refresh_expired"]


def test_dossier_decoy_prefix_lookalike_not_surfaced():
    # A prefix look-alike NOT in the territory registry must NOT fire.
    d = _dossier(phone=[_rec("phone_registrations", "uid:1", uid=1,
                             phone_prefix="+9996", carrier="Global Roaming Co")])
    assert d.surfaced is False
