# Screening-Coverage Methodology (v1.0.0)

**Status:** synthetic-data research prototype. This document explains Okojo's
**screening coverage-gap check** — the institution-level third act of the
cross-list story. Part I-B built the multi-list screen; the v1.1 subject-as-seed
check told an investigator what was screened for *their* subject. This asks the
same question for the **whole book**, and as a standing signal:

> **Are we screening against the lists our actual customer exposure calls for?**

It is written for three readers at once — a compliance lead who owns the
screening program, a model-risk reviewer, and an external auditor. It is the
automated form of a coverage argument a practitioner otherwise makes by hand on a
whiteboard, once, and loses.

## 1. What it is — and is not

The check measures the customer base's **geographic footprint** against the
**enabled + ingested** list-source regimes and surfaces the mismatch as a
**finding**, never an action. It:

- **surfaces** the jurisdictions the customer base touches with no enabled list
  coverage (the *gap*), and the regimes declared but not ingested;
- **cites** every line — footprint counts to the account / KYC rows they come
  from, coverage verdicts to the published policy and the frozen list-source
  registry;
- **proposes nothing and changes nothing** — it is a read-only derivation. A
  human reads the finding and decides whether the screening program's scope
  should change.

It is deliberately **not** a claim that any customer is sanctioned, that any
jurisdiction is high-risk, or that a gap is a violation. A footprint in a
jurisdiction with no enabled list coverage is a *screening-scope observation*,
not a legal conclusion.

## 2. The footprint — three legs, counted separately

An investigator does not read "customer geography" as one number. The check
derives three **separately-counted, separately-cited** legs and never merges
them:

| Leg | Source field | Counts | Reads as |
| --- | --- | --- | --- |
| `residence` | `accounts.residence_country` | customers | where the customer is |
| `kyc_issuing` | `kyc_docs.issuing_country` | documents | where their identity document was issued |
| `nationality` | `accounts.nationality_country` | customers | claimed nationality |

The **nationality** leg is present on a deliberate ruling: it is necessary to an
investigation, and it is the leg that surfaces the sole no-coverage gap in this
world (`XV`, below) — a finding the residence leg alone would miss. Each leg
skips blank / `nan` values and carries its `source[*].field` citation.

The **footprint** the coverage model is assessed against is the **union** of the
three legs' jurisdictions.

## 3. Coverage & the two gap classes

For each footprint jurisdiction, the check asks which list-source regimes declare
coverage of it (the published policy, §6) and which of those are **ingested**
(read live from the frozen sweep `LIST_SOURCE_REGISTRY` — never copied, so
coverage and the sweep can never disagree on what is enabled):

- **Covered** — at least one *ingested* regime declares coverage.
- **Ingestion gap** — coverage is declared *only* by a regime that is **not
  ingested**. Coverage exists on paper but is not enabled. This is the
  visible-absence principle elevated from a footer line to a first-class finding.
- **No-coverage gap** — **no** regime declares coverage at all. The jurisdiction
  is outside every declared list's scope. This is the live tripwire: it fires the
  day the customer base reaches a jurisdiction the policy never anticipated.

The three classes **partition** the footprint (disjoint and exhaustive) — a
property the eval asserts.

### 3a. The territory-scoping annotation

Two footprint codes are annotated because they are also part of a **designated
territory**, screened by the territory / geo path rather than a standing list:

- `QZ` — the designated **Qazrun Free Zone** territory (`DES-2026-0008`). Here it
  is counted only as a plain footprint jurisdiction; its designation is handled
  by the geo triangulation layer.
- `XV` — the **fictional parent country** of that territory. No standing
  list-source regime enumerates it, so it is the world's one *no-coverage* gap.

Both annotations are **data-derived** from `territory_profile` (never hardcoded to
a code) and cited to it, so the note is grounded and moves with the data.

## 4. What this world's numbers say

Against the current synthetic scenario, with the domestic and foreign-NCT lists
ingested and the UN-style backstop declared-but-not-ingested:

- **Covered** (an ingested regime lists them): `AE`, `DE`, `GB`, `US`.
- **Ingestion gaps** (only the un-ingested UN backstop lists them):
  `BR`, `CN`, `HK`, `NZ`, `QZ`, `SG`, `TR`, `ZA`.
- **No-coverage gap** (no regime lists it): `XV`.
- **Declared but not ingested** (elevated to a finding): the Synthetic UN-style
  Consolidated List.

The finding is calibrated in exactly those terms: *"footprint in `<jurisdiction>`
with no enabled list coverage — a screening-scope observation, not a legal
claim."*

## 5. Evaluation — what the numbers do and do not claim

The check is scored against `ground_truth.json` in the P8-A / P8-G discipline
(`tests/test_coverage_eval.py`). The gold keys
(`coverage_footprint_jurisdictions`, `coverage_covered_jurisdictions`,
`coverage_ingestion_gaps`, `coverage_no_coverage_gaps`,
`coverage_declared_not_ingested_regimes`) are **hand-authored in the generator,
independent of `coverage_config`** (never imported there), so scoring the
assessment against them is a real check, never circular:

- **Exact-set** membership on the footprint, the covered set, both gap sets, and
  the declared-not-ingested set.
- **Partition** — the three classes are disjoint and cover the footprint.
- **Grounding** — every leg and every verdict carries provenance; gap rows cite
  the registry's ingested flag; the `QZ` / `XV` rows cite `territory_profile`.
- **P8-G falsification** — ingesting the UN backstop (via an injected registry
  copy, *never* editing the frozen `sweep_config`) collapses the ingestion-gap
  set to empty; de-ingesting the domestic regime moves `AE` out of the covered
  set. The answer key is the arbiter against silent drift.

## 6. Reproducibility & versioning

The regime → jurisdiction coverage map is a **policy**, not world data: a
published assertion of which jurisdictions each list is treated as an
authoritative standing screen for. It lives in its own versioned config
(`okojo.coverage.coverage_config`), **not** in the frozen `sweep_config`, and is
regression-tested against this document so the doc and the code can never
silently drift. The map is deliberately **not exhaustive** over the ISO
namespace: a footprint jurisdiction absent from every regime's list is a
no-coverage finding, never a silent pass.

Bump `version` whenever the coverage map, the gap taxonomy, or the footprint-leg
set changes. The ingested status of each regime is **not** part of this config —
it is read live from the sweep registry, so enabling a list is a sweep-side
change, not a coverage-side one.

**Version 1.0.0 — canonical policy:**

<!-- coverage-config:begin -->
```json
{
  "version": "1.0.0",
  "regime_jurisdiction_coverage": {
    "SYN-DOMESTIC-OFAC": ["AE"],
    "SYN-FOREIGN-NCT": ["DE", "GB", "US"],
    "SYN-UN-CONSOLIDATED": ["BR", "CN", "HK", "NZ", "QZ", "SG", "TR", "ZA"]
  },
  "gap_taxonomy": {
    "no_coverage": "footprint jurisdiction covered by NO list-source regime at all (ingested or not); outside every declared list's scope",
    "ingestion": "footprint jurisdiction covered ONLY by a declared-but-not-ingested regime; coverage exists on paper but is not enabled (visible absence)"
  },
  "footprint_legs": [
    {"leg": "residence", "source": "accounts", "field": "residence_country", "label": "declared residence country", "count_unit": "customers"},
    {"leg": "kyc_issuing", "source": "kyc_docs", "field": "issuing_country", "label": "KYC document issuing country", "count_unit": "documents"},
    {"leg": "nationality", "source": "accounts", "field": "nationality_country", "label": "declared nationality", "count_unit": "customers"}
  ]
}
```
<!-- coverage-config:end -->
