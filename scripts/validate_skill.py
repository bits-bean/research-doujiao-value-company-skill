#!/usr/bin/env python3
"""Validate the research skill bundle and run deterministic self-tests."""

from __future__ import annotations

import hashlib
import json
import re
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "research-doujiao-value-company"
TRUSTED_LOCK_KEYS = {
    "lock_version",
    "research_protocol",
    "execution_integrity",
    "company_schema",
}
RESEARCH_PROTOCOL_KEYS = {
    "authority",
    "repository",
    "ref",
    "commit",
    "protocol_version",
    "digest_sha256",
    "documents",
}
COMPANY_SCHEMA_KEYS = {
    "repository",
    "ref",
    "commit",
    "path",
    "blob_sha1",
    "sha256",
    "size_bytes",
    "schema_version",
    "bundled_path",
}
EXECUTION_INTEGRITY_KEYS = {
    "profile",
    "normative_digest_sha256",
    "toolchain_digest_sha256",
    "bundle_digest_sha256",
    "artifacts",
    "source_binding",
}
EXECUTION_ARTIFACT_KEYS = {"path", "role", "sha256", "size_bytes"}
EXECUTION_SOURCE_BINDING_KEYS = {
    "repository",
    "ref",
    "payload_commit",
    "verification_status",
}
EXECUTION_PROFILE = "execution-bound-v1"
REQUIRED = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/source-routing.md",
    "references/classification-and-chart-routing.md",
    "references/research-contract.md",
    "references/evidence-and-calculation.md",
    "references/income-statement-sankey.md",
    "references/valuation-qa.md",
    "references/qa-gates.md",
    "references/github-archive.md",
    "references/identity-assets.md",
    "references/research-execution-and-audit.md",
    "references/trusted-spec-lock.json",
    "references/specs/project-instructions.md",
    "references/specs/research-methodology.md",
    "references/specs/automation-workflow.md",
    "references/specs/company.schema.json",
    "scripts/validate_research_package.py",
    "scripts/validate_research_process.py",
    "scripts/freeze_research.py",
    "scripts/prepare_github_archive.py",
    "scripts/verify_spec_anchor.py",
    "scripts/validate_skill.py",
    "tests/package_fixture.py",
    "tests/test_incremental_chain.py",
    "tests/test_github_archive.py",
    "tests/test_spec_anchor.py",
    "tests/test_semantic_gates.py",
    "tests/test_research_process.py",
    "tests/test_validation_gates.py",
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values


def canonical_sha256(value: object) -> str:
    """Hash the canonical UTF-8 JSON representation used by integrity locks."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def expected_execution_artifacts() -> dict[str, str]:
    """Return the exact executable/normative inventory keyed by relative path."""
    paths = {
        "SKILL.md": "normative",
        "agents/openai.yaml": "normative",
    }
    references_root = ROOT / "references"
    scripts_root = ROOT / "scripts"
    for local in references_root.rglob("*.md"):
        paths[local.relative_to(ROOT).as_posix()] = "normative"
    for local in scripts_root.glob("*.py"):
        paths[local.relative_to(ROOT).as_posix()] = "toolchain"
    return dict(sorted(paths.items()))


def validate_execution_integrity(value: object) -> int:
    """Validate exact inventory bindings and the three role-aware digests."""
    errors = 0
    if not isinstance(value, dict) or set(value) != EXECUTION_INTEGRITY_KEYS:
        fail("execution_integrity must contain exactly the required keys")
        return 1
    if value.get("profile") != EXECUTION_PROFILE:
        fail(f"execution_integrity profile must be {EXECUTION_PROFILE}")
        errors += 1

    binding = value.get("source_binding")
    if not isinstance(binding, dict) or set(binding) != EXECUTION_SOURCE_BINDING_KEYS:
        fail("execution_integrity source_binding must contain exactly the required keys")
        errors += 1
    elif binding != {
        "repository": "bits-bean/doujiao-value-research-skill",
        "ref": "main",
        "payload_commit": None,
        "verification_status": "unverified",
    }:
        fail("execution_integrity source_binding must explicitly remain unverified")
        errors += 1

    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list):
        fail("execution_integrity artifacts must be an array")
        return errors + 1

    expected = expected_execution_artifacts()
    valid_entries: list[dict[str, object]] = []
    observed_paths: list[str] = []
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict) or set(item) != EXECUTION_ARTIFACT_KEYS:
            fail(
                "execution_integrity artifact entries must contain exactly "
                "path, role, sha256, and size_bytes"
            )
            errors += 1
            continue
        path = item.get("path")
        role = item.get("role")
        digest = item.get("sha256")
        size_bytes = item.get("size_bytes")
        if not isinstance(path, str):
            fail(f"execution_integrity artifact {index} has a non-string path")
            errors += 1
            continue
        observed_paths.append(path)
        expected_role = expected.get(path)
        if expected_role is None:
            fail(f"execution_integrity includes an unexpected artifact: {path}")
            errors += 1
            continue
        if role != expected_role:
            fail(
                f"execution_integrity artifact has the wrong role: "
                f"{path} (expected {expected_role})"
            )
            errors += 1
        if re.fullmatch(r"[0-9a-f]{64}", str(digest)) is None:
            fail(f"execution_integrity artifact has an invalid SHA-256: {path}")
            errors += 1
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            fail(f"execution_integrity artifact has an invalid size_bytes: {path}")
            errors += 1
        local = ROOT / path
        if not local.is_file():
            fail(f"execution_integrity artifact is missing: {path}")
            errors += 1
            continue
        data = local.read_bytes()
        if digest != hashlib.sha256(data).hexdigest() or size_bytes != len(data):
            fail(f"execution_integrity artifact lock mismatch: {path}")
            errors += 1
        valid_entries.append(item)

    expected_paths = list(expected)
    if observed_paths != sorted(observed_paths):
        fail("execution_integrity artifacts must be path-sorted")
        errors += 1
    if len(observed_paths) != len(set(observed_paths)):
        fail("execution_integrity artifacts must be unique")
        errors += 1
    if observed_paths != expected_paths:
        missing = sorted(set(expected_paths) - set(observed_paths))
        unexpected = sorted(set(observed_paths) - set(expected_paths))
        detail = []
        if missing:
            detail.append(f"missing={missing}")
        if unexpected:
            detail.append(f"unexpected={unexpected}")
        fail(
            "execution_integrity artifact inventory differs from the skill bundle"
            + (f": {'; '.join(detail)}" if detail else "")
        )
        errors += 1

    # Only compute digests from a structurally complete, exact inventory.  This
    # avoids blessing malformed entries merely because their JSON happens to hash.
    if len(valid_entries) == len(artifacts) and observed_paths == expected_paths:
        normative = [item for item in valid_entries if item["role"] == "normative"]
        toolchain = [item for item in valid_entries if item["role"] == "toolchain"]
        expected_digests = {
            "normative_digest_sha256": canonical_sha256(normative),
            "toolchain_digest_sha256": canonical_sha256(toolchain),
            "bundle_digest_sha256": canonical_sha256(valid_entries),
        }
        for key, expected_digest in expected_digests.items():
            if value.get(key) != expected_digest:
                fail(f"execution_integrity {key} is invalid")
                errors += 1
    else:
        for key in (
            "normative_digest_sha256",
            "toolchain_digest_sha256",
            "bundle_digest_sha256",
        ):
            if re.fullmatch(r"[0-9a-f]{64}", str(value.get(key, ""))) is None:
                fail(f"execution_integrity {key} must be a lowercase SHA-256")
                errors += 1
    return errors


def main() -> int:
    errors = 0
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}")
            errors += 1
    if errors:
        return 1

    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    metadata = frontmatter(skill_text)
    if set(metadata) != {"name", "description"}:
        fail(f"frontmatter must contain only name and description, got {sorted(metadata)}")
        errors += 1
    if metadata.get("name") != SKILL_NAME:
        fail("frontmatter name does not match skill directory identity")
        errors += 1
    if len(metadata.get("description", "")) < 80:
        fail("description is too short to trigger reliably")
        errors += 1
    if re.search(r"\bTODO\b|\bFIXME\b", skill_text):
        fail("SKILL.md still contains a placeholder")
        errors += 1
    for required_boundary in (
        "不调用 `doujiao-value-system` 的图表导出命令或接口",
        "不生成网站图、社媒图或背景",
        "不选择平台比例",
        "公司 Logo 是唯一视觉素材例外",
        "不得生成、重绘或用近似图替代公司 Logo",
        "除公司 Logo 外",
    ):
        if required_boundary not in skill_text:
            fail(f"SKILL.md lacks responsibility boundary: {required_boundary}")
            errors += 1

    archive_text = (ROOT / "scripts/prepare_github_archive.py").read_text(encoding="utf-8")
    for required_logo_hook in (
        "--identity-assets-root",
        "--remote-identity-assets-state",
        "--confirm-identity-asset-replacement",
        "--confirm-identity-asset-clear",
        "--confirm-new-company-without-logo",
        "missing-explicitly-authorized",
        "new_company_without_logo_confirmed",
        '"identity_assets"',
        "prepare_identity_asset_files",
        "sharp.versions",
        "0.35.3",
        "8.18.3",
        "2.62.90",
    ):
        if required_logo_hook not in archive_text:
            fail(f"research archive lacks company Logo delivery guard: {required_logo_hook}")
            errors += 1
    for forbidden_non_logo_hook in (
        "visual-assets.json",
        "cover_product",
        "PRODUCT_ASSET_SUFFIXES",
    ):
        if forbidden_non_logo_hook in archive_text:
            fail(f"research archive exposes non-Logo visual-asset management: {forbidden_non_logo_hook}")
            errors += 1

    package_validator_text = (ROOT / "scripts/validate_research_package.py").read_text(encoding="utf-8")
    for required_package_boundary in (
        "embedded-visual-asset",
        "markdown_image_pattern",
        "raw_html_tag_pattern",
        "company_slug",
        "future_or_negated_search",
    ):
        if required_package_boundary not in package_validator_text:
            fail(f"research package validator lacks boundary: {required_package_boundary}")
            errors += 1

    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", skill_text):
        if "://" in target or target.startswith("#"):
            continue
        resolved = (ROOT / target.split("#", 1)[0]).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            fail(f"link escapes skill root: {target}")
            errors += 1
            continue
        if not resolved.exists():
            fail(f"broken local link: {target}")
            errors += 1

    ui_text = (ROOT / "agents/openai.yaml").read_text(encoding="utf-8")
    for key in ("display_name:", "short_description:", "default_prompt:"):
        if key not in ui_text:
            fail(f"agents/openai.yaml lacks {key}")
            errors += 1
    if f"${SKILL_NAME}" not in ui_text:
        fail("default_prompt must explicitly mention the skill")
        errors += 1

    try:
        lock = json.loads((ROOT / "references/trusted-spec-lock.json").read_text(encoding="utf-8"))
        protocol = lock.get("research_protocol", {})
        execution_integrity = lock.get("execution_integrity", {})
        schema = lock.get("company_schema", {})
        if set(lock) != TRUSTED_LOCK_KEYS or lock.get("lock_version") != "3.0":
            fail("trusted specification lock must use version 3.0 and the exact top-level keys")
            errors += 1
        if (
            set(protocol) != RESEARCH_PROTOCOL_KEYS
            or
            protocol.get("authority") != SKILL_NAME
            or protocol.get("repository") != "bits-bean/doujiao-value-research-skill"
            or protocol.get("ref") != "main"
            or re.fullmatch(r"[0-9a-f]{40}", str(protocol.get("commit", ""))) is None
            or protocol.get("commit") == "0" * 40
        ):
            fail("research_protocol has the wrong authority, repository, ref, or commit")
            errors += 1
        documents = protocol.get("documents")
        if not isinstance(documents, list):
            fail("research_protocol documents must be an array")
            errors += 1
        else:
            expected_paths = {
                "references/specs/project-instructions.md",
                "references/specs/research-methodology.md",
                "references/specs/automation-workflow.md",
            }
            if [item.get("path") for item in documents if isinstance(item, dict)] != sorted(expected_paths):
                fail("research_protocol documents must be complete, unique, and path-sorted")
                errors += 1
            for item in documents:
                if not isinstance(item, dict) or set(item) != {"path", "sha256", "size_bytes"}:
                    fail("research_protocol document entries must contain exactly path, sha256, and size_bytes")
                    errors += 1
                    continue
                if item.get("path") not in expected_paths:
                    continue
                local = ROOT / item["path"]
                data = local.read_bytes()
                if item.get("sha256") != hashlib.sha256(data).hexdigest() or item.get("size_bytes") != len(data):
                    fail(f"research protocol lock mismatch: {item['path']}")
                    errors += 1
            digest = hashlib.sha256(
                json.dumps(documents, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if protocol.get("digest_sha256") != digest:
                fail("research_protocol digest is invalid")
                errors += 1
        errors += validate_execution_integrity(execution_integrity)
        if (
            set(schema) != COMPANY_SCHEMA_KEYS
            or
            schema.get("repository") != "bits-bean/doujiao-value-system"
            or schema.get("ref") != "main"
            or schema.get("path") != "schemas/company.schema.json"
            or schema.get("bundled_path") != "references/specs/company.schema.json"
            or re.fullmatch(r"[0-9a-f]{40}", str(schema.get("commit", ""))) is None
            or re.fullmatch(r"[0-9a-f]{40}", str(schema.get("blob_sha1", ""))) is None
            or re.fullmatch(r"[0-9a-f]{64}", str(schema.get("sha256", ""))) is None
        ):
            fail("company_schema has the wrong authority binding")
            errors += 1
        bundled_schema = (ROOT / "references/specs/company.schema.json").read_bytes()
        schema_variants = {bundled_schema}
        if bundled_schema.endswith(b"\n"):
            schema_variants.add(bundled_schema[:-1])
        else:
            schema_variants.add(bundled_schema + b"\n")
        if schema.get("sha256") not in {hashlib.sha256(item).hexdigest() for item in schema_variants}:
            fail("bundled company Schema differs from company_schema SHA-256")
            errors += 1
        if schema.get("size_bytes") not in {len(item) for item in schema_variants}:
            fail("bundled company Schema size differs from company_schema lock")
            errors += 1
    except (OSError, ValueError, AttributeError) as exc:
        fail(f"invalid trusted specification lock: {exc}")
        errors += 1

    with tempfile.TemporaryDirectory() as temp_dir:
        for script in (
            "validate_research_package.py",
            "validate_research_process.py",
            "freeze_research.py",
            "prepare_github_archive.py",
            "verify_spec_anchor.py",
            "validate_skill.py",
        ):
            try:
                py_compile.compile(
                    str(ROOT / "scripts" / script),
                    cfile=str(Path(temp_dir) / f"{script}.pyc"),
                    doraise=True,
                )
            except py_compile.PyCompileError as exc:
                fail(f"{script} does not compile: {exc}")
                errors += 1

    if not errors:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_research_package.py"), "--self-test"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            fail(f"package validator self-test failed: {completed.stderr.strip()}")
            errors += 1
        else:
            print(completed.stdout.strip())

    if not errors:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(ROOT / "tests"),
                "-p",
                "test_*.py",
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if completed.returncode:
            fail(f"validation regression tests failed: {completed.stderr.strip()}")
            errors += 1
        else:
            print(completed.stderr.strip() or completed.stdout.strip())

    if errors:
        print(f"skill bundle validation failed with {errors} error(s)", file=sys.stderr)
        return 1
    print("skill bundle validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
