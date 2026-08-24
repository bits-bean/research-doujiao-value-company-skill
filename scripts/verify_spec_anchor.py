#!/usr/bin/env python3
"""Verify the system repository's Schema anchor; research protocol lives in this Skill."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from validate_research_package import (
    EXPECTED_SCHEMA_PATH,
    load_trusted_spec_lock,
    write_json,
)


SHA1 = re.compile(r"[0-9a-f]{40}")


class SpecAnchorError(ValueError):
    """Raised when the authoritative Schema repository is incompatible with the lock."""


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise SpecAnchorError(f"cannot execute git: {exc}") from exc
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise SpecAnchorError(detail)
    return completed


def _normalize_remote(url: str) -> str | None:
    value = url.strip()
    ssh = re.fullmatch(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?", value)
    if ssh:
        return ssh.group(1).removesuffix(".git")
    https = re.fullmatch(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?", value)
    if https:
        return https.group(1).removesuffix(".git")
    return None


def verify_spec_anchor(repo: Path, lock: dict[str, Any], head_ref: str = "main") -> dict[str, Any]:
    if repo.is_symlink() or not repo.is_dir():
        raise SpecAnchorError("Schema repository must be a non-symlink directory")
    repo = repo.resolve()
    if _git(repo, "rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        raise SpecAnchorError("Schema repository is not a Git worktree")

    schema = lock.get("company_schema")
    if not isinstance(schema, dict):
        raise SpecAnchorError("trusted v3 lock lacks company_schema")
    expected_repo = schema.get("repository")
    if not isinstance(expected_repo, str) or not expected_repo:
        raise SpecAnchorError("company_schema lacks repository identity")
    remote = _git(repo, "remote", "get-url", "origin").stdout.strip()
    if _normalize_remote(remote) != expected_repo:
        raise SpecAnchorError("origin does not match the authoritative Schema repository")

    anchor = str(schema.get("commit", ""))
    if SHA1.fullmatch(anchor) is None:
        raise SpecAnchorError("company_schema lacks an exact anchor commit")
    if schema.get("ref") != "main":
        raise SpecAnchorError("company_schema ref must be main")
    schema_path = schema.get("path")
    if schema_path != EXPECTED_SCHEMA_PATH:
        raise SpecAnchorError("company_schema path is not the authoritative company Schema")
    expected_blob = str(schema.get("blob_sha1", ""))
    if SHA1.fullmatch(expected_blob) is None:
        raise SpecAnchorError("company_schema lacks an exact blob SHA")

    head = _git(repo, "rev-parse", f"{head_ref}^{{commit}}").stdout.strip()
    if SHA1.fullmatch(head) is None:
        raise SpecAnchorError("head ref did not resolve to an exact commit")
    ancestor = _git(repo, "merge-base", "--is-ancestor", anchor, head, check=False)
    if ancestor.returncode == 1:
        raise SpecAnchorError("trusted Schema anchor is not an ancestor of the selected head")
    if ancestor.returncode != 0:
        raise SpecAnchorError(ancestor.stderr.strip() or "cannot verify Schema anchor ancestry")

    actual_blob = _git(repo, "rev-parse", f"{head}:{schema_path}").stdout.strip()
    if actual_blob != expected_blob:
        raise SpecAnchorError(f"authoritative Schema changed: {schema_path}")

    return {
        "repository": expected_repo,
        "head_ref": head_ref,
        "head_commit": head,
        "schema_anchor_commit": anchor,
        "anchor_is_ancestor": True,
        "schema_path": schema_path,
        "schema_blob_sha1": actual_blob,
        "compatible": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path, help="Trusted checkout of bits-bean/doujiao-value-system")
    parser.add_argument("--head-ref", default="main")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        findings: list[Any] = []
        lock = load_trusted_spec_lock(findings)
        if lock is None:
            raise SpecAnchorError("bundled v3 trust lock or local Skill execution files failed integrity validation")
        result = verify_spec_anchor(args.repo, lock, args.head_ref)
        if args.output:
            if args.output.is_symlink():
                raise SpecAnchorError("output cannot be a symlink")
            write_json(args.output, result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError, SpecAnchorError) as exc:
        print(f"Schema anchor verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
