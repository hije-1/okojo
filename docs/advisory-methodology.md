# Advisory-Matching Methodology (v1.0.0)

**Status:** synthetic-data research prototype. This document explains *how* Okojo
decides that a case matches a FinCEN advisory, *why* the corroboration gate exists,
and *where* every dial sits. It is written for an investigator, a model-risk
reviewer, and an external auditor alike. It is the companion to
`docs/scoring-methodology.md`.

Two principles govern everything below:

1. **A topical hit is not a match.** Advisories are written in broad language, so a
   keyword or a paraphrase alone is noisy. Okojo *surfaces* an advisory only when a
   topical signal is **corroborated** by independent structured case evidence. The
   corroborators are the artifact; the match is a transparent consequence of them.
2. **These are tunable policy parameters, not universal truths.** The threshold and
   rule here are defensible defaults for the synthetic scenario; a deploying
   institution would recalibrate against its own data. They are version-stamped (see
   §5) and stamped into the tamper-evident audit trail, so any historical match is
   reproducible.

Okojo prepares evidence for a human reviewer. It does not screen, advise, or file.

---

## 1. The three signals

For each advisory, the matcher runs three independent passes over the case
documents (currently the subject's RFI response text) and the shared entity backbone.

1. **Keyword / regex.** The advisory's published *trigger terms* matched over the
   case text (word-boundary for alphanumeric terms, substring otherwise). This is
   the advisory's own vocabulary — the strongest *topical* signal.
2. **Semantic.** Each numbered red-flag indicator (`RF-*`) is embedded; each case
   document is embedded and queried against them by exact cosine similarity. A hit
   at or above the semantic threshold becomes a `SemanticIndicator` mapped to the
   specific `RF-*` it resembles — so a paraphrase that shares no trigger word still
   maps to the indicator it matches.
3. **Structured.** Advisory-named attributes checked against the shared
   `EntityBackbone` and the case's screening/exposure facts, yielding
   *corroborators* of three kinds:
   - **jurisdiction** — a case entity sits in a jurisdiction the advisory names
     (the backbone's residence + nationality + KYC-issuing country);
   - **watchlist** — an account name resembles a synthetic watchlist alias;
   - **sanctioned_exposure** — the case has on-chain exposure to the synthetic
     sanctioned set.

Every asserted fact carries a provenance pointer (the grounding contract): keyword
document provenances, semantic document provenances, and corroborator provenances,
all deduped.

## 2. The corroboration rule (the primary false-positive control)

> **Surface an advisory only when a primary hit (keyword **or** semantic) is
> corroborated by ≥ 1 structured corroborator.**

When structured case evidence is supplied (always, in the running pipeline), a
topical hit with no corroborator is **suppressed**. Without structured context
(isolated/unit calls) the matcher degrades to keyword surfacing and never fabricates
a corroborator it does not have.

**Tuning basis — an FP-rate ablation, not a magic number.** The gate is justified by
running the eval **with and without** the structured-corroborator requirement on a
committed gold key of positives and decoys (`tests/data/advisory_gold.json`,
`tests/test_advisory_eval.py`). With the gate **on**, the topical-but-innocent oil
decoys (a licensed commodities trader; a domestic petrochemical supplier) are
correctly suppressed — false-positive rate **0/6**. With the gate **off**, those same
decoys reappear as false positives. The gate is *what removes them*.

## 3. The semantic threshold

`semantic_threshold = 0.22`. Calibrated on the crafted gold set the same way
`SCREEN_THRESHOLD = 85` is: the value that cleanly separates planted true red-flag
paraphrases from decoys. **This value and the observed separation are
embedder-dependent.**

- The number **0.22** was calibrated for, and the CI scorecards are produced by, the
  **deterministic lexical fallback embedder** (`lexical-fallback-v1`) — a
  dependency-free hashed word-overlap proxy, **not** a neural semantic model. On the
  gold set the fallback's true red-flag paraphrases score ~0.24–0.30 while off-topic
  decoys sit ~0.15–0.19, so 0.22 sits in the gap. This is an **honest-metrics**
  disclosure: the reported separation is lexical resemblance, not learned semantics.
- The intended production embedder is the local **`sentence-transformers/
  all-MiniLM-L6-v2`** model (offline, no secrets — see §4). When it is installed it
  supersedes the fallback, and **the threshold should be re-calibrated** against the
  same gold set with that model; the cosine geometry differs. Record the recalibrated
  value here together with the embedder name.

Because the corroboration gate is the primary false-positive control, the exact
threshold is a secondary dial: even a permissive threshold is checked by the
requirement for independent structured corroboration.

## 4. Stack rationale (right-sized, offline, no secrets)

- **Exact brute-force cosine, no vector DB.** The corpus is tiny (a handful of
  advisories, each a few dozen terms + ~15 red-flag indicators = dozens to
  low-hundreds of chunks). At that scale an exact in-memory cosine is *exact*, fully
  deterministic, and adds no DB/persistence/secrets. A vector DB (FAISS/Chroma) adds
  weight for no benefit here, and Chroma's default approximate (HNSW) search would
  undercut determinism.
- **Local embedding model, never an API.** A local model keeps offline / no-secrets /
  deterministic intact; an embeddings API would introduce the project's first secret,
  network dependency, and server-side reproducibility risk. Offline-no-external-calls
  is itself a compliance/privacy property.
- **Upgrade path behind one interface.** Both the embedder and the similarity search
  sit behind small swappable seams (`okojo.advisory.embeddings.Embedder`,
  `okojo.advisory.retrieval.CosineRetriever`). If the corpus ever grows, swapping in
  FAISS `IndexFlatIP` — or a different embedding backend — is an isolated change that
  never touches call sites.

## 5. What discriminates the *right* advisory among several

Okojo carries four advisories (Iran illicit oil, Russia sanctions evasion, fentanyl
precursors, DPRK). `match_advisories` matches each independently and returns the
survivors ranked best-first; the pipeline takes the top one. Two honest points:

- **Jurisdiction is the advisory-discriminating corroborator.** The **watchlist** and
  **sanctioned_exposure** corroborators are advisory-*agnostic* sanctions-relevance
  signals — they say "this case is sanctions-relevant", not "this case matches *this*
  advisory". The **jurisdiction** corroborator (does the advisory name a jurisdiction
  the case sits in?) is what ties a case to a specific advisory, alongside the
  specificity of the trigger terms / red flags.
- **Best-of ranking breaks ties.** When two advisories both fire, the ranking prefers
  more independent signal types, then more published trigger terms, then more
  structured corroborators, then stronger semantic scores, then the advisory id
  (stable). On the gold discrimination set this routes all six positives to the
  correct advisory and surfaces none of the six decoys (**12/12**).

## 6. Reproducibility & versioning

Every run stamps its retrieval configuration into the tamper-evident audit trail
(`advisory_matcher / retrieval_config`) plus the actually-active embedder
(`advisory_matcher / embedder_active`), so any historical match can be reproduced
from the record. The canonical parameter set for this version is below; it is the
single source of truth (`okojo.advisory.retrieval_config`) and is regression-tested
against this document, so the doc and the code can never silently drift.

**Version 1.0.0 — canonical parameters:**

<!-- advisory-config:begin -->
```json
{
  "version": "1.0.0",
  "embedder": "sentence-transformers/all-MiniLM-L6-v2",
  "embedder_fallback": "lexical-fallback-v1",
  "semantic_threshold": 0.22,
  "top_k": 3,
  "corroboration_rule": "primary_hit(keyword OR semantic) AND >=1 structured corroborator",
  "jurisdictions_source": "shared EntityBackbone (residence + nationality + KYC-issuing country)"
}
```
<!-- advisory-config:end -->

Bump `version` whenever a parameter, the corroboration rule, or the ranking changes;
already-audited matches remain reproducible under the version they were computed with.

---

*All data referenced here is synthetic (Okojo's seeded generator) or public (FinCEN
advisory red-flag typologies, OFAC SDN structure). No real identities, addresses, or
documents are used. This prototype prepares evidence for a human reviewer; it does not
screen, advise, or file.*
