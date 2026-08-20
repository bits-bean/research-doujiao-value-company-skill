#!/usr/bin/env python3
"""Regression tests for verified incremental research ancestry."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from freeze_research import (  # noqa: E402
    build_manifest,
    validate_incremental_transition,
    verify_previous_manifest,
)
from package_fixture import make_valid_unfrozen_package  # noqa: E402
from validate_research_package import (  # noqa: E402
    file_sha256,
    git_blob_sha1_candidates,
    load_json,
    write_json,
)


class IncrementalChainTests(unittest.TestCase):
    def make_predecessor(self, root: Path, *, with_gap: bool = False) -> tuple[Path, Path, dict, dict]:
        package, schema_path, _ = make_valid_unfrozen_package(root)
        trusted_lock = load_json(ROOT / "references/trusted-spec-lock.json")
        validation = {
            "validator": "research-doujiao-value-company/2.0",
            "mode": "full",
            "errors": 0,
            "warnings": 0,
        }
        write_json(package / "validation-report.json", validation)
        if with_gap:
            (package / "schema-gap-report.md").write_text("# Schema gap\nDocumented.\n", encoding="utf-8")
        company_schema = trusted_lock["company_schema"]
        manifest = build_manifest(
            package,
            schema_path,
            company_schema["commit"],
            company_schema["ref"],
            company_schema["blob_sha1"],
            trusted_lock["research_protocol"],
            "full",
            validation,
            True,
            False,
        )
        manifest_path = package / "research-manifest.json"
        write_json(manifest_path, manifest)
        return manifest_path, schema_path, trusted_lock, manifest

    def test_v1_predecessor_is_audit_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path, schema_path, trusted_lock, manifest = self.make_predecessor(Path(temp_dir))
            manifest["manifest_version"] = "1.0"
            manifest.pop("research_protocol")
            self.write_manifest(manifest_path, manifest)
            _, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock)
            self.assertTrue(any("audit-only" in item for item in errors), errors)

    def write_manifest(self, path: Path, manifest: dict) -> None:
        write_json(path, manifest)

    def test_complete_predecessor_and_optional_gap_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path, schema_path, trusted_lock, _ = self.make_predecessor(Path(temp_dir), with_gap=True)
            _, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock)
            self.assertEqual(errors, [])

    def test_forged_zero_error_report_cannot_hide_fresh_full_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path, schema_path, trusted_lock, manifest = self.make_predecessor(Path(temp_dir))
            company_path = manifest_path.parent / "company.json"
            company = load_json(company_path)
            company["financials"] = []
            write_json(company_path, company)
            company_entry = next(item for item in manifest["files"] if item["path"] == "company.json")
            company_entry["sha256"] = file_sha256(company_path)
            company_entry["size_bytes"] = company_path.stat().st_size
            self.write_manifest(manifest_path, manifest)
            _, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock)
            self.assertTrue(any("fresh full validation failed" in item for item in errors), errors)

    def test_manifest_symlink_is_rejected_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path, schema_path, trusted_lock, _ = self.make_predecessor(root)
            link = root / "research-manifest.json"
            link.symlink_to(manifest_path)
            previous, errors = verify_previous_manifest(link, schema_path, trusted_lock)
            self.assertIsNone(previous)
            self.assertTrue(any("non-symlink" in item for item in errors), errors)

    def test_predecessor_rejects_review_warning_hash_file_set_spec_and_identity_bypasses(self) -> None:
        mutations = {
            "pending human review": lambda manifest: manifest.__setitem__("human_review_status", "pending"),
            "unacknowledged warnings": lambda manifest: manifest["validation"].__setitem__("warnings", 1),
            "wrong trusted commit": lambda manifest: manifest["specification"].__setitem__("commit", "b" * 40),
            "wrong company identity": lambda manifest: manifest["research"].__setitem__("ticker", "OTHER"),
            "missing frozen file entry": lambda manifest: manifest["files"].pop(),
            "bad frozen hash": lambda manifest: manifest["files"][0].__setitem__("sha256", "0" * 64),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                manifest_path, schema_path, trusted_lock, original = self.make_predecessor(Path(temp_dir))
                changed = copy.deepcopy(original)
                mutate(changed)
                self.write_manifest(manifest_path, changed)
                _, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock)
                self.assertTrue(errors, label)

    def test_incremental_transition_records_verified_ancestry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            previous_path, schema_path, trusted_lock, _ = self.make_predecessor(root)
            current = root / "current"
            current.mkdir()
            current_company = {
                "meta": {
                    "schema_version": "test-1",
                    "company_name_cn": "测试公司",
                    "company_name_en": "Test Company",
                    "ticker": "TEST",
                    "exchange": "NYSE",
                    "report_currency": "USD",
                    "data_as_of": "2026-06-30",
                    "valuation_date": "2026-07-15",
                    "source_version": "2026Q2",
                },
                "sources": [
                    {
                        "id": "SRC-Q1",
                        "source_type": "quarterly_report",
                        "url": "https://example.com/2026-q1",
                        "published_at": "2026-07-10",
                    }
                ],
                "reporting": {"latest_report": {"date_status": "official", "source_ids": ["SRC-Q1"]}},
            }
            write_json(current / "company.json", current_company)
            errors, transition = validate_incremental_transition(
                current,
                previous_path,
                "SRC-Q1",
                schema_path,
                trusted_lock,
            )
            self.assertEqual(errors, [])
            self.assertIsNotNone(transition)
            assert transition is not None
            self.assertEqual(transition["previous_manifest_sha256"], file_sha256(previous_path))
            self.assertEqual(transition["previous_research"]["ticker"], "TEST")
            self.assertEqual(transition["previous_research"]["data_as_of"], "2026-03-31")
            self.assertEqual(transition["official_trigger_source_id"], "SRC-Q1")

    def test_full_manifest_omits_incremental_provenance_and_incremental_requires_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path, schema_path, _, _ = self.make_predecessor(root)
            package = manifest_path.parent
            validation = {"validator": "v", "mode": "full", "errors": 0, "warnings": 0}
            full = build_manifest(
                package,
                schema_path,
                "a" * 40,
                "main",
                next(iter(git_blob_sha1_candidates(schema_path))),
                {"authority": "test"},
                "full",
                validation,
                True,
                False,
            )
            self.assertNotIn("incremental_transition", full)
            with self.assertRaises(ValueError):
                build_manifest(
                    package,
                    schema_path,
                    "a" * 40,
                    "main",
                    next(iter(git_blob_sha1_candidates(schema_path))),
                    {"authority": "test"},
                    "incremental",
                    validation,
                    True,
                    False,
                )


if __name__ == "__main__":
    unittest.main()
