# Identity Resolution — methodology (v1.0.0)

**Status:** Phase 8 Part II. This document is the published, versioned policy for
Okojo's identity-resolution layer. Its canonical policy block (below) equals
`identity_config()` in `src/okojo/identity/__init__.py` **exactly** — a test
(`tests/test_identity_methodology.py`) fails if the two ever drift, and the
config is stamped into every sweep's tamper-evident audit chain once per run.
This is the **ninth** doc↔code anti-drift pair.

Everything in this layer is **REVIEW-tier**: it *surfaces* candidates and
*proposes*; a human resolves. **The agent never asserts identity — or, in later
slices, kinship — as fact.**

---

## 1. What identity resolution does

Given a designated name (foreign or domestic), resolve which customers might *be*
that party — starting with the problem a plain screen fails on: **romanization
variants**. A customer who opened an account under a different published
romanization of a designated name slides past an exact-match screen, and often
past a single-script fuzzy screen too. This layer expands the designated name
into its published-romanization variant space and matches each variant against
customer-typed names, showing **which rule path fired** and the score for every
hit — the evidence for *how* the name resolved, never a bare "match".

Part II lands in slices. **T1 is the variant-aware name screen; T2 (this
version's companion) adds the corroboration decision.** The beneficial-owner +
officer walk (T3) and the proximity ring (T4) consume the reserved policy
declared below (the ownership-control threshold and the proximity-signal
registry) with **no further version bump** — the same "declare the full surface
once" discipline `sweep_config()` used in Slice S1.

**Corroboration before proposal (T2) — a recorded decision, not a routing
branch.** A name match, and especially a cross-romanization one, is never enough
to assert identity. T2 compares a matched customer's KYC identity attributes
against the identifiers the sanctions list published for the designated party
and proposes one of three REVIEW-tier dispositions — *corroborated true hit*,
*possible match (needs human)*, or *name-only dismissed* — with a dismissal
always recording **which identifiers disqualified the match**. Crucially, this
step **adds no branch to the sweep**: the remediation sweep stays a linear
pipeline, and each corroboration is *stamped into its audit chain as a recorded
decision* that drives review triage, never control flow. The decision rule, its
outcomes, and its version live in the agency policy (`agency_config`,
`docs/agency-methodology.md` §6); the identity module supplies the identifiers
and KYC-attribute substrate it compares. This is the "corroboration-before-
proposal" value named in §3: identifying data must agree before the system ever
proposes that a customer *is* a designated party.

## 2. Variant-aware name screen

### 2.1 Transliteration equivalence rule tables

The rule tables encode **published romanization conventions only** — no
proprietary or scraped table. Two families ship in v1.0.0:

- **Cyrillic (Russian):** BGN/PCGN 1947, ISO 9:1995, ALA-LC (Russian),
  UNGEGN / GOST 7.79 System B.
- **Arabic:** BGN/PCGN 1956, ISO 233:1984, ALA-LC (Arabic), UNGEGN (Arabic).

Each equivalence class names an underlying name-part and the specific published
divergence it unifies (e.g. the Cyrillic initial Е as *Ye-* in BGN/PCGN vs *E-*
in ISO 9; the Arabic definite article ال as *al-* vs *el-*; محمد across its
common romanizations). The full set — every class, its forms, and its basis — is
published verbatim in the canonical block in §4, so a reviewer (or a regulator)
sees the exact equivalence policy and its citations, not a black box.

These tables are **bounded and illustrative, not a complete transliteration
engine.** They encode the specific divergences the synthetic scenario exercises
and a handful of common neighbours; the honest scope is a reference
implementation, not exhaustive multilingual coverage (see §3).

### 2.2 Expansion, screening, and the rule path

`expand_name_variants(name)` produces an ordered set of `(variant, fired_rules)`
pairs: the identity variant (no rule fired) plus every combination reachable by
substituting a class form for an original token. `screen_name_variants(...)` then
scores each customer name against the variant space with the same RapidFuzz
`WRatio` the direct screen uses, and records a match **only when a transliteration
rule actually fired** — a name that reaches threshold with no rule applied is, by
definition, a **direct** screen hit (already surfaced by the sweep's
`match_designated_name`), not a variant one. Each variant hit carries the winning
variant, the ordered `rule_path` of equivalence-class ids that produced it, the
families those classes belong to, and the score. Deterministic and RNG-free:
variant enumeration is an ordered Cartesian product; scoring ties break toward
the lexicographically smallest variant.

Variant hits are surfaced for **identity review** (in `SweepResult` and the
`name_screen` audit record). In T1 they deliberately **do not** feed the
exposure/hold worksheet — a name match is not flow exposure — so the variant
layer adds no exposure and moves no legacy scorecard.

### 2.3 Two thresholds, pinned together

The variant layer runs at `VARIANT_MATCH_THRESHOLD` (85). It is declared as its
own pinned policy parameter, and a tripwire test asserts it equals the sweep's
`NAME_MATCH_THRESHOLD` (and, transitively, the SDN screener's
`SCREEN_THRESHOLD`) — so the variant layer can never silently run at a different
bar than the direct screen it sharpens. Intentional divergence must be argued
through an `IDENTITY_VERSION` bump, never drift in.

## 2.4 Beneficial-owner + officer walk (T3)

Once a designated party is *resolved* to a customer (matched by the screen and
**not dismissed** by corroboration), the walk follows the synthetic KYB ownership
and officer structure around it and surfaces three REVIEW-tier findings, each
grounded in the row it cites:

- **Ownership propagation.** Designation status propagates to a company owned by
  the resolved party **at or above `ownership_control_threshold` (0.50)** —
  surfaced as *owned/controlled by a designated party*. A stake **below** the
  threshold does not propagate. The threshold is a tunable policy parameter
  stated at **principle level** (majority-ownership control); no statute is
  cited.
- **Fictitious executive.** An officer of record with **no resolvable identity
  footprint** — a name-only appointment whose name matches no customer account
  and no KYC holder — is flagged. An officer whose uid resolves to an account, or
  whose name matches a real account, has a footprint and is **not** flagged.
- **Post-designation control change.** An officer appointment (or ownership
  record) dated **after** the designation is flagged as a control change that
  postdates the designation event — the same date-vs-designation discipline the
  sweep already uses for exposure timing. A change dated **before** the
  designation is not flagged.

**Ownership and officer edges are a DISTINCT edge type.** Exactly like a
gas-funding edge, they can never fabricate on-chain flow exposure: the walk
returns review findings and their provenance only, never a tainted amount, and a
test asserts the propagation adds **zero USDT**. A party corroboration *dismissed*
as a same-name collision seeds no walk. The walk is stamped into the sweep's audit
chain only where it produces a finding, so a designation with no resolved
corporate footprint leaves its chain byte-unchanged.

## 2.5 Proximity ring (T4)

Around a *resolved* designated party (an individual the screen matched and
corroboration did not dismiss), the proximity layer surfaces the ring of
relatives and close associates for **REVIEW — never exposure, and never asserted
kinship.** Kinship is a **correlational signal the system surfaces with its
evidence**; a human decides. Every ring statement stays in calibrated language
(*candidate* / *possible* / *shares*), never "is the sister of".

- **Primary signals** (surface a candidate into the ring): a shared
  surname/patronymic token, declared-relationship metadata on file, a
  relationship-asserting remark, or a KYC-document cross-holding (one party's
  identity document inside another's account).
- **Weighting signals** (add evidence to an already-surfaced candidate, never
  surface one alone — "shared surname *weighted by* shared KYC attributes"): a
  shared KYC attribute (address / contact) or a shared email-handle pattern.
  **Non-distinctive placeholder values are ignored**, so a value shared by
  construction across synthetic subjects can never fabricate a weight.

**Not weighted by activity volume — dormancy is not innocence.** A dormant,
densely-linked account surfaces exactly as loudly as an active one, while an
active but unconnected stranger does not surface at all. The **shared-device**
registry signal is deliberately *not* re-evaluated here: device linkage is
already surfaced by the sweep's exposure/adjacency walk, so the proximity layer
adds only the kinship signals that walk does not cover, and accounts already
surfaced as exposed or adjacent are excluded (the ring is the *otherwise-
unconnected* associates). The ring carries **zero flow exposure** (asserted), is
stamped into the sweep chain only where non-empty, and — like the ownership walk
— never runs for a party corroboration dismissed as a same-name collision.

## 2.6 Identity-review RFI (T5) — the first subject-facing surface

Every layer above is *internal*: worksheets, decisions, and drafts read by a
compliance officer. The identity-review RFI is the first surface in the sweep
that could ever be put to a **customer**, so it is the most tightly governed.

- **Who it addresses.** Only the candidate corroboration could neither confirm
  nor dismiss (outcome ``possible_match_needs_human``). A *corroborated true hit*
  is already resolved and a *name-only dismissal* is a cleared collision — asking
  either would be pointless or a disclosure risk, so neither is ever contacted.
- **What it may say.** A **routine identity/document-verification request** —
  please confirm the identity details already on file and provide a current
  identity document. It reveals **nothing** about a designation match, the
  screening or corroboration method, any list source, or any investigation or
  law-enforcement interest.
- **The guard.** The fully rendered text is validated **fail-closed** by
  ``assert_no_tipping_off`` (the subject-facing guard). A request that trips the
  check is **suppressed and surfaced** for human authoring — never emitted.
- **Grounded, and drafted-only.** Each request cites the candidate's own KYC
  identity-attributes row (the record it asks them to confirm), and that pointer
  must resolve before the draft is emitted. The only representable status is
  ``drafted_pending_human_review``: **no send path exists**; a human owns
  assembly, judgment, and any sending. It is stamped into the sweep chain only
  where a draft (or a suppression) exists.

## 3. Production posture (vendor-agnostic)

In a real deployment, the variant-matching layer above is the piece an
institution would delegate to a **commercial screening API** — cross-script
transliteration at scale is a solved, commoditised problem. Okojo's distinct
value is what no screening vendor provides: **registry governance** (visible
absence — a declared-but-not-ingested list is a published fact, not a silent
gap), **corroboration-before-proposal** (T2: identifying data must agree before
any true-hit is proposed), **calibrated action proposals** (the layer proposes
and flags; a human resolves), and the **tamper-evident audit chain** that records
every screen, decision, and citation. No vendor is named or implied; this is an
in-house reference implementation over fully synthetic data.

### 3.1 Guard-surface map

Every text surface identity resolution produces is governed by a specific,
fail-closed guard. Which guard applies is a function of **who could read the
text**, never of the surface's name:

| Surface | Who reads it | Guard | On failure |
|---|---|---|---|
| Identity-review RFI (§2.6) | the **customer** (subject-facing) | `assert_no_tipping_off` | suppressed & surfaced for human authoring; never sent |
| Sweep worksheet / escalation drafts | internal (compliance) | `SIGNAL_BANNED_TERMS` (foreign-list signals) + grounding/resolvability | suppressed & surfaced with reason |
| Any internal narrative that could over-claim | internal (compliance) | `BANNED_TERMS` calibration | flagged; calibrated language required |

The single rule behind the table: **only subject-facing text passes through
`assert_no_tipping_off`.** The RFI is the sole subject-facing surface identity
resolution produces; everything else is internal analyst material, which uses
the calibrated-language guards but legitimately names methods and evidence a
customer must never see. The guard is chosen by the audience, so a future
subject-facing surface inherits the tipping-off guard by construction, and no
internal artifact is ever weakened to satisfy a subject-facing rule.

## 4. The versioned policy (canonical block)

The block below is the single source of truth, stamped into every sweep's audit
chain (`remediation_sweep / identity_config`) and asserted equal to
`identity_config()` by `tests/test_identity_methodology.py`.

<!-- identity-config:begin -->
```json
{
  "version": "1.0.0",
  "variant_match_threshold": 85,
  "transliteration_families": {
    "cyrillic": {
      "romanization_standards": [
        "BGN/PCGN 1947 (Romanization of Russian)",
        "ISO 9:1995 (Transliteration of Cyrillic)",
        "ALA-LC Romanization Tables (Russian)",
        "UNGEGN / GOST 7.79 System B"
      ],
      "equivalence_classes": [
        {
          "id": "cyr-yevgeniy",
          "forms": [
            "yevgeniy",
            "evgenii",
            "evgeny",
            "yevgeni"
          ],
          "basis": "Cyrillic Е initial (Ye- BGN/PCGN vs E- ISO 9) and -ий ending (-iy / -ii / -y across standards)"
        },
        {
          "id": "cyr-skiy",
          "forms": [
            "zhukovskiy",
            "zhukovsky",
            "zhukovski"
          ],
          "basis": "-ский surname ending romanized -skiy (BGN/PCGN) / -sky (traditional) / -ski (ISO 9)"
        },
        {
          "id": "cyr-aleksandr",
          "forms": [
            "aleksandr",
            "alexander",
            "aleksander"
          ],
          "basis": "Александр — Cyrillic кс as ks (ISO 9 / ALA-LC) vs x (traditional English)"
        },
        {
          "id": "cyr-ov",
          "forms": [
            "volkov",
            "volkoff"
          ],
          "basis": "-ов surname ending: -ov (modern standards) vs -off (older French/passport transliteration)"
        }
      ]
    },
    "arabic": {
      "romanization_standards": [
        "BGN/PCGN 1956 (Romanization of Arabic)",
        "ISO 233:1984 (Transliteration of Arabic)",
        "ALA-LC Romanization Tables (Arabic)",
        "UNGEGN (Arabic)"
      ],
      "equivalence_classes": [
        {
          "id": "ara-muhammad",
          "forms": [
            "muhammad",
            "mohammed",
            "mohamed",
            "mohamad",
            "muhammed"
          ],
          "basis": "محمد — short-vowel a/o and gemination differences across BGN/PCGN, ISO 233, and common usage"
        },
        {
          "id": "ara-article",
          "forms": [
            "al",
            "el",
            "ul"
          ],
          "basis": "the definite article ال romanized al- (BGN/PCGN, ISO 233) vs el- / ul- (regional/common usage)"
        },
        {
          "id": "ara-sayigh",
          "forms": [
            "sayigh",
            "sayegh",
            "sayagh"
          ],
          "basis": "long-vowel and غ (gh) rendering differences in the surname الصايغ across standards"
        },
        {
          "id": "ara-rashid",
          "forms": [
            "rashid",
            "rasheed",
            "rachid"
          ],
          "basis": "long ī romanized -i (ISO 233) vs -ee (common) and ش as sh vs ch (Francophone)"
        }
      ]
    }
  },
  "ownership_control_threshold": 0.5,
  "proximity_signal_registry": [
    {
      "id": "shared_surname",
      "description": "shared surname / patronymic token"
    },
    {
      "id": "shared_kyc_attribute",
      "description": "shared KYC attribute (address, contact)"
    },
    {
      "id": "declared_relationship",
      "description": "declared-relationship metadata on file"
    },
    {
      "id": "relationship_remark",
      "description": "a relationship-asserting free-text remark"
    },
    {
      "id": "shared_device",
      "description": "a shared device_fingerprint"
    },
    {
      "id": "email_handle_pattern",
      "description": "a shared email-handle pattern"
    },
    {
      "id": "kyc_document_cross_holding",
      "description": "KYC documents of one party inside another's account"
    }
  ],
  "posture": "REVIEW-tier throughout: the layer surfaces and proposes; a human resolves. Identity and kinship are never asserted as fact. The variant-matching layer is what a real deployment would delegate to a commercial screening API; Okojo's distinct value is registry governance, corroboration-before-proposal, calibrated proposals, and the tamper-evident chain (no vendor named or implied)."
}
```
<!-- identity-config:end -->

### Reserved for T2–T4 (declared complete here)

- `ownership_control_threshold` (0.50) — the documented ownership fraction at or
  above which designation status propagates through an ownership edge, stated at
  **principle level** (majority-ownership control), never a statute citation.
  Ownership/officer edges are a distinct edge type that can never fabricate flow
  exposure (the gas-edge discipline). Consumed by T3.
- `proximity_signal_registry` — the correlational signals by which a
  relative/associate of a *resolved* designated party is surfaced for review
  (never exposure, never asserted kinship, never weighted by activity volume).
  Consumed by T4.

## 5. Reproducibility

`identity_config()` is stamped into the sweep's own hash chain once per run,
alongside `sweep_config()`. Because the block above is asserted byte-equal to the
code and the version string is asserted present, the published methodology and
the running policy cannot silently diverge. Any change to a threshold, a rule
table, or the reserved policy is a versioned change: bump `IDENTITY_VERSION`,
regenerate this block in the same commit, and the anti-drift test stays green.
