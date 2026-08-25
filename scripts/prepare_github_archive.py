#!/usr/bin/env python3
"""Create a fail-closed GitHub delivery plan for an accepted frozen research package."""

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
SHA1_PATTERN = re.compile(r"[0-9a-f]{40}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
IDENTITY_FIELDS = ("company_name_cn", "company_name_en", "ticker", "exchange")
CANONICAL_IDENTITY_FIELDS = IDENTITY_FIELDS + ("schema_version",)
COMPANY_PACKAGE_STATE_KEYS = {"repository", "branch", "base_head", "root", "exists", "files"}
MANAGED_PACKAGE_FILENAMES = {
    "research-report.md",
    "company.json",
    "research-completeness.md",
    "evidence-ledger.json",
    "calculation-ledger.json",
    "validation-report.json",
    "schema-gap-report.md",
    "research-manifest.json",
}
SLUG_REGISTRY_STATE_KEYS = {
    "repository",
    "branch",
    "base_head",
    "company_slug",
    "identity",
    "slug_exists",
    "slug_identity",
    "identity_slugs",
}
CANONICAL_STATE_KEYS = {"repository", "branch", "base_head", "path", "exists", "content"}
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
    """Raised when a package cannot be safely planned for GitHub delivery."""


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
    confirm_same_date_revision: bool,
    confirm_schema_migration: bool = False,
) -> str:
    """Return create/update/noop after identity and monotonicity checks."""
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

    for field in IDENTITY_FIELDS:
        if new_meta.get(field) != existing_meta.get(field):
            raise ArchivePlanError(f"canonical company.json conflicts on {field}")

    new_schema = new_meta.get("schema_version")
    existing_schema = existing_meta.get("schema_version")
    schema_migration = new_schema != existing_schema
    if schema_migration:
        allowed = (
            isinstance(existing_schema, str)
            and existing_schema.startswith("1.")
            and new_schema == "2.0.0"
        )
        if not allowed:
            raise ArchivePlanError("canonical company.json only permits a 1.x to 2.0.0 Schema migration")
        if not confirm_schema_migration:
            raise ArchivePlanError("canonical Schema migration requires explicit confirmation")

    new_date = _iso_date(new_meta.get("data_as_of"), "new company.json meta.data_as_of")
    existing_date = _iso_date(existing_meta.get("data_as_of"), "existing company.json meta.data_as_of")
    new_valuation = _iso_date(new_meta.get("valuation_date"), "new company.json meta.valuation_date")
    existing_valuation = _iso_date(existing_meta.get("valuation_date"), "existing company.json meta.valuation_date")
    if new_date < existing_date:
        raise ArchivePlanError("canonical company.json would roll back data_as_of")
    if new_valuation < existing_valuation:
        raise ArchivePlanError("canonical company.json would roll back valuation_date")
    if new_date == existing_date:
        if not confirm_same_date_revision:
            raise ArchivePlanError(
                "canonical company.json has different content for the same data_as_of; "
                "explicitly confirm the accepted same-date revision"
            )
        return "update-confirmed-schema-migration" if schema_migration else "update-confirmed-revision"
    return "update-confirmed-schema-migration" if schema_migration else "update"


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



def package_action(
    company_root: str,
    local_files: list[dict[str, Any]],
    remote_state: dict[str, Any] | None,
) -> tuple[str, str | None, list[str]]:
    """Resolve create/update/noop for the company's single current package directory."""
    if remote_state is None:
        return "remote-preflight-required", None, []
    if set(remote_state) != COMPANY_PACKAGE_STATE_KEYS:
        raise ArchivePlanError("remote company package state has unexpected or missing fields")
    if remote_state.get("repository") != TARGET_REPOSITORY or remote_state.get("branch") != TARGET_BRANCH:
        raise ArchivePlanError("remote company package state has the wrong repository or branch")
    if remote_state.get("root") != company_root:
        raise ArchivePlanError("remote company package state is for a different company path")
    base_head = str(remote_state.get("base_head", ""))
    if SHA1_PATTERN.fullmatch(base_head) is None:
        raise ArchivePlanError("remote company package state lacks an exact base_head")
    exists = remote_state.get("exists")
    if not isinstance(exists, bool):
        raise ArchivePlanError("remote company package state exists must be boolean")
    remote_files = remote_state.get("files")
    if not isinstance(remote_files, list):
        raise ArchivePlanError("remote company package state files must be an array")
    if not exists:
        if remote_files:
            raise ArchivePlanError("absent remote company package directory cannot contain direct files")
        return "create", base_head, []

    expected = {
        Path(item["target_path"]).name: (item["sha256"], item["size_bytes"])
        for item in local_files
    }
    if not {"company.json", "research-manifest.json"}.issubset(expected):
        raise ArchivePlanError("local company package lacks required managed files")
    if not set(expected).issubset(MANAGED_PACKAGE_FILENAMES):
        raise ArchivePlanError("local company package contains an unmanaged target filename")
    actual: dict[str, tuple[str, int]] = {}
    for entry in remote_files:
        if not isinstance(entry, dict):
            raise ArchivePlanError("remote company package state contains an invalid file entry")
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
            raise ArchivePlanError("remote company package state contains an unsafe or malformed direct file")
        actual[name] = (str(sha256), size)
    managed_actual = {name: value for name, value in actual.items() if name in MANAGED_PACKAGE_FILENAMES}
    if managed_actual == expected:
        return "noop", base_head, []
    delete_paths = [f"{company_root}/{name}" for name in sorted(set(managed_actual) - set(expected))]
    return "update", base_head, delete_paths


def _research_identity(research: dict[str, Any]) -> dict[str, str]:
    identity: dict[str, str] = {}
    for field in IDENTITY_FIELDS:
        value = research.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ArchivePlanError(f"verified manifest research identity lacks {field}")
        identity[field] = value
    return identity


def _state_base_head(state: dict[str, Any], label: str, expected_base_head: str | None) -> str:
    if state.get("repository") != TARGET_REPOSITORY or state.get("branch") != TARGET_BRANCH:
        raise ArchivePlanError(f"{label} has the wrong repository or branch")
    base_head = str(state.get("base_head", ""))
    if SHA1_PATTERN.fullmatch(base_head) is None:
        raise ArchivePlanError(f"{label} lacks an exact base_head")
    if expected_base_head is not None and base_head != expected_base_head:
        raise ArchivePlanError(f"{label} and remote company package state came from different base heads")
    return base_head


def slug_binding_action(
    company_slug: str,
    identity: dict[str, str],
    remote_state: dict[str, Any] | None,
    expected_base_head: str | None,
) -> tuple[str, str | None]:
    if remote_state is None:
        return "remote-preflight-required", None
    if set(remote_state) != SLUG_REGISTRY_STATE_KEYS:
        raise ArchivePlanError("remote slug registry state has unexpected or missing fields")
    base_head = _state_base_head(remote_state, "remote slug registry state", expected_base_head)
    if remote_state.get("company_slug") != company_slug:
        raise ArchivePlanError("remote slug registry state is for a different company slug")
    if remote_state.get("identity") != identity:
        raise ArchivePlanError("remote slug registry requested identity does not match the frozen research package")
    slug_exists = remote_state.get("slug_exists")
    if not isinstance(slug_exists, bool):
        raise ArchivePlanError("remote slug registry state slug_exists must be boolean")
    identity_slugs = remote_state.get("identity_slugs")
    if (
        not isinstance(identity_slugs, list)
        or any(not isinstance(item, str) or SLUG_PATTERN.fullmatch(item) is None for item in identity_slugs)
        or len(identity_slugs) != len(set(identity_slugs))
    ):
        raise ArchivePlanError("remote slug registry state identity_slugs must be unique safe slugs")
    slug_identity = remote_state.get("slug_identity")
    if slug_exists:
        if slug_identity != identity:
            raise ArchivePlanError("remote company slug is bound to a different company identity")
        if identity_slugs != [company_slug]:
            raise ArchivePlanError("remote company identity is not bound one-to-one to the requested slug")
        return "verified-bound", base_head
    if slug_identity is not None:
        raise ArchivePlanError("absent remote company slug cannot carry a bound identity")
    if identity_slugs:
        raise ArchivePlanError("remote company identity is already registered under a different slug")
    return "verified-available", base_head


def _canonical_identity(company: dict[str, Any], label: str) -> dict[str, Any]:
    meta = _meta(company, label)
    return {field: meta.get(field) for field in CANONICAL_IDENTITY_FIELDS}


def canonical_preflight_action(
    new_company_path: Path,
    *,
    company_slug: str,
    confirm_same_date_revision: bool,
    confirm_schema_migration: bool,
    remote_state: dict[str, Any] | None,
    expected_base_head: str | None,
) -> tuple[str, str | None, bool | None]:
    if remote_state is None:
        return "remote-preflight-required", None, None
    if set(remote_state) != CANONICAL_STATE_KEYS:
        raise ArchivePlanError("remote canonical state has unexpected or missing fields")
    base_head = _state_base_head(remote_state, "remote canonical state", expected_base_head)
    expected_path = f"companies/{company_slug}/company.json"
    if remote_state.get("path") != expected_path:
        raise ArchivePlanError("remote canonical state is for a different company path")
    exists = remote_state.get("exists")
    if not isinstance(exists, bool):
        raise ArchivePlanError("remote canonical state exists must be boolean")
    content = remote_state.get("content")
    if not exists:
        if content is not None:
            raise ArchivePlanError("absent remote canonical state cannot contain file content")
        return "create", base_head, False
    if not isinstance(content, dict):
        raise ArchivePlanError("existing remote canonical state requires content metadata")
    if set(content) != {"source_path", "sha256", "size_bytes", "identity"}:
        raise ArchivePlanError("remote canonical content must contain only source_path, sha256, size_bytes, and identity")
    source_value = content.get("source_path")
    if not isinstance(source_value, str) or not source_value:
        raise ArchivePlanError("remote canonical content requires a source_path")
    source_path = _safe_regular_file(Path(source_value), "remote canonical company.json")
    sha256 = content.get("sha256")
    size_bytes = content.get("size_bytes")
    if SHA256_PATTERN.fullmatch(str(sha256)) is None:
        raise ArchivePlanError("remote canonical content has an invalid SHA-256")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
        raise ArchivePlanError("remote canonical content has an invalid size")
    if file_sha256(source_path) != sha256 or source_path.stat().st_size != size_bytes:
        raise ArchivePlanError("remote canonical content hash or size does not match the downloaded file")
    existing_company = _read_object(source_path, "remote canonical company.json")
    if content.get("identity") != _canonical_identity(existing_company, "remote canonical company.json"):
        raise ArchivePlanError("remote canonical content identity does not match the downloaded file")
    action = canonical_action(
        new_company_path,
        existing_company_path=source_path,
        canonical_absent=False,
        confirm_same_date_revision=confirm_same_date_revision,
        confirm_schema_migration=confirm_schema_migration,
    )
    return action, base_head, True


def build_archive_plan(
    root: Path,
    schema_path: Path,
    *,
    company_slug: str,
    strategy: str,
    write_authorized: bool = False,
    direct_main_authorized: bool = False,
    remote_company_state: dict[str, Any] | None = None,
    remote_slug_registry_state: dict[str, Any] | None = None,
    remote_canonical_state: dict[str, Any] | None = None,
    confirm_same_date_revision: bool = False,
    confirm_schema_migration: bool = False,
    trusted_lock: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise ArchivePlanError("research package root must be a non-symlink directory")
    if schema_path.is_symlink() or not schema_path.is_file():
        raise ArchivePlanError("Schema must be a non-symlink regular file")
    if SLUG_PATTERN.fullmatch(company_slug) is None:
        raise ArchivePlanError("company-slug must contain only lowercase letters, digits, and single hyphens")
    if strategy not in {"pull-request", "direct-main"}:
        raise ArchivePlanError("strategy must be pull-request or direct-main")
    if strategy == "direct-main" and not direct_main_authorized:
        raise ArchivePlanError("direct-main requires explicit direct-main authorization")

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
    company_root = f"companies/{company_slug}"
    package_files: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ArchivePlanError("verified manifest contains an invalid file entry")
        name = entry["path"]
        source = _safe_regular_file(root / name, f"frozen file {name}")
        package_files.append(
            {
                "source_path": str(source),
                "target_path": f"{company_root}/{name}",
                "sha256": file_sha256(source),
                "size_bytes": source.stat().st_size,
            }
        )
    package_files.append(
        {
            "source_path": str(manifest_path),
            "target_path": f"{company_root}/research-manifest.json",
            "sha256": file_sha256(manifest_path),
            "size_bytes": manifest_path.stat().st_size,
        }
    )
    scan_sensitive_material([Path(item["source_path"]) for item in package_files])
    remote_action, base_head, delete_paths = package_action(
        company_root,
        package_files,
        remote_company_state,
    )

    company_path = _safe_regular_file(root / "company.json", "company.json")
    company = _read_object(company_path, "company.json")
    research = manifest.get("research") if isinstance(manifest.get("research"), dict) else {}
    identity = _research_identity(research)
    slug_action, slug_head = slug_binding_action(
        company_slug,
        identity,
        remote_slug_registry_state,
        base_head,
    )
    canonical, canonical_head, canonical_exists = canonical_preflight_action(
        company_path,
        company_slug=company_slug,
        confirm_same_date_revision=confirm_same_date_revision,
        confirm_schema_migration=confirm_schema_migration,
        remote_state=remote_canonical_state,
        expected_base_head=base_head,
    )
    ready_for_write = (
        write_authorized
        and remote_action in {"create", "update", "noop"}
        and slug_action in {"verified-bound", "verified-available"}
        and canonical in {"create", "update", "update-confirmed-revision", "update-confirmed-schema-migration", "noop"}
    )
    return {
        "plan_version": "8.0",
        "repository": TARGET_REPOSITORY,
        "target_branch": TARGET_BRANCH,
        "strategy": strategy,
        "delivery_mode": "single-company-directory",
        "write_authorized": write_authorized,
        "direct_main_authorized": direct_main_authorized,
        "requires_atomic_commit": True,
        "force_update_allowed": False,
        "base_head": base_head,
        "ready_for_write": ready_for_write,
        "source": {
            "manifest_sha256": file_sha256(manifest_path),
            "manifest_version": manifest.get("manifest_version"),
            "human_review_status": manifest.get("human_review_status"),
            "data_as_of": research.get("data_as_of"),
            "valuation_date": research.get("valuation_date"),
            "research_protocol": manifest.get("research_protocol"),
            "integrity_profile": manifest.get("integrity_profile"),
            "execution_integrity": manifest.get("execution_integrity"),
            "validator_sha256": recorded_validation.get("validator_sha256"),
            "specification": manifest.get("specification"),
        },
        "slug_binding": {
            "company_slug": company_slug,
            "identity": identity,
            "remote_action": slug_action,
            "base_head": slug_head,
        },
        "company_package": {
            "root": company_root,
            "remote_action": remote_action,
            "replacement_policy": "managed-research-files",
            "preserve_unmanaged_company_assets": True,
            "files": package_files,
            "delete_paths": delete_paths,
        },
        "canonical_guard": {
            "source_path": str(company_path),
            "target_path": f"companies/{company_slug}/company.json",
            "sha256": file_sha256(company_path),
            "size_bytes": company_path.stat().st_size,
            "action": canonical,
            "remote_base_head": canonical_head,
            "remote_exists": canonical_exists,
            "schema_migration_confirmed": confirm_schema_migration,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Accepted frozen research package root")
    parser.add_argument("--schema", type=Path, required=True, help="Locked company.schema.json used to freeze")
    parser.add_argument("--company-slug", required=True)
    parser.add_argument("--strategy", choices=("pull-request", "direct-main"), default="pull-request")
    parser.add_argument("--confirm-write-authorization", action="store_true")
    parser.add_argument("--confirm-direct-main-authorization", action="store_true")
    parser.add_argument(
        "--remote-company-state",
        type=Path,
        help="Connector-produced JSON describing direct files in companies/<company-slug> at one exact main head",
    )
    parser.add_argument(
        "--remote-slug-registry-state",
        type=Path,
        help="Connector-produced exact-main-head slug/identity registry observation",
    )
    parser.add_argument(
        "--remote-canonical-state",
        type=Path,
        help="Connector-produced exact-main-head canonical path/content observation",
    )
    parser.add_argument(
        "--confirm-same-date-revision",
        action="store_true",
        help="Allow an accepted correction to replace different canonical content for the same data_as_of",
    )
    parser.add_argument(
        "--confirm-schema-migration",
        action="store_true",
        help="Allow an accepted Schema 1.x package to be replaced by the fully rebuilt Schema 2.0.0 package",
    )
    parser.add_argument("--output", type=Path, help="Write plan outside the frozen package; default stdout")
    args = parser.parse_args()

    try:
        remote_company_state = (
            _read_object(
                _safe_regular_file(args.remote_company_state, "remote company package state"),
                "remote company package state",
            )
            if args.remote_company_state is not None
            else None
        )
        remote_slug_registry_state = (
            _read_object(
                _safe_regular_file(args.remote_slug_registry_state, "remote slug registry state"),
                "remote slug registry state",
            )
            if args.remote_slug_registry_state is not None
            else None
        )
        remote_canonical_state = (
            _read_object(
                _safe_regular_file(args.remote_canonical_state, "remote canonical state"),
                "remote canonical state",
            )
            if args.remote_canonical_state is not None
            else None
        )
        plan = build_archive_plan(
            args.root,
            args.schema,
            company_slug=args.company_slug,
            strategy=args.strategy,
            write_authorized=args.confirm_write_authorization,
            direct_main_authorized=args.confirm_direct_main_authorization,
            remote_company_state=remote_company_state,
            remote_slug_registry_state=remote_slug_registry_state,
            remote_canonical_state=remote_canonical_state,
            confirm_same_date_revision=args.confirm_same_date_revision,
            confirm_schema_migration=args.confirm_schema_migration,
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
                raise ArchivePlanError("delivery plan must be written outside the frozen package")
            skill_root = Path(__file__).resolve().parents[1]
            try:
                output_resolved.relative_to(skill_root)
            except ValueError:
                pass
            else:
                raise ArchivePlanError("delivery plan cannot overwrite files inside the Skill")
            forbidden = {
                args.schema.resolve(),
                TRUSTED_LOCK_PATH.resolve(),
                *(Path(item["source_path"]).resolve() for item in plan["company_package"]["files"]),
            }
            for observation in (
                args.remote_company_state,
                args.remote_slug_registry_state,
                args.remote_canonical_state,
            ):
                if observation is not None:
                    forbidden.add(observation.resolve())
            content = remote_canonical_state.get("content") if isinstance(remote_canonical_state, dict) else None
            if isinstance(content, dict) and isinstance(content.get("source_path"), str):
                forbidden.add(Path(content["source_path"]).resolve())
            if output_resolved in forbidden:
                raise ArchivePlanError("delivery plan output would overwrite an input or frozen file")
            output.parent.mkdir(parents=True, exist_ok=True)
            write_json(output, plan)
        else:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
    except (ArchivePlanError, OSError) as exc:
        print(f"Delivery plan refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
