"""Audit Narrator — a grounded, read-only summarizer over the hash chain.

The audit trail is Okojo's centerpiece control: tamper-evident and *provable*.
This module makes it *reviewable* — it reads a chain and produces a
plain-language narrative of what the agent did, in order, and why. Three
disciplines carry over from the rest of the system, unchanged:

* **Grounding contract.** One narrative sentence per record (1:1), and every
  sentence cites the exact record it reads by ``(seq, hash)``. Validation is
  fail-closed: a sentence whose citation does not resolve to a real record in
  the verified chain is rejected (:func:`assert_narrative_grounded`), the same
  "no receipt, no claim" rule the SAR drafter enforces.
* **Calibrated language.** Narrator output is screened with the SAR drafter's
  *exact* ``BANNED_TERMS`` tuple (:func:`assert_calibrated`); it narrates what
  was recorded ("stamped / drafted / proposed / flagged"), never more.
* **Verify first.** The chain is verified before anything is narrated. A chain
  that fails verification IS the narrative: the break is located and cited, the
  count that verified before it is stated, and content at or beyond the break is
  never summarized (it cannot be trusted).

Deterministic by construction: a ``(actor, action) -> sentence`` template map,
no LLM. A template is a faithful 1:1 reading of a record, so the narrative is
byte-deterministic per chain and the eval holds. The narrator writes NOTHING to
any chain; its version is pinned through the narrative artifact (like
``packager_config``), never stamped into a chain.

Scope: this slice ships the CASE-family templates. Records without a
family-specific template still narrate faithfully via a generic reading, so
coverage is additive and does not itself move the version.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional, Union

from ..audit.log import verify_records
from ..sar.schema import BANNED_TERMS, CalibrationViolationError

NARRATOR_VERSION = "1.0.0"

RecordSource = Union[str, Path, Iterable[dict]]


# --------------------------------------------------------------------------- #
# Artifact types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RecordRef:
    """A pointer to the chain record a sentence reads: its seq and hash."""

    seq: int
    hash: str

    def cite(self) -> str:
        return f"record#{self.seq}@{self.hash[:12]}"


@dataclass(frozen=True)
class NarrativeSentence:
    """One plain-language sentence bound to the record it narrates.

    ``register`` is ``"action"`` for a consequential step, ``"setup"`` for a
    de-emphasized provenance record (tool-call / policy stamp), or ``"break"``
    for the single sentence of a failed-verification report. ``templated`` is
    ``False`` when the generic reading was used (no family-specific template).
    """

    ref: RecordRef
    register: str
    text: str
    templated: bool = True

    def cited(self) -> str:
        return f"{self.text}  (source: {self.ref.cite()})"


@dataclass(frozen=True)
class AuditChainNarrative:
    """A narrative over one chain: two-register output + per-sentence provenance."""

    family: str                 # "case" | "sweep" | "batch"
    subject: Optional[str]      # e.g. "uid:500000003" or a designation id
    verified: bool
    record_count: int
    sentences: list[NarrativeSentence]
    narrator_version: str = NARRATOR_VERSION

    def plain(self) -> str:
        """Screen register: the sentences, in order (setup lines de-emphasized)."""
        lines = []
        for s in self.sentences:
            prefix = "  · " if s.register == "setup" else "- "
            lines.append(f"{prefix}{s.text}")
        return "\n".join(lines)

    def provenance(self) -> list[str]:
        """The record citations behind each sentence, in order."""
        return [s.ref.cite() for s in self.sentences]

    def cited(self) -> str:
        """Both registers combined: each sentence with its citation."""
        return "\n".join(s.cited() for s in self.sentences)


@dataclass(frozen=True)
class AuditBatchNarrative:
    """A narrative over a whole list drop: N constituent sweep-chain narratives
    plus a roll-up.

    A batch owns no chain of its own — it is N independent sweep chains plus a
    derived, non-chained ``rollup`` dict (a view, never a grounding source). So
    the batch narrative is exactly: each constituent chain narrated on its own
    terms (``chain_narratives``, break-report-only where one fails verification),
    and a ``rollup`` narrative whose every sentence is grounded to a REAL record
    in a constituent chain — the terminal ``sweep_complete`` of a verified chain,
    or the break-position record of a broken one. Nothing is read from the
    non-chained ``rollup`` dict; nothing past a break is summarized.
    """

    designation_count: int
    chain_narratives: list[AuditChainNarrative]
    rollup: AuditChainNarrative           # family="batch"; grounded to constituent records
    narrator_version: str = NARRATOR_VERSION

    def plain(self) -> str:
        """The roll-up first, then each constituent chain in order."""
        blocks = [f"Batch roll-up over {self.designation_count} designation(s):",
                  self.rollup.plain(), "", "Per-designation chains:"]
        for nar in self.chain_narratives:
            blocks.append(f"[{nar.subject or 'sweep'}]")
            blocks.append(nar.plain())
        return "\n".join(blocks)

    def provenance(self) -> list[str]:
        """The record citations behind each roll-up sentence, in order."""
        return self.rollup.provenance()


# --------------------------------------------------------------------------- #
# Grounding + calibration (fail-closed, over narrator output)
# --------------------------------------------------------------------------- #
class NarrativeGroundingError(ValueError):
    """Raised when a narrative sentence cites a record not in the chain."""


class NarrativeGroundingResolver:
    """Membership over a chain's own ``(seq, hash)`` pairs (the narrator's
    analogue of the SAR ``GroundingResolver``, but over records not rows)."""

    def __init__(self, records: Iterable[dict]):
        self._valid = {(int(r["seq"]), str(r["hash"])) for r in records}

    def resolves(self, ref: RecordRef) -> bool:
        return (ref.seq, ref.hash) in self._valid


def assert_narrative_grounded(narrative: AuditChainNarrative, records: Iterable[dict]) -> None:
    """Fail closed if any sentence cites a record absent from the chain."""
    resolver = NarrativeGroundingResolver(records)
    bad = [s for s in narrative.sentences if not resolver.resolves(s.ref)]
    if bad:
        raise NarrativeGroundingError(
            f"{len(bad)} narrative sentence(s) cite a record not in the chain: "
            + " | ".join(f"{s.ref.cite()} :: {s.text}" for s in bad)
        )


def assert_calibrated(narrative: AuditChainNarrative) -> None:
    """Fail closed if any sentence uses over-claiming language (SAR BANNED_TERMS)."""
    bad = [s.text for s in narrative.sentences
           if any(term in s.text.lower() for term in BANNED_TERMS)]
    if bad:
        raise CalibrationViolationError(
            f"{len(bad)} narrative sentence(s) use over-claiming language "
            f"(banned: {', '.join(BANNED_TERMS)}): " + " | ".join(bad)
        )


# --------------------------------------------------------------------------- #
# Detail helpers (deterministic, defensive)
# --------------------------------------------------------------------------- #
def _one_line(value) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _json_dict(detail) -> Optional[dict]:
    if not isinstance(detail, str):
        return None
    s = detail.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    try:
        v = json.loads(s)
    except (ValueError, TypeError):
        return None
    return v if isinstance(v, dict) else None


def _json_get(detail, key):
    d = _json_dict(detail)
    return d.get(key) if d else None


def _json_len(detail, key) -> int:
    """Count the members of a list/dict field in a JSON detail (0 if absent).

    A faithful reading of a record whose detail carries collections (matches,
    dispositions, gaps): the narrative reports *how many*, from the record's own
    payload — never from a derived view.
    """
    v = _json_get(detail, key)
    return len(v) if isinstance(v, (list, dict)) else 0


def _compact(detail) -> str:
    """A faithful, one-line rendering of a record's detail.

    A JSON detail is flattened to ``key=value`` over its scalar fields; a plain
    string is passed through collapsed to one line. Deterministic either way.
    """
    if not detail:
        return ""
    d = _json_dict(detail)
    if d is None:
        return _one_line(detail)
    parts = [f"{k}={v}" for k, v in d.items()
             if isinstance(v, (str, int, float, bool)) or v is None]
    return ", ".join(parts) if parts else _one_line(detail)


# --------------------------------------------------------------------------- #
# CASE-family template registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Template:
    register: str
    render: Callable[[dict], str]


def _period(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else text + "."


def _phrase(register: str, text: str, *, detail: bool = False,
            target: bool = False) -> _Template:
    def render(rec: dict) -> str:
        out = text
        if target and rec.get("target"):
            out = f"{out} ({rec['target']})"
        if detail:
            compact = _compact(rec.get("detail"))
            if compact:
                out = f"{out}: {compact}"
        return _period(out)
    return _Template(register, render)


def _tool(label: str) -> _Template:
    return _Template("setup", lambda rec: f"Invoked the {label} stage.")


def _config(label: str) -> _Template:
    def render(rec: dict) -> str:
        v = _json_get(rec.get("detail"), "version")
        suffix = f" (v{v})" if v else ""
        return f"Stamped the {label} into the record{suffix}."
    return _Template("setup", render)


def _decision_render(rec: dict) -> str:
    d = _json_dict(rec.get("detail")) or {}
    did = rec.get("target") or d.get("decision_id") or "decision"
    plain = d.get("plain_language")
    if plain:
        return _period(f"Recorded the bounded decision '{did}': {_one_line(plain)}")
    outcome = d.get("outcome")
    if outcome:
        return _period(f"Recorded the bounded decision '{did}': proposed {outcome}")
    return f"Recorded the bounded decision '{did}'."


def _packaged_render(rec: dict) -> str:
    d = _json_dict(rec.get("detail")) or {}
    tgt = rec.get("target") or d.get("package") or "the package"
    disp = d.get("disposition")
    sha = d.get("sha256") or ""
    out = f"Assembled the decision-ready package ({tgt}) for human review"
    if disp:
        out = f"{out}; disposition {disp}"
    out = _period(out)
    if sha:
        out = f"{out} The chain stamps its SHA-256 ({sha[:12]}…)."
    return out


CASE_TEMPLATES: dict[tuple, _Template] = {
    ("orchestrator", "case_open"): _Template(
        "action",
        lambda r: _period(
            f"Opened the case for {_one_line(r.get('detail')) or 'the subject'}"
            f" ({r.get('target')})"
        ),
    ),
    ("orchestrator", "human_referral"): _phrase(
        "action", "Referred the case to a human investigator", detail=True, target=True),
    ("agency", "agency_config"): _config("agency decision policy"),
    ("agency", "decision"): _Template("action", _decision_render),
    ("agency", "rfi_followup_drafted"): _phrase(
        "action", "Drafted a follow-up RFI (never sent)", detail=True, target=True),
    ("case_graph", "casegraph_config"): _config("case-graph policy"),
    ("case_graph", "recidivism_flagged"): _phrase(
        "action", "Flagged the subject for human review — prior cleared reviews surfaced",
        detail=True, target=True),
    ("case_graph", "history_clear"): _phrase(
        "action", "Recorded a clear case-graph history for the subject",
        detail=True, target=True),
    ("case_graph", "case_recorded"): _phrase(
        "action", "Recorded the case in the persistent case graph", detail=True, target=True),
    ("profile_aggregator", "tool_call"): _tool("profile aggregator"),
    ("profile_aggregator", "profile_built"): _phrase(
        "action", "Built the subject profile", detail=True),
    ("network_expander", "tool_call"): _tool("network expander"),
    ("network_expander", "expanded"): _phrase(
        "action", "Expanded the network", detail=True),
    ("network_expander", "graph_render_failed"): _phrase(
        "action", "The network-graph render failed and was recorded; the pipeline continued",
        detail=True),
    ("network_expander", "graph_rendered"): _phrase(
        "setup", "Rendered the network graph", target=True),
    ("risk_scorer", "tool_call"): _tool("risk scorer"),
    ("risk_scorer", "scoring_config"): _config("on-chain scoring policy"),
    ("risk_scorer", "scored"): _phrase("action", "Scored on-chain risk", detail=True),
    ("designation_check", "screened"): _phrase(
        "action", "Screened the subject and cluster against every designation",
        detail=True, target=True),
    ("remark_miner", "tool_call"): _tool("remark miner"),
    ("remark_miner", "mined"): _phrase("action", "Mined remark tells", detail=True),
    ("remark_miner", "alias_screened"): _phrase(
        "action", "Screened names against the watchlist", detail=True),
    ("advisory_matcher", "tool_call"): _tool("advisory matcher"),
    ("advisory_matcher", "retrieval_config"): _config("advisory-retrieval policy"),
    ("advisory_matcher", "embedder_active"): _phrase(
        "setup", "Recorded the active advisory embedder", detail=True),
    ("advisory_matcher", "matched"): _phrase(
        "action", "Matched a regulatory advisory", detail=True),
    ("advisory_matcher", "secondary_surfaced"): _phrase(
        "action", "Surfaced a secondary advisory for analyst context", detail=True),
    ("rfi_reader", "rfi_surfaced"): _phrase(
        "action", "Surfaced the RFI", detail=True, target=True),
    ("rfi_checker", "tool_call"): _tool("RFI checker"),
    ("rfi_checker", "contradiction_config"): _config("RFI contradiction policy"),
    ("rfi_checker", "decomposed"): _phrase(
        "action", "Decomposed the RFI response into discrete claims", detail=True, target=True),
    ("rfi_checker", "adjudicated"): _phrase(
        "action", "Adjudicated the RFI claims", detail=True, target=True),
    ("rfi_checker", "claim_verdict"): _phrase(
        "action", "Recorded an RFI claim verdict", detail=True, target=True),
    ("sar_drafter", "tool_call"): _tool("SAR drafter"),
    ("sar_drafter", "grounding_validated"): _phrase(
        "action", "Validated SAR grounding", detail=True, target=True),
    ("sar_drafter", "drafted"): _phrase(
        "action", "Drafted the SAR narrative", detail=True, target=True),
    ("sar_critic", "critic_config"): _config("SAR critic policy"),
    ("sar_critic", "graded"): _phrase(
        "action", "Graded the draft against the FinCEN rubric", detail=True, target=True),
    ("sar_critic", "revision"): _phrase(
        "action", "Revised the draft to close rubric gaps", detail=True, target=True),
    ("sar_critic", "converged"): _phrase(
        "action", "The revision loop converged", detail=True, target=True),
    ("sar_critic", "human_fallback"): _phrase(
        "action", "Flagged residual gaps for human review", detail=True, target=True),
    ("case_packager", "packaged"): _Template("action", _packaged_render),
}

# --------------------------------------------------------------------------- #
# SWEEP-family template registry
#
# The Designation-Triggered Remediation Sweep writes its own hash-chained trail
# over two actors — ``remediation_sweep`` (the sweep engine) and
# ``sweep_packager`` — with 19 actions. Each template is a faithful 1:1 reading
# of the record's own detail: it reports the counts and identifiers the record
# actually carries, and nothing more. Setup register for the three versioned
# policy stamps (``sweep_config`` / ``identity_config`` / ``geo_config``); the
# action register for every consequential step.
# --------------------------------------------------------------------------- #
def _sweep_open_render(rec: dict) -> str:
    d = _json_dict(rec.get("detail")) or {}
    name = d.get("designated_name") or "the designated party"
    out = f"Opened the remediation sweep for {_one_line(name)} ({rec.get('target')})"
    lt = d.get("list_type")
    if lt:
        out = f"{out}; list type {lt}"
    return _period(out)


def _name_screen_render(rec: dict) -> str:
    nd = _json_len(rec.get("detail"), "matches")
    nv = _json_len(rec.get("detail"), "variant_matches")
    return _period(
        f"Screened registered account names against the designated name: "
        f"{nd} direct match(es), {nv} variant match(es)")


def _corroboration_render(rec: dict) -> str:
    d = _json_dict(rec.get("detail")) or {}
    tgt = rec.get("target") or "the candidate"
    plain = d.get("plain_language")
    if plain:
        return _period(f"Recorded a corroboration decision for {tgt}: {_one_line(plain)}")
    outcome = d.get("outcome")
    if outcome:
        return _period(f"Recorded a corroboration decision for {tgt}: {outcome}")
    return _period(f"Recorded a corroboration decision for {tgt}")


def _ownership_render(rec: dict) -> str:
    d = rec.get("detail")
    return _period(
        f"Walked beneficial ownership from the resolved parties: "
        f"{_json_len(d, 'propagations')} ownership propagation(s), "
        f"{_json_len(d, 'fictitious_executives')} fictitious officer(s), "
        f"{_json_len(d, 'post_designation_control_changes')} post-designation "
        f"control change(s) (review-only, no flow exposure)")


def _exposure_render(rec: dict) -> str:
    d = rec.get("detail")
    return _period(
        f"Swept the ledger for exposure from the designated addresses: "
        f"{_json_len(d, 'direct_uids')} directly exposed account(s), "
        f"{_json_len(d, 'adjacent_review_only_uids')} adjacent review-only account(s)")


def _proximity_render(rec: dict) -> str:
    return _period(
        f"Surfaced a proximity ring of {_json_len(rec.get('detail'), 'members')} "
        f"review-tier associate(s) (correlational signals, no kinship asserted, "
        f"no exposure)")


def _geo_triangulation_render(rec: dict) -> str:
    d = _json_dict(rec.get("detail")) or {}
    terr = d.get("territory") or "the territory"
    ns = _json_len(rec.get("detail"), "surfaced")
    return _period(
        f"Triangulated location signals over {_one_line(terr)}: {ns} account(s) "
        f"surfaced for review (signals indicate possible presence, never prove it)")


def _geo_proposal_render(rec: dict) -> str:
    return _period(
        f"Proposed {_json_len(rec.get('detail'), 'proposals')} review-tier geo "
        f"action(s) for a human (proposed, never executed; any RFI drafted, never sent)")


def _cp_notification_render(rec: dict) -> str:
    d = rec.get("detail")
    return _period(
        f"Drafted {_json_len(d, 'drafted')} subject-facing counterparty "
        f"notification(s) (never sent), {_json_len(d, 'suppressed')} suppressed")


def _cp_lifecycle_render(rec: dict) -> str:
    return _period(
        f"Recorded {_json_len(rec.get('detail'), 'dispositions')} counterparty "
        f"relationship disposition(s) for human review (no hold status mutated; "
        f"unblock exists only as a proposal)")


def _block_verify_render(rec: dict) -> str:
    d = _json_dict(rec.get("detail")) or {}
    nr = d.get("accounts_reconciled") or 0
    return _period(
        f"Reconciled hold status across two systems: {nr} account(s) reconciled, "
        f"{_json_len(rec.get('detail'), 'gaps')} gap(s) found")


def _worksheet_render(rec: dict) -> str:
    d = _json_dict(rec.get("detail")) or {}
    nr = d.get("rows") or 0
    return _period(f"Built the grounded remediation worksheet: {nr} row(s)")


def _escalations_render(rec: dict) -> str:
    d = rec.get("detail")
    return _period(
        f"Drafted {_json_len(d, 'drafted')} internal escalation(s) (never sent), "
        f"{_json_len(d, 'suppressed')} suppressed")


def _identity_rfi_render(rec: dict) -> str:
    d = rec.get("detail")
    return _period(
        f"Drafted {_json_len(d, 'drafted')} subject-facing identity-review RFI(s) "
        f"(never sent), {_json_len(d, 'suppressed')} suppressed")


def _sweep_complete_render(rec: dict) -> str:
    d = _json_dict(rec.get("detail")) or {}
    ex = d.get("exposed_accounts") or 0
    nm = d.get("name_matches") or 0
    wr = d.get("worksheet_rows") or 0
    return _period(
        f"Completed the sweep: {ex} exposed account(s), {nm} name match(es), "
        f"{wr} worksheet row(s); results surfaced for human remediation, no status changed")


def _sweep_packaged_render(rec: dict) -> str:
    d = _json_dict(rec.get("detail")) or {}
    tgt = rec.get("target") or d.get("package") or "the package"
    ex = d.get("exposed_accounts")
    sha = d.get("sha256") or ""
    out = f"Assembled the decision-ready remediation package ({tgt}) for human review"
    if ex is not None:
        out = f"{out}; {ex} exposed account(s)"
    out = _period(out)
    if sha:
        out = f"{out} The chain stamps its SHA-256 ({sha[:12]}…)."
    return out


SWEEP_TEMPLATES: dict[tuple, _Template] = {
    ("remediation_sweep", "sweep_open"): _Template("action", _sweep_open_render),
    ("remediation_sweep", "sweep_config"): _config("sweep policy"),
    ("remediation_sweep", "identity_config"): _config("identity-resolution policy"),
    ("remediation_sweep", "name_screen"): _Template("action", _name_screen_render),
    ("remediation_sweep", "corroboration_decision"): _Template("action", _corroboration_render),
    ("remediation_sweep", "ownership_walk"): _Template("action", _ownership_render),
    ("remediation_sweep", "exposure_sweep"): _Template("action", _exposure_render),
    ("remediation_sweep", "proximity_ring"): _Template("action", _proximity_render),
    ("remediation_sweep", "geo_config"): _config("geo-triangulation policy"),
    ("remediation_sweep", "geo_triangulation"): _Template("action", _geo_triangulation_render),
    ("remediation_sweep", "geo_proposal"): _Template("action", _geo_proposal_render),
    ("remediation_sweep", "counterparty_notification"): _Template("action", _cp_notification_render),
    ("remediation_sweep", "counterparty_lifecycle"): _Template("action", _cp_lifecycle_render),
    ("remediation_sweep", "block_verify"): _Template("action", _block_verify_render),
    ("remediation_sweep", "worksheet_build"): _Template("action", _worksheet_render),
    ("remediation_sweep", "escalations_draft"): _Template("action", _escalations_render),
    ("remediation_sweep", "identity_review_rfi"): _Template("action", _identity_rfi_render),
    ("remediation_sweep", "sweep_complete"): _Template("action", _sweep_complete_render),
    ("sweep_packager", "packaged"): _Template("action", _sweep_packaged_render),
}

_TEMPLATES: dict[str, dict[tuple, _Template]] = {
    "case": CASE_TEMPLATES,
    "sweep": SWEEP_TEMPLATES,
}


def _is_setup(action: str) -> bool:
    return (action == "tool_call" or action.endswith("_config")
            or action in ("embedder_active", "graph_rendered"))


def _fallback(rec: dict) -> str:
    actor = _one_line(rec.get("actor")).replace("_", " ")
    action = _one_line(rec.get("action")).replace("_", " ")
    out = f"The {actor} recorded {action}"
    if rec.get("target"):
        out = f"{out} for {rec['target']}"
    compact = _compact(rec.get("detail"))
    if compact:
        out = f"{out}: {compact}"
    return _period(out)


def _narrate_record(rec: dict, family: str) -> NarrativeSentence:
    ref = RecordRef(seq=int(rec["seq"]), hash=str(rec["hash"]))
    tmpl = _TEMPLATES.get(family, {}).get((rec.get("actor"), rec.get("action")))
    if tmpl is not None:
        return NarrativeSentence(ref=ref, register=tmpl.register,
                                 text=tmpl.render(rec), templated=True)
    register = "setup" if _is_setup(rec.get("action") or "") else "action"
    return NarrativeSentence(ref=ref, register=register, text=_fallback(rec),
                             templated=False)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def _load_records(source: RecordSource) -> list[dict]:
    if isinstance(source, (str, Path)):
        out: list[dict] = []
        with Path(source).open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(json.loads(line))
        return out
    return list(source)


def _break_report(records: list[dict], ver, family: str,
                  subject: Optional[str]) -> AuditChainNarrative:
    """The narrative for a chain that fails verification: the break, cited.

    Cites the record at the break *position* by its own stored ``(seq, hash)``
    (so the citation resolves against the chain as read), reports the count that
    verified before it, and summarizes nothing at or beyond the break.
    """
    idx = (ver.break_seq or 1) - 1
    broken = records[idx] if 0 <= idx < len(records) else None
    ref = (RecordRef(seq=int(broken["seq"]), hash=str(broken["hash"]))
           if broken is not None else RecordRef(seq=ver.break_seq or 0, hash=""))
    text = (
        f"Chain verification FAILED at record position #{ver.break_seq} "
        f"({ver.reason}); {ver.verified_count} record(s) verified before the break. "
        f"The narrative is withheld beyond this point: content at or past a broken "
        f"link cannot be trusted, and a human must inspect the record."
    )
    sentence = NarrativeSentence(ref=ref, register="break", text=text, templated=True)
    return AuditChainNarrative(family=family, subject=subject, verified=False,
                          record_count=len(records), sentences=[sentence])


def narrate_chain(source: RecordSource, *, family: str = "case",
                  subject: Optional[str] = None) -> AuditChainNarrative:
    """Read one audit chain and return its grounded, calibrated narrative.

    ``source`` is a path to an ``audit_log.jsonl`` or an already-read list of
    records. The chain is verified FIRST; on a break the narrative is the break
    report (:func:`_break_report`). Otherwise every record is narrated 1:1 and
    the result is validated fail-closed (grounding + calibration) before return.
    """
    records = _load_records(source)
    ver = verify_records(records)
    if not ver.ok:
        narrative = _break_report(records, ver, family, subject)
    else:
        sentences = [_narrate_record(rec, family) for rec in records]
        narrative = AuditChainNarrative(family=family, subject=subject, verified=True,
                                   record_count=len(records), sentences=sentences)
    assert_narrative_grounded(narrative, records)
    assert_calibrated(narrative)
    return narrative


def _find_record(records: list[dict], key: tuple) -> Optional[dict]:
    for r in records:
        if (r.get("actor"), r.get("action")) == key:
            return r
    return None


def _rollup_sentence(subject: Optional[str], records: list[dict],
                     nar: AuditChainNarrative) -> NarrativeSentence:
    """One roll-up line for a constituent sweep, grounded to a real record of it.

    A verified chain is summarized from the record it cites — the terminal
    ``sweep_complete`` (or ``packaged``) of that very chain, read for its own
    counts. A broken chain is NOT summarized: the line is a break report citing
    the break-position record, and it is excluded from the roll-up totals (Q2 —
    content past a break cannot be trusted).
    """
    label = subject or "the designation"
    if not nar.verified:
        ref = nar.sentences[0].ref
        return NarrativeSentence(
            ref=ref, register="break",
            text=_period(
                f"{label}: chain verification FAILED at record #{ref.seq}; excluded "
                f"from the roll-up — a human must inspect the record"))
    rec = (_find_record(records, ("remediation_sweep", "sweep_complete"))
           or _find_record(records, ("sweep_packager", "packaged"))
           or records[-1])
    d = _json_dict(rec.get("detail")) or {}
    parts = [f"{label}: sweep chain verified across {len(records)} record(s)"]
    if d.get("exposed_accounts") is not None:
        parts.append(f"{d['exposed_accounts']} exposed account(s)")
    if d.get("name_matches") is not None:
        parts.append(f"{d['name_matches']} name match(es)")
    ref = RecordRef(seq=int(rec["seq"]), hash=str(rec["hash"]))
    return NarrativeSentence(ref=ref, register="action", text=_period("; ".join(parts)))


def narrate_chain_batch(chains: Iterable[tuple[Optional[str], RecordSource]]) -> AuditBatchNarrative:
    """Narrate a whole list drop: each constituent sweep chain + a grounded roll-up.

    ``chains`` is an iterable of ``(subject, source)`` — one per swept
    designation, where ``source`` is a path or an already-read record list. Each
    constituent is narrated with :func:`narrate_chain` (family ``"sweep"``,
    break-report-only on a failed chain). The roll-up is one line per constituent,
    each grounded to a REAL record in that constituent's chain (never the derived
    ``rollup`` dict), then validated fail-closed (grounding + calibration) over the
    union of all constituent records before return.
    """
    items = [(subject, _load_records(source)) for subject, source in chains]
    chain_narratives = [narrate_chain(records, family="sweep", subject=subject)
                        for subject, records in items]
    rollup_sentences = [_rollup_sentence(subject, records, nar)
                        for (subject, records), nar in zip(items, chain_narratives)]
    all_records = [r for _, records in items for r in records]
    rollup = AuditChainNarrative(
        family="batch", subject=None,
        verified=all(nar.verified for nar in chain_narratives),
        record_count=len(all_records), sentences=rollup_sentences)
    # The roll-up grounds ONLY to constituent chain records (never the rollup view).
    assert_narrative_grounded(rollup, all_records)
    assert_calibrated(rollup)
    return AuditBatchNarrative(designation_count=len(items),
                          chain_narratives=chain_narratives, rollup=rollup)


# --------------------------------------------------------------------------- #
# Versioned policy (pinned through the artifact, doc<->code anti-drift guarded)
# --------------------------------------------------------------------------- #
def narrator_config() -> dict:
    """The versioned narration policy.

    Like ``packager_config``, this is pinned through the artifact — each
    narrative embeds ``narrator_version`` — and is never stamped into a chain
    (the narrator writes nothing). Regression-tested against the published
    methodology doc so the two cannot silently drift.
    """
    return {
        "version": NARRATOR_VERSION,
        "narration": (
            "one sentence per audit record (1:1), in the order recorded; setup "
            "records (tool_call, *_config, embedder_active, graph_rendered) render "
            "in a de-emphasized register, consequential actions in the action register"
        ),
        "determinism": (
            "a deterministic (actor, action) -> sentence template map; no LLM. A "
            "template is a faithful 1:1 reading of the record, so the narrative is "
            "byte-deterministic per chain and the eval holds"
        ),
        "grounding": (
            "every sentence cites the specific record it reads by (seq, hash); "
            "validation is fail-closed — a sentence whose citation does not resolve "
            "to a real record in the verified chain is rejected"
        ),
        "calibration": (
            "narrator output is screened with the SAR drafter's exact BANNED_TERMS "
            "tuple; over-claiming language is rejected"
        ),
        "verification": (
            "the chain is verified FIRST; a chain that fails verification is reported "
            "as the narrative itself (the break located and cited, the count that "
            "verified before it stated), and content at or beyond the break is never "
            "summarized"
        ),
        "read_only": (
            "the narrator writes NOTHING to any chain; its version is pinned through "
            "the narrative artifact (like packager_config), never stamped into a chain"
        ),
        "scope": (
            "all chain families (case, sweep, batch); records lacking a "
            "family-specific template still narrate faithfully via a generic reading, "
            "so template coverage is additive and does not itself move the version"
        ),
    }
