# Case-Packager Methodology (v1.0.0)

**Status:** synthetic-data research prototype. This document explains how
Okojo assembles the decision-ready case package, why the package can be
trusted to reflect the run that produced it, and exactly which policy version
produced any given package. It is the seventh doc↔code anti-drift pair,
alongside scoring, retrieval, critic, contradiction, agency, and casegraph.

## What the package is

One deterministic JSON document per case, assembled **for human review and
decision** — nothing in it files, closes, or determines anything. It holds
the subject summary, the recidivism view from the persistent case graph, the
full bounded-decision trace, the grounded SAR draft (or the human-referral
disposition), the Critic's grade, the advisory basis, the drafted RFI
follow-up worklist, and the audit reference block described below.

## Built ON the audit trail, not beside it

The package and the tamper-evident chain pin each other, with no
self-reference:

1. Every chain record is referenced in the package as
   `(seq, actor, action, hash)`, together with the tip hash and the
   verification result — captured **before** the `packaged` stamp is
   appended.
2. The chain then appends the `packaged` stamp, whose detail carries the
   package **file's SHA-256**.

The log covers the package; the package pins the log. Tampering with either
is visible from the other.

## The red herring, preserved as evidence

When the subject carries an internal/privileged "do-not-block" tag, the
package embeds the tag verbatim together with the policy line stating it was
**flagged for human review, never obeyed** — and the disposition rationale is
always the recorded `sar_bar` decision (or the human-referral note), so a
test can and does pin that no disposition ever cites the tag.

## Determinism

Package bytes are reproducible exactly: sorted keys, ASCII-only, no
wall-clock values of the package's own (the audit references carry the run's
timestamps), and files written with `\n` newlines so the recorded SHA-256
equals the on-disk bytes on every platform. Regression-tested under an
injected audit clock.

## Versioning — why this config is not a seventh audit stamp

The six other capability configs stamp themselves into the audit chain once
per run. The packaging policy is pinned through the **artifact itself**
instead: every package embeds `package_version`, and the chain's `packaged`
stamp carries the package file's SHA-256 — so each audited run already fixes
the exact packaging policy it ran under, without a second stamp. The
canonical policy for this version is below; it is the single source of truth
(`okojo.packager.packager_config`) and is regression-tested against this
document, so the doc and the code can never silently drift.

**Version 1.0.0 — canonical policy:**

<!-- packager-config:begin -->
```json
{
  "version": "1.0.0",
  "internal_tag_policy": "internal/privileged account tag FLAGGED for human review, never obeyed; it does not exempt the subject from scrutiny and played no role in the disposition",
  "audit_reference": "each chain record referenced as (seq, actor, action, hash) plus tip hash and verification result, captured BEFORE the packaged stamp; the stamp then carries the package file's SHA-256",
  "determinism": "sorted keys; ASCII-only; no wall-clock values of its own; bytes reproducible exactly under an injected audit clock",
  "disposition": "the recorded sar_bar decision outcome, or insufficient_evidence on the human-referral path; never derived from an internal tag"
}
```
<!-- packager-config:end -->

Bump `version` whenever the package schema, the audit-reference structure,
the determinism rules, or the internal-tag policy changes; already-emitted
packages remain interpretable under the version they embed.
