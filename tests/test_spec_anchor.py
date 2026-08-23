#!/usr/bin/env python3
"""Regression tests for spec-anchor compatibility after research-data commits."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_spec_anchor import SpecAnchorError, verify_spec_anchor  # noqa: E402


class SpecAnchorTests(unittest.TestCase):
    def git(self, repo: Path, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    def write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def make_repo(self, root: Path) -> tuple[Path, dict]:
        repo = root / "repo"
        repo.mkdir()
        self.git(repo, "init", "-b", "main")
        self.git(repo, "config", "user.name", "Test")
        self.git(repo, "config", "user.email", "test@example.com")
        self.git(repo, "remote", "add", "origin", "https://github.com/bits-bean/doujiao-value-system.git")
        source_paths = (
            "docs/research-methodology.md",
            "schemas/company.schema.json",
        )
        for path in source_paths:
            self.write(repo / path, f"trusted {path}\n")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", "trusted spec")
        anchor = self.git(repo, "rev-parse", "HEAD")
        lock = {
            "lock_version": "2.0",
            "research_protocol": {"authority": "research-doujiao-value-company"},
            "company_schema": {
                "repository": "bits-bean/doujiao-value-system",
                "ref": "main",
                "commit": anchor,
                "path": "schemas/company.schema.json",
                "blob_sha1": self.git(repo, "rev-parse", "HEAD:schemas/company.schema.json"),
            },
        }
        return repo, lock

    def test_data_only_commit_can_advance_main(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, lock = self.make_repo(Path(temp_dir))
            self.write(repo / "companies/test/company.json", "{}\n")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "archive research")
            result = verify_spec_anchor(repo, lock)
            self.assertTrue(result["compatible"])
            self.assertNotEqual(result["head_commit"], result["schema_anchor_commit"])

    def test_system_method_change_does_not_change_skill_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, lock = self.make_repo(Path(temp_dir))
            self.write(repo / "docs/research-methodology.md", "changed\n")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "change method")
            result = verify_spec_anchor(repo, lock)
            self.assertTrue(result["compatible"])

    def test_schema_change_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, lock = self.make_repo(Path(temp_dir))
            self.write(repo / "schemas/company.schema.json", "changed\n")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "change schema")
            with self.assertRaises(SpecAnchorError):
                verify_spec_anchor(repo, lock)

    def test_non_descendant_head_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, lock = self.make_repo(Path(temp_dir))
            self.git(repo, "checkout", "--orphan", "other")
            self.git(repo, "rm", "-rf", ".")
            self.write(repo / "unrelated.txt", "unrelated\n")
            self.git(repo, "add", ".")
            self.git(repo, "commit", "-m", "unrelated")
            with self.assertRaises(SpecAnchorError):
                verify_spec_anchor(repo, lock, "other")


if __name__ == "__main__":
    unittest.main()
