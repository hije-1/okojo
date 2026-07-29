"""Geo-triangulation signal collectors + the totality dossier (Phase 8 Part III).

A TERRITORY designation names a *geography*, not a party — so there is no name
screen. Instead the sweep collects **location signals** per account and
**triangulates** possible presence inside the sanctioned region. Everything here
is REVIEW-tier and calibrated: a signal **indicates possible presence**, it never
**proves location**; a human resolves.

Design discipline (mirrors the identity layer):

* **Each collector is independent and grounded to its OWN record.** A collector
  reads exactly one evidence surface and returns zero or more :class:`GeoSignal`,
  each carrying the provenance pointer of the single row it read. Collectors are
  blind to one another (multi-modal-sweep discipline).
* **Pure functions over already-fetched rows.** The collectors take
  :class:`~okojo.connectors.Record` lists and a :class:`TerritoryProfile`; they
  touch no store and no designation. This keeps them exhaustively unit-testable
  over constructed fixtures (U1a is audit-safe: no generator change), and lets
  the U1b wiring fetch rows via the connectors and feed them straight in.
* **VPN is NEVER location evidence.** A VPN login yields no location signal — only
  a :class:`GeoVpnMarker` (an obfuscation/contradiction marker). A territory IP
  observed during a *gap* in otherwise-continuous VPN use is a **VPN-slip**: a
  HIGHER-VALUE signal that cites the slip window explicitly.
* **Document staleness is NOT a location signal.** Counter-evidence (a residency
  document issued OUTSIDE the territory) argues *against* presence; an EXPIRED one
  argues much less (its counter-weight is degraded). Expiry itself is never read
  as evidence of presence, and every stale/missing counter-document also raises a
  KYC-refresh control gap (the exchange failed to re-verify).
* **The one-signal rule:** ANY single positive location signal surfaces the
  account for review; the signals then accumulate into the totality dossier — more
  strengthen the picture, but one is sufficient to surface.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..connectors import Record
from ..provenance import Provenance

# Weight classes a signal can carry — a tunable, published attribute consumed by
# the (later) proposal rule; declared here so the dossier records it now.
WEIGHT_STANDARD = "standard"
WEIGHT_HIGH_VALUE = "high_value"
WEIGHT_WEAK = "weak"

# Onboarding-artifact types that function as counter-evidence: a residency/
# domicile document issued OUTSIDE the territory argues against presence. Other
# document types (a passport, a utility bill) say nothing about domicile and are
# never treated as counter-evidence.
COUNTER_EVIDENCE_DOC_TYPES = ("residency_card", "residence_permit")


class TerritoryProfile(BaseModel):
    """What DEFINES a synthetic sanctioned territory — the triangulation target.

    Fully fictional (no real occupied-territory name, no real carrier). Built in
    U1b from the ``territory_profile`` sibling row; constructed directly in U1a
    unit tests. ``territory_code`` is the region's own code (also used as a
    residence jurisdiction for in-region personas); ``country_code`` is the
    fictional parent country (used for nationality). Both are named by NO advisory
    (advisory-ranking inertness — proven by stash a/b in the U1b report)."""

    territory_code: str
    territory_label: str
    country_code: str
    ip_tokens: list[str]          # geolocation substrings that indicate the territory
    phone_prefixes: list[str]     # regional dialling prefixes
    timezones: list[str]          # IANA timezone(s) the territory sits in

    def geo_tokens(self) -> set[str]:
        """Lowercased tokens that indicate the territory / its country — the
        in-vs-out test for IP geolocation, KYC-issuing geography, declared
        residence, and the counter-evidence 'issued outside' check."""
        base = [self.territory_code, self.territory_label, self.country_code]
        return {t.strip().lower() for t in (base + list(self.ip_tokens)) if t and t.strip()}


class GeoSignal(BaseModel):
    """One positive location signal, grounded to the single row it was read from."""

    signal_id: str
    value: str                    # the concrete value observed (an IP geo, a prefix, ...)
    detail: str                   # calibrated: "indicates possible presence", never "proves"
    weight_class: str
    provenance: Provenance


class GeoVpnMarker(BaseModel):
    """A VPN login — an obfuscation/contradiction marker, NEVER location evidence."""

    detail: str
    timestamp: str
    provenance: Provenance


class GeoCounterEvidence(BaseModel):
    """A document arguing AGAINST presence (a residency doc issued elsewhere),
    with its staleness modifier. An EXPIRED document's counter-weight is degraded;
    a valid one argues in full. Staleness is never evidence of presence."""

    artifact_type: str
    issuing_geography: str
    staleness: str                # "valid" | "expired"
    counterweight: str            # "full" | "degraded"  (qualitative; U2 owns any numeric use)
    detail: str
    provenance: Provenance


class GeoControlGap(BaseModel):
    """The dual flag: a stale/missing counter-document also means the exchange
    failed to re-verify — a KYC-refresh control gap, surfaced for the control
    owner. NOT a location signal and never read as one."""

    gap_type: str                 # "kyc_refresh_expired" | "kyc_refresh_missing"
    artifact_type: str
    detail: str
    provenance: Provenance


class GeoDossier(BaseModel):
    """The totality dossier for one account — the decision surface a human reads.

    Every line is provenance-pointed. ``surfaced`` is the one-signal-rule verdict:
    True iff at least one positive location signal was collected. VPN markers,
    counter-evidence, and control gaps do NOT surface an account (VPN is never
    location evidence; counter-evidence argues the other way)."""

    uid: int
    entity_name: str
    signals: list[GeoSignal] = []
    vpn_markers: list[GeoVpnMarker] = []
    counter_evidence: list[GeoCounterEvidence] = []
    control_gaps: list[GeoControlGap] = []
    note: str = ""

    @property
    def surfaced(self) -> bool:
        return bool(self.signals)

    def signal_ids(self) -> list[str]:
        return [s.signal_id for s in self.signals]

    def has_vpn_slip(self) -> bool:
        return any(s.signal_id == "vpn_slip" for s in self.signals)

    @property
    def provenance(self) -> list[Provenance]:
        return ([s.provenance for s in self.signals]
                + [m.provenance for m in self.vpn_markers]
                + [c.provenance for c in self.counter_evidence]
                + [g.provenance for g in self.control_gaps])


# --------------------------------------------------------------------------- #
# The six signal collectors + VPN discipline + staleness. Each is pure over its
# rows and the territory profile; each grounds every signal it emits.
# --------------------------------------------------------------------------- #


def _s(v: object) -> str:
    """One CSV cell as a clean string (robust to None / NaN round-trips)."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def collect_ip_geolocation(ip_records: list[Record],
                           territory: TerritoryProfile) -> list[GeoSignal]:
    """(a) IP geolocation: a NON-VPN login resolving into the territory.

    VPN logins are skipped here (they are never location evidence) and are picked
    up as markers by :func:`collect_vpn_markers`. A territory IP that is a
    VPN-slip is emitted by :func:`collect_vpn_slip` as a higher-value signal and
    is NOT double-counted here."""
    tokens = territory.geo_tokens()
    slip_ts = {r["timestamp"] for r in _vpn_slip_records(ip_records, territory)}
    out: list[GeoSignal] = []
    for r in ip_records:
        if _truthy(r.get("is_vpn")):
            continue
        geo = _s(r["geolocation"]).lower()
        if geo and any(tok in geo for tok in tokens) and _s(r["timestamp"]) not in slip_ts:
            out.append(GeoSignal(
                signal_id="ip_geolocation", value=_s(r["geolocation"]),
                detail=f"a login IP resolved to {_s(r['geolocation'])}, which "
                       "indicates possible presence in the territory",
                weight_class=WEIGHT_STANDARD, provenance=r.provenance,
            ))
    return out


def _digits(s: str) -> str:
    """Digit-only form of a dialling prefix — robust to a leading ``+``, spaces,
    or dashes, and to the CSV round-trip that reads ``"+99720"`` back as the
    integer ``99720`` (a leading ``+`` is a valid integer sign)."""
    return "".join(ch for ch in str(s) if ch.isdigit())


def collect_phone_prefix(phone_records: list[Record],
                         territory: TerritoryProfile) -> list[GeoSignal]:
    """(b) Phone prefix: a regional dialling prefix on file."""
    prefixes = {_digits(p) for p in territory.phone_prefixes if _digits(p)}
    out: list[GeoSignal] = []
    for r in phone_records:
        pref = _s(r["phone_prefix"])
        if pref and _digits(pref) in prefixes:
            out.append(GeoSignal(
                signal_id="phone_prefix", value=pref,
                detail=f"a registered phone number carries the regional prefix "
                       f"{pref}, which indicates possible presence in the territory",
                weight_class=WEIGHT_STANDARD, provenance=r.provenance,
            ))
    return out


def collect_exclusive_carrier(phone_records: list[Record],
                              exclusive_carriers: set[str]) -> list[GeoSignal]:
    """(c) Region-exclusive carrier (practitioner addition): a carrier that
    operates ONLY inside the territory. Carrier alone is a signal even when the
    prefix is inconclusive — so this reads the carrier independently of the
    prefix, and is classed higher-value (a region-locked carrier is distinctive)."""
    out: list[GeoSignal] = []
    for r in phone_records:
        carrier = _s(r["carrier"])
        if carrier and carrier in exclusive_carriers:
            out.append(GeoSignal(
                signal_id="exclusive_carrier", value=carrier,
                detail=f"the number is on {carrier}, a carrier that operates only "
                       "inside the territory; this indicates possible presence "
                       "even where the dialling prefix is inconclusive",
                weight_class=WEIGHT_HIGH_VALUE, provenance=r.provenance,
            ))
    return out


def collect_kyc_geography(kyc_doc_records: list[Record],
                          territory: TerritoryProfile) -> list[GeoSignal]:
    """(d) KYC document geography: an identity document issued within the
    territory (issuing authority / place of issue)."""
    tokens = territory.geo_tokens()
    out: list[GeoSignal] = []
    for r in kyc_doc_records:
        issuing = _s(r["issuing_country"]).lower()
        if issuing and issuing in tokens:
            out.append(GeoSignal(
                signal_id="kyc_geography", value=_s(r["issuing_country"]),
                detail=f"a KYC document was issued in {_s(r['issuing_country'])}, "
                       "which indicates possible presence in the territory",
                weight_class=WEIGHT_STANDARD, provenance=r.provenance,
            ))
    return out


def collect_declared_residence(account_record: Optional[Record],
                               territory: TerritoryProfile) -> list[GeoSignal]:
    """(e) Declared residence: the account's declared residence jurisdiction is
    the territory (or its parent country)."""
    if account_record is None:
        return []
    tokens = territory.geo_tokens()
    residence = _s(account_record["residence_country"]).lower()
    if residence and residence in tokens:
        return [GeoSignal(
            signal_id="declared_residence", value=_s(account_record["residence_country"]),
            detail=f"the account's declared residence is {_s(account_record['residence_country'])}, "
                   "which indicates possible presence in the territory",
            weight_class=WEIGHT_STANDARD, provenance=account_record.provenance,
        )]
    return []


def collect_device_timezone(timezone_records: list[Record],
                            territory: TerritoryProfile) -> list[GeoSignal]:
    """(f) Device timezone: a device clock set to the territory's timezone. A
    coarse locator (many regions share a timezone), so it is classed WEAK."""
    zones = {z.strip() for z in territory.timezones if z.strip()}
    out: list[GeoSignal] = []
    for r in timezone_records:
        tz = _s(r["timezone"])
        if tz and tz in zones:
            out.append(GeoSignal(
                signal_id="device_timezone", value=tz,
                detail=f"a device timezone is set to {tz}, which weakly indicates "
                       "possible presence in the territory",
                weight_class=WEIGHT_WEAK, provenance=r.provenance,
            ))
    return out


def collect_vpn_markers(ip_records: list[Record]) -> list[GeoVpnMarker]:
    """VPN logins — recorded as obfuscation markers, NEVER as location signals."""
    out: list[GeoVpnMarker] = []
    for r in ip_records:
        if _truthy(r.get("is_vpn")):
            out.append(GeoVpnMarker(
                detail="a login used a VPN/anonymising IP; recorded as an "
                       "obfuscation marker, not as location evidence",
                timestamp=_s(r["timestamp"]), provenance=r.provenance,
            ))
    return out


def _vpn_slip_records(ip_records: list[Record],
                      territory: TerritoryProfile) -> list[Record]:
    """The NON-VPN territory IP rows that sit in a gap of otherwise-continuous VPN
    use — a VPN record exists both BEFORE and AFTER them in the timeline. Ordered
    by timestamp; deterministic."""
    tokens = territory.geo_tokens()
    rows = sorted(ip_records, key=lambda r: _s(r["timestamp"]))
    vpn_ts = [_s(r["timestamp"]) for r in rows if _truthy(r.get("is_vpn"))]
    if not vpn_ts:
        return []
    first_vpn, last_vpn = vpn_ts[0], vpn_ts[-1]
    slips: list[Record] = []
    for r in rows:
        if _truthy(r.get("is_vpn")):
            continue
        geo = _s(r["geolocation"]).lower()
        ts = _s(r["timestamp"])
        if geo and any(tok in geo for tok in tokens) and first_vpn < ts < last_vpn:
            slips.append(r)
    return slips


def collect_vpn_slip(ip_records: list[Record],
                     territory: TerritoryProfile) -> list[GeoSignal]:
    """VPN-slip: a territory IP observed during a gap in otherwise-continuous VPN
    use. Higher-value than an ordinary IP hit; the slip window (the bracketing VPN
    timestamps) is cited in the detail so a human can see exactly why it counts
    for more."""
    rows = sorted(ip_records, key=lambda r: _s(r["timestamp"]))
    vpn_ts = [_s(r["timestamp"]) for r in rows if _truthy(r.get("is_vpn"))]
    out: list[GeoSignal] = []
    for r in _vpn_slip_records(ip_records, territory):
        ts = _s(r["timestamp"])
        before = max((t for t in vpn_ts if t < ts), default="")
        after = min((t for t in vpn_ts if t > ts), default="")
        out.append(GeoSignal(
            signal_id="vpn_slip", value=_s(r["geolocation"]),
            detail=f"a territory IP ({_s(r['geolocation'])}) appeared at {ts}, in a "
                   f"gap of otherwise-continuous VPN use (VPN seen {before} and {after}); "
                   "a higher-value indication of possible presence than an ordinary "
                   "IP hit, because the surrounding VPN use was briefly interrupted",
            weight_class=WEIGHT_HIGH_VALUE, provenance=r.provenance,
        ))
    return out


def collect_counter_evidence(validity_records: list[Record],
                             territory: TerritoryProfile,
                             reference_date: str) -> tuple[list[GeoCounterEvidence],
                                                           list[GeoControlGap]]:
    """Counter-evidence + the dual control-gap flag, from the ``kyc_artifact_validity``
    sibling. A residency-type document issued OUTSIDE the territory argues against
    presence; if EXPIRED (``expiry_date`` before ``reference_date``) its
    counter-weight is degraded AND a KYC-refresh control gap is raised. A residency
    document with no expiry on file is treated as a MISSING-refresh control gap.
    Expiry is never read as evidence of presence."""
    tokens = territory.geo_tokens()
    counter: list[GeoCounterEvidence] = []
    gaps: list[GeoControlGap] = []
    for r in validity_records:
        atype = _s(r["artifact_type"])
        if atype not in COUNTER_EVIDENCE_DOC_TYPES:
            continue
        issuing = _s(r["issuing_geography"])
        if not issuing or issuing.lower() in tokens:
            continue  # issued inside the territory: not counter-evidence
        expiry = _s(r["expiry_date"])
        if not expiry:
            gaps.append(GeoControlGap(
                gap_type="kyc_refresh_missing", artifact_type=atype,
                detail=f"a {atype} issued in {issuing} has no expiry/refresh date "
                       "on file; the exchange cannot confirm it is current",
                provenance=r.provenance,
            ))
            continue
        expired = expiry < reference_date
        if expired:
            tail = (f"it expired on {expiry}, so its weight as counter-evidence "
                    "is degraded")
        else:
            tail = (f"it is valid (expiry {expiry}), so it argues against presence "
                    "in full")
        counter.append(GeoCounterEvidence(
            artifact_type=atype, issuing_geography=issuing,
            staleness="expired" if expired else "valid",
            counterweight="degraded" if expired else "full",
            detail=f"a {atype} issued in {issuing} argues against presence in the "
                   f"territory; {tail}",
            provenance=r.provenance,
        ))
        if expired:
            gaps.append(GeoControlGap(
                gap_type="kyc_refresh_expired", artifact_type=atype,
                detail=f"a {atype} expired on {expiry}; the exchange failed to "
                       "re-verify it (KYC-refresh control gap)",
                provenance=r.provenance,
            ))
    return counter, gaps


def _truthy(v: object) -> bool:
    """A CSV boolean cell (``True``/``"True"``/``"true"``/1) as a bool."""
    if isinstance(v, bool):
        return v
    return _s(v).lower() in ("true", "1")


def assemble_dossier(
    uid: int,
    entity_name: str,
    *,
    territory: TerritoryProfile,
    reference_date: str,
    ip_records: list[Record],
    phone_records: list[Record],
    kyc_doc_records: list[Record],
    account_record: Optional[Record],
    timezone_records: list[Record],
    validity_records: list[Record],
    exclusive_carriers: set[str],
) -> GeoDossier:
    """Assemble one account's totality dossier from every collector.

    Deterministic: signals are composed in a fixed collector order (VPN-slip
    before ordinary IP so the higher-value form leads; then phone, carrier, KYC
    geography, residence, timezone). The one-signal rule is applied by
    :attr:`GeoDossier.surfaced`. Pure over its inputs — the U1b wiring supplies
    the rows from the connectors."""
    signals: list[GeoSignal] = []
    signals += collect_vpn_slip(ip_records, territory)
    signals += collect_ip_geolocation(ip_records, territory)
    signals += collect_phone_prefix(phone_records, territory)
    signals += collect_exclusive_carrier(phone_records, exclusive_carriers)
    signals += collect_kyc_geography(kyc_doc_records, territory)
    signals += collect_declared_residence(account_record, territory)
    signals += collect_device_timezone(timezone_records, territory)

    vpn_markers = collect_vpn_markers(ip_records)
    counter, gaps = collect_counter_evidence(validity_records, territory, reference_date)

    if signals:
        note = (
            f"Surfaced for review under the one-signal rule: {len(signals)} "
            f"location signal(s) ({', '.join(s.signal_id for s in signals)}) "
            "indicate possible presence in the territory. Signals are "
            "correlational and calibrated — presence is not asserted; a human "
            "resolves. VPN use (if any) is recorded as an obfuscation marker, "
            "never as location evidence."
        )
    else:
        note = (
            "Not surfaced: no positive location signal was collected. Any VPN "
            "markers or counter-evidence below are recorded for completeness and "
            "do not, on their own, indicate presence."
        )
    return GeoDossier(
        uid=uid, entity_name=entity_name, signals=signals,
        vpn_markers=vpn_markers, counter_evidence=counter, control_gaps=gaps,
        note=note,
    )
