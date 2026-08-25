#!/usr/bin/env python3
"""Freeze a fully validated Doujiao research package with provenance and hashes."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from validate_research_package import (
    EXPECTED_SCHEMA_DRAFT,
    EXPECTED_SCHEMA_ID,
    EXPECTED_SCHEMA_PATH,
    EXPECTED_SPEC_REPOSITORY,
    FROZEN_HASH_FILES,
    INTEGRITY_PROFILE,
    PRIMARY_SOURCE_TYPES,
    extract_schema_version,
    file_sha256,
    git_blob_sha1_candidates,
    load_json,
    load_trusted_spec_lock,
    nonblank,
    report_payload,
    protocol_fingerprint,
    schema_sha256_candidates,
    validate_research_package,
    write_json,
)


TRUSTED_LOCK_PATH = Path(__file__).resolve().parents[1] / "references" / "trusted-spec-lock.json"
RESEARCH_IDENTITY_FIELDS = (
    "company_name_cn",
    "company_name_en",
    "ticker",
    "exchange",
    "report_currency",
)
RESEARCH_MANIFEST_FIELDS = RESEARCH_IDENTITY_FIELDS + ("data_as_of", "valuation_date", "source_version")
DCF_PARAMETER_FIELDS = ("revenue_growth", "margin", "discount_rate", "terminal_growth")


def valid_aware_datetime(value: Any) -> bool:
    if not nonblank(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_incremental_research_drift(
    current_root: Path,
    previous_root: Path,
) -> list[str]:
    """Reject silent thesis-state and DCF-assumption drift across frozen versions."""
    errors: list[str] = []
    try:
        current_evidence = load_json(current_root / "evidence-ledger.json")
        previous_evidence = load_json(previous_root / "evidence-ledger.json")
        current_company = load_json(current_root / "company.json")
        previous_company = load_json(previous_root / "company.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot read incremental drift inputs: {exc}"]
    if not all(isinstance(item, dict) for item in (current_evidence, previous_evidence, current_company, previous_company)):
        return ["incremental drift inputs must all be JSON objects"]

    current_run = current_evidence.get("run") if isinstance(current_evidence.get("run"), dict) else {}
    if current_run.get("research_mode") != "incremental":
        errors.append("incremental evidence run must declare research_mode incremental")

    current_thesis = current_evidence.get("thesis")
    previous_thesis = previous_evidence.get("thesis")
    if not isinstance(current_thesis, dict) or not isinstance(previous_thesis, dict):
        return ["incremental research requires structured thesis state in both current and predecessor evidence ledgers"]
    if current_thesis.get("overall_change") == "baseline":
        errors.append("incremental thesis overall_change cannot be baseline")

    def assumption_index(thesis: dict[str, Any], label: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        items = thesis.get("assumptions")
        if not isinstance(items, list):
            errors.append(f"{label} thesis assumptions must be an array")
            return result
        for item in items:
            if not isinstance(item, dict) or not nonblank(item.get("id")):
                errors.append(f"{label} thesis contains an invalid assumption record")
                continue
            if item["id"] in result:
                errors.append(f"{label} thesis repeats assumption id {item['id']!r}")
                continue
            result[item["id"]] = item
        return result

    current_assumptions = assumption_index(current_thesis, "current")
    previous_assumptions = assumption_index(previous_thesis, "previous")
    revision_text = json.dumps(current_thesis.get("revision_log", []), ensure_ascii=False, sort_keys=True)
    for assumption_id, previous in previous_assumptions.items():
        current = current_assumptions.get(assumption_id)
        if current is None:
            if assumption_id not in revision_text:
                errors.append(f"removed assumption {assumption_id!r} is absent from the incremental revision log")
            continue
        if current.get("prior_status") != previous.get("current_status"):
            errors.append(f"assumption {assumption_id!r} prior_status does not match the predecessor current_status")
        changed = current.get("current_status") != previous.get("current_status")
        if changed and current.get("change_type") in {None, "none", "wording", "market_price"}:
            errors.append(f"assumption {assumption_id!r} changed status without a substantive change_type")
        if changed and not current.get("evidence_claim_ids"):
            errors.append(f"assumption {assumption_id!r} changed status without new evidence claims")
    for assumption_id in sorted(set(current_assumptions) - set(previous_assumptions)):
        if assumption_id not in revision_text:
            errors.append(f"new assumption {assumption_id!r} is absent from the incremental revision log")

    def scenario_index(company: dict[str, Any]) -> dict[str, dict[str, Any]]:
        valuation = company.get("valuation") if isinstance(company.get("valuation"), dict) else {}
        scenarios = valuation.get("dcf_scenarios") if isinstance(valuation.get("dcf_scenarios"), list) else []
        return {
            str(item.get("name")): item
            for item in scenarios
            if isinstance(item, dict) and nonblank(item.get("name"))
        }

    previous_scenarios = scenario_index(previous_company)
    current_scenarios = scenario_index(current_company)
    recorded_changes = current_thesis.get("valuation_assumption_changes")
    if not isinstance(recorded_changes, list):
        errors.append("incremental thesis valuation_assumption_changes must be an array")
        recorded_changes = []
    change_index: dict[tuple[str, str], dict[str, Any]] = {}
    for item in recorded_changes:
        if not isinstance(item, dict):
            errors.append("incremental valuation assumption change must be an object")
            continue
        key = (str(item.get("scenario")), str(item.get("parameter")))
        if key in change_index:
            errors.append(f"incremental valuation assumption change is duplicated for {key!r}")
        change_index[key] = item

    actual_changes: set[tuple[str, str]] = set()
    for scenario_name in sorted(set(previous_scenarios) | set(current_scenarios)):
        previous = previous_scenarios.get(scenario_name)
        current = current_scenarios.get(scenario_name)
        if previous is None or current is None:
            errors.append(f"incremental DCF scenario set changed for {scenario_name!r}; use a full baseline or document a methodology migration")
            continue
        for parameter in DCF_PARAMETER_FIELDS:
            old_value = previous.get(parameter)
            new_value = current.get(parameter)
            if isinstance(old_value, (int, float)) and not isinstance(old_value, bool) and isinstance(new_value, (int, float)) and not isinstance(new_value, bool):
                changed = not math.isclose(float(old_value), float(new_value), rel_tol=1e-12, abs_tol=1e-12)
            else:
                changed = old_value != new_value
            key = (scenario_name, parameter)
            if not changed:
                continue
            actual_changes.add(key)
            record = change_index.get(key)
            if record is None:
                errors.append(f"DCF parameter drift for {scenario_name!r}.{parameter} is not recorded")
                continue
            if record.get("previous_value") != old_value or record.get("current_value") != new_value:
                errors.append(f"recorded DCF parameter values do not match {scenario_name!r}.{parameter}")
            if record.get("change_type") in {None, "none", "market_price", "wording"}:
                errors.append(f"DCF parameter drift for {scenario_name!r}.{parameter} lacks a substantive change_type")
            if not nonblank(record.get("reason")) or not record.get("evidence_claim_ids"):
                errors.append(f"DCF parameter drift for {scenario_name!r}.{parameter} lacks reason or evidence claims")
    for key in sorted(set(change_index) - actual_changes):
        errors.append(f"recorded valuation assumption change {key!r} does not correspond to an actual DCF parameter change")
    return errors


def verify_previous_manifest(
    path: Path,
    schema_path: Path,
    trusted_lock: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Verify a predecessor as a complete, immutable, trusted frozen package."""
    errors: list[str] = []
    # This check must happen on the caller-supplied path, before any resolve().
    if path.is_symlink() or not path.is_file():
        return None, ["previous manifest itself must be a non-symlink regular file"]
    if path.name != "research-manifest.json":
        errors.append("previous manifest must be named research-manifest.json")
    try:
        manifest = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, [f"cannot read previous manifest: {exc}"]
    if not isinstance(manifest, dict):
        return None, ["previous manifest must be an object"]
    if manifest.get("manifest_version") != "2.0" or manifest.get("status") != "frozen":
        errors.append("previous manifest requires manifest_version 2.0 and status frozen; v1 is audit-only")
    if manifest.get("human_review_status") != "accepted":
        errors.append("previous frozen package must have accepted human review")
    warning_acknowledged = manifest.get("warning_acknowledged")
    if not isinstance(warning_acknowledged, bool):
        errors.append("previous manifest warning_acknowledged must be boolean")
    if not valid_aware_datetime(manifest.get("frozen_at")):
        errors.append("previous manifest needs a timezone-aware frozen_at")

    trusted_schema = trusted_lock.get("company_schema") if isinstance(trusted_lock.get("company_schema"), dict) else {}
    specification = manifest.get("specification")
    if not isinstance(specification, dict):
        errors.append("previous manifest specification block is missing")
    else:
        expected_specification = {
            "repository": EXPECTED_SPEC_REPOSITORY,
            "ref": trusted_schema.get("ref"),
            "commit": trusted_schema.get("commit"),
            "schema_path": EXPECTED_SCHEMA_PATH,
            "schema_blob_sha1": trusted_schema.get("blob_sha1"),
            "schema_version": trusted_schema.get("schema_version"),
        }
        for key, expected in expected_specification.items():
            if specification.get(key) != expected:
                errors.append(f"previous manifest specification {key} does not match the trusted lock or Schema")
        if specification.get("schema_sha256") not in schema_sha256_candidates(schema_path):
            errors.append("previous manifest specification schema_sha256 differs beyond one transport-added final LF")
        if str(specification.get("schema_blob_sha1", "")) not in git_blob_sha1_candidates(schema_path):
            errors.append("previous manifest Schema blob does not match the supplied Schema bytes")
    if manifest.get("research_protocol") != trusted_lock.get("research_protocol"):
        errors.append("previous manifest research_protocol does not match the current Skill trust lock")
    if manifest.get("integrity_profile") != INTEGRITY_PROFILE:
        errors.append("previous manifest lacks the current execution integrity profile and is audit-only")
    if manifest.get("execution_integrity") != trusted_lock.get("execution_integrity"):
        errors.append("previous manifest execution_integrity does not match the complete current Skill release")

    validation = manifest.get("validation")
    if not isinstance(validation, dict):
        errors.append("previous manifest validation block is missing")
    else:
        error_count = validation.get("errors")
        warning_count = validation.get("warnings")
        if (
            validation.get("mode") != "full"
            or not isinstance(error_count, int)
            or isinstance(error_count, bool)
            or error_count != 0
        ):
            errors.append("previous manifest must record full validation with zero errors")
        if not nonblank(validation.get("validator")):
            errors.append("previous manifest validation must identify its validator")
        if not isinstance(warning_count, int) or isinstance(warning_count, bool) or warning_count < 0:
            errors.append("previous manifest validation warnings must be a non-negative integer")
        elif warning_count > 0 and warning_acknowledged is not True:
            errors.append("previous manifest warnings were not acknowledged")
        expected_validation_integrity = {
            "integrity_profile": INTEGRITY_PROFILE,
            "validator_sha256": protocol_fingerprint(trusted_lock).get("validator_sha256"),
            "toolchain_digest_sha256": trusted_lock.get("execution_integrity", {}).get("toolchain_digest_sha256"),
            "protocol_fingerprint": protocol_fingerprint(trusted_lock),
        }
        for key, expected in expected_validation_integrity.items():
            if validation.get(key) != expected:
                errors.append(f"previous manifest validation {key} does not match the current locked execution")

    update_mode = manifest.get("update_mode")
    if update_mode not in {"full", "incremental"}:
        errors.append("previous manifest update_mode must be full or incremental")
    if update_mode == "incremental":
        transition = manifest.get("incremental_transition")
        if not isinstance(transition, dict):
            errors.append("previous incremental manifest is missing verified transition provenance")
        else:
            if re.fullmatch(r"[0-9a-f]{64}", str(transition.get("previous_manifest_sha256", ""))) is None:
                errors.append("previous incremental manifest has an invalid predecessor manifest hash")
            if not nonblank(transition.get("official_trigger_source_id")):
                errors.append("previous incremental manifest is missing its official trigger source ID")
            transition_research = transition.get("previous_research")
            if not isinstance(transition_research, dict):
                errors.append("previous incremental manifest is missing predecessor research identity")
            else:
                for key in RESEARCH_IDENTITY_FIELDS:
                    if not nonblank(transition_research.get(key)):
                        errors.append(f"previous incremental manifest predecessor identity {key} must be nonblank")
                try:
                    date.fromisoformat(transition_research.get("data_as_of", ""))
                except (TypeError, ValueError):
                    errors.append("previous incremental manifest predecessor data_as_of must be a valid ISO date")

    entries = manifest.get("files")
    if not isinstance(entries, list):
        errors.append("previous manifest files must be an array")
        entries = []
    root = path.parent.resolve()
    gap_path = path.parent / "schema-gap-report.md"
    expected_paths = set(FROZEN_HASH_FILES)
    if gap_path.exists() or gap_path.is_symlink():
        expected_paths.add("schema-gap-report.md")
        if gap_path.is_symlink() or not gap_path.is_file():
            errors.append("previous optional schema-gap-report.md must be a non-symlink regular file")
        else:
            try:
                if not gap_path.read_text(encoding="utf-8").strip():
                    errors.append("previous optional schema-gap-report.md must be nonempty")
            except (OSError, UnicodeError) as exc:
                errors.append(f"cannot read previous schema-gap-report.md: {exc}")

    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not nonblank(entry.get("path")):
            errors.append(f"previous manifest file entry {index} is invalid")
            continue
        relative = entry["path"]
        if relative in seen:
            errors.append(f"previous manifest repeats {relative!r}")
        seen.add(relative)
        relative_path = Path(relative)
        if relative_path.is_absolute() or len(relative_path.parts) != 1 or relative_path.name != relative:
            errors.append(f"previous manifest path is not a safe package-local filename: {relative!r}")
            continue
        candidate = path.parent / relative
        if candidate.is_symlink():
            errors.append(f"previous frozen file is a symlink: {relative}")
            continue
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            errors.append(f"previous file escapes its package: {relative}")
            continue
        if not candidate.is_file():
            errors.append(f"previous frozen file is missing: {relative}")
            continue
        recorded_hash = entry.get("sha256")
        recorded_size = entry.get("size_bytes")
        if re.fullmatch(r"[0-9a-f]{64}", str(recorded_hash)) is None:
            errors.append(f"previous frozen file has an invalid SHA-256: {relative}")
        if not isinstance(recorded_size, int) or isinstance(recorded_size, bool) or recorded_size < 0:
            errors.append(f"previous frozen file has an invalid size: {relative}")
        if recorded_hash != file_sha256(candidate) or recorded_size != candidate.stat().st_size:
            errors.append(f"previous frozen file hash or size changed: {relative}")

    if seen != expected_paths:
        errors.append(f"previous manifest must hash exactly {sorted(expected_paths)!r}")

    previous_company_path = path.parent / "company.json"
    if previous_company_path.is_symlink() or not previous_company_path.is_file():
        errors.append("previous company.json must be a non-symlink regular file")
        previous_company = None
    else:
        try:
            previous_company = load_json(previous_company_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read previous company.json: {exc}")
            previous_company = None
    research = manifest.get("research")
    if not isinstance(research, dict):
        errors.append("previous manifest research identity block is missing")
    elif not isinstance(previous_company, dict):
        errors.append("previous company.json must be an object")
    else:
        previous_meta = previous_company.get("meta") if isinstance(previous_company.get("meta"), dict) else {}
        for key in RESEARCH_MANIFEST_FIELDS:
            if research.get(key) != previous_meta.get(key):
                errors.append(f"previous manifest research {key} does not match previous company.json")
        for key in RESEARCH_IDENTITY_FIELDS + ("source_version",):
            if not nonblank(research.get(key)):
                errors.append(f"previous manifest research {key} must be nonblank")
        for key in ("data_as_of", "valuation_date"):
            try:
                date.fromisoformat(research.get(key, ""))
            except (TypeError, ValueError):
                errors.append(f"previous manifest research {key} must be a valid ISO date")
        if previous_meta.get("schema_version") != trusted_schema.get("schema_version"):
            errors.append("previous company.json schema_version does not match the trusted lock; rebuild it as a new full Schema 2.0 baseline before incremental updates")

    validation_report_path = path.parent / "validation-report.json"
    if validation_report_path.is_symlink() or not validation_report_path.is_file():
        errors.append("previous validation-report.json must be a non-symlink regular file")
    else:
        try:
            validation_report = load_json(validation_report_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read previous validation-report.json: {exc}")
        else:
            if not isinstance(validation_report, dict):
                errors.append("previous validation-report.json must be an object")
            elif isinstance(validation, dict):
                report_errors = validation_report.get("errors")
                report_warnings = validation_report.get("warnings")
                if (
                    validation_report.get("mode") != "full"
                    or not isinstance(report_errors, int)
                    or isinstance(report_errors, bool)
                    or report_errors != 0
                ):
                    errors.append("previous validation-report.json must record full validation with zero errors")
                if (
                    not isinstance(report_warnings, int)
                    or isinstance(report_warnings, bool)
                    or report_warnings < 0
                ):
                    errors.append("previous validation-report.json warnings must be a non-negative integer")
                for key in (
                    "validator",
                    "mode",
                    "errors",
                    "warnings",
                    "integrity_profile",
                    "validator_sha256",
                    "toolchain_digest_sha256",
                    "protocol_fingerprint",
                ):
                    if validation.get(key) != validation_report.get(key):
                        errors.append(f"previous manifest validation {key} does not match validation-report.json")

    # Never trust the predecessor's self-reported zero-error result. Re-run the
    # current full gate after its immutable files, protocol, and Schema anchor
    # have been verified, then reconcile the fresh counts with the frozen record.
    try:
        fresh_findings = validate_research_package(path.parent, schema_path, "full")
    except (OSError, ValueError) as exc:
        errors.append(f"cannot run fresh full validation on previous package: {exc}")
    else:
        fresh_errors = [item for item in fresh_findings if item.severity == "error"]
        fresh_warnings = [item for item in fresh_findings if item.severity == "warning"]
        if fresh_errors:
            codes = ", ".join(sorted({item.code for item in fresh_errors}))
            errors.append(f"previous package fresh full validation failed: {codes}")
        if isinstance(validation, dict):
            if validation.get("errors") != len(fresh_errors) or validation.get("warnings") != len(fresh_warnings):
                errors.append("previous manifest validation counts do not match fresh full validation")
        if fresh_warnings and warning_acknowledged is not True:
            errors.append("previous package fresh validation warnings were not acknowledged")
    return manifest, errors


def validate_incremental_transition(
    root: Path,
    previous_path: Path,
    official_trigger_source_id: str,
    schema_path: Path,
    trusted_lock: dict[str, Any],
) -> tuple[list[str], dict[str, Any] | None]:
    previous, errors = verify_previous_manifest(previous_path, schema_path, trusted_lock)
    if previous is None:
        return errors, None
    try:
        company = load_json(root / "company.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return errors + [f"cannot read current company.json: {exc}"], None
    if not isinstance(company, dict):
        return errors + ["current company.json must be an object"], None
    meta = company.get("meta") if isinstance(company.get("meta"), dict) else {}
    previous_research = previous.get("research") if isinstance(previous.get("research"), dict) else {}
    for key in ("company_name_cn", "company_name_en", "ticker", "exchange", "report_currency"):
        if meta.get(key) != previous_research.get(key):
            errors.append(f"incremental identity mismatch for {key}")
    for key in ("data_as_of", "valuation_date"):
        try:
            current_date = date.fromisoformat(meta.get(key, ""))
            old_date = date.fromisoformat(previous_research.get(key, ""))
        except (TypeError, ValueError):
            errors.append(f"cannot compare incremental {key}")
            continue
        if key == "data_as_of" and current_date <= old_date:
            errors.append("incremental data_as_of must be newer than the previous frozen version")
        if key == "valuation_date" and current_date < old_date:
            errors.append("incremental valuation_date cannot move backward")
    sources = company.get("sources") if isinstance(company.get("sources"), list) else []
    trigger = next((item for item in sources if isinstance(item, dict) and item.get("id") == official_trigger_source_id), None)
    if not isinstance(trigger, dict):
        errors.append("official trigger source ID is absent from current sources")
    else:
        if trigger.get("source_type") not in PRIMARY_SOURCE_TYPES or not nonblank(trigger.get("url")):
            errors.append("incremental trigger must be a primary official source with a URL")
        try:
            published = date.fromisoformat(trigger.get("published_at", ""))
            prior_data = date.fromisoformat(previous_research.get("data_as_of", ""))
            if published <= prior_data:
                errors.append("official trigger publication is not newer than the previous data date")
        except (TypeError, ValueError):
            errors.append("official trigger needs a valid published_at date")
    reporting = company.get("reporting") if isinstance(company.get("reporting"), dict) else {}
    latest = reporting.get("latest_report") if isinstance(reporting.get("latest_report"), dict) else {}
    if latest.get("date_status") != "official" or official_trigger_source_id not in latest.get("source_ids", []):
        errors.append("latest_report must be official and cite the incremental trigger source")
    errors.extend(validate_incremental_research_drift(root, previous_path.parent))
    transition = {
        "previous_manifest_sha256": file_sha256(previous_path),
        "previous_research": {
            key: previous_research.get(key)
            for key in RESEARCH_IDENTITY_FIELDS + ("data_as_of",)
        },
        "official_trigger_source_id": official_trigger_source_id,
    }
    return errors, transition


def build_manifest(
    root: Path,
    schema_path: Path,
    schema_commit: str,
    schema_ref: str,
    schema_blob_sha: str,
    research_protocol: dict[str, Any],
    update_mode: str,
    validation: dict[str, Any],
    human_reviewed: bool,
    warning_acknowledged: bool,
    incremental_transition: dict[str, Any] | None = None,
    execution_integrity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(research_protocol, dict) or not isinstance(execution_integrity, dict):
        raise ValueError("manifest requires locked research_protocol and execution_integrity objects")
    expected_validation = {
        "mode": "full",
        "errors": 0,
        "integrity_profile": INTEGRITY_PROFILE,
        "toolchain_digest_sha256": execution_integrity.get("toolchain_digest_sha256"),
    }
    for key, expected in expected_validation.items():
        if validation.get(key) != expected:
            raise ValueError(f"manifest validation {key} does not match the locked full-validation contract")
    fingerprint = validation.get("protocol_fingerprint")
    if (
        not isinstance(fingerprint, dict)
        or fingerprint.get("execution_bundle_digest_sha256") != execution_integrity.get("bundle_digest_sha256")
        or fingerprint.get("research_protocol_digest_sha256") != research_protocol.get("digest_sha256")
    ):
        raise ValueError("manifest validation protocol_fingerprint does not match the locked protocol and execution bundle")
    company = load_json(root / "company.json")
    schema = load_json(schema_path)
    meta = company.get("meta", {}) if isinstance(company, dict) else {}
    names = list(FROZEN_HASH_FILES)
    if (root / "schema-gap-report.md").is_file():
        names.append("schema-gap-report.md")
    files = [
        {"path": name, "sha256": file_sha256(root / name), "size_bytes": (root / name).stat().st_size}
        for name in names
    ]
    manifest = {
        "manifest_version": "2.0",
        "status": "frozen",
        "human_review_status": "accepted" if human_reviewed else "pending",
        "warning_acknowledged": warning_acknowledged,
        "frozen_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "specification": {
            "repository": EXPECTED_SPEC_REPOSITORY,
            "ref": schema_ref,
            "commit": schema_commit,
            "schema_path": EXPECTED_SCHEMA_PATH,
            "schema_sha256": file_sha256(schema_path),
            "schema_blob_sha1": schema_blob_sha,
            "schema_version": extract_schema_version(schema),
        },
        "research_protocol": research_protocol,
        "integrity_profile": INTEGRITY_PROFILE,
        "execution_integrity": execution_integrity,
        "research": {
            "company_name_cn": meta.get("company_name_cn"),
            "company_name_en": meta.get("company_name_en"),
            "ticker": meta.get("ticker"),
            "exchange": meta.get("exchange"),
            "report_currency": meta.get("report_currency"),
            "data_as_of": meta.get("data_as_of"),
            "valuation_date": meta.get("valuation_date"),
            "source_version": meta.get("source_version"),
        },
        "update_mode": update_mode,
        "validation": {
            "validator": validation.get("validator"),
            "mode": validation.get("mode"),
            "errors": validation.get("errors"),
            "warnings": validation.get("warnings"),
            "integrity_profile": validation.get("integrity_profile"),
            "validator_sha256": validation.get("validator_sha256"),
            "toolchain_digest_sha256": validation.get("toolchain_digest_sha256"),
            "protocol_fingerprint": validation.get("protocol_fingerprint"),
        },
        "files": files,
    }
    if update_mode == "incremental":
        if incremental_transition is None:
            raise ValueError("incremental manifest requires verified predecessor provenance")
        manifest["incremental_transition"] = incremental_transition
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Research package root")
    parser.add_argument("--schema", type=Path, required=True, help="Locked company.schema.json")
    parser.add_argument("--schema-blob-sha", required=True, help="Blob SHA returned for the locked Schema at the resolved commit")
    parser.add_argument(
        "--schema-commit",
        "--spec-commit",
        dest="schema_commit",
        required=True,
        help="Locked 40-character Schema commit SHA (--spec-commit remains a compatibility alias)",
    )
    parser.add_argument("--mode", choices=("full", "incremental"), default="full")
    parser.add_argument("--previous-manifest", type=Path, help="Required frozen predecessor for incremental mode")
    parser.add_argument("--official-trigger-source-id", help="Required new official source ID for incremental mode")
    parser.add_argument("--allow-warnings", action="store_true", help="Freeze only after warnings and their impact were reviewed")
    parser.add_argument("--human-reviewed", action="store_true", help="Mark accepted only after a real human review")
    args = parser.parse_args()

    if args.root.is_symlink() or args.schema.is_symlink():
        parser.error("package root and Schema cannot be symlinks")
    root, schema_path = args.root.resolve(), args.schema.resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    if not schema_path.is_file():
        parser.error(f"schema does not exist: {schema_path}")
    if re.fullmatch(r"[0-9a-fA-F]{40}", args.schema_commit) is None:
        parser.error("--schema-commit must be an exact 40-character SHA")
    if re.fullmatch(r"[0-9a-fA-F]{40}", args.schema_blob_sha) is None:
        parser.error("--schema-blob-sha must be an exact 40-character blob SHA")
    try:
        trusted_lock = load_json(TRUSTED_LOCK_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"cannot read bundled trusted specification lock: {exc}")
    if not isinstance(trusted_lock, dict):
        parser.error("bundled trusted specification lock is invalid")
    lock_findings: list[Any] = []
    validated_lock = load_trusted_spec_lock(lock_findings)
    if validated_lock is None:
        parser.error("bundled v3 trust lock or local research execution files failed integrity validation")
    trusted_lock = validated_lock
    trusted_schema = trusted_lock.get("company_schema") if isinstance(trusted_lock.get("company_schema"), dict) else {}
    if (
        trusted_lock.get("lock_version") != "3.0"
        or trusted_schema.get("repository") != EXPECTED_SPEC_REPOSITORY
        or trusted_schema.get("ref") != "main"
        or trusted_schema.get("commit") != args.schema_commit.lower()
        or trusted_schema.get("path") != EXPECTED_SCHEMA_PATH
        or trusted_schema.get("blob_sha1") != args.schema_blob_sha.lower()
        or not isinstance(trusted_lock.get("research_protocol"), dict)
        or not isinstance(trusted_lock.get("execution_integrity"), dict)
    ):
        parser.error("Schema commit/blob, research protocol, or execution bundle is not approved by this Skill release's v3 trust lock")
    try:
        schema = load_json(schema_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"cannot read Schema: {exc}")
    if not isinstance(schema, dict) or schema.get("$schema") != EXPECTED_SCHEMA_DRAFT or schema.get("$id") != EXPECTED_SCHEMA_ID:
        parser.error("Schema identity is not the authoritative Doujiao Draft 2020-12 contract")
    if extract_schema_version(schema) != trusted_schema.get("schema_version"):
        parser.error("Schema version differs from the trusted Skill release lock")
    actual_blobs = git_blob_sha1_candidates(schema_path)
    if args.schema_blob_sha.lower() not in actual_blobs:
        parser.error(f"local Schema blob candidates {sorted(actual_blobs)} do not match --schema-blob-sha")

    manifest_path = root / "research-manifest.json"
    if manifest_path.exists() or manifest_path.is_symlink():
        print("Refusing to modify a package that already has a manifest; create a new version directory.", file=sys.stderr)
        return 1
    for name in FROZEN_HASH_FILES + ("schema-gap-report.md",):
        path = root / name
        if path.is_symlink():
            print(f"Refusing symlinked package file: {name}", file=sys.stderr)
            return 1

    incremental_transition: dict[str, Any] | None = None
    if args.mode == "incremental":
        if args.previous_manifest is None or not args.official_trigger_source_id:
            parser.error("incremental mode requires --previous-manifest and --official-trigger-source-id")
        # Preserve the supplied path so a symlink cannot be hidden by resolve().
        transition_errors, incremental_transition = validate_incremental_transition(
            root,
            args.previous_manifest,
            args.official_trigger_source_id,
            schema_path,
            trusted_lock,
        )
        if transition_errors:
            print(json.dumps({"incremental_transition_errors": transition_errors}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
    elif args.previous_manifest is not None or args.official_trigger_source_id:
        parser.error("incremental transition arguments are only valid with --mode incremental")

    # Every final package, including an incremental update, must pass the complete gate.
    findings = validate_research_package(root, schema_path, "full")
    validation = report_payload(root, schema_path, "full", findings)
    validation_path = root / "validation-report.json"
    try:
        write_json(validation_path, validation)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if validation["errors"]:
        print(json.dumps(validation, ensure_ascii=False, indent=2), file=sys.stderr)
        print("Freeze refused because blocking validation errors remain.", file=sys.stderr)
        return 1
    if validation["warnings"] and not args.allow_warnings:
        print(json.dumps(validation, ensure_ascii=False, indent=2), file=sys.stderr)
        print("Freeze refused until warnings are reviewed; use --allow-warnings only after documenting their impact.", file=sys.stderr)
        return 1

    manifest = build_manifest(
        root=root,
        schema_path=schema_path,
        schema_commit=args.schema_commit.lower(),
        schema_ref=trusted_schema["ref"],
        schema_blob_sha=args.schema_blob_sha.lower(),
        research_protocol=trusted_lock["research_protocol"],
        execution_integrity=trusted_lock["execution_integrity"],
        update_mode=args.mode,
        validation=validation,
        human_reviewed=args.human_reviewed,
        warning_acknowledged=args.allow_warnings,
        incremental_transition=incremental_transition,
    )
    try:
        write_json(manifest_path, manifest)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    post_findings = validate_research_package(root, schema_path, "full")
    post_errors = [item for item in post_findings if item.severity == "error"]
    if post_errors:
        manifest_path.unlink(missing_ok=True)
        print(json.dumps([item.__dict__ for item in post_errors], ensure_ascii=False, indent=2), file=sys.stderr)
        print("Freeze verification failed; the manifest was removed.", file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
