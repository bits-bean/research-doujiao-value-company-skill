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
TRUSTED_LOCK_KEYS = {"lock_version", "research_protocol", "company_schema"}
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
REQUIRED = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/source-routing.md",
    "references/research-contract.md",
    "references/evidence-and-calculation.md",
    "references/valuation-qa.md",
    "references/qa-gates.md",
    "references/github-archive.md",
    "references/trusted-spec-lock.json",
    "references/specs/project-instructions.md",
    "references/specs/research-methodology.md",
    "references/specs/automation-workflow.md",
    "references/specs/company.schema.json",
    "scripts/validate_research_package.py",
    "scripts/freeze_research.py",
    "scripts/prepare_github_archive.py",
    "scripts/verify_spec_anchor.py",
    "scripts/validate_skill.py",
    "tests/package_fixture.py",
    "tests/test_incremental_chain.py",
    "tests/test_github_archive.py",
    "tests/test_spec_anchor.py",
    "tests/test_semantic_gates.py",
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

    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", skill_text):
        if "://" in target or target.startswith("#"):
            continue
        resolved = (ROOT / target).resolve()
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
        schema = lock.get("company_schema", {})
        if set(lock) != TRUSTED_LOCK_KEYS or lock.get("lock_version") != "2.0":
            fail("trusted specification lock must use version 2.0 and the exact top-level keys")
            errors += 1
        if (
            set(protocol) != RESEARCH_PROTOCOL_KEYS
            or
            protocol.get("authority") != SKILL_NAME
            or protocol.get("repository") != "bits-bean/doujiao-value-research-skill"
            or protocol.get("ref") != "main"
            or re.fullmatch(r"[0-9a-f]{40}", str(protocol.get("commit", ""))) is None
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
