#!/usr/bin/env python3
"""Validate the execution record in a Doujiao evidence ledger.

The package validator owns JSON loading, company Schema validation and the
long-standing evidence/calculation gates.  This module deliberately has no
filesystem or network side effects: it validates the v2 execution record and
returns small, serialisable issues for the package validator to translate into
its own finding type.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence


LEDGER_VERSION = "2.0"
LEDGER_ROOT_KEYS = {
    "ledger_version",
    "run",
    "researchability",
    "business_driver_map",
    "management_decision_ledger",
    "thesis",
    "valuation_review",
    "source_audit",
    "claims",
}
PROTOCOL_FINGERPRINT_KEYS = {
    "research_protocol_digest_sha256",
    "execution_bundle_digest_sha256",
    "schema_version",
    "schema_sha256",
    "validator_sha256",
}
PREFLIGHT_CAPABILITIES = {
    "protocol_access",
    "schema_access",
    "official_source_retrieval",
    "challenge_source_retrieval",
    "calculation_runtime",
    "package_write",
}
RUN_STATUSES = {
    "preflight",
    "collecting",
    "reconciled",
    "modeled",
    "audited",
    "ready_to_freeze",
}
RUN_MODES = {"full", "incremental", "repair", "migration"}
PASS_ROLES = {"primary_research", "adversarial_review", "source_audit", "synthesis"}
ISOLATED_EXECUTIONS = {"isolated_agent", "isolated_context"}
CONFIDENCE = {"high", "medium", "low"}
RESEARCH_MODULES = {
    "business",
    "financials",
    "competition",
    "management",
    "governance",
    "industry",
    "valuation",
    "risk",
}
DECISION_RELEVANCE = {"critical", "supporting", "context"}
ADJUDICATION = {"upheld", "narrowed", "conflicted", "rejected", "unresolved"}
DRIVER_ROLES = {
    "volume",
    "price",
    "mix",
    "take_rate",
    "retention",
    "margin",
    "capital_intensity",
    "other",
}
MANAGEMENT_KINDS = {
    "commitment",
    "forecast",
    "aspiration",
    "capital_allocation",
    "crisis_response",
    "stop_doing",
    "governance",
    "succession",
}
PROCESS_QUALITY = {"high", "mixed", "low", "uncertain"}
OUTCOME_QUALITY = {"positive", "mixed", "negative", "pending", "uncertain"}
SUCCESSION_DEPENDENCY = {"high", "medium", "low", "unknown"}
ASSUMPTION_IMPORTANCE = {"core", "supporting"}
ASSUMPTION_STATUS = {"supported", "strained", "broken", "uncertain"}
CHANGE_TYPES = {
    "baseline",
    "fundamental",
    "market_price",
    "accounting_restatement",
    "methodology",
    "correction",
    "wording",
    "none",
}
OVERALL_CHANGES = {"baseline", "strengthened", "unchanged", "weakened", "broken", "uncertain"}
MODEL_ROLES = {"primary", "reverse", "cross_check"}
MODEL_STATUSES = {"appropriate", "limited", "inappropriate"}
RESULT_DIRECTIONS = {"undervalued", "fair", "overvalued", "indeterminate"}
RISK_PLACEMENTS = {"cash_flow", "scenario", "tail_case", "discount_rate"}
VALUATION_STATUSES = {"明显低估", "可能低估", "接近合理", "偏高", "无法判断"}
STABILITY_ACTIONS = {"maintain", "downgrade", "too_hard"}
SOURCE_AUDIT_TARGET_TYPES = {"claim", "calculation", "company_field", "valuation_assumption"}
SOURCE_AUDIT_STATUSES = {"pass", "fail", "unavailable"}
OFFICIAL_SOURCE_TYPES = {
    "annual_report",
    "quarterly_report",
    "earnings_release",
    "regulatory_filing",
    "investor_presentation",
    "official_website",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProcessIssue:
    """A package-validator-neutral research process finding."""

    severity: str
    code: str
    path: str
    message: str


def canonical_company_sha256(company: Mapping[str, Any]) -> str:
    """Return the reproducible selection seed defined by the audit contract."""

    encoded = json.dumps(
        company,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def deterministic_ordinary_claim_sample(claim_ids: Sequence[str], selection_seed: str) -> list[str]:
    """Choose the required 15% (at least three) ordinary-claim audit sample."""

    unique_ids = sorted(set(claim_ids))
    if not unique_ids:
        return []
    sample_size = min(len(unique_ids), max(3, math.ceil(len(unique_ids) * 0.15)))
    ranked = sorted(
        unique_ids,
        key=lambda claim_id: (hashlib.sha256(f"{selection_seed}:{claim_id}".encode()).hexdigest(), claim_id),
    )
    return ranked[:sample_size]


def _add(
    issues: list[ProcessIssue],
    severity: str,
    code: str,
    path: str,
    message: str,
) -> None:
    issues.append(ProcessIssue(severity, code, path, message))


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _substantive(value: Any, minimum: int = 6) -> bool:
    if not _nonblank(value):
        return False
    return len(re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE)) >= minimum


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _valid_datetime(value: Any) -> bool:
    if not _nonblank(value):
        return False
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _valid_date_or_datetime(value: Any) -> bool:
    if _valid_datetime(value):
        return True
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _string_list(value: Any, minimum: int = 0, substantive: bool = False) -> bool:
    predicate = _substantive if substantive else _nonblank
    return isinstance(value, list) and len(value) >= minimum and all(predicate(item) for item in value)


def _narrative_or_list(value: Any) -> bool:
    return _substantive(value) or _string_list(value, 1, substantive=True)


def _known_ids(value: Any, known: set[str], allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and len(value) == len(set(value))
        and all(_nonblank(item) and item in known for item in value)
    )


def _required_keys(
    value: Any,
    required: set[str],
    issues: list[ProcessIssue],
    path: str,
    code: str,
) -> bool:
    if not isinstance(value, dict):
        _add(issues, "error", f"{code}-shape", path, "expected an object")
        return False
    missing = sorted(required.difference(value))
    if missing:
        _add(issues, "error", f"{code}-required", path, f"missing required keys {missing!r}")
    return not missing


def _is_too_hard(company: Mapping[str, Any]) -> bool:
    verdict = company.get("verdict") if isinstance(company.get("verdict"), dict) else {}
    return verdict.get("research_status") == "Too Hard" or verdict.get("valuation_status") == "无法判断"


def _validate_run(
    run: Any,
    claims: Mapping[str, Mapping[str, Any]],
    source_records: Mapping[str, Mapping[str, Any]],
    mode: str,
    expected_fingerprint: Mapping[str, Any],
    issues: list[ProcessIssue],
) -> tuple[str | None, str | None, list[Mapping[str, Any]]]:
    path = "evidence-ledger.json.run"
    required = {
        "run_id",
        "research_mode",
        "workflow_tier",
        "data_cutoff_at",
        "status",
        "protocol_fingerprint",
        "preflight",
        "passes",
    }
    if not _required_keys(run, required, issues, path, "research-run"):
        if not isinstance(run, dict):
            return None, None, []

    if not _nonblank(run.get("run_id")):
        _add(issues, "error", "research-run-id", f"{path}.run_id", "run_id must be nonblank")
    research_mode = run.get("research_mode")
    if research_mode not in RUN_MODES:
        _add(issues, "error", "research-run-mode", f"{path}.research_mode", f"must be one of {sorted(RUN_MODES)!r}")
    elif mode == "incremental" and research_mode != "incremental":
        _add(issues, "error", "research-run-mode", f"{path}.research_mode", "incremental validation requires an incremental research run")
    workflow_tier = run.get("workflow_tier")
    if workflow_tier not in {"standard", "audit"}:
        _add(issues, "error", "workflow-tier", f"{path}.workflow_tier", "workflow_tier must be standard or audit")
    if not _valid_datetime(run.get("data_cutoff_at")):
        _add(issues, "error", "research-data-cutoff", f"{path}.data_cutoff_at", "must be an ISO 8601 date-time with timezone")
    if run.get("status") not in RUN_STATUSES:
        _add(issues, "error", "research-run-status", f"{path}.status", f"must be one of {sorted(RUN_STATUSES)!r}")
    elif run.get("status") != "ready_to_freeze":
        _add(issues, "error", "research-not-ready-to-freeze", f"{path}.status", "formal package must be ready_to_freeze")

    fingerprint = run.get("protocol_fingerprint")
    if not isinstance(fingerprint, dict) or set(fingerprint) != PROTOCOL_FINGERPRINT_KEYS:
        _add(
            issues,
            "error",
            "protocol-fingerprint-shape",
            f"{path}.protocol_fingerprint",
            f"fingerprint must contain exactly {sorted(PROTOCOL_FINGERPRINT_KEYS)!r}",
        )
    else:
        for key in (
            "research_protocol_digest_sha256",
            "execution_bundle_digest_sha256",
            "schema_sha256",
            "validator_sha256",
        ):
            if not isinstance(fingerprint.get(key), str) or HEX64.fullmatch(fingerprint[key]) is None:
                _add(issues, "error", "protocol-fingerprint-hash", f"{path}.protocol_fingerprint.{key}", "must be a lowercase SHA-256")
        if fingerprint != dict(expected_fingerprint):
            _add(issues, "error", "protocol-fingerprint-mismatch", f"{path}.protocol_fingerprint", "does not exactly match the active protocol, Schema and validator")

    known_sources = set(source_records)
    preflight = run.get("preflight")
    seen_capabilities: dict[str, Mapping[str, Any]] = {}
    if not isinstance(preflight, list):
        _add(issues, "error", "preflight-shape", f"{path}.preflight", "preflight must be an array")
    else:
        item_keys = {"capability", "status", "checked_at", "method", "source_id", "evidence_sha256", "failure_reason"}
        for index, item in enumerate(preflight):
            item_path = f"{path}.preflight[{index}]"
            if not _required_keys(item, item_keys, issues, item_path, "preflight-item"):
                if not isinstance(item, dict):
                    continue
            capability = item.get("capability")
            if capability not in PREFLIGHT_CAPABILITIES:
                _add(issues, "error", "preflight-capability", f"{item_path}.capability", "unknown preflight capability")
            elif capability in seen_capabilities:
                _add(issues, "error", "preflight-duplicate", f"{item_path}.capability", f"duplicate capability {capability!r}")
            else:
                seen_capabilities[capability] = item
            if item.get("status") not in {"passed", "failed"}:
                _add(issues, "error", "preflight-status", f"{item_path}.status", "status must be passed or failed")
            elif item.get("status") != "passed":
                _add(issues, "error", "preflight-failed", item_path, f"capability {capability!r} did not pass")
            if not _valid_datetime(item.get("checked_at")):
                _add(issues, "error", "preflight-checked-at", f"{item_path}.checked_at", "must be an ISO 8601 date-time with timezone")
            if not _substantive(item.get("method")):
                _add(issues, "error", "preflight-method", f"{item_path}.method", "must describe the probe actually performed")
            failure_reason = item.get("failure_reason")
            if item.get("status") == "failed" and not _substantive(failure_reason):
                _add(issues, "error", "preflight-failure-reason", f"{item_path}.failure_reason", "failed probes require a reason")
            if item.get("status") == "passed" and failure_reason not in (None, ""):
                _add(issues, "error", "preflight-failure-reason", f"{item_path}.failure_reason", "passed probes cannot retain a failure reason")
            digest = item.get("evidence_sha256")
            if digest is not None and (not isinstance(digest, str) or HEX64.fullmatch(digest) is None):
                _add(issues, "error", "preflight-evidence-hash", f"{item_path}.evidence_sha256", "must be null or a lowercase SHA-256")

        missing_capabilities = sorted(PREFLIGHT_CAPABILITIES.difference(seen_capabilities))
        if missing_capabilities:
            _add(issues, "error", "preflight-coverage", f"{path}.preflight", f"missing probes {missing_capabilities!r}")
        if len(preflight) != len(PREFLIGHT_CAPABILITIES):
            _add(issues, "error", "preflight-cardinality", f"{path}.preflight", "preflight must contain each required capability exactly once")

        source_probe_names = ("official_source_retrieval", "challenge_source_retrieval")
        source_probe_ids: list[str] = []
        for capability in source_probe_names:
            item = seen_capabilities.get(capability)
            if item is None:
                continue
            source_id = item.get("source_id")
            if source_id not in known_sources:
                _add(issues, "error", "preflight-source", f"{path}.preflight", f"{capability} must bind a resolved company source")
            else:
                source_probe_ids.append(source_id)
            if not isinstance(item.get("evidence_sha256"), str) or HEX64.fullmatch(item["evidence_sha256"]) is None:
                _add(issues, "error", "preflight-source-hash", f"{path}.preflight", f"{capability} must save the retrieved content SHA-256")
        official_probe = seen_capabilities.get("official_source_retrieval")
        if official_probe is not None:
            official_record = source_records.get(official_probe.get("source_id"))
            if not isinstance(official_record, Mapping) or official_record.get("source_type") not in OFFICIAL_SOURCE_TYPES:
                _add(
                    issues,
                    "error",
                    "preflight-official-source-type",
                    f"{path}.preflight",
                    "official_source_retrieval must bind a first-party or regulatory source record",
                )
        if len(source_probe_ids) == 2 and source_probe_ids[0] == source_probe_ids[1]:
            _add(issues, "error", "preflight-source-independence", f"{path}.preflight", "official and challenge probes must use different source IDs")

    passes_value = run.get("passes")
    valid_passes: list[Mapping[str, Any]] = []
    if not isinstance(passes_value, list):
        _add(issues, "error", "research-passes-shape", f"{path}.passes", "passes must be an array")
        return research_mode if isinstance(research_mode, str) else None, workflow_tier if isinstance(workflow_tier, str) else None, valid_passes

    pass_ids: set[str] = set()
    pass_keys = {"id", "role", "actor_id", "execution", "status", "scope", "claim_ids", "source_ids_accessed"}
    for index, item in enumerate(passes_value):
        item_path = f"{path}.passes[{index}]"
        if not _required_keys(item, pass_keys, issues, item_path, "research-pass"):
            if not isinstance(item, dict):
                continue
        valid_passes.append(item)
        pass_id = item.get("id")
        if not _nonblank(pass_id):
            _add(issues, "error", "research-pass-id", f"{item_path}.id", "pass id must be nonblank")
        elif pass_id in pass_ids:
            _add(issues, "error", "research-pass-duplicate", f"{item_path}.id", f"duplicate pass id {pass_id!r}")
        else:
            pass_ids.add(pass_id)
        role = item.get("role")
        if role not in PASS_ROLES:
            _add(issues, "error", "research-pass-role", f"{item_path}.role", f"must be one of {sorted(PASS_ROLES)!r}")
        if not _nonblank(item.get("actor_id")):
            _add(issues, "error", "research-pass-actor", f"{item_path}.actor_id", "actor_id must be nonblank")
        if not _nonblank(item.get("execution")):
            _add(issues, "error", "research-pass-execution", f"{item_path}.execution", "execution must identify the actual context")
        if item.get("status") not in {"completed", "failed"}:
            _add(issues, "error", "research-pass-status", f"{item_path}.status", "status must be completed or failed")
        elif item.get("status") != "completed":
            _add(issues, "error", "research-pass-failed", item_path, f"research pass {pass_id!r} did not complete")
        if not _substantive(item.get("scope")):
            _add(issues, "error", "research-pass-scope", f"{item_path}.scope", "scope must be substantive")
        if not _known_ids(item.get("claim_ids"), set(claims), allow_empty=role == "source_audit"):
            _add(issues, "error", "research-pass-claims", f"{item_path}.claim_ids", "claim_ids must be unique and resolve to claims")
        if not _known_ids(item.get("source_ids_accessed"), known_sources, allow_empty=role == "synthesis"):
            _add(issues, "error", "research-pass-sources", f"{item_path}.source_ids_accessed", "source_ids_accessed must be unique and resolve to company sources")

    roles = [item.get("role") for item in valid_passes if item.get("status") == "completed"]
    for role in PASS_ROLES:
        if role not in roles:
            _add(issues, "error", "research-pass-coverage", f"{path}.passes", f"missing completed {role!r} pass")
    adversarial_passes = [item for item in valid_passes if item.get("role") == "adversarial_review" and item.get("status") == "completed"]
    if workflow_tier == "audit" and len(adversarial_passes) < 2:
        _add(issues, "error", "audit-adversarial-coverage", f"{path}.passes", "audit tier requires at least two adversarial reviews")
    primary_actors = {item.get("actor_id") for item in valid_passes if item.get("role") == "primary_research" and _nonblank(item.get("actor_id"))}
    challenge_actors: list[str] = []
    for index, item in enumerate(valid_passes):
        if item.get("role") not in {"adversarial_review", "source_audit"}:
            continue
        item_path = f"{path}.passes[{index}]"
        actor = item.get("actor_id")
        if actor in primary_actors:
            _add(issues, "error", "research-pass-independence", f"{item_path}.actor_id", "challenge and audit actors must differ from primary research")
        if item.get("execution") not in ISOLATED_EXECUTIONS:
            _add(issues, "error", "research-pass-isolation", f"{item_path}.execution", "challenge and source audit must use an isolated agent or context")
        if item.get("role") == "adversarial_review" and _nonblank(actor):
            challenge_actors.append(actor)
    if workflow_tier == "audit" and len(set(challenge_actors)) < 2:
        _add(issues, "error", "audit-adversarial-independence", f"{path}.passes", "audit-tier adversarial reviews require distinct actor IDs")
    return research_mode if isinstance(research_mode, str) else None, workflow_tier if isinstance(workflow_tier, str) else None, valid_passes


def _validate_researchability(value: Any, issues: list[ProcessIssue]) -> None:
    path = "evidence-ledger.json.researchability"
    required = {
        "official_source_coverage",
        "operating_kpi_coverage",
        "third_party_verifiability",
        "timeliness",
        "opacity",
        "evidence_confidence",
        "thesis_certainty",
        "assessment",
        "limitations",
    }
    if not _required_keys(value, required, issues, path, "researchability"):
        if not isinstance(value, dict):
            return
    for key in (
        "official_source_coverage",
        "operating_kpi_coverage",
        "third_party_verifiability",
        "timeliness",
        "evidence_confidence",
        "thesis_certainty",
    ):
        if value.get(key) not in CONFIDENCE:
            _add(issues, "error", "researchability-rating", f"{path}.{key}", "must be high, medium or low")
    if value.get("opacity") not in {"low", "medium", "high"}:
        _add(issues, "error", "researchability-opacity", f"{path}.opacity", "must be low, medium or high")
    if not _substantive(value.get("assessment"), 12):
        _add(issues, "error", "researchability-assessment", f"{path}.assessment", "must separately explain evidence availability and thesis certainty")
    if not _string_list(value.get("limitations"), 0, substantive=True):
        _add(issues, "error", "researchability-limitations", f"{path}.limitations", "limitations must be an array of substantive strings")
    if value.get("official_source_coverage") == "low" and value.get("evidence_confidence") == "high":
        _add(issues, "error", "researchability-overconfidence", path, "low official-source coverage cannot support high evidence confidence")


def _validate_driver_map(
    value: Any,
    known_sources: set[str],
    issues: list[ProcessIssue],
) -> None:
    path = "evidence-ledger.json.business_driver_map"
    if not _required_keys(value, {"equation", "value_capture_chain", "drivers"}, issues, path, "driver-map"):
        if not isinstance(value, dict):
            return
    if not _substantive(value.get("equation"), 12):
        _add(issues, "error", "driver-equation", f"{path}.equation", "must state a substantive value-formation relationship")
    if not _string_list(value.get("value_capture_chain"), 2, substantive=True):
        _add(issues, "error", "value-capture-chain", f"{path}.value_capture_chain", "must contain at least two substantive causal steps")
    drivers = value.get("drivers")
    if not isinstance(drivers, list) or not 2 <= len(drivers) <= 5:
        _add(issues, "error", "driver-count", f"{path}.drivers", "must contain two to five drivers")
        if not isinstance(drivers, list):
            return
    required = {
        "id", "name", "metric", "definition", "historical_baseline", "current_state", "causal_role",
        "direction_and_mechanism", "cash_flow_link", "moat_link", "valuation_link", "monitoring_indicator",
        "source_ids", "confidence", "counterevidence", "would_falsify",
    }
    seen: set[str] = set()
    for index, driver in enumerate(drivers):
        item_path = f"{path}.drivers[{index}]"
        if not _required_keys(driver, required, issues, item_path, "driver"):
            if not isinstance(driver, dict):
                continue
        driver_id = driver.get("id")
        if not _nonblank(driver_id):
            _add(issues, "error", "driver-id", f"{item_path}.id", "driver id must be nonblank")
        elif driver_id in seen:
            _add(issues, "error", "driver-duplicate", f"{item_path}.id", f"duplicate driver id {driver_id!r}")
        else:
            seen.add(driver_id)
        for key in (
            "name", "metric", "definition", "historical_baseline", "current_state", "direction_and_mechanism",
            "cash_flow_link", "moat_link", "valuation_link", "monitoring_indicator", "would_falsify",
        ):
            if not _substantive(driver.get(key)):
                _add(issues, "error", "driver-substance", f"{item_path}.{key}", "must be substantive and testable")
        if driver.get("causal_role") not in DRIVER_ROLES:
            _add(issues, "error", "driver-causal-role", f"{item_path}.causal_role", f"must be one of {sorted(DRIVER_ROLES)!r}")
        if driver.get("confidence") not in CONFIDENCE:
            _add(issues, "error", "driver-confidence", f"{item_path}.confidence", "must be high, medium or low")
        if not _known_ids(driver.get("source_ids"), known_sources):
            _add(issues, "error", "driver-sources", f"{item_path}.source_ids", "must contain unique resolved source IDs")
        if not _string_list(driver.get("counterevidence"), 0, substantive=True):
            _add(issues, "error", "driver-counterevidence", f"{item_path}.counterevidence", "must be an array of substantive strings")


def _validate_management_decisions(
    value: Any,
    known_sources: set[str],
    claim_ids: set[str],
    issues: list[ProcessIssue],
) -> None:
    path = "evidence-ledger.json.management_decision_ledger"
    if not isinstance(value, list):
        _add(issues, "error", "management-decision-ledger-shape", path, "must be an array")
        return
    if len(value) < 3:
        _add(issues, "error", "management-decision-coverage", path, "must contain at least three decisions spanning the required behavior groups")
    required = {
        "id", "kind", "date", "decision", "information_available", "public_rationale", "alternatives",
        "constraints", "ex_ante_process", "process_quality", "outcome", "outcome_quality", "confounders",
        "stakeholder_claim_ids", "succession_dependency", "source_ids", "confidence",
    }
    seen: set[str] = set()
    kinds: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not _required_keys(item, required, issues, item_path, "management-decision"):
            if not isinstance(item, dict):
                continue
        decision_id = item.get("id")
        if not _nonblank(decision_id):
            _add(issues, "error", "management-decision-id", f"{item_path}.id", "decision id must be nonblank")
        elif decision_id in seen:
            _add(issues, "error", "management-decision-duplicate", f"{item_path}.id", f"duplicate decision id {decision_id!r}")
        else:
            seen.add(decision_id)
        kind = item.get("kind")
        if kind not in MANAGEMENT_KINDS:
            _add(issues, "error", "management-decision-kind", f"{item_path}.kind", f"must be one of {sorted(MANAGEMENT_KINDS)!r}")
        else:
            kinds.add(kind)
        if not _valid_date_or_datetime(item.get("date")):
            _add(issues, "error", "management-decision-date", f"{item_path}.date", "must be a valid ISO date or date-time")
        for key in ("decision", "information_available", "public_rationale", "ex_ante_process"):
            if not _substantive(item.get(key)):
                _add(issues, "error", "management-decision-substance", f"{item_path}.{key}", "must be substantive")
        for key in ("alternatives", "constraints", "confounders"):
            if not _narrative_or_list(item.get(key)):
                _add(issues, "error", "management-decision-context", f"{item_path}.{key}", "must be a substantive narrative or nonempty string array")
        if item.get("process_quality") not in PROCESS_QUALITY:
            _add(issues, "error", "management-process-quality", f"{item_path}.process_quality", f"must be one of {sorted(PROCESS_QUALITY)!r}")
        if item.get("outcome_quality") not in OUTCOME_QUALITY:
            _add(issues, "error", "management-outcome-quality", f"{item_path}.outcome_quality", f"must be one of {sorted(OUTCOME_QUALITY)!r}")
        outcome = item.get("outcome")
        if item.get("outcome_quality") in {"pending", "uncertain"}:
            if outcome is not None and not _substantive(outcome):
                _add(issues, "error", "management-outcome", f"{item_path}.outcome", "must be null or substantive when outcome is pending/uncertain")
        elif not _substantive(outcome):
            _add(issues, "error", "management-outcome", f"{item_path}.outcome", "completed outcomes require a substantive description")
        if item.get("succession_dependency") not in SUCCESSION_DEPENDENCY:
            _add(issues, "error", "management-succession-dependency", f"{item_path}.succession_dependency", f"must be one of {sorted(SUCCESSION_DEPENDENCY)!r}")
        if item.get("confidence") not in CONFIDENCE:
            _add(issues, "error", "management-decision-confidence", f"{item_path}.confidence", "must be high, medium or low")
        if not _known_ids(item.get("stakeholder_claim_ids"), claim_ids, allow_empty=True):
            _add(issues, "error", "management-stakeholder-claims", f"{item_path}.stakeholder_claim_ids", "must be a unique array resolving to claims")
        if not _known_ids(item.get("source_ids"), known_sources):
            _add(issues, "error", "management-decision-sources", f"{item_path}.source_ids", "must contain unique resolved source IDs")
    required_groups = (
        {"commitment", "forecast", "aspiration"},
        {"capital_allocation", "crisis_response", "stop_doing"},
        {"governance", "succession"},
    )
    for group in required_groups:
        if not kinds.intersection(group):
            _add(issues, "error", "management-decision-coverage", path, f"missing a decision from {sorted(group)!r}")


def _validate_claim_extensions(
    claims_value: Any,
    known_sources: set[str],
    passes: Sequence[Mapping[str, Any]],
    too_hard: bool,
    issues: list[ProcessIssue],
) -> dict[str, Mapping[str, Any]]:
    path = "evidence-ledger.json.claims"
    if not isinstance(claims_value, list):
        _add(issues, "error", "process-claims-shape", path, "claims must be an array")
        return {}
    required = {
        "id", "claim", "classification", "confidence", "source_ids", "research_module", "decision_relevance",
        "adjudication", "counterevidence", "counterevidence_search", "would_falsify",
    }
    claims: dict[str, Mapping[str, Any]] = {}
    challenged_claims: set[str] = set()
    for research_pass in passes:
        if research_pass.get("role") == "adversarial_review" and research_pass.get("status") == "completed":
            challenged_claims.update(item for item in research_pass.get("claim_ids", []) if isinstance(item, str))
    for index, claim in enumerate(claims_value):
        item_path = f"{path}[{index}]"
        if not _required_keys(claim, required, issues, item_path, "process-claim"):
            if not isinstance(claim, dict):
                continue
        claim_id = claim.get("id")
        if _nonblank(claim_id):
            if claim_id in claims:
                _add(issues, "error", "process-claim-duplicate", f"{item_path}.id", f"duplicate claim id {claim_id!r}")
            else:
                claims[claim_id] = claim
        if claim.get("research_module") not in RESEARCH_MODULES:
            _add(issues, "error", "claim-research-module", f"{item_path}.research_module", f"must be one of {sorted(RESEARCH_MODULES)!r}")
        relevance = claim.get("decision_relevance")
        if relevance not in DECISION_RELEVANCE:
            _add(issues, "error", "claim-decision-relevance", f"{item_path}.decision_relevance", f"must be one of {sorted(DECISION_RELEVANCE)!r}")
        adjudication = claim.get("adjudication")
        if adjudication not in ADJUDICATION:
            _add(issues, "error", "claim-adjudication", f"{item_path}.adjudication", f"must be one of {sorted(ADJUDICATION)!r}")
        if not _string_list(claim.get("counterevidence"), 0, substantive=True):
            _add(issues, "error", "claim-counterevidence", f"{item_path}.counterevidence", "must be an array of substantive strings")
        if relevance == "critical":
            if not _substantive(claim.get("counterevidence_search"), 10):
                _add(issues, "error", "critical-claim-counterevidence-search", f"{item_path}.counterevidence_search", "critical claims require a substantive adverse-source search record")
            if not _substantive(claim.get("would_falsify"), 10):
                _add(issues, "error", "critical-claim-falsifiability", f"{item_path}.would_falsify", "critical claims require a substantive testable falsifier")
            if claim.get("classification") in {"inference", "estimate", "management_claim", "third_party"} and claim_id not in challenged_claims:
                _add(issues, "error", "critical-claim-unchallenged", item_path, "critical analytical or asserted claims must be covered by an isolated adversarial pass")
            if adjudication in {"unresolved", "rejected"} and not too_hard:
                _add(issues, "error", "critical-claim-not-adjudicated", item_path, "non-Too-Hard formal research cannot retain a critical unresolved or rejected claim")
        else:
            search = claim.get("counterevidence_search")
            if search is not None and not _substantive(search):
                _add(issues, "error", "claim-counterevidence-search", f"{item_path}.counterevidence_search", "must be null or substantive")
        if not _known_ids(claim.get("source_ids"), known_sources):
            _add(issues, "error", "process-claim-sources", f"{item_path}.source_ids", "must contain unique resolved source IDs")
    return claims


def _validate_thesis(
    value: Any,
    company: Mapping[str, Any],
    claims: Mapping[str, Mapping[str, Any]],
    research_mode: str | None,
    issues: list[ProcessIssue],
) -> None:
    path = "evidence-ledger.json.thesis"
    required = {
        "overall_change", "assumptions", "valuation_assumption_changes", "rejected_claim_ids",
        "unresolved_conflicts", "revision_log",
    }
    if not _required_keys(value, required, issues, path, "thesis"):
        if not isinstance(value, dict):
            return
    overall_change = value.get("overall_change")
    if overall_change not in OVERALL_CHANGES:
        _add(issues, "error", "thesis-overall-change", f"{path}.overall_change", f"must be one of {sorted(OVERALL_CHANGES)!r}")
    if research_mode == "incremental" and overall_change == "baseline":
        _add(issues, "error", "incremental-thesis-baseline", f"{path}.overall_change", "incremental research cannot reset the thesis to baseline")
    if research_mode != "incremental" and overall_change == "unchanged":
        _add(issues, "warning", "nonincremental-thesis-unchanged", f"{path}.overall_change", "unchanged normally belongs to an incremental comparison")

    assumptions = value.get("assumptions")
    verdict = company.get("verdict") if isinstance(company.get("verdict"), dict) else {}
    company_assumptions = verdict.get("key_assumptions") if isinstance(verdict.get("key_assumptions"), list) else []
    if not isinstance(assumptions, list) or not 2 <= len(assumptions) <= 4:
        _add(issues, "error", "thesis-assumption-count", f"{path}.assumptions", "must contain two to four assumptions")
        if not isinstance(assumptions, list):
            assumptions = []
    required_assumption = {
        "id", "assumption", "importance", "prior_status", "current_status", "change_type", "evidence_claim_ids",
        "reason", "falsifier", "red_lines", "next_validation",
    }
    seen_ids: set[str] = set()
    assumption_texts: list[str] = []
    for index, assumption in enumerate(assumptions):
        item_path = f"{path}.assumptions[{index}]"
        if not _required_keys(assumption, required_assumption, issues, item_path, "thesis-assumption"):
            if not isinstance(assumption, dict):
                continue
        assumption_id = assumption.get("id")
        if not _nonblank(assumption_id):
            _add(issues, "error", "thesis-assumption-id", f"{item_path}.id", "assumption id must be nonblank")
        elif assumption_id in seen_ids:
            _add(issues, "error", "thesis-assumption-duplicate", f"{item_path}.id", f"duplicate assumption id {assumption_id!r}")
        else:
            seen_ids.add(assumption_id)
        text = assumption.get("assumption")
        if not _substantive(text, 10):
            _add(issues, "error", "thesis-assumption-text", f"{item_path}.assumption", "must be substantive")
        elif isinstance(text, str):
            assumption_texts.append(text)
        if assumption.get("importance") not in ASSUMPTION_IMPORTANCE:
            _add(issues, "error", "thesis-assumption-importance", f"{item_path}.importance", f"must be one of {sorted(ASSUMPTION_IMPORTANCE)!r}")
        prior = assumption.get("prior_status")
        if prior is not None and prior not in ASSUMPTION_STATUS:
            _add(issues, "error", "thesis-assumption-prior-status", f"{item_path}.prior_status", "must be null or a valid assumption status")
        if assumption.get("current_status") not in ASSUMPTION_STATUS:
            _add(issues, "error", "thesis-assumption-current-status", f"{item_path}.current_status", f"must be one of {sorted(ASSUMPTION_STATUS)!r}")
        change_type = assumption.get("change_type")
        if change_type not in CHANGE_TYPES:
            _add(issues, "error", "thesis-assumption-change-type", f"{item_path}.change_type", f"must be one of {sorted(CHANGE_TYPES)!r}")
        if research_mode == "incremental":
            if prior is None:
                _add(issues, "error", "incremental-thesis-prior-status", f"{item_path}.prior_status", "incremental assumptions must carry the predecessor status")
            if change_type == "baseline":
                _add(issues, "error", "incremental-thesis-change-type", f"{item_path}.change_type", "incremental assumptions cannot use baseline")
        else:
            if overall_change == "baseline" and prior is not None:
                _add(issues, "error", "baseline-thesis-prior-status", f"{item_path}.prior_status", "baseline assumptions must have null prior_status")
            if overall_change == "baseline" and change_type != "baseline":
                _add(issues, "error", "baseline-thesis-change-type", f"{item_path}.change_type", "baseline assumptions must use baseline change_type")
        if not _known_ids(assumption.get("evidence_claim_ids"), set(claims)):
            _add(issues, "error", "thesis-assumption-evidence", f"{item_path}.evidence_claim_ids", "must contain unique resolved claim IDs")
        for key in ("reason", "falsifier", "next_validation"):
            if not _substantive(assumption.get(key), 8):
                _add(issues, "error", "thesis-assumption-substance", f"{item_path}.{key}", "must be substantive and testable")
        if not _string_list(assumption.get("red_lines"), 1, substantive=True):
            _add(issues, "error", "thesis-assumption-red-lines", f"{item_path}.red_lines", "must contain at least one substantive red line")
    if sorted(assumption_texts) != sorted(item for item in company_assumptions if isinstance(item, str)):
        _add(issues, "error", "thesis-assumption-mapping", f"{path}.assumptions", "assumption text must map one-to-one to company.json verdict.key_assumptions")

    changes = value.get("valuation_assumption_changes")
    if not isinstance(changes, list):
        _add(issues, "error", "valuation-assumption-changes-shape", f"{path}.valuation_assumption_changes", "must be an array")
    else:
        change_keys = {"scenario", "parameter", "previous_value", "current_value", "change_type", "reason", "evidence_claim_ids"}
        for index, change in enumerate(changes):
            item_path = f"{path}.valuation_assumption_changes[{index}]"
            if not _required_keys(change, change_keys, issues, item_path, "valuation-assumption-change"):
                if not isinstance(change, dict):
                    continue
            if not _nonblank(change.get("scenario")) or not _nonblank(change.get("parameter")):
                _add(issues, "error", "valuation-assumption-change-key", item_path, "scenario and parameter must be nonblank")
            elif change.get("parameter") not in {"revenue_growth", "margin", "discount_rate", "terminal_growth"}:
                _add(
                    issues,
                    "error",
                    "valuation-assumption-change-parameter",
                    f"{item_path}.parameter",
                    "parameter must be revenue_growth, margin, discount_rate or terminal_growth",
                )
            if change.get("change_type") not in CHANGE_TYPES.difference({"baseline", "none"}):
                _add(issues, "error", "valuation-assumption-change-type", f"{item_path}.change_type", "must identify a substantive parameter-change type")
            if change.get("previous_value") == change.get("current_value"):
                _add(issues, "error", "valuation-assumption-no-change", item_path, "previous_value and current_value must differ")
            if not _substantive(change.get("reason")):
                _add(issues, "error", "valuation-assumption-change-reason", f"{item_path}.reason", "must explain the change")
            if not _known_ids(change.get("evidence_claim_ids"), set(claims)):
                _add(issues, "error", "valuation-assumption-change-evidence", f"{item_path}.evidence_claim_ids", "must contain unique resolved claim IDs")

    rejected_ids = value.get("rejected_claim_ids")
    actual_rejected = {claim_id for claim_id, claim in claims.items() if claim.get("adjudication") == "rejected"}
    if not isinstance(rejected_ids, list) or len(rejected_ids) != len(set(rejected_ids)) or set(rejected_ids) != actual_rejected:
        _add(issues, "error", "thesis-rejected-claims", f"{path}.rejected_claim_ids", "must exactly list every rejected claim and no others")

    conflicts = value.get("unresolved_conflicts")
    conflict_claim_ids: set[str] = set()
    unresolved = False
    if not isinstance(conflicts, list):
        _add(issues, "error", "thesis-conflicts-shape", f"{path}.unresolved_conflicts", "must be an array")
    else:
        conflict_keys = {"id", "topic", "evidence_claim_ids", "status", "resolution", "impact_on_conclusion"}
        seen_conflicts: set[str] = set()
        for index, conflict in enumerate(conflicts):
            item_path = f"{path}.unresolved_conflicts[{index}]"
            if not _required_keys(conflict, conflict_keys, issues, item_path, "thesis-conflict"):
                if not isinstance(conflict, dict):
                    continue
            conflict_id = conflict.get("id")
            if not _nonblank(conflict_id) or conflict_id in seen_conflicts:
                _add(issues, "error", "thesis-conflict-id", f"{item_path}.id", "conflict id must be nonblank and unique")
            else:
                seen_conflicts.add(conflict_id)
            if not _substantive(conflict.get("topic")) or not _substantive(conflict.get("impact_on_conclusion")):
                _add(issues, "error", "thesis-conflict-substance", item_path, "topic and impact_on_conclusion must be substantive")
            if not _known_ids(conflict.get("evidence_claim_ids"), set(claims)):
                _add(issues, "error", "thesis-conflict-evidence", f"{item_path}.evidence_claim_ids", "must contain unique resolved claim IDs")
            else:
                conflict_claim_ids.update(conflict.get("evidence_claim_ids", []))
            status = conflict.get("status")
            if status not in {"resolved", "unresolved"}:
                _add(issues, "error", "thesis-conflict-status", f"{item_path}.status", "must be resolved or unresolved")
            elif status == "unresolved":
                unresolved = True
                if conflict.get("resolution") not in (None, "") and not _substantive(conflict.get("resolution")):
                    _add(issues, "error", "thesis-conflict-resolution", f"{item_path}.resolution", "must be null/blank or substantive")
            elif not _substantive(conflict.get("resolution")):
                _add(issues, "error", "thesis-conflict-resolution", f"{item_path}.resolution", "resolved conflicts require a substantive resolution")
    critical_conflicted = {
        claim_id for claim_id, claim in claims.items()
        if claim.get("decision_relevance") == "critical" and claim.get("adjudication") == "conflicted"
    }
    if not critical_conflicted.issubset(conflict_claim_ids):
        _add(issues, "error", "critical-claim-conflict-missing", f"{path}.unresolved_conflicts", "every critical conflicted claim must appear in the conflict ledger")
    confidence = verdict.get("confidence")
    if unresolved and critical_conflicted and confidence in {"high", "高"}:
        _add(issues, "error", "unresolved-conflict-overconfidence", f"{path}.unresolved_conflicts", "unresolved critical conflict cannot retain high verdict confidence")

    revisions = value.get("revision_log")
    if not isinstance(revisions, list):
        _add(issues, "error", "thesis-revision-log-shape", f"{path}.revision_log", "must be an array")
    else:
        if research_mode == "incremental" and not revisions:
            _add(issues, "error", "incremental-revision-log", f"{path}.revision_log", "incremental research requires a revision record")
        revision_ids: set[str] = set()
        revision_keys = {
            "id", "changed_at", "change_type", "summary", "affected_assumption_ids", "evidence_claim_ids",
        }
        for index, revision in enumerate(revisions):
            item_path = f"{path}.revision_log[{index}]"
            if not isinstance(revision, dict):
                _add(issues, "error", "thesis-revision-shape", item_path, "revision must be an object")
                continue
            if set(revision) != revision_keys:
                _add(issues, "error", "thesis-revision-keys", item_path, f"revision must contain exactly {sorted(revision_keys)!r}")
            revision_id = revision.get("id")
            if not _nonblank(revision_id) or revision_id in revision_ids:
                _add(issues, "error", "thesis-revision-id", f"{item_path}.id", "revision id must be nonblank and unique")
            else:
                revision_ids.add(revision_id)
            if not _valid_datetime(revision.get("changed_at")):
                _add(issues, "error", "thesis-revision-changed-at", f"{item_path}.changed_at", "must be an ISO 8601 date-time with timezone")
            if revision.get("change_type") not in CHANGE_TYPES:
                _add(issues, "error", "thesis-revision-change-type", f"{item_path}.change_type", f"must be one of {sorted(CHANGE_TYPES)!r}")
            if not _substantive(revision.get("summary"), 10):
                _add(issues, "error", "thesis-revision-substance", f"{item_path}.summary", "must contain a substantive summary")
            affected = revision.get("affected_assumption_ids")
            if not isinstance(affected, list) or not affected or len(affected) != len(set(affected)) or any(not _nonblank(item) for item in affected):
                _add(issues, "error", "thesis-revision-assumptions", f"{item_path}.affected_assumption_ids", "must contain unique nonblank assumption IDs")
            if not _known_ids(revision.get("evidence_claim_ids"), set(claims)):
                _add(issues, "error", "thesis-revision-evidence", f"{item_path}.evidence_claim_ids", "must contain unique resolved claim IDs")


def _scenario_coordinates(company: Mapping[str, Any]) -> set[tuple[float, float]]:
    valuation = company.get("valuation") if isinstance(company.get("valuation"), dict) else {}
    rows = valuation.get("dcf_sensitivity") if isinstance(valuation.get("dcf_sensitivity"), list) else []
    return {
        (round(float(item["discount_rate"]), 12), round(float(item["terminal_growth"]), 12))
        for item in rows
        if isinstance(item, dict) and _finite(item.get("discount_rate")) and _finite(item.get("terminal_growth"))
    }


def _validate_valuation_review(
    value: Any,
    company: Mapping[str, Any],
    claims: Mapping[str, Mapping[str, Any]],
    too_hard: bool,
    issues: list[ProcessIssue],
) -> None:
    path = "evidence-ledger.json.valuation_review"
    required = {"model_applicability", "risk_placements", "model_conflicts", "conclusion_stability"}
    if not _required_keys(value, required, issues, path, "valuation-review"):
        if not isinstance(value, dict):
            return
    models = value.get("model_applicability")
    valid_models: list[Mapping[str, Any]] = []
    if not isinstance(models, list):
        _add(issues, "error", "model-applicability-shape", f"{path}.model_applicability", "must be an array")
    else:
        model_keys = {"model", "role", "status", "reason", "key_assumptions", "result_direction"}
        model_names: set[str] = set()
        for index, model in enumerate(models):
            item_path = f"{path}.model_applicability[{index}]"
            if not _required_keys(model, model_keys, issues, item_path, "model-applicability"):
                if not isinstance(model, dict):
                    continue
            valid_models.append(model)
            name = model.get("model")
            if not _nonblank(name) or name in model_names:
                _add(issues, "error", "model-name", f"{item_path}.model", "model name must be nonblank and unique")
            else:
                model_names.add(name)
            if model.get("role") not in MODEL_ROLES:
                _add(issues, "error", "model-role", f"{item_path}.role", f"must be one of {sorted(MODEL_ROLES)!r}")
            if model.get("status") not in MODEL_STATUSES:
                _add(issues, "error", "model-status", f"{item_path}.status", f"must be one of {sorted(MODEL_STATUSES)!r}")
            if not _substantive(model.get("reason")):
                _add(issues, "error", "model-reason", f"{item_path}.reason", "must explain applicability")
            if not _string_list(model.get("key_assumptions"), 1, substantive=True):
                _add(issues, "error", "model-key-assumptions", f"{item_path}.key_assumptions", "must contain substantive assumptions")
            if model.get("result_direction") not in RESULT_DIRECTIONS:
                _add(issues, "error", "model-result-direction", f"{item_path}.result_direction", f"must be one of {sorted(RESULT_DIRECTIONS)!r}")
        roles = {item.get("role") for item in valid_models}
        if not MODEL_ROLES.issubset(roles):
            _add(issues, "error", "model-role-coverage", f"{path}.model_applicability", "must cover primary DCF, Reverse DCF and a cross-check")
        primary = [item for item in valid_models if item.get("role") == "primary"]
        if primary and all(item.get("status") == "inappropriate" for item in primary) and not too_hard:
            _add(issues, "error", "primary-model-inappropriate", f"{path}.model_applicability", "non-Too-Hard research requires an applicable primary valuation model")

    risk_placements = value.get("risk_placements")
    risks = company.get("risks") if isinstance(company.get("risks"), dict) else {}
    pre_mortem = risks.get("pre_mortem") if isinstance(risks.get("pre_mortem"), list) else []
    expected_risks = [item.get("failure_path") for item in pre_mortem if isinstance(item, dict) and _nonblank(item.get("failure_path"))]
    observed_risks: list[str] = []
    if not isinstance(risk_placements, list):
        _add(issues, "error", "risk-placement-shape", f"{path}.risk_placements", "must be an array")
    else:
        risk_keys = {"risk", "placement", "scenario", "rationale", "claim_ids"}
        for index, risk in enumerate(risk_placements):
            item_path = f"{path}.risk_placements[{index}]"
            if not _required_keys(risk, risk_keys, issues, item_path, "risk-placement"):
                if not isinstance(risk, dict):
                    continue
            risk_text = risk.get("risk")
            if not _substantive(risk_text, 10):
                _add(issues, "error", "risk-placement-risk", f"{item_path}.risk", "must identify a Pre-Mortem failure path")
            elif isinstance(risk_text, str):
                observed_risks.append(risk_text)
            if risk.get("placement") not in RISK_PLACEMENTS:
                _add(issues, "error", "risk-placement-location", f"{item_path}.placement", f"must be one of {sorted(RISK_PLACEMENTS)!r}")
            scenario = risk.get("scenario")
            if scenario is not None and not _nonblank(scenario):
                _add(issues, "error", "risk-placement-scenario", f"{item_path}.scenario", "must be null or nonblank")
            if risk.get("placement") in {"scenario", "tail_case"} and not _nonblank(scenario):
                _add(issues, "error", "risk-placement-scenario", f"{item_path}.scenario", "scenario/tail-case placement must name the scenario")
            if not _substantive(risk.get("rationale"), 8):
                _add(issues, "error", "risk-placement-rationale", f"{item_path}.rationale", "must explain why the risk belongs only here")
            if not _known_ids(risk.get("claim_ids"), set(claims)):
                _add(issues, "error", "risk-placement-claims", f"{item_path}.claim_ids", "must contain unique resolved claim IDs")
        if len(observed_risks) != len(set(observed_risks)):
            _add(issues, "error", "risk-double-count", f"{path}.risk_placements", "each Pre-Mortem risk may be placed only once")
        if sorted(observed_risks) != sorted(expected_risks):
            _add(issues, "error", "risk-placement-coverage", f"{path}.risk_placements", "must map every Pre-Mortem failure path exactly once")

    conflicts = value.get("model_conflicts")
    covered_pairs: set[frozenset[str]] = set()
    if not isinstance(conflicts, list):
        _add(issues, "error", "model-conflicts-shape", f"{path}.model_conflicts", "must be an array")
    else:
        conflict_keys = {
            "id", "models", "applicability_boundary", "authoritative_value_basis", "explanation",
            "impact_on_conclusion", "resolved",
        }
        conflict_ids: set[str] = set()
        known_model_names = {item.get("model") for item in valid_models if _nonblank(item.get("model"))}
        for index, conflict in enumerate(conflicts):
            item_path = f"{path}.model_conflicts[{index}]"
            if not _required_keys(conflict, conflict_keys, issues, item_path, "model-conflict"):
                if not isinstance(conflict, dict):
                    continue
            conflict_id = conflict.get("id")
            if not _nonblank(conflict_id) or conflict_id in conflict_ids:
                _add(issues, "error", "model-conflict-id", f"{item_path}.id", "conflict id must be nonblank and unique")
            else:
                conflict_ids.add(conflict_id)
            conflict_models = conflict.get("models")
            if not isinstance(conflict_models, list) or len(conflict_models) < 2 or len(conflict_models) != len(set(conflict_models)) or any(item not in known_model_names for item in conflict_models):
                _add(issues, "error", "model-conflict-models", f"{item_path}.models", "must name at least two unique reviewed models")
            else:
                for left in range(len(conflict_models)):
                    for right in range(left + 1, len(conflict_models)):
                        covered_pairs.add(frozenset((conflict_models[left], conflict_models[right])))
            for key in ("applicability_boundary", "authoritative_value_basis", "explanation", "impact_on_conclusion"):
                if not _substantive(conflict.get(key), 8):
                    _add(issues, "error", "model-conflict-substance", f"{item_path}.{key}", "must be substantive")
            if conflict.get("resolved") is not True:
                _add(issues, "error", "model-conflict-unresolved", f"{item_path}.resolved", "model conflicts must be resolved before freeze")
    directional = [item for item in valid_models if item.get("status") != "inappropriate" and item.get("result_direction") in {"undervalued", "overvalued"}]
    for left in range(len(directional)):
        for right in range(left + 1, len(directional)):
            if directional[left].get("result_direction") == directional[right].get("result_direction"):
                continue
            pair = frozenset((directional[left].get("model"), directional[right].get("model")))
            if pair not in covered_pairs:
                _add(issues, "error", "model-conflict-missing", f"{path}.model_conflicts", f"opposing model directions require a conflict record for {sorted(pair)!r}")

    stability = value.get("conclusion_stability")
    stability_path = f"{path}.conclusion_stability"
    if not _required_keys(stability, {"cells", "verdict_flip", "action", "explanation"}, issues, stability_path, "conclusion-stability"):
        if not isinstance(stability, dict):
            return
    verdict = company.get("verdict") if isinstance(company.get("verdict"), dict) else {}
    current_status = verdict.get("valuation_status")
    empty_too_hard_grid = (
        too_hard
        and current_status == "无法判断"
        and stability.get("cells") == []
    )
    cells = stability.get("cells")
    observed_coordinates: set[tuple[float, float]] = set()
    cell_statuses: list[Any] = []
    if not isinstance(cells, list) or (not empty_too_hard_grid and len(cells) != 9):
        _add(issues, "error", "conclusion-stability-cells", f"{stability_path}.cells", "must contain exactly nine sensitivity cells")
        if not isinstance(cells, list):
            cells = []
    for index, cell in enumerate(cells):
        item_path = f"{stability_path}.cells[{index}]"
        if not _required_keys(cell, {"discount_rate", "terminal_growth", "valuation_status"}, issues, item_path, "stability-cell"):
            if not isinstance(cell, dict):
                continue
        if not _finite(cell.get("discount_rate")) or not _finite(cell.get("terminal_growth")):
            _add(issues, "error", "stability-cell-coordinate", item_path, "discount_rate and terminal_growth must be finite numbers")
        else:
            coordinate = (round(float(cell["discount_rate"]), 12), round(float(cell["terminal_growth"]), 12))
            if coordinate in observed_coordinates:
                _add(issues, "error", "stability-cell-duplicate", item_path, "duplicate sensitivity coordinate")
            observed_coordinates.add(coordinate)
        if cell.get("valuation_status") not in VALUATION_STATUSES:
            _add(issues, "error", "stability-cell-status", f"{item_path}.valuation_status", f"must be one of {sorted(VALUATION_STATUSES)!r}")
        cell_statuses.append(cell.get("valuation_status"))
    expected_coordinates = _scenario_coordinates(company)
    if not empty_too_hard_grid and (len(expected_coordinates) != 9 or observed_coordinates != expected_coordinates):
        _add(issues, "error", "conclusion-stability-grid", f"{stability_path}.cells", "must map one-to-one to company.json's DCF 3x3 sensitivity grid")
    actual_flip = any(status != current_status for status in cell_statuses)
    if not isinstance(stability.get("verdict_flip"), bool) or stability.get("verdict_flip") != actual_flip:
        _add(issues, "error", "conclusion-stability-flip", f"{stability_path}.verdict_flip", "must truthfully state whether any sensitivity cell changes the valuation status")
    action = stability.get("action")
    if action not in STABILITY_ACTIONS:
        _add(issues, "error", "conclusion-stability-action", f"{stability_path}.action", f"must be one of {sorted(STABILITY_ACTIONS)!r}")
    if actual_flip and action not in {"downgrade", "too_hard"}:
        _add(issues, "error", "conclusion-stability-action", f"{stability_path}.action", "a valuation-status flip requires downgrade or too_hard")
    if empty_too_hard_grid and action != "too_hard":
        _add(issues, "error", "conclusion-stability-action", f"{stability_path}.action", "an unavailable Too Hard valuation with no grid must use too_hard")
    if not _substantive(stability.get("explanation"), 10):
        _add(issues, "error", "conclusion-stability-explanation", f"{stability_path}.explanation", "must explain sensitivity and the resulting action")


def _direct_value(company: Mapping[str, Any], target_id: str) -> Any:
    if target_id == "company.valuation.market_price":
        return (company.get("valuation") or {}).get("market_price") if isinstance(company.get("valuation"), dict) else None
    if target_id == "company.valuation.diluted_shares":
        return (company.get("valuation") or {}).get("diluted_shares") if isinstance(company.get("valuation"), dict) else None
    if target_id == "company.valuation.market_cap":
        return (company.get("valuation") or {}).get("market_cap") if isinstance(company.get("valuation"), dict) else None
    if target_id == "company.valuation.enterprise_value":
        return (company.get("valuation") or {}).get("enterprise_value") if isinstance(company.get("valuation"), dict) else None
    return None


def _same_number(left: Any, right: Any) -> bool:
    if not _finite(left) or not _finite(right):
        return False
    return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-9)


def expected_dcf_audit_value(company: Mapping[str, Any], calculations: Any) -> dict[str, Any]:
    """Return the exact structured value a DCF assumption audit must reproduce."""
    valuation = company.get("valuation") if isinstance(company.get("valuation"), dict) else {}
    scenarios = valuation.get("dcf_scenarios") if isinstance(valuation.get("dcf_scenarios"), list) else []
    scenario_values = [
        {
            "name": item.get("name"),
            "revenue_growth": item.get("revenue_growth"),
            "margin": item.get("margin"),
            "discount_rate": item.get("discount_rate"),
            "terminal_growth": item.get("terminal_growth"),
        }
        for item in scenarios
        if isinstance(item, dict)
    ]
    scenario_values.sort(key=lambda item: str(item.get("name")))
    calculation_rows = calculations.get("calculations", []) if isinstance(calculations, dict) else []
    bridge_ids = sorted(
        item.get("id")
        for item in calculation_rows
        if isinstance(item, dict)
        and item.get("valuation_role") == "equity_value_bridge"
        and _nonblank(item.get("id"))
    )
    return {
        "scenarios": scenario_values,
        "equity_bridge_calculation_ids": bridge_ids,
    }


def _validate_source_audit(
    value: Any,
    company: Mapping[str, Any],
    calculations: Any,
    source_records: Mapping[str, Mapping[str, Any]],
    claims: Mapping[str, Mapping[str, Any]],
    passes: Sequence[Mapping[str, Any]],
    issues: list[ProcessIssue],
) -> None:
    path = "evidence-ledger.json.source_audit"
    if not _required_keys(value, {"audit_pass_id", "selection_seed", "checks"}, issues, path, "source-audit"):
        if not isinstance(value, dict):
            return
    audit_passes = {
        item.get("id"): item
        for item in passes
        if item.get("role") == "source_audit" and item.get("status") == "completed" and _nonblank(item.get("id"))
    }
    if value.get("audit_pass_id") not in audit_passes:
        _add(issues, "error", "source-audit-pass", f"{path}.audit_pass_id", "must resolve to a completed source_audit pass")
    expected_seed = canonical_company_sha256(company)
    selection_seed = value.get("selection_seed")
    if selection_seed != expected_seed:
        _add(issues, "error", "source-audit-seed", f"{path}.selection_seed", "must equal the canonical company.json SHA-256")
    checks = value.get("checks")
    if not isinstance(checks, list):
        _add(issues, "error", "source-audit-checks-shape", f"{path}.checks", "checks must be an array")
        return
    required = {
        "id", "target_type", "target_id", "criticality", "source_ids", "status", "checked_at",
        "location", "observed", "observed_value", "notes",
    }
    known_sources = set(source_records)
    check_ids: set[str] = set()
    by_target: dict[str, Mapping[str, Any]] = {}
    for index, check in enumerate(checks):
        item_path = f"{path}.checks[{index}]"
        if not _required_keys(check, required, issues, item_path, "source-audit-check"):
            if not isinstance(check, dict):
                continue
        check_id = check.get("id")
        if not _nonblank(check_id) or check_id in check_ids:
            _add(issues, "error", "source-audit-check-id", f"{item_path}.id", "check id must be nonblank and unique")
        else:
            check_ids.add(check_id)
        target_type = check.get("target_type")
        if target_type not in SOURCE_AUDIT_TARGET_TYPES:
            _add(issues, "error", "source-audit-target-type", f"{item_path}.target_type", f"must be one of {sorted(SOURCE_AUDIT_TARGET_TYPES)!r}")
        target_id = check.get("target_id")
        if not _nonblank(target_id):
            _add(issues, "error", "source-audit-target-id", f"{item_path}.target_id", "target_id must be nonblank")
        elif target_id in by_target:
            _add(issues, "error", "source-audit-target-duplicate", f"{item_path}.target_id", "each audit target must appear once")
        else:
            by_target[target_id] = check
        if check.get("criticality") not in {"critical", "ordinary"}:
            _add(issues, "error", "source-audit-criticality", f"{item_path}.criticality", "must be critical or ordinary")
        if not _known_ids(check.get("source_ids"), known_sources):
            _add(issues, "error", "source-audit-sources", f"{item_path}.source_ids", "must contain unique resolved source IDs")
        status = check.get("status")
        if status not in SOURCE_AUDIT_STATUSES:
            _add(issues, "error", "source-audit-status", f"{item_path}.status", f"must be one of {sorted(SOURCE_AUDIT_STATUSES)!r}")
        elif status != "pass":
            _add(issues, "error", "source-audit-not-passed", item_path, "source audit fail/unavailable must be resolved before freeze")
        if not _valid_datetime(check.get("checked_at")):
            _add(issues, "error", "source-audit-checked-at", f"{item_path}.checked_at", "must be an ISO 8601 date-time with timezone")
        if not _substantive(check.get("location"), 4):
            _add(issues, "error", "source-audit-location", f"{item_path}.location", "must save a precise source location")
        if not _substantive(check.get("observed"), 4):
            _add(issues, "error", "source-audit-observed", f"{item_path}.observed", "must describe what the independent re-open observed")
        notes = check.get("notes")
        if notes is not None and not _substantive(notes):
            _add(issues, "error", "source-audit-notes", f"{item_path}.notes", "must be null or substantive")
        if target_type == "claim" and target_id not in claims:
            _add(issues, "error", "source-audit-claim-target", f"{item_path}.target_id", "claim target must resolve to evidence-ledger claims")

    audit_pass = audit_passes.get(value.get("audit_pass_id"))
    if audit_pass is not None:
        declared_access = set(audit_pass.get("source_ids_accessed", []))
        checked_sources = {
            source_id
            for check in checks
            if isinstance(check, dict)
            for source_id in check.get("source_ids", [])
            if isinstance(source_id, str)
        }
        if not checked_sources.issubset(declared_access):
            _add(
                issues,
                "error",
                "source-audit-pass-sources",
                f"{path}.audit_pass_id",
                "the source_audit pass must declare every source reopened by its checks",
            )

    mandatory_targets = {
        "company.meta.identity": "company_field",
        "company.valuation.market_price": "company_field",
        "company.valuation.diluted_shares": "company_field",
        "company.valuation.market_cap": "company_field",
        "company.valuation.enterprise_value": "company_field",
        "calculation.starting_cash_flow": "calculation",
        "valuation.dcf_assumptions": "valuation_assumption",
    }
    classification = company.get("classification") if isinstance(company.get("classification"), dict) else {}
    if classification.get("accounting_profile") == "regulated_bank" or classification.get("returns_profile") in {"regulated_bank", "payments_credit"}:
        mandatory_targets["company.industry_metrics.regulatory_capital"] = "company_field"
    critical_claim_ids = {
        claim_id for claim_id, claim in claims.items() if claim.get("decision_relevance") == "critical"
    }
    for claim_id in critical_claim_ids:
        mandatory_targets[claim_id] = "claim"
    for target_id, target_type in mandatory_targets.items():
        check = by_target.get(target_id)
        if check is None:
            _add(issues, "error", "source-audit-critical-coverage", f"{path}.checks", f"missing mandatory audit target {target_id!r}")
            continue
        if check.get("target_type") != target_type or check.get("criticality") != "critical" or check.get("status") != "pass":
            _add(issues, "error", "source-audit-critical-result", f"{path}.checks", f"mandatory target {target_id!r} must be a passing critical {target_type} check")

    for target_id in (
        "company.valuation.market_price",
        "company.valuation.diluted_shares",
        "company.valuation.market_cap",
        "company.valuation.enterprise_value",
    ):
        check = by_target.get(target_id)
        expected = _direct_value(company, target_id)
        if check is not None and not _same_number(check.get("observed_value"), expected):
            _add(issues, "error", "source-audit-observed-value", f"{path}.checks", f"observed_value for {target_id!r} must equal company.json")

    start_records = [
        item for item in (calculations.get("calculations", []) if isinstance(calculations, dict) else [])
        if isinstance(item, dict) and item.get("valuation_role") == "starting_cash_flow"
    ]
    start_check = by_target.get("calculation.starting_cash_flow")
    if len(start_records) == 1 and start_check is not None and not _same_number(start_check.get("observed_value"), start_records[0].get("result")):
        _add(issues, "error", "source-audit-observed-value", f"{path}.checks", "starting-cash-flow observed_value must equal the calculation-ledger result")

    dcf_check = by_target.get("valuation.dcf_assumptions")
    if dcf_check is not None and dcf_check.get("observed_value") != expected_dcf_audit_value(company, calculations):
        _add(
            issues,
            "error",
            "source-audit-dcf-value",
            f"{path}.checks",
            "DCF audit observed_value must exactly reproduce scenario assumptions and equity-bridge calculation IDs",
        )

    identity_check = by_target.get("company.meta.identity")
    if identity_check is not None:
        observed_identity = identity_check.get("observed_value")
        meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
        expected_identity = {key: meta.get(key) for key in ("company_name_en", "ticker", "exchange")}
        if observed_identity is not None and (
            not isinstance(observed_identity, dict)
            or any(observed_identity.get(key) != expected for key, expected in expected_identity.items())
        ):
            _add(issues, "error", "source-audit-identity-value", f"{path}.checks", "identity observed_value must reproduce company_name_en, ticker and exchange")

    ordinary_claim_ids = [
        claim_id for claim_id, claim in claims.items() if claim.get("decision_relevance") != "critical"
    ]
    expected_sample = deterministic_ordinary_claim_sample(ordinary_claim_ids, expected_seed)
    for claim_id in expected_sample:
        check = by_target.get(claim_id)
        if check is None:
            _add(issues, "error", "source-audit-ordinary-sample", f"{path}.checks", f"missing deterministic ordinary-claim sample {claim_id!r}")
        elif check.get("target_type") != "claim" or check.get("criticality") != "ordinary" or check.get("status") != "pass":
            _add(issues, "error", "source-audit-ordinary-result", f"{path}.checks", f"sampled claim {claim_id!r} must be a passing ordinary claim check")


BUSINESS_ILLUSTRATIONS = {
    "company", "participant", "cardholder", "merchant", "travel", "gamer", "advertiser",
    "cloud", "creator", "distributor", "consumer", "supplier", "search-user",
    "developer", "bank", "social-user", "digital-buyer", "search-distribution",
}
GENERIC_BUSINESS_LABELS = {
    "客户", "用户", "产品与渠道", "生态伙伴", "合作伙伴", "公司",
    "customer", "customers", "user", "users", "offer & channels",
    "products & channels", "partners", "partner", "company", "ecosystem partners",
}
GENERIC_EXCHANGE_TYPES = {"money", "value", "data", "资金", "价值", "数据"}


def _specific_exchange_type(value: Any) -> bool:
    return _nonblank(value) and value.strip().casefold() not in GENERIC_EXCHANGE_TYPES


def validate_business_model(
    graph: Any,
    company: Mapping[str, Any],
    source_ids: set[str],
    mode: str = "full",
) -> list[ProcessIssue]:
    """Validate the frozen actor graph without inferring business relationships."""
    issues: list[ProcessIssue] = []
    root = "evidence-ledger.json.business_model"

    def fail(code: str, path: str, message: str) -> None:
        _add(issues, "error", "business-model-" + code, root + path, message)

    if graph is None:
        _add(issues, "warning" if mode == "audit" else "error", "business-model-missing",
             root, "a company-specific actor graph is required for new research handoff")
        return issues
    if not isinstance(graph, dict):
        fail("shape", "", "must be an object")
        return issues
    if graph.get("version") != "1.0":
        fail("version", ".version", "must equal 1.0")
    meta = company.get("meta") if isinstance(company.get("meta"), Mapping) else {}
    identity = graph.get("company_identity")
    identity_keys = {"company_name_en", "ticker", "exchange"}
    if not isinstance(identity, dict) or set(identity) != identity_keys or any(
        not _nonblank(identity.get(key)) or identity.get(key) != meta.get(key) for key in identity_keys
    ):
        fail("identity", ".company_identity", "must match this company's legal name, ticker and exchange")
    sankey = company.get("income_statement_sankey")
    fiscal_year = sankey.get("fiscal_year") if isinstance(sankey, Mapping) else None
    if not _nonblank(graph.get("period")) or graph.get("period") != fiscal_year:
        fail("period", ".period", "must match the same package's Sankey fiscal year")
    for key in ("notes", "notes_en"):
        if not _nonblank(graph.get(key)):
            fail("notes", "." + key, "must explain the diagram's business scope and limits")

    def identifier(value: Any) -> bool:
        return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value) is not None

    def sources(value: Any, path: str) -> None:
        if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value):
            fail("sources", path, "must be a nonempty array of source IDs")
        elif len(value) != len(set(value)) or any(x not in source_ids for x in value):
            fail("sources", path, "must contain unique, resolved company source IDs")

    actors = graph.get("actors")
    if not isinstance(actors, list) or len(actors) < 2:
        fail("actors", ".actors", "must contain the company and at least one actual counterparty")
        return issues
    actor_ids: set[str] = set()
    company_count = 0
    for index, actor in enumerate(actors):
        path = f".actors[{index}]"
        if not isinstance(actor, dict):
            fail("actor", path, "must be an object")
            continue
        actor_id = actor.get("id")
        if not identifier(actor_id) or actor_id in actor_ids:
            fail("actor-id", path + ".id", "must be a unique lowercase semantic ID")
        else:
            actor_ids.add(actor_id)
        for key in ("label", "label_en", "detail", "detail_en"):
            value = actor.get(key)
            if not _nonblank(value):
                fail("actor-text", path + "." + key, "must be a nonblank description of this actual actor")
            elif key.startswith("label") and value.strip().casefold() in GENERIC_BUSINESS_LABELS:
                fail("generic-label", path + "." + key, "use a specific company or counterparty name")
        illustration = actor.get("illustration")
        if not isinstance(illustration, str) or illustration not in BUSINESS_ILLUSTRATIONS:
            fail("illustration", path + ".illustration", "must use a supported semantic illustration key")
        if actor_id == "company":
            company_count += 1
            if illustration != "company":
                fail("company-illustration", path, "the company actor must use the company identity asset")
        elif illustration == "company":
            fail("company-illustration", path, "only the company actor may use the company identity asset")
        sources(actor.get("source_ids"), path + ".source_ids")
        if "official_logos" in actor:
            logos = actor["official_logos"]
            logo_path = path + ".official_logos"
            if not isinstance(logos, list):
                fail("official-logos", logo_path, "must be an array of sourced brand references")
                continue
            if actor_id == "company" and logos:
                fail("company-official-logos", logo_path, "the company actor must keep its canonical company identity asset")
            asset_ids: set[str] = set()
            for logo_index, logo in enumerate(logos):
                item_path = f"{logo_path}[{logo_index}]"
                if not isinstance(logo, dict) or set(logo) != {"asset_id", "brand_name", "brand_name_en", "source_ids"}:
                    fail("official-logo", item_path, "must contain only asset_id, brand_name, brand_name_en and source_ids; asset bytes and provenance belong downstream")
                    continue
                asset_id = logo.get("asset_id")
                if not identifier(asset_id) or asset_id in asset_ids:
                    fail("official-logo-id", item_path + ".asset_id", "must be a unique opaque lowercase asset key, not a URL or path")
                else:
                    asset_ids.add(asset_id)
                for key in ("brand_name", "brand_name_en"):
                    if not _nonblank(logo.get(key)):
                        fail("official-logo-brand", item_path + "." + key, "must name the actual official brand or product without replacing the role caption")
                sources(logo.get("source_ids"), item_path + ".source_ids")
    if company_count != 1:
        fail("company-count", ".actors", "must have exactly one actor with id company")
    flows = graph.get("flows")
    if not isinstance(flows, list) or not flows:
        fail("flows", ".flows", "must contain sourced directed relationships")
        return issues
    flow_ids: set[str] = set()
    neighbors = {actor_id: set() for actor_id in actor_ids}
    for index, flow in enumerate(flows):
        path = f".flows[{index}]"
        if not isinstance(flow, dict):
            fail("flow", path, "must be an object")
            continue
        flow_id = flow.get("id")
        if not identifier(flow_id) or flow_id in flow_ids:
            fail("flow-id", path + ".id", "must be a unique lowercase semantic ID")
        else:
            flow_ids.add(flow_id)
        source, target = flow.get("source"), flow.get("target")
        if not isinstance(source, str) or not isinstance(target, str) or source not in actor_ids or target not in actor_ids or source == target:
            fail("endpoints", path, "source and target must name two different actors")
        else:
            neighbors[source].add(target)
            neighbors[target].add(source)
        if flow.get("kind") not in ("money", "value", "data"):
            fail("flow-kind", path + ".kind", "must be money, value or data")
        if "exchange_type" not in flow:
            _add(issues, "warning" if mode == "audit" else "error", "business-model-exchange-type-missing",
                 root + path + ".exchange_type", "new handoffs must name the actual exchange beyond the legacy display kind")
        elif not _specific_exchange_type(flow.get("exchange_type")):
            fail("exchange-type", path + ".exchange_type", "must name the actual exchange; the vocabulary is open")
        for key in ("label", "label_en"):
            if not _nonblank(flow.get(key)):
                fail("flow-label", path + "." + key, "must describe the actual directed exchange")
        sources(flow.get("source_ids"), path + ".source_ids")
    reached: set[str] = set()
    pending = ["company"] if "company" in actor_ids else []
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(neighbors[current] - reached)
    if reached != actor_ids:
        fail("disconnected", "", "every actor must connect to the company through actual relationships")
    return issues


def canonical_business_model_sha256(graph: Mapping[str, Any]) -> str:
    """Bind the review to the entire graph, including labels and optional metadata."""
    payload = json.dumps(graph, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_business_model_coverage(
    coverage: Any,
    graph: Any,
    source_ids: set[str],
    passes: Any,
    mode: str = "full",
    *,
    declared: bool = True,
) -> list[ProcessIssue]:
    """Reconcile an independently researched candidate inventory with its graph.

    This checks traceability and review integrity, not whether researchers found
    every economic relationship. It never invents pairs, reverse edges or types.
    """
    issues: list[ProcessIssue] = []
    root = "evidence-ledger.json.business_model_coverage"

    def fail(code: str, path: str, message: str) -> None:
        _add(issues, "error", "business-model-coverage-" + code, root + path, message)

    if not declared:
        _add(issues, "warning" if mode == "audit" else "error", "business-model-coverage-missing", root,
             "historical relationship completeness is unverified; new handoffs require a reviewed candidate inventory")
        return issues
    if not isinstance(coverage, dict):
        fail("shape", "", "declared coverage must be an object")
        return issues
    if coverage.get("version") != "1.0":
        fail("version", ".version", "must equal 1.0")
    if not _nonblank(coverage.get("scope")):
        fail("scope", ".scope", "must explain the researched business scope and materiality boundary")
    if not isinstance(graph, dict):
        fail("graph", "", "coverage requires a valid business_model graph")
        return issues

    def identifier(value: Any) -> bool:
        return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value) is not None

    reviewed_source_ids: set[str] = set()

    def sources(value: Any, path: str) -> None:
        if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
            fail("sources", path, "must be a nonempty array of unique resolved source IDs")
        elif len(value) != len(set(value)) or any(item not in source_ids for item in value):
            fail("sources", path, "must contain unique source IDs from this company package")
        else:
            reviewed_source_ids.update(value)

    def source_locations(item: dict[str, Any], path: str) -> None:
        locations, ids = item.get("source_locations"), item.get("source_ids")
        if (not isinstance(locations, dict) or not isinstance(ids, list)
                or not all(isinstance(source_id, str) for source_id in ids)
                or set(locations) != set(ids)
                or not all(_nonblank(location) for location in locations.values())):
            fail("source-locations", path + ".source_locations",
                 "must map exactly every source_id to a nonblank precise page or section location")

    def records(value: Any, path: str) -> list[tuple[int, dict[str, Any]]]:
        if not isinstance(value, list) or not value:
            fail("collection", path, "must be a nonempty array")
            return []
        result: list[tuple[int, dict[str, Any]]] = []
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                fail("record", f"{path}[{index}]", "must be an object")
            else:
                result.append((index, item))
        return result

    actor_values = graph.get("actors")
    actors = {item["id"]: item for item in actor_values
              if isinstance(item, dict) and identifier(item.get("id"))} if isinstance(actor_values, list) else {}
    flow_values = graph.get("flows")
    flows = {item["id"]: item for item in flow_values
             if isinstance(item, dict) and identifier(item.get("id"))} if isinstance(flow_values, list) else {}

    participants: dict[str, dict[str, Any]] = {}
    mapped_actor_ids: set[str] = set()
    for index, item in records(coverage.get("participants"), ".participants"):
        path = f".participants[{index}]"
        candidate_id = item.get("id")
        if not identifier(candidate_id) or candidate_id in participants:
            fail("participant-id", path + ".id", "must be a unique lowercase candidate participant ID")
        else:
            participants[candidate_id] = item
        for key in ("label", "reason"):
            if not _nonblank(item.get(key)):
                fail("participant-text", path + "." + key, "must explain the actual participant and inclusion decision")
        disposition = item.get("disposition")
        actor_id = item.get("actor_id")
        if disposition in ("included", "aggregated"):
            if not isinstance(actor_id, str) or actor_id not in actors:
                fail("participant-actor", path + ".actor_id", "included or aggregated participants must map to an existing actor")
            else:
                mapped_actor_ids.add(actor_id)
        elif disposition in ("excluded", "unresolved"):
            if "actor_id" not in item or actor_id is not None:
                fail("participant-actor", path + ".actor_id", "excluded or unresolved participants must explicitly use null")
        else:
            fail("participant-disposition", path + ".disposition", "must be included, aggregated, excluded or unresolved")
        if disposition == "unresolved":
            fail("unresolved-participant", path, "resolve material participant gaps before formal handoff")
        sources(item.get("source_ids"), path + ".source_ids")
        source_locations(item, path)
    if set(actors) != mapped_actor_ids:
        fail("actor-omission", ".participants", "every graph actor must be represented in the candidate inventory")

    relationship_ids: set[str] = set()
    covered_flow_ids: set[str] = set()
    for index, item in records(coverage.get("relationships"), ".relationships"):
        path = f".relationships[{index}]"
        relationship_id = item.get("id")
        if not identifier(relationship_id) or relationship_id in relationship_ids:
            fail("relationship-id", path + ".id", "must be a unique lowercase candidate relationship ID")
        else:
            relationship_ids.add(relationship_id)
        candidate_source, candidate_target = item.get("source"), item.get("target")
        endpoints_valid = (
            isinstance(candidate_source, str) and isinstance(candidate_target, str)
            and candidate_source in participants and candidate_target in participants and candidate_source != candidate_target
        )
        if not endpoints_valid:
            fail("relationship-endpoints", path, "source and target must name two different candidate participants")
        if not _specific_exchange_type(item.get("exchange_type")):
            fail("exchange-type", path + ".exchange_type", "must name the actual exchange using an open vocabulary")
        if not _nonblank(item.get("reason")):
            fail("relationship-reason", path + ".reason", "must explain the evidence and drawing or exclusion decision")
        disposition, flow_id = item.get("disposition"), item.get("flow_id")
        if disposition == "drawn":
            if not isinstance(flow_id, str) or flow_id not in flows:
                fail("relationship-flow", path + ".flow_id", "a drawn relationship must resolve to an existing graph flow")
            else:
                covered_flow_ids.add(flow_id)
                flow = flows[flow_id]
                if endpoints_valid:
                    source_actor = participants[candidate_source].get("actor_id")
                    target_actor = participants[candidate_target].get("actor_id")
                    if (not isinstance(source_actor, str) or not isinstance(target_actor, str)
                            or source_actor != flow.get("source") or target_actor != flow.get("target")):
                        fail("relationship-direction", path, "mapped participant endpoints must match the directed graph flow exactly")
                if item.get("exchange_type") != flow.get("exchange_type"):
                    fail("relationship-type", path + ".exchange_type", "must equal the graph flow's actual exchange_type")
        elif disposition in ("excluded", "unresolved"):
            if "flow_id" not in item or flow_id is not None:
                fail("relationship-flow", path + ".flow_id", "excluded or unresolved relationships must explicitly use null")
        else:
            fail("relationship-disposition", path + ".disposition", "must be drawn, excluded or unresolved")
        if disposition == "unresolved":
            fail("unresolved-relationship", path, "resolve material relationship gaps before formal handoff")
        sources(item.get("source_ids"), path + ".source_ids")
        source_locations(item, path)
    if set(flows) != covered_flow_ids:
        fail("flow-omission", ".relationships", "every graph flow must have a drawn, sourced candidate relationship")

    stages: list[str] = []
    for index, item in records(coverage.get("value_logic"), ".value_logic"):
        path = f".value_logic[{index}]"
        stage = item.get("stage")
        if stage not in ("creation", "delivery", "capture"):
            fail("value-stage", path + ".stage", "must be creation, delivery or capture")
        else:
            stages.append(stage)
        if not _nonblank(item.get("explanation")):
            fail("value-explanation", path + ".explanation", "must explain this company's value mechanism")
        value_flow_ids = item.get("flow_ids")
        if (not isinstance(value_flow_ids, list) or not value_flow_ids
                or not all(isinstance(flow_id, str) for flow_id in value_flow_ids)
                or len(value_flow_ids) != len(set(value_flow_ids))
                or any(flow_id not in flows for flow_id in value_flow_ids)):
            fail("value-flows", path + ".flow_ids", "must contain nonempty unique references to graph flows")
        sources(item.get("source_ids"), path + ".source_ids")
    if sorted(stages) != ["capture", "creation", "delivery"]:
        fail("value-stage-coverage", ".value_logic", "must explain creation, delivery and capture exactly once each")

    review = coverage.get("review")
    if not isinstance(review, dict):
        fail("review", ".review", "must bind an independent completed review to the actual graph")
        return issues
    if not _nonblank(review.get("conclusion")):
        fail("review-conclusion", ".review.conclusion", "must record the independent review's conclusion and limits")
    try:
        expected_hash = canonical_business_model_sha256(graph)
    except (TypeError, ValueError, OverflowError):
        fail("graph-hash", ".review.graph_sha256", "graph must be canonical JSON without nonfinite values")
    else:
        if review.get("graph_sha256") != expected_hash:
            fail("graph-hash", ".review.graph_sha256", "must match SHA-256 of the entire canonical graph reviewed")
    pass_values = [item for item in passes if isinstance(item, dict)] if isinstance(passes, (list, tuple)) else []
    pass_id = review.get("pass_id")
    matches = [item for item in pass_values if isinstance(pass_id, str) and item.get("id") == pass_id]
    primary_actors = {item.get("actor_id") for item in pass_values
                      if item.get("role") == "primary_research" and _nonblank(item.get("actor_id"))}
    if len(matches) != 1:
        fail("review-pass", ".review.pass_id", "must reference one existing independent review pass")
    else:
        reviewer = matches[0]
        reviewer_actor = reviewer.get("actor_id")
        if (reviewer.get("role") not in ("adversarial_review", "source_audit")
                or reviewer.get("execution") not in ("isolated_agent", "isolated_context")
                or reviewer.get("status") != "completed" or not _nonblank(reviewer_actor)
                or reviewer_actor in primary_actors):
            fail("review-pass", ".review.pass_id", "must reference a completed isolated adversarial/source audit pass distinct from primary research")
        accessed = reviewer.get("source_ids_accessed")
        if (not isinstance(accessed, list) or not all(isinstance(item, str) for item in accessed)
                or not reviewed_source_ids.issubset(set(accessed))):
            fail("review-sources", ".review.pass_id", "the reviewer must declare access to every coverage source")
    return issues


def validate_research_process(
    evidence: Any,
    company: Mapping[str, Any],
    calculations: Any,
    source_records: Mapping[str, Mapping[str, Any]],
    mode: str,
    expected_fingerprint: Mapping[str, Any],
) -> list[ProcessIssue]:
    """Validate a current research execution record.

    ``mode='audit'`` accepts a legacy claims-only evidence ledger and returns a
    warning because the historical execution cannot be reconstructed.  A ledger
    declaring version 2.0 is always validated strictly, including in audit mode.
    New ``full`` and ``incremental`` packages must declare the complete v2 shape.
    """

    issues: list[ProcessIssue] = []
    path = "evidence-ledger.json"
    if mode not in {"full", "incremental", "audit"}:
        return [ProcessIssue("error", "research-process-mode", path, f"unsupported validation mode {mode!r}")]
    if not isinstance(evidence, dict):
        return [ProcessIssue("error", "research-process-ledger-shape", path, "evidence ledger must be an object")]
    if not isinstance(company, Mapping) or not isinstance(source_records, Mapping):
        return [ProcessIssue("error", "research-process-input-shape", path, "company and source_records must be mappings")]
    if not isinstance(expected_fingerprint, Mapping) or set(expected_fingerprint) != PROTOCOL_FINGERPRINT_KEYS:
        return [ProcessIssue("error", "expected-protocol-fingerprint", path, "validator supplied an invalid expected protocol fingerprint")]

    current_only_keys = LEDGER_ROOT_KEYS.difference({"claims"}) | {"business_model_coverage", "business_model_feedback"}
    declares_current = evidence.get("ledger_version") is not None or bool(current_only_keys.intersection(evidence))
    if mode == "audit" and not declares_current:
        _add(
            issues,
            "warning",
            "legacy-evidence-process-unverifiable",
            path,
            "legacy evidence ledger has no v2 execution record; audit can verify package artifacts but cannot reconstruct preflight, independent challenge or source re-open history",
        )
        return issues
    if evidence.get("ledger_version") != LEDGER_VERSION:
        _add(issues, "error", "evidence-ledger-version", f"{path}.ledger_version", f"must equal {LEDGER_VERSION!r}")
    missing = sorted(LEDGER_ROOT_KEYS.difference(evidence))
    if missing:
        _add(issues, "error", "research-process-ledger-required", path, f"missing required root keys {missing!r}")
        return issues

    raw_claims = evidence.get("claims")
    preliminary_claims = {
        item.get("id"): item
        for item in raw_claims if isinstance(raw_claims, list) and isinstance(item, dict) and _nonblank(item.get("id"))
    } if isinstance(raw_claims, list) else {}
    research_mode, _workflow_tier, passes = _validate_run(
        evidence.get("run"),
        preliminary_claims,
        source_records,
        mode,
        expected_fingerprint,
        issues,
    )
    claims = _validate_claim_extensions(
        raw_claims,
        set(source_records),
        passes,
        _is_too_hard(company),
        issues,
    )
    issues.extend(validate_business_model(evidence.get("business_model"), company, set(source_records), mode))
    issues.extend(validate_business_model_coverage(
        evidence.get("business_model_coverage"), evidence.get("business_model"), set(source_records), passes, mode,
        declared="business_model_coverage" in evidence,
    ))
    # Local import keeps the optional module's shared finding type acyclic.
    from validate_business_feedback import validate_business_model_feedback
    issues.extend(validate_business_model_feedback(
        evidence.get("business_model_feedback"), evidence.get("business_model"), set(source_records), passes,
        declared="business_model_feedback" in evidence,
    ))
    _validate_researchability(evidence.get("researchability"), issues)
    _validate_driver_map(evidence.get("business_driver_map"), set(source_records), issues)
    _validate_management_decisions(
        evidence.get("management_decision_ledger"),
        set(source_records),
        set(claims),
        issues,
    )
    _validate_thesis(evidence.get("thesis"), company, claims, research_mode, issues)
    _validate_valuation_review(evidence.get("valuation_review"), company, claims, _is_too_hard(company), issues)
    _validate_source_audit(
        evidence.get("source_audit"),
        company,
        calculations,
        source_records,
        claims,
        passes,
        issues,
    )
    return issues


__all__ = [
    "ProcessIssue",
    "canonical_company_sha256",
    "canonical_business_model_sha256",
    "deterministic_ordinary_claim_sample",
    "expected_dcf_audit_value",
    "validate_research_process",
    "validate_business_model_coverage",
]
