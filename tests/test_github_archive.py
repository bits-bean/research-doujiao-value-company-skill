#!/usr/bin/env python3
"""Regression tests for the optional GitHub archive planning gate."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_github_archive import ArchivePlanError, build_archive_plan, snapshot_action  # noqa: E402
from validate_research_package import (  # noqa: E402
    EXPECTED_SCHEMA_PATH,
    EXPECTED_SPEC_REPOSITORY,
    FROZEN_HASH_FILES,
    Finding,
    file_sha256,
    git_blob_sha1_candidates,
    write_json,
)


class GithubArchiveTests(unittest.TestCase):
    def make_package(self, root: Path) -> tuple[Path, Path, dict]:
        schema_path = root / "company.schema.json"
        write_json(schema_path, {"$schema": "test", "version": "test-1"})
        schema_blob = next(iter(git_blob_sha1_candidates(schema_path)))
        trusted_lock = {
            "repository": EXPECTED_SPEC_REPOSITORY,
            "ref": "main",
            "commit": "a" * 40,
            "schema_version": "test-1",
            "files": {EXPECTED_SCHEMA_PATH: schema_blob},
        }
        package = root / "package"
        package.mkdir()
        meta = {
            "schema_version": "test-1",
            "company_name_cn": "测试公司",
            "company_name_en": "Test Company",
            "ticker": "TEST",
            "exchange": "NYSE",
            "report_currency": "USD",
            "data_as_of": "2025-12-31",
            "valuation_date": "2026-01-15",
            "source_version": "FY2025",
        }
        write_json(package / "company.json", {"meta": meta, "sources": []})
        for name in FROZEN_HASH_FILES:
            if name == "company.json":
                continue
            if name == "validation-report.json":
                write_json(
                    package / name,
                    {"validator": "doujiao-research-validator", "mode": "full", "errors": 0, "warnings": 0},
                )
            elif name.endswith(".json"):
                write_json(package / name, {"ok": True})
            else:
                (package / name).write_text(f"verified {name}\n", encoding="utf-8")
        manifest = {
            "manifest_version": "1.0",
            "status": "frozen",
            "human_review_status": "accepted",
            "warning_acknowledged": False,
            "frozen_at": "2026-01-15T12:00:00Z",
            "specification": {
                "repository": EXPECTED_SPEC_REPOSITORY,
                "ref": "main",
                "commit": "a" * 40,
                "schema_path": EXPECTED_SCHEMA_PATH,
                "schema_sha256": file_sha256(schema_path),
                "schema_blob_sha1": schema_blob,
                "schema_version": "test-1",
            },
            "research": {
                key: meta[key]
                for key in (
                    "company_name_cn",
                    "company_name_en",
                    "ticker",
                    "exchange",
                    "report_currency",
                    "data_as_of",
                    "valuation_date",
                    "source_version",
                )
            },
            "update_mode": "full",
            "validation": {"validator": "doujiao-research-validator", "mode": "full", "errors": 0, "warnings": 0},
            "files": [
                {
                    "path": name,
                    "sha256": file_sha256(package / name),
                    "size_bytes": (package / name).stat().st_size,
                }
                for name in FROZEN_HASH_FILES
            ],
        }
        write_json(package / "research-manifest.json", manifest)
        return package, schema_path, trusted_lock

    def plan(self, package: Path, schema: Path, lock: dict, **kwargs: object) -> dict:
        if kwargs.get("existing_company_path") is not None and "existing_company_head" not in kwargs:
            kwargs["existing_company_head"] = "b" * 40
        with patch("prepare_github_archive.validate_research_package", return_value=[]):
            return build_archive_plan(
                package,
                schema,
                company_slug="test-company",
                version="2026-01-15",
                strategy="pull-request",
                promotion="archive-and-promote",
                promotion_authorized=True,
                trusted_lock=lock,
                **kwargs,
            )

    def test_plan_contains_exact_snapshot_and_canonical_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            plan = self.plan(package, schema, lock, canonical_absent=True)
            self.assertEqual(plan["repository"], EXPECTED_SPEC_REPOSITORY)
            self.assertEqual(plan["snapshot"]["root"], "research/test-company/2026-01-15")
            targets = {item["target_path"] for item in plan["snapshot"]["files"]}
            self.assertIn("research/test-company/2026-01-15/research-manifest.json", targets)
            self.assertEqual(len(targets), len(FROZEN_HASH_FILES) + 1)
            self.assertEqual(plan["canonical_company"]["target_path"], "companies/test-company/company.json")
            self.assertEqual(plan["canonical_company"]["action"], "create")
            remote_state = {
                "repository": EXPECTED_SPEC_REPOSITORY,
                "branch": "main",
                "base_head": "c" * 40,
                "root": "research/test-company/2026-01-15",
                "exists": False,
                "files": [],
            }
            with patch("prepare_github_archive.validate_research_package", return_value=[]):
                ready = build_archive_plan(
                    package,
                    schema,
                    company_slug="test-company",
                    version="2026-01-15",
                    strategy="pull-request",
                    promotion="archive-and-promote",
                    write_authorized=True,
                    promotion_authorized=True,
                    remote_snapshot_state=remote_state,
                    canonical_absent=True,
                    trusted_lock=lock,
                )
            self.assertTrue(ready["ready_for_write"])
            self.assertEqual(ready["base_head"], "c" * 40)

    def test_unaccepted_or_mutated_package_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            manifest_path = package / "research-manifest.json"
            manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
            manifest["human_review_status"] = "pending"
            write_json(manifest_path, manifest)
            with self.assertRaises(ArchivePlanError):
                self.plan(package, schema, lock, canonical_absent=True)

            manifest["human_review_status"] = "accepted"
            write_json(manifest_path, manifest)
            (package / "research-report.md").write_text("mutated\n", encoding="utf-8")
            with self.assertRaises(ArchivePlanError):
                self.plan(package, schema, lock, canonical_absent=True)

    def test_slug_and_version_cannot_escape_repository_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            with self.assertRaises(ArchivePlanError):
                build_archive_plan(
                    package,
                    schema,
                    company_slug="../escape",
                    version="2026-01-15",
                    strategy="pull-request",
                    promotion="archive-and-promote",
                    canonical_absent=True,
                    trusted_lock=lock,
                )
            with self.assertRaises(ArchivePlanError):
                build_archive_plan(
                    package,
                    schema,
                    company_slug="test-company",
                    version="2026-01-15-v1",
                    strategy="pull-request",
                    promotion="archive-only",
                    trusted_lock=lock,
                )
            with self.assertRaises(ArchivePlanError):
                build_archive_plan(
                    package,
                    schema,
                    company_slug="test-company",
                    version="latest",
                    strategy="pull-request",
                    promotion="archive-and-promote",
                    canonical_absent=True,
                    trusted_lock=lock,
                )

    def test_canonical_update_is_monotonic_and_identity_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            existing = root / "existing.json"
            existing.write_bytes((package / "company.json").read_bytes())
            plan = self.plan(package, schema, lock, existing_company_path=existing)
            self.assertEqual(plan["canonical_company"]["action"], "noop")

            company = __import__("json").loads(existing.read_text(encoding="utf-8"))
            company["meta"]["data_as_of"] = "2025-09-30"
            write_json(existing, company)
            plan = self.plan(package, schema, lock, existing_company_path=existing)
            self.assertEqual(plan["canonical_company"]["action"], "update")

            company["meta"]["data_as_of"] = "2026-03-31"
            write_json(existing, company)
            with self.assertRaises(ArchivePlanError):
                self.plan(package, schema, lock, existing_company_path=existing)

            company["meta"]["data_as_of"] = "2025-12-31"
            company["meta"]["ticker"] = "OTHER"
            write_json(existing, company)
            with self.assertRaises(ArchivePlanError):
                self.plan(package, schema, lock, existing_company_path=existing)

    def test_same_date_different_content_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            existing = root / "existing.json"
            company = copy.deepcopy(__import__("json").loads((package / "company.json").read_text(encoding="utf-8")))
            company["sources"] = [{"id": "DIFFERENT"}]
            write_json(existing, company)
            with self.assertRaises(ArchivePlanError):
                self.plan(package, schema, lock, existing_company_path=existing)

            with patch("prepare_github_archive.validate_research_package", return_value=[]):
                plan = build_archive_plan(
                    package,
                    schema,
                    company_slug="test-company",
                    version="2026-01-15-v2",
                    strategy="pull-request",
                    promotion="archive-and-promote",
                    promotion_authorized=True,
                    existing_company_path=existing,
                    existing_company_head="b" * 40,
                    confirm_same_date_revision=True,
                    trusted_lock=lock,
                )
            self.assertEqual(plan["canonical_company"]["action"], "update-confirmed-revision")

    def test_archive_only_never_plans_a_canonical_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            with patch("prepare_github_archive.validate_research_package", return_value=[]):
                plan = build_archive_plan(
                    package,
                    schema,
                    company_slug="test-company",
                    version="2026-01-15",
                    strategy="pull-request",
                    promotion="archive-only",
                    trusted_lock=lock,
                )
            self.assertEqual(plan["canonical_company"]["action"], "not-requested")
            with self.assertRaises(ArchivePlanError):
                build_archive_plan(
                    package,
                    schema,
                    company_slug="test-company",
                    version="2026-01-15",
                    strategy="pull-request",
                    promotion="archive-only",
                    canonical_absent=True,
                    trusted_lock=lock,
                )

    def test_sensitive_material_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            report = package / "research-report.md"
            report.write_text("token=abcdefghijklmnop1234567890\n", encoding="utf-8")
            manifest_path = package / "research-manifest.json"
            manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest["files"]:
                if entry["path"] == "research-report.md":
                    entry["sha256"] = file_sha256(report)
                    entry["size_bytes"] = report.stat().st_size
            write_json(manifest_path, manifest)
            with self.assertRaises(ArchivePlanError):
                self.plan(package, schema, lock, canonical_absent=True)

    def test_forged_zero_error_report_does_not_replace_fresh_full_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            with self.assertRaisesRegex(ArchivePlanError, "fresh full validation failed"):
                build_archive_plan(
                    package,
                    schema,
                    company_slug="test-company",
                    version="2026-01-15",
                    strategy="pull-request",
                    promotion="archive-only",
                    trusted_lock=lock,
                )

    def test_fresh_warning_count_must_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            warning = Finding("warning", "fresh-warning", "company.json", "warning")
            with patch("prepare_github_archive.validate_research_package", return_value=[warning]):
                with self.assertRaisesRegex(ArchivePlanError, "counts do not match"):
                    build_archive_plan(
                        package,
                        schema,
                        company_slug="test-company",
                        version="2026-01-15",
                        strategy="pull-request",
                        promotion="archive-only",
                        trusted_lock=lock,
                    )

    def test_remote_snapshot_create_noop_and_conflict(self) -> None:
        root = "research/test-company/2026-01-15"
        local = [
            {"target_path": f"{root}/company.json", "sha256": "a" * 64, "size_bytes": 10},
            {"target_path": f"{root}/research-manifest.json", "sha256": "b" * 64, "size_bytes": 20},
        ]
        absent = {
            "repository": EXPECTED_SPEC_REPOSITORY,
            "branch": "main",
            "base_head": "c" * 40,
            "root": root,
            "exists": False,
            "files": [],
        }
        self.assertEqual(snapshot_action(root, local, absent), ("create", "c" * 40))
        present = {
            **absent,
            "exists": True,
            "files": [
                {"path": "company.json", "sha256": "a" * 64, "size_bytes": 10},
                {"path": "research-manifest.json", "sha256": "b" * 64, "size_bytes": 20},
            ],
        }
        self.assertEqual(snapshot_action(root, local, present), ("noop", "c" * 40))
        for files in (
            present["files"][:-1],
            present["files"] + [{"path": "extra.txt", "sha256": "d" * 64, "size_bytes": 1}],
            [{**present["files"][0], "sha256": "e" * 64}, present["files"][1]],
        ):
            with self.subTest(files=files), self.assertRaisesRegex(ArchivePlanError, "immutable snapshot conflict"):
                snapshot_action(root, local, {**present, "files": files})

    def test_newer_data_cannot_hide_valuation_date_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            existing = root / "existing.json"
            company = __import__("json").loads((package / "company.json").read_text(encoding="utf-8"))
            company["meta"]["data_as_of"] = "2025-09-30"
            company["meta"]["valuation_date"] = "2027-01-01"
            write_json(existing, company)
            with self.assertRaisesRegex(ArchivePlanError, "valuation_date"):
                self.plan(package, schema, lock, existing_company_path=existing)

    def test_direct_main_requires_separate_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            with self.assertRaisesRegex(ArchivePlanError, "direct-main authorization"):
                build_archive_plan(
                    package,
                    schema,
                    company_slug="test-company",
                    version="2026-01-15",
                    strategy="direct-main",
                    promotion="archive-only",
                    trusted_lock=lock,
                )


if __name__ == "__main__":
    unittest.main()
