#!/usr/bin/env python3
"""Create a fail-closed GitHub archive plan for an accepted frozen research package."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from freeze_research import TRUSTED_LOCK_PATH, verify_previous_manifest
from validate_research_package import file_sha256, load_json, validate_research_package, write_json


TARGET_REPOSITORY = "bits-bean/doujiao-value-system"
TARGET_BRANCH = "main"
SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
VERSION_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}(?:-v(?:[2-9]|[1-9]\d+))?")
SHA1_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
IDENTITY_FIELDS = ("company_name_cn", "company_name_en", "ticker", "exchange")
SENSITIVE_PATTERNS = (
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|-----BEGIN PGP PRIVATE KEY BLOCK-----"),
    ),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("authorization-header", re.compile(r"(?i)\bauthorization\s*:\s*(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}")),
    (
        "assigned-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|token|secret|password)\b\s*[=:]\s*[\"']?[A-Za-z0-9_./+\-]{16,}"
        ),
    ),
    (
        "signed-url",
        re.compile(
            r"(?i)https?://\S+[?&](?:x-amz-signature|x-amz-credential|signature|sig|token|access_token|key|sharedaccesssignature)="
        ),
    ),
)


class ArchivePlanError(ValueError):
    """Raised when a package cannot be safely planned for GitHub archival."""


def _safe_regular_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ArchivePlanError(f"{label} must be a non-symlink regular file")
    return path.resolve()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ArchivePlanError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArchivePlanError(f"{label} must be a JSON object")
    return payload


def _meta(company: dict[str, Any], label: str) -> dict[str, Any]:
    meta = company.get("meta")
    if not isinstance(meta, dict):
        raise ArchivePlanError(f"{label} lacks a meta object")
    return meta


def _iso_date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ArchivePlanError(f"{label} must be an ISO date") from exc


def canonical_action(
    new_company_path: Path,
    *,
    existing_company_path: Path | None,
    canonical_absent: bool,
    version: str,
    confirm_same_date_revision: bool,
) -> str:
    """Return create/update/noop/preflight-required after monotonicity checks."""
    if existing_company_path is not None and canonical_absent:
        raise ArchivePlanError("existing canonical file and canonical-absent are mutually exclusive")
    if canonical_absent:
        return "create"
    if existing_company_path is None:
        return "remote-preflight-required"

    existing_path = _safe_regular_file(existing_company_path, "existing canonical company.json")
    if new_company_path.read_bytes() == existing_path.read_bytes():
        return "noop"

    new_company = _read_object(new_company_path, "new company.json")
    existing_company = _read_object(existing_path, "existing canonical company.json")
    new_meta = _meta(new_company, "new company.json")
    existing_meta = _meta(existing_company, "existing canonical company.json")

    for field in IDENTITY_FIELDS + ("schema_version",):
        if new_meta.get(field) != existing_meta.get(field):
            raise ArchivePlanError(f"canonical company.json conflicts on {field}")

    new_date = _iso_date(new_meta.get("data_as_of"), "new company.json meta.data_as_of")
    existing_date = _iso_date(existing_meta.get("data_as_of"), "existing company.json meta.data_as_of")
    new_valuation = _iso_date(new_meta.get("valuation_date"), "new company.json meta.valuation_date")
    existing_valuation = _iso_date(
        existing_meta.get("valuation_date"),
        "existing company.json meta.valuation_date",
    )
    if new_date < existing_date:
        raise ArchivePlanError("canonical company.json would roll back data_as_of")
    if new_valuation < existing_valuation:
        raise ArchivePlanError("canonical company.json would roll back valuation_date")
    if new_date == existing_date:
        if not confirm_same_date_revision or re.search(r"-v[1-9]\d*$", version) is None:
            raise ArchivePlanError(
                "canonical company.json has different content for the same data_as_of; "
                "use a -vN version and explicit revision confirmation"
            )
        return "update-confirmed-revision"
    return "update"


def scan_sensitive_material(paths: list[Path]) -> None:
    findings: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ArchivePlanError(f"cannot safely inspect publication file {path.name}: {exc}") from exc
        decoded = unquote(text)
        for code, pattern in SENSITIVE_PATTERNS:
            if pattern.search(text) or (decoded != text and pattern.search(decoded)):
                findings.append(f"{path.name}:{code}")
    if findings:
        raise ArchivePlanError(f"sensitive material scan failed: {', '.join(sorted(findings))}")


def snapshot_action(
    snapshot_root: str,
    local_files: list[dict[str, Any]],
    remote_state: dict[str, Any] | None,
) -> tuple[str, str | None]:
    """Resolve create/noop/conflict from a connector-produced remote directory state."""
    if remote_state is None:
        return "remote-preflight-required", None
    if remote_state.get("repository") != TARGET_REPOSITORY or remote_state.get("branch") != TARGET_BRANCH:
        raise ArchivePlanError("remote snapshot state has the wrong repository or branch")
    if remote_state.get("root") != snapshot_root:
        raise ArchivePlanError("remote snapshot state is for a different version path")
    base_head = str(remote_state.get("base_head", ""))
    if SHA1_PATTERN.fullmatch(base_head) is None:
        raise ArchivePlanError("remote snapshot state lacks an exact base_head")
    exists = remote_state.get("exists")
    if not isinstance(exists, bool):
        raise ArchivePlanError("remote snapshot state exists must be boolean")
    remote_files = remote_state.get("files")
    if not isinstance(remote_files, list):
        raise ArchivePlanError("remote snapshot state files must be an array")
    if not exists:
        if remote_files:
            raise ArchivePlanError("absent remote snapshot cannot contain files")
        return "create", base_head

    expected = {
        Path(item["target_path"]).name: (item["sha256"], item["size_bytes"])
        for item in local_files
    }
    actual: dict[str, tuple[str, int]] = {}
    for entry in remote_files:
        if not isinstance(entry, dict):
            raise ArchivePlanError("remote snapshot contains an invalid file entry")
        name = entry.get("path")
        sha256 = entry.get("sha256")
        size = entry.get("size_bytes")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or SHA256_PATTERN.fullmatch(str(sha256)) is None
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or name in actual
        ):
            raise ArchivePlanError("remote snapshot contains an unsafe or malformed file entry")
        actual[name] = (str(sha256), size)
    if actual == expected:
        return "noop", base_head
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(name for name in set(expected) & set(actual) if expected[name] != actual[name])
    raise ArchivePlanError(
        f"immutable snapshot conflict at {snapshot_root}: missing={missing}, extra={extra}, changed={changed}"
    )


def build_archive_plan(
    root: Path,
    schema_path: Path,
    *,
    company_slug: str,
    version: str,
    strategy: str,
    promotion: str = "archive-only",
    write_authorized: bool = False,
    promotion_authorized: bool = False,
    direct_main_authorized: bool = False,
    remote_snapshot_state: dict[str, Any] | None = None,
    existing_company_path: Path | None = None,
    existing_company_head: str | None = None,
    canonical_absent: bool = False,
    confirm_same_date_revision: bool = False,
    trusted_lock: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise ArchivePlanError("research package root must be a non-symlink directory")
    if schema_path.is_symlink() or not schema_path.is_file():
        raise ArchivePlanError("Schema must be a non-symlink regular file")
    if SLUG_PATTERN.fullmatch(company_slug) is None:
        raise ArchivePlanError("company-slug must contain only lowercase letters, digits, and single hyphens")
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ArchivePlanError("version must be YYYY-MM-DD or YYYY-MM-DD-vN")
    _iso_date(version[:10], "version date")
    if strategy not in {"pull-request", "direct-main"}:
        raise ArchivePlanError("strategy must be pull-request or direct-main")
    if strategy == "direct-main" and not direct_main_authorized:
        raise ArchivePlanError("direct-main requires explicit direct-main authorization")
    if promotion not in {"archive-only", "archive-and-promote"}:
        raise ArchivePlanError("promotion must be archive-only or archive-and-promote")
    if promotion == "archive-and-promote" and not promotion_authorized:
        raise ArchivePlanError("archive-and-promote requires explicit promotion authorization")
    if existing_company_path is None and existing_company_head is not None:
        raise ArchivePlanError("existing-company-head requires existing-company")
    if promotion == "archive-only" and (
        existing_company_path is not None
        or existing_company_head is not None
        or canonical_absent
        or confirm_same_date_revision
    ):
        raise ArchivePlanError("canonical preflight and revision confirmation require archive-and-promote")

    root = root.resolve()
    schema_path = schema_path.resolve()
    manifest_path = _safe_regular_file(root / "research-manifest.json", "research-manifest.json")
    if trusted_lock is None:
        trusted_lock = _read_object(TRUSTED_LOCK_PATH, "trusted specification lock")
    manifest, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock)
    if manifest is None or errors:
        detail = "; ".join(errors) if errors else "manifest could not be verified"
        raise ArchivePlanError(f"frozen package verification failed: {detail}")

    fresh_findings = validate_research_package(root, schema_path, "full")
    fresh_errors = [item for item in fresh_findings if item.severity == "error"]
    fresh_warnings = [item for item in fresh_findings if item.severity == "warning"]
    if fresh_errors:
        codes = ", ".join(sorted({item.code for item in fresh_errors}))
        raise ArchivePlanError(f"fresh full validation failed: {codes}")
    recorded_validation = manifest.get("validation")
    if not isinstance(recorded_validation, dict):
        raise ArchivePlanError("verified manifest lacks validation metadata")
    if recorded_validation.get("errors") != len(fresh_errors) or recorded_validation.get("warnings") != len(fresh_warnings):
        raise ArchivePlanError("fresh validation counts do not match the frozen manifest")
    if fresh_warnings and manifest.get("warning_acknowledged") is not True:
        raise ArchivePlanError("fresh validation warnings were not acknowledged")

    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ArchivePlanError("verified manifest has no files array")
    snapshot_root = f"research/{company_slug}/{version}"
    snapshot_files: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ArchivePlanError("verified manifest contains an invalid file entry")
        name = entry["path"]
        source = _safe_regular_file(root / name, f"frozen file {name}")
        snapshot_files.append(
            {
                "source_path": str(source),
                "target_path": f"{snapshot_root}/{name}",
                "sha256": file_sha256(source),
                "size_bytes": source.stat().st_size,
            }
        )
    snapshot_files.append(
        {
            "source_path": str(manifest_path),
            "target_path": f"{snapshot_root}/research-manifest.json",
            "sha256": file_sha256(manifest_path),
            "size_bytes": manifest_path.stat().st_size,
        }
    )
    scan_sensitive_material([Path(item["source_path"]) for item in snapshot_files])
    remote_action, base_head = snapshot_action(snapshot_root, snapshot_files, remote_snapshot_state)

    company_path = _safe_regular_file(root / "company.json", "company.json")
    if promotion == "archive-and-promote":
        if existing_company_path is not None:
            if SHA1_PATTERN.fullmatch(str(existing_company_head or "")) is None:
                raise ArchivePlanError("existing canonical company.json requires an exact source head")
            if base_head is not None and existing_company_head != base_head:
                raise ArchivePlanError("canonical company.json and snapshot state came from different base heads")
        action = canonical_action(
            company_path,
            existing_company_path=existing_company_path,
            canonical_absent=canonical_absent,
            version=version,
            confirm_same_date_revision=confirm_same_date_revision,
        )
    else:
        action = "not-requested"
    ready_for_write = (
        write_authorized
        and remote_action in {"create", "noop"}
        and action != "remote-preflight-required"
    )
    research = manifest.get("research") if isinstance(manifest.get("research"), dict) else {}
    return {
        "plan_version": "1.0",
        "repository": TARGET_REPOSITORY,
        "target_branch": TARGET_BRANCH,
        "strategy": strategy,
        "promotion": promotion,
        "write_authorized": write_authorized,
        "promotion_authorized": promotion_authorized,
        "direct_main_authorized": direct_main_authorized,
        "requires_atomic_commit": True,
        "force_update_allowed": False,
        "base_head": base_head,
        "ready_for_write": ready_for_write,
        "source": {
            "manifest_sha256": file_sha256(manifest_path),
            "human_review_status": manifest.get("human_review_status"),
            "data_as_of": research.get("data_as_of"),
            "valuation_date": research.get("valuation_date"),
        },
        "slug_binding": {
            "company_slug": company_slug,
            "company_name_cn": research.get("company_name_cn"),
            "company_name_en": research.get("company_name_en"),
            "ticker": research.get("ticker"),
            "exchange": research.get("exchange"),
            "requires_remote_registry_check": True,
        },
        "snapshot": {
            "root": snapshot_root,
            "remote_action": remote_action,
            "conflict_policy": "identical-noop-otherwise-new-version",
            "files": snapshot_files,
        },
        "canonical_company": {
            "source_path": str(company_path),
            "target_path": f"companies/{company_slug}/company.json",
            "sha256": file_sha256(company_path),
            "size_bytes": company_path.stat().st_size,
            "action": action,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Accepted frozen research package root")
    parser.add_argument("--schema", type=Path, required=True, help="Locked company.schema.json used to freeze")
    parser.add_argument("--company-slug", required=True)
    parser.add_argument("--version", required=True, help="YYYY-MM-DD or YYYY-MM-DD-vN")
    parser.add_argument("--strategy", choices=("pull-request", "direct-main"), default="pull-request")
    parser.add_argument("--confirm-write-authorization", action="store_true")
    parser.add_argument("--confirm-promotion-authorization", action="store_true")
    parser.add_argument("--confirm-direct-main-authorization", action="store_true")
    parser.add_argument(
        "--promotion",
        choices=("archive-only", "archive-and-promote"),
        default="archive-only",
    )
    parser.add_argument(
        "--remote-snapshot-state",
        type=Path,
        help="Connector-produced JSON describing the version directory at one exact main head",
    )
    canonical = parser.add_mutually_exclusive_group()
    canonical.add_argument("--existing-company", type=Path, help="Remote canonical company.json downloaded at preflight")
    canonical.add_argument("--canonical-absent", action="store_true", help="Confirm remote canonical path returned not found")
    parser.add_argument("--existing-company-head", help="Exact main SHA used to fetch --existing-company")
    parser.add_argument(
        "--confirm-same-date-revision",
        action="store_true",
        help="Allow a reviewed -vN snapshot to replace different canonical content for the same data_as_of",
    )
    parser.add_argument("--output", type=Path, help="Write plan outside the frozen package; default stdout")
    args = parser.parse_args()

    try:
        remote_state = (
            _read_object(
                _safe_regular_file(args.remote_snapshot_state, "remote snapshot state"),
                "remote snapshot state",
            )
            if args.remote_snapshot_state is not None
            else None
        )
        plan = build_archive_plan(
            args.root,
            args.schema,
            company_slug=args.company_slug,
            version=args.version,
            strategy=args.strategy,
            promotion=args.promotion,
            write_authorized=args.confirm_write_authorization,
            promotion_authorized=args.confirm_promotion_authorization,
            direct_main_authorized=args.confirm_direct_main_authorization,
            remote_snapshot_state=remote_state,
            existing_company_path=args.existing_company,
            existing_company_head=args.existing_company_head,
            canonical_absent=args.canonical_absent,
            confirm_same_date_revision=args.confirm_same_date_revision,
        )
        if args.output is not None:
            output = args.output
            if output.is_symlink():
                raise ArchivePlanError("output cannot be a symlink")
            root_resolved = args.root.resolve()
            output_resolved = output.resolve(strict=False)
            try:
                output_resolved.relative_to(root_resolved)
            except ValueError:
                pass
            else:
                raise ArchivePlanError("archive plan must be written outside the frozen package")
            skill_root = Path(__file__).resolve().parents[1]
            try:
                output_resolved.relative_to(skill_root)
            except ValueError:
                pass
            else:
                raise ArchivePlanError("archive plan cannot overwrite files inside the Skill")
            forbidden = {
                args.schema.resolve(),
                TRUSTED_LOCK_PATH.resolve(),
                *(Path(item["source_path"]).resolve() for item in plan["snapshot"]["files"]),
            }
            if args.existing_company is not None:
                forbidden.add(args.existing_company.resolve())
            if args.remote_snapshot_state is not None:
                forbidden.add(args.remote_snapshot_state.resolve())
            if output_resolved in forbidden:
                raise ArchivePlanError("archive plan output would overwrite an input or frozen file")
            output.parent.mkdir(parents=True, exist_ok=True)
            write_json(output, plan)
        else:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
    except (ArchivePlanError, OSError) as exc:
        print(f"Archive plan refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
