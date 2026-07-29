# Geo Triangulation — methodology (v1.0.0)

**Status:** Phase 8 Part III. This document is the published, versioned policy
for Okojo's geo-triangulation layer. Its canonical policy block (below) equals
`geo_config()` in `src/okojo/geo/__init__.py` **exactly** — a test
(`tests/test_geo_methodology.py`) fails if the two ever drift, and the config is
stamped into every territory sweep's tamper-evident audit chain once per run.
This is the **tenth** doc↔code anti-drift pair.

Everything in this layer is **REVIEW-tier** and **calibrated**: a signal
**indicates possible presence**, it never **proves location**. The layer
*surfaces* accounts and (in a later slice) *proposes* an action; **a human
resolves**. Presence is never asserted as fact.

All data is **synthetic**: the territory is a **fictional** region (no real
occupied-territory name), the carriers are **invented** (no real carrier), and
the territory / country codes are **named by no advisory** (so the shared
advisory matcher is provably inert to them).

---

## 1. What geo triangulation does

A new designation **kind** — **TERRITORY** — designates a *geography*, not a
party. The sweep response differs in kind: there is **no name screen** (there is
no name to screen). Instead the sweep **collects location signals per account and
triangulates** possible presence inside the sanctioned region — the practitioner's
manual geo-sweep, signal by signal.

Part III lands in slices. **U1a** (this version) stands up the module, the six
signal collectors, the VPN discipline, the staleness modifier, the totality
dossier, and this published policy — declared **complete** here, so that **U1b**
(the territory scenario + the collector data + the sweep wiring) and **U2** (the
proposal decision) consume it with **no further version bump** — the same
"declare the full surface once" discipline `sweep_config()` used in Slice S1 and
`identity_config()` in T1.

## 2. The six signal collectors

Each collector reads exactly one evidence surface and grounds every signal it
emits to the single row it read. Collectors are independent and blind to one
another (multi-modal-sweep discipline):

| # | Signal | Reads | Fires when |
|---|--------|-------|-----------|
| a | `ip_geolocation` | `ip_logs` | a **non-VPN** login IP resolves into the territory |
| b | `phone_prefix` | `phone_registrations` | the registered number carries a regional dialling prefix |
| c | `exclusive_carrier` | `phone_registrations` + `exclusive_carriers` | the number is on a carrier that operates **only** inside the territory — a signal **even when the prefix is inconclusive** (the practitioner addition) |
| d | `kyc_geography` | `kyc_docs` | a KYC identity document was issued within the territory |
| e | `declared_residence` | `accounts` | the account's declared residence jurisdiction is the territory |
| f | `device_timezone` | `device_timezones` | a device clock is set to the territory's timezone (coarse → **weak**) |

`weight_class` (standard / high_value / weak) is a published, tunable attribute
recorded on every signal: a region-locked carrier or a VPN-slip is a stronger
locator than a shared timezone. It is consumed by the U2 proposal rule.

### 2.1 The one-signal rule

**ANY single positive location signal surfaces the account for review.** Signals
then accumulate into the totality dossier — more signals strengthen the picture,
but one is sufficient to surface. This is verbatim practitioner testimony, and it
is why the sweep casts wide and then reads the totality, rather than gating on a
score.

## 3. VPN discipline

**VPN use is NEVER location evidence.** A VPN/anonymising login yields **no**
location signal — only a marker in the dossier, recorded as
obfuscation/contradiction context.

**The VPN-slip is the one higher-value form.** A territory IP observed during a
*gap* in otherwise-continuous VPN use (a VPN record exists both before and after
it in the timeline) is a **higher-value** signal than an ordinary IP hit — the
surrounding VPN use was briefly interrupted. The dossier cites the **slip window**
(the bracketing VPN timestamps) explicitly, so a human can see exactly why it
counts for more.

## 4. Document-staleness modifier (NOT a location signal)

Counter-evidence is a **residency/domicile document issued OUTSIDE the territory**
(a foreign residency card) — it argues *against* presence. Its weight carries a
**staleness modifier**:

- a **valid** counter-document argues against presence in full;
- an **EXPIRED** one argues much less (its counter-weight is **degraded**);
- a **MISSING** one (no expiry/refresh on file) carries none.

**Document staleness is never read as evidence of presence** — an expired
residency card does not make presence *more* likely, it merely makes the
counter-argument weaker. Every EXPIRED or MISSING counter-document also raises a
**dual flag**: a **KYC-refresh control gap** — the exchange failed to re-verify —
surfaced for the control owner, separately from any location signal.

## 5. The totality dossier

Per account, `assemble_dossier` composes every collector's output into a
`GeoDossier`: the positive **signals**, the **VPN markers**, the
**counter-evidence** (with staleness), and the **control gaps** — every line
provenance-pointed. `dossier.surfaced` is the one-signal-rule verdict (True iff
at least one positive location signal was collected; VPN markers and
counter-evidence never surface an account). The dossier is the decision surface a
human reads, and (in U2) the input to the proposal decision.

## 6. Production posture

The signal collectors are the piece a real deployment would assemble from device,
telecom, and KYC feeds. Okojo's distinct value is the same as elsewhere: grounded
signals, the totality dossier a human reads, calibrated language throughout, and
the tamper-evident audit chain — plus the discipline that VPN is never location
evidence and that document staleness never argues *for* presence. No real
territory, carrier, or jurisdiction is named or implied.

### 6.1 Guard-surface map (the two-audience boundary)

Geo triangulation produces one **subject-facing** surface — the enhanced-due-
diligence RFI proposed for the ambiguous case — and several **internal** ones
(the dossier a reviewer reads, the decision rationale, the audit stamps). Which
guard applies is a function of **who could read the text**, never of the
surface's name:

| Surface | Who reads it | Guard | On failure |
|---|---|---|---|
| EDD identity/geography RFI (`propose_edd_rfi`) | the **customer** (subject-facing) | `assert_no_tipping_off`, on the fully rendered text, plus grounding to the account row | suppressed & surfaced for human authoring; never sent |
| Geo dossier / signal detail / decision rationale | internal (compliance reviewer) | grounding to the single row read; calibrated language | flagged; a signal that cannot cite its row is never emitted |
| `geo_triangulation` / `geo_proposal` audit stamps | internal (audit) | provenance-pointed, chain-verified | — |

The single rule behind the table: **only subject-facing text passes through
`assert_no_tipping_off`.** The EDD RFI is the sole subject-facing surface geo
triangulation produces; the neutral records-maintenance template names no
territory, match, method, or list, and is validated fail-closed *after*
rendering (the interpolated customer name is the likeliest smuggling path). The
`drafted_pending_human_review` status is the only one representable — there is no
send path and no execution path. Everything else is internal analyst material,
which legitimately names the territory, the signals, and the net-presence score a
customer must never see. The guard is chosen by the audience, so no internal
artifact is ever weakened to satisfy a subject-facing rule, and no subject-facing
surface can be added without inheriting the tipping-off guard by construction.

## 7. The versioned policy (canonical block)

The block below is the single source of truth, stamped into every territory
sweep's audit chain (`remediation_sweep / geo_config`) and asserted equal to
`geo_config()` by `tests/test_geo_methodology.py`.

<!-- geo-config:begin -->
```json
{
  "version": "1.0.0",
  "signal_registry": [
    {
      "id": "ip_geolocation",
      "source": "ip_logs",
      "weight_class": "standard",
      "description": "a non-VPN login IP resolving into the territory"
    },
    {
      "id": "phone_prefix",
      "source": "phone_registrations",
      "weight_class": "standard",
      "description": "a regional dialling prefix on the registered number"
    },
    {
      "id": "exclusive_carrier",
      "source": "phone_registrations + exclusive_carriers",
      "weight_class": "high_value",
      "description": "a carrier that operates ONLY inside the territory (a signal even when the prefix is inconclusive)"
    },
    {
      "id": "kyc_geography",
      "source": "kyc_docs",
      "weight_class": "standard",
      "description": "a KYC identity document issued within the territory"
    },
    {
      "id": "declared_residence",
      "source": "accounts",
      "weight_class": "standard",
      "description": "the account's declared residence jurisdiction is the territory"
    },
    {
      "id": "device_timezone",
      "source": "device_timezones",
      "weight_class": "weak",
      "description": "a device clock set to the territory's timezone (coarse)"
    },
    {
      "id": "vpn_slip",
      "source": "ip_logs",
      "weight_class": "high_value",
      "description": "a territory IP observed in a gap of otherwise-continuous VPN use (higher-value than an ordinary IP hit)"
    }
  ],
  "one_signal_rule": "ANY single positive location signal surfaces the account for review. Signals then accumulate into the totality dossier — more signals strengthen the picture, but one is sufficient to surface. Calibrated throughout: signals indicate possible presence, never prove location.",
  "vpn_discipline": {
    "rule": "VPN use is NEVER location evidence; it is recorded in the dossier as an obfuscation/contradiction marker.",
    "vpn_slip": "a territory IP observed during a gap in otherwise-continuous VPN use is a HIGHER-VALUE signal than an ordinary IP hit; the dossier cites the slip window (the bracketing VPN timestamps) explicitly."
  },
  "staleness_modifier": {
    "gap_categories": [
      "MISSING",
      "EXPIRED"
    ],
    "counter_evidence_doc_types": [
      "residency_card",
      "residence_permit"
    ],
    "counterweight_by_status": {
      "valid": "full",
      "expired": "degraded",
      "missing": "none"
    },
    "rule": "a residency/domicile document issued OUTSIDE the territory argues against presence; if EXPIRED its counter-weight is degraded, if MISSING it carries none. Document staleness is NEVER read as evidence of presence.",
    "dual_flag": "an EXPIRED or MISSING counter-document also raises a KYC-refresh control gap — the exchange failed to re-verify — surfaced for the control owner, separately from any location signal."
  },
  "proposal_menu": [
    {
      "id": "propose_edd_rfi",
      "description": "ask the customer (an enhanced-due-diligence identity/geography RFI) — the honest proposal when the totality cannot resolve"
    },
    {
      "id": "propose_withdrawal_only_restriction",
      "description": "propose a withdrawal-only restriction for human action"
    },
    {
      "id": "propose_trade_and_withdrawal_block",
      "description": "propose a trade + withdrawal block for human action"
    },
    {
      "id": "propose_full_block_and_escalate",
      "description": "propose a full block and escalation for human action"
    }
  ],
  "posture": "REVIEW-tier throughout: the layer surfaces and (in U2) proposes; a human resolves. Presence is never asserted as fact. A TERRITORY designation has no name screen — location signals are triangulated instead. All data is synthetic: a fictional region, invented carriers, and territory/country codes named by no advisory."
}
```
<!-- geo-config:end -->

### Declared complete here (consumed later with no version bump)

- The **six signal collectors** and the **VPN-slip** form (the `signal_registry`)
  are consumed by the U1b territory scenario + sweep wiring.
- The **proposal menu** (`proposal_menu`) is consumed by U2's `decide_geo_action`;
  the concrete dossier-totality → action **threshold mapping** is a tunable policy
  brought to the PM before U2 builds, and lands as a versioned change (AGENCY
  bump), not here.

## 8. Reproducibility

`geo_config()` is stamped into the territory sweep's own hash chain once per run,
alongside `sweep_config()`. Because the block above is asserted byte-equal to the
code and the version string is asserted present, the published methodology and
the running policy cannot silently diverge. Any change to a signal, a rule, or the
proposal menu is a versioned change: bump `GEO_VERSION`, regenerate this block in
the same commit, and the anti-drift test stays green.
