"""Case Packager (Phase 6) — the decision-ready package, built ON the audit
trail.

The package is one deterministic JSON document per case holding everything a
human reviewer needs to decide: the subject and its anomalies, the recidivism
view from the persistent case graph, the full bounded-decision trace, the
grounded SAR draft (or the human-referral disposition), the Critic's grade,
the advisory basis, the drafted RFI follow-up — and an **audit reference
block** that pins the package to the tamper-evident chain.

Two structural rules keep the package honest:

* **References, never re-derivations.** The audit block lists each chain
  record as ``(seq, actor, action, hash)`` plus the tip hash and the
  verification result, captured *before* the ``packaged`` stamp — the chain
  then stamps the package file's SHA-256, so the log covers the package and
  the package pins the log, with no self-reference.
* **Deterministic bytes.** The document is serialized with sorted keys and
  ASCII-only; it contains no wall-clock values of its own (audit hashes carry
  the run's timestamps, so package bytes are reproducible exactly when the
  audit clock is injected — regression-tested).

Calibrated language: the package is *assembled for human review and
decision*. Nothing in it files, closes, or determines anything.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

PACKAGE_VERSION = "1.0.0"

# The red-herring policy line, verbatim in every package whose subject
# carries an internal tag: the tag is evidence to weigh, never an instruction
# to follow.
INTERNAL_TAG_POLICY = (
    "internal/privileged account tag FLAGGED for human review, never obeyed; "
    "it does not exempt the subject from scrutiny and played no role in the "
    "disposition"
)


def _advisory_ref(match: Any) -> Optional[dict]:
    if match is None:
        return None
    return {"advisory_id": match.advisory_id, "title": getattr(match, "title", None)}


def build_package(state: Mapping[str, Any], audit_records: list[dict],
                  audit_verified: bool) -> dict:
    """Assemble the decision-ready package from a completed case state.

    ``state`` is the orchestrator's case state (read-only here); the audit
    records and verification result are passed explicitly because they must
    be captured *before* the ``packaged`` stamp is appended.
    """
    profile = state["profile"]
    recidivism = state.get("recidivism")
    decisions = state.get("decisions", [])
    sar = state.get("sar")
    history = state.get("critique_history")
    followup = state.get("rfi_followup")
    risk = state["risk"]

    sar_bar = next((d for d in decisions if d.decision_id == "sar_bar"), None)
    disposition = "insufficient_evidence" if sar is None else sar_bar.outcome
    disposition_rationale = (
        sar_bar.rationale if sar is not None and sar_bar is not None
        else "the evidence-sufficiency gate referred the case to a human "
             "investigator; no draft was attempted"
    )

    package: dict = {
        "package_version": PACKAGE_VERSION,
        "readme": (
            "Decision-ready case package assembled by Okojo (synthetic-data "
            "research prototype) for HUMAN review and decision. Nothing here "
            "is filed, determined, or final. Every audit reference below "
            "resolves into the tamper-evident hash chain in audit_log.jsonl."
        ),
        "subject": {
            "uid": state["subject_uid"],
            "name": state["subject_name"],
            "entity_type": profile.entity_type,
            "residence_country": profile.residence_country,
            "account_status": profile.account_status,
            "prior_review_count": profile.prior_review_count,
            "anomaly_codes": sorted(profile.anomaly_codes()),
            "timeline_events": len(profile.events),
        },
        "red_herring": None,
        "recidivism": None,
        "disposition": disposition,
        "disposition_rationale": disposition_rationale,
        "decision_trace": [d.summary() for d in decisions],
        "network": {
            "accounts_reached": len(state["expansion"].reached_account_uids),
            "sanctioned_addresses_reached":
                list(state["expansion"].sanctioned_addresses_reached),
            "sanctioned_exposed_accounts":
                list(state["expansion"].sanctioned_exposed_uids),
            "gas_funding_links": len(state["expansion"].gas_funding_links),
        },
        "risk_summary": risk.summary(),
        "tells": len(state.get("tells") or []),
        "watchlist_alias_hits": len(state.get("alias_hits") or []),
        "advisory": {
            "primary": _advisory_ref(state.get("advisory")),
            "secondary_surfaced": _advisory_ref(state.get("secondary_advisory")),
            "note": "the SAR draft consumes the primary match alone; a "
                    "surfaced runner-up is analyst context, never a second "
                    "narrative source",
        },
        "rfi_followup": None,
        "sar_draft": None,
        "critic": None,
        "audit": {
            "log": "audit_log.jsonl",
            "verified": audit_verified,
            "tip_hash": audit_records[-1]["hash"],
            "record_count": len(audit_records),
            "records": [
                {"seq": r["seq"], "actor": r["actor"], "action": r["action"],
                 "hash": r["hash"]}
                for r in audit_records
            ],
        },
    }

    tag = profile.internal_tag
    if tag:
        package["red_herring"] = {
            "internal_tag": str(tag),
            "policy": INTERNAL_TAG_POLICY,
            "anomaly_code": "internal_account_tag",
        }

    if recidivism is not None:
        package["recidivism"] = {
            **recidivism.summary(),
            "overlaps": [o.model_dump() for o in recidivism.entity_overlaps],
            "note": "surfaced for human review at case open; prior cleared "
                    "reviews do not exempt a subject",
        }

    if followup is not None:
        package["rfi_followup"] = {
            "rfi_id": followup.rfi_id,
            "note": "drafted and proposed to the human investigator, never sent",
            "questions": [q.model_dump() for q in followup.questions],
        }

    if sar is not None:
        package["sar_draft"] = {
            "disclaimer": sar.disclaimer,
            "filing_note": sar.filing_note,
            "claims": [
                {"element": c.element, "statement": c.statement,
                 "citations": c.citations()}
                for c in sar.claims
            ],
        }
    if history is not None:
        final = history.final
        package["critic"] = {
            "coverage": round(final.coverage, 3),
            "meets_bar": final.meets_bar(),
            "converged": history.converged,
            "revision_passes": len(history.revisions),
            "flagged_for_human": list(history.flagged),
        }

    return package
