#!/usr/bin/env python3
"""Validate the research skill bundle and run deterministic self-tests."""

from __future__ import annotations

import re
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "research-doujiao-value-company"
REQUIRED = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/source-routing.md",
    "references/research-contract.md",
    "references/evidence-and-calculation.md",
    "references/valuation-qa.md",
    "references/qa-gates.md",
    "references/trusted-spec-lock.json",
    "scripts/validate_research_package.py",
    "scripts/freeze_research.py",
    "scripts/validate_skill.py",
    "tests/test_incremental_chain.py",
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
        import json

        lock = json.loads((ROOT / "references/trusted-spec-lock.json").read_text(encoding="utf-8"))
        if lock.get("repository") != "bits-bean/doujiao-value-system" or lock.get("ref") != "main":
            fail("trusted specification lock has the wrong repository or ref")
            errors += 1
        if re.fullmatch(r"[0-9a-f]{40}", str(lock.get("commit", ""))) is None:
            fail("trusted specification lock lacks an exact commit")
            errors += 1
        schema_blob = lock.get("files", {}).get("schemas/company.schema.json")
        if re.fullmatch(r"[0-9a-f]{40}", str(schema_blob or "")) is None:
            fail("trusted specification lock lacks the Schema blob")
            errors += 1
    except (OSError, ValueError, AttributeError) as exc:
        fail(f"invalid trusted specification lock: {exc}")
        errors += 1

    with tempfile.TemporaryDirectory() as temp_dir:
        for script in ("validate_research_package.py", "freeze_research.py", "validate_skill.py"):
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
