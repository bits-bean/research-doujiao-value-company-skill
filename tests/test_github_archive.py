#!/usr/bin/env python3
"""Regression tests for the fail-closed GitHub delivery planning gate."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_github_archive import (  # noqa: E402
    ArchivePlanError,
    build_archive_plan,
    canonical_action,
    package_action,
)
from validate_research_package import (  # noqa: E402
    EXPECTED_SCHEMA_PATH,
    EXPECTED_SPEC_REPOSITORY,
    FROZEN_HASH_FILES,
    Finding,
    file_sha256,
    git_blob_sha1_candidates,
    write_json,
)


class GithubDeliveryTests(unittest.TestCase):
    def make_package(self, root: Path) -> tuple[Path, Path, dict]:
        schema_path = root / "company.schema.json"
        write_json(schema_path, {"$schema": "test", "version": "test-1"})
        schema_blob = next(iter(git_blob_sha1_candidates(schema_path)))
        research_protocol = {
            "authority": "research-doujiao-value-company",
            "repository": "bits-bean/doujiao-value-research-skill",
            "ref": "main",
            "commit": "c" * 40,
            "protocol_version": "test-1",
            "digest_sha256": "d" * 64,
            "documents": [],
        }
        trusted_lock = {
            "lock_version": "2.0",
            "research_protocol": research_protocol,
            "company_schema": {
                "repository": EXPECTED_SPEC_REPOSITORY,
                "ref": "main",
                "commit": "a" * 40,
                "path": EXPECTED_SCHEMA_PATH,
                "blob_sha1": schema_blob,
                "schema_version": "test-1",
            },
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
            "manifest_version": "2.0",
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
            "research_protocol": research_protocol,
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
            "validation": {
                "validator": "doujiao-research-validator",
                "mode": "full",
                "errors": 0,
                "warnings": 0,
            },
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

    @staticmethod
    def identity() -> dict[str, str]:
        return {
            "company_name_cn": "测试公司",
            "company_name_en": "Test Company",
            "ticker": "TEST",
            "exchange": "NYSE",
        }

    def registry_state(
        self,
        base_head: str = "c" * 40,
        *,
        company_slug: str = "test-company",
        identity: dict[str, str] | None = None,
        slug_exists: bool = False,
    ) -> dict:
        requested_identity = identity or self.identity()
        return {
            "repository": EXPECTED_SPEC_REPOSITORY,
            "branch": "main",
            "base_head": base_head,
            "company_slug": company_slug,
            "identity": requested_identity,
            "slug_exists": slug_exists,
            "slug_identity": requested_identity if slug_exists else None,
            "identity_slugs": [company_slug] if slug_exists else [],
        }

    @staticmethod
    def company_state(*, base_head: str = "c" * 40, exists: bool = False, files: list | None = None) -> dict:
        return {
            "repository": EXPECTED_SPEC_REPOSITORY,
            "branch": "main",
            "base_head": base_head,
            "root": "companies/test-company",
            "exists": exists,
            "files": files or [],
        }

    @staticmethod
    def canonical_absent_state(base_head: str = "c" * 40) -> dict:
        return {
            "repository": EXPECTED_SPEC_REPOSITORY,
            "branch": "main",
            "base_head": base_head,
            "path": "companies/test-company/company.json",
            "exists": False,
            "content": None,
        }

    @staticmethod
    def canonical_present_state(path: Path, base_head: str = "c" * 40) -> dict:
        company = json.loads(path.read_text(encoding="utf-8"))
        meta = company["meta"]
        return {
            "repository": EXPECTED_SPEC_REPOSITORY,
            "branch": "main",
            "base_head": base_head,
            "path": "companies/test-company/company.json",
            "exists": True,
            "content": {
                "source_path": str(path),
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
                "identity": {
                    key: meta[key]
                    for key in (
                        "company_name_cn",
                        "company_name_en",
                        "ticker",
                        "exchange",
                        "schema_version",
                    )
                },
            },
        }

    def plan(self, package: Path, schema: Path, lock: dict, **kwargs: object) -> dict:
        with (
            patch("freeze_research.validate_research_package", return_value=[]),
            patch("prepare_github_archive.validate_research_package", return_value=[]),
        ):
            return build_archive_plan(
                package,
                schema,
                company_slug="test-company",
                strategy="pull-request",
                trusted_lock=lock,
                **kwargs,
            )

    def test_plan_uses_single_flat_company_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            preflight = self.plan(package, schema, lock)
            self.assertEqual(preflight["company_package"]["root"], "companies/test-company")
            targets = {item["target_path"] for item in preflight["company_package"]["files"]}
            self.assertIn("companies/test-company/research-manifest.json", targets)
            self.assertIn("companies/test-company/company.json", targets)
            self.assertFalse(any("2026-01-15" in target for target in targets))
            self.assertEqual(
                preflight["canonical_guard"]["target_path"],
                "companies/test-company/company.json",
            )
            self.assertEqual(preflight["canonical_guard"]["action"], "remote-preflight-required")

            ready = self.plan(
                package,
                schema,
                lock,
                write_authorized=True,
                remote_company_state=self.company_state(),
                remote_slug_registry_state=self.registry_state(),
                remote_canonical_state=self.canonical_absent_state(),
            )
            self.assertTrue(ready["ready_for_write"])
            self.assertEqual(ready["delivery_mode"], "single-company-directory")
            self.assertEqual(ready["company_package"]["remote_action"], "create")
            self.assertEqual(ready["canonical_guard"]["action"], "create")

    def test_v1_unaccepted_or_mutated_package_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            manifest_path = package / "research-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["manifest_version"] = "1.0"
            manifest.pop("research_protocol")
            write_json(manifest_path, manifest)
            with self.assertRaises(ArchivePlanError):
                self.plan(package, schema, lock)

        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            manifest_path = package / "research-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["human_review_status"] = "pending"
            write_json(manifest_path, manifest)
            with self.assertRaises(ArchivePlanError):
                self.plan(package, schema, lock)

        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            (package / "research-report.md").write_text("mutated\n", encoding="utf-8")
            with self.assertRaises(ArchivePlanError):
                self.plan(package, schema, lock)

    def test_slug_cannot_escape_repository_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            with self.assertRaises(ArchivePlanError):
                build_archive_plan(
                    package,
                    schema,
                    company_slug="../escape",
                    strategy="pull-request",
                    trusted_lock=lock,
                )

    def test_package_action_create_noop_update_and_extra_deletion(self) -> None:
        root = "companies/test-company"
        local = [
            {"target_path": f"{root}/company.json", "sha256": "a" * 64, "size_bytes": 10},
            {"target_path": f"{root}/research-manifest.json", "sha256": "b" * 64, "size_bytes": 20},
        ]
        absent = self.company_state()
        self.assertEqual(package_action(root, local, absent), ("create", "c" * 40, []))
        present_files = [
            {"path": "company.json", "sha256": "a" * 64, "size_bytes": 10},
            {"path": "research-manifest.json", "sha256": "b" * 64, "size_bytes": 20},
        ]
        present = self.company_state(exists=True, files=present_files)
        self.assertEqual(package_action(root, local, present), ("noop", "c" * 40, []))

        changed = self.company_state(
            exists=True,
            files=[
                {**present_files[0], "sha256": "d" * 64},
                present_files[1],
                {"path": "schema-gap-report.md", "sha256": "e" * 64, "size_bytes": 1},
                {"path": "logo.svg", "sha256": "f" * 64, "size_bytes": 1},
            ],
        )
        self.assertEqual(
            package_action(root, local, changed),
            ("update", "c" * 40, ["companies/test-company/schema-gap-report.md"]),
        )

    def test_company_state_requires_exact_flat_company_root(self) -> None:
        local = [{"target_path": "companies/test-company/company.json", "sha256": "a" * 64, "size_bytes": 1}]
        nested = {**self.company_state(), "root": "companies/test-company/2026-01-15"}
        with self.assertRaisesRegex(ArchivePlanError, "different company path"):
            package_action("companies/test-company", local, nested)
        extra_key = {**self.company_state(), "legacy": []}
        with self.assertRaisesRegex(ArchivePlanError, "unexpected or missing"):
            package_action("companies/test-company", local, extra_key)

    def test_canonical_update_is_monotonic_and_identity_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, _, _ = self.make_package(root)
            new_path = package / "company.json"
            existing = root / "existing.json"
            existing.write_bytes(new_path.read_bytes())
            self.assertEqual(
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=False,
                ),
                "noop",
            )

            company = json.loads(existing.read_text(encoding="utf-8"))
            company["meta"]["data_as_of"] = "2025-09-30"
            company["meta"]["valuation_date"] = "2025-10-15"
            write_json(existing, company)
            self.assertEqual(
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=False,
                ),
                "update",
            )

            company["meta"]["data_as_of"] = "2026-03-31"
            write_json(existing, company)
            with self.assertRaisesRegex(ArchivePlanError, "data_as_of"):
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=False,
                )

            company["meta"]["data_as_of"] = "2025-12-31"
            company["meta"]["ticker"] = "OTHER"
            write_json(existing, company)
            with self.assertRaisesRegex(ArchivePlanError, "ticker"):
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=True,
                )

    def test_same_date_revision_requires_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            existing = root / "existing.json"
            company = copy.deepcopy(json.loads((package / "company.json").read_text(encoding="utf-8")))
            company["sources"] = [{"id": "DIFFERENT"}]
            write_json(existing, company)
            state = self.canonical_present_state(existing)
            with self.assertRaisesRegex(ArchivePlanError, "same data_as_of"):
                self.plan(
                    package,
                    schema,
                    lock,
                    remote_company_state=self.company_state(),
                    remote_slug_registry_state=self.registry_state(),
                    remote_canonical_state=state,
                )
            plan = self.plan(
                package,
                schema,
                lock,
                write_authorized=True,
                remote_company_state=self.company_state(),
                remote_slug_registry_state=self.registry_state(),
                remote_canonical_state=state,
                confirm_same_date_revision=True,
            )
            self.assertTrue(plan["ready_for_write"])
            self.assertEqual(plan["canonical_guard"]["action"], "update-confirmed-revision")

    def test_all_three_remote_observations_are_required_at_same_head(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            missing = self.plan(
                package,
                schema,
                lock,
                write_authorized=True,
                remote_company_state=self.company_state(),
                remote_slug_registry_state=self.registry_state(),
            )
            self.assertFalse(missing["ready_for_write"])
            self.assertEqual(missing["canonical_guard"]["action"], "remote-preflight-required")

            with self.assertRaisesRegex(ArchivePlanError, "different base heads"):
                self.plan(
                    package,
                    schema,
                    lock,
                    write_authorized=True,
                    remote_company_state=self.company_state(),
                    remote_slug_registry_state=self.registry_state("d" * 40),
                    remote_canonical_state=self.canonical_absent_state(),
                )

    def test_slug_registry_binding_is_identity_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            with self.assertRaisesRegex(ArchivePlanError, "different company slug"):
                self.plan(
                    package,
                    schema,
                    lock,
                    remote_company_state=self.company_state(),
                    remote_slug_registry_state=self.registry_state(company_slug="wrong-company"),
                    remote_canonical_state=self.canonical_absent_state(),
                )
            with self.assertRaisesRegex(ArchivePlanError, "frozen research package"):
                self.plan(
                    package,
                    schema,
                    lock,
                    remote_company_state=self.company_state(),
                    remote_slug_registry_state=self.registry_state(identity={**self.identity(), "ticker": "OTHER"}),
                    remote_canonical_state=self.canonical_absent_state(),
                )

    def test_sensitive_material_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            report = package / "research-report.md"
            report.write_text("token=abcdefghijklmnop1234567890\n", encoding="utf-8")
            manifest_path = package / "research-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in manifest["files"]:
                if entry["path"] == "research-report.md":
                    entry["sha256"] = file_sha256(report)
                    entry["size_bytes"] = report.stat().st_size
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ArchivePlanError, "sensitive material"):
                self.plan(package, schema, lock)

    def test_fresh_validation_cannot_be_replaced_by_recorded_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            with self.assertRaisesRegex(ArchivePlanError, "fresh full validation failed"):
                build_archive_plan(
                    package,
                    schema,
                    company_slug="test-company",
                    strategy="pull-request",
                    trusted_lock=lock,
                )

    def test_fresh_warning_count_must_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            warning = Finding("warning", "fresh-warning", "company.json", "warning")
            with (
                patch("freeze_research.validate_research_package", return_value=[warning]),
                patch("prepare_github_archive.validate_research_package", return_value=[warning]),
            ):
                with self.assertRaisesRegex(ArchivePlanError, "counts do not match"):
                    build_archive_plan(
                        package,
                        schema,
                        company_slug="test-company",
                        strategy="pull-request",
                        trusted_lock=lock,
                    )

    def test_canonical_observation_hash_and_identity_are_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            existing = root / "existing.json"
            existing.write_bytes((package / "company.json").read_bytes())
            state = self.canonical_present_state(existing)
            state["content"]["sha256"] = "f" * 64
            with self.assertRaisesRegex(ArchivePlanError, "hash or size"):
                self.plan(
                    package,
                    schema,
                    lock,
                    remote_company_state=self.company_state(),
                    remote_slug_registry_state=self.registry_state(),
                    remote_canonical_state=state,
                )

    def test_newer_data_cannot_hide_valuation_date_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, _, _ = self.make_package(root)
            existing = root / "existing.json"
            company = json.loads((package / "company.json").read_text(encoding="utf-8"))
            company["meta"]["data_as_of"] = "2025-09-30"
            company["meta"]["valuation_date"] = "2027-01-01"
            write_json(existing, company)
            with self.assertRaisesRegex(ArchivePlanError, "valuation_date"):
                canonical_action(
                    package / "company.json",
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=False,
                )

    def test_direct_main_requires_separate_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            with self.assertRaisesRegex(ArchivePlanError, "direct-main authorization"):
                build_archive_plan(
                    package,
                    schema,
                    company_slug="test-company",
                    strategy="direct-main",
                    trusted_lock=lock,
                )


if __name__ == "__main__":
    unittest.main()
