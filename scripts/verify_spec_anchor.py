#!/usr/bin/env python3
"""Verify that current main descends from the approved spec anchor without protected-file changes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from validate_research_package import load_json, write_json


LOCK_PATH = Path(__file__).resolve().parents[1] / "references" / "trusted-spec-lock.json"
SHA1 = re.compile(r"[0-9a-f]{40}")


class SpecAnchorError(ValueError):
    """Raised when a repository is not compatible with the trusted spec anchor."""


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
        raise SpecAnchorError("spec repository must be a non-symlink directory")
    repo = repo.resolve()
    if _git(repo, "rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        raise SpecAnchorError("spec repository is not a Git worktree")

    expected_repo = lock.get("repository")
    if not isinstance(expected_repo, str) or not expected_repo:
        raise SpecAnchorError("trusted lock lacks repository identity")
    remote = _git(repo, "remote", "get-url", "origin").stdout.strip()
    if _normalize_remote(remote) != expected_repo:
        raise SpecAnchorError("origin does not match the trusted specification repository")

    anchor = str(lock.get("commit", ""))
    if SHA1.fullmatch(anchor) is None:
        raise SpecAnchorError("trusted lock lacks an exact anchor commit")
    head = _git(repo, "rev-parse", f"{head_ref}^{{commit}}").stdout.strip()
    if SHA1.fullmatch(head) is None:
        raise SpecAnchorError("head ref did not resolve to an exact commit")
    ancestor = _git(repo, "merge-base", "--is-ancestor", anchor, head, check=False)
    if ancestor.returncode == 1:
        raise SpecAnchorError("trusted spec anchor is not an ancestor of the selected head")
    if ancestor.returncode != 0:
        raise SpecAnchorError(ancestor.stderr.strip() or "cannot verify spec anchor ancestry")

    protected = lock.get("files")
    if not isinstance(protected, dict) or not protected:
        raise SpecAnchorError("trusted lock has no protected files")
    resolved_files: dict[str, str] = {}
    for path, expected_blob in protected.items():
        if not isinstance(path, str) or Path(path).is_absolute() or ".." in Path(path).parts:
            raise SpecAnchorError("trusted lock contains an unsafe protected path")
        if SHA1.fullmatch(str(expected_blob)) is None:
            raise SpecAnchorError(f"trusted lock has invalid blob for {path}")
        actual_blob = _git(repo, "rev-parse", f"{head}:{path}").stdout.strip()
        if actual_blob != expected_blob:
            raise SpecAnchorError(f"protected specification file changed: {path}")
        resolved_files[path] = actual_blob

    return {
        "repository": expected_repo,
        "head_ref": head_ref,
        "head_commit": head,
        "anchor_commit": anchor,
        "anchor_is_ancestor": True,
        "protected_files": resolved_files,
        "compatible": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path, help="Trusted checkout of bits-bean/doujiao-value-system")
    parser.add_argument("--head-ref", default="main")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        lock = load_json(LOCK_PATH)
        if not isinstance(lock, dict):
            raise SpecAnchorError("trusted specification lock must be an object")
        result = verify_spec_anchor(args.repo, lock, args.head_ref)
        if args.output:
            if args.output.is_symlink():
                raise SpecAnchorError("output cannot be a symlink")
            write_json(args.output, result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError, SpecAnchorError) as exc:
        print(f"Spec anchor verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
