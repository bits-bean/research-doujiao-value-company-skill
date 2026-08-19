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

from freeze_research import (  # noqa: E402
    build_manifest,
    validate_incremental_transition,
    verify_previous_manifest,
)
from validate_research_package import (  # noqa: E402
    EXPECTED_SCHEMA_PATH,
    EXPECTED_SPEC_REPOSITORY,
    FROZEN_HASH_FILES,
    file_sha256,
    git_blob_sha1_candidates,
    write_json,
)


class IncrementalChainTests(unittest.TestCase):
    def make_predecessor(self, root: Path, *, with_gap: bool = False) -> tuple[Path, Path, dict, dict]:
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
        package = root / "previous"
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
        write_json(package / "company.json", {"meta": meta})
        for name in FROZEN_HASH_FILES:
            if name == "company.json":
                continue
            if name == "validation-report.json":
                write_json(
                    package / name,
                    {"validator": "doujiao-research-validator", "mode": "full", "errors": 0, "warnings": 1},
                )
            elif name.endswith(".json"):
                write_json(package / name, {"ok": True})
            else:
                (package / name).write_text(f"verified {name}\n", encoding="utf-8")
        if with_gap:
            (package / "schema-gap-report.md").write_text("# Schema gap\nDocumented.\n", encoding="utf-8")
        frozen_names = list(FROZEN_HASH_FILES) + (["schema-gap-report.md"] if with_gap else [])
        manifest = {
            "manifest_version": "1.0",
            "status": "frozen",
            "human_review_status": "accepted",
            "warning_acknowledged": True,
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
            "validation": {"validator": "doujiao-research-validator", "mode": "full", "errors": 0, "warnings": 1},
            "files": [
                {
                    "path": name,
                    "sha256": file_sha256(package / name),
                    "size_bytes": (package / name).stat().st_size,
                }
                for name in frozen_names
            ],
        }
        manifest_path = package / "research-manifest.json"
        write_json(manifest_path, manifest)
        return manifest_path, schema_path, trusted_lock, manifest

    def write_manifest(self, path: Path, manifest: dict) -> None:
        write_json(path, manifest)

    def test_complete_predecessor_and_optional_gap_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path, schema_path, trusted_lock, _ = self.make_predecessor(Path(temp_dir), with_gap=True)
            _, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock)
            self.assertEqual(errors, [])

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
            "unacknowledged warnings": lambda manifest: manifest.__setitem__("warning_acknowledged", False),
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
                    "data_as_of": "2026-03-31",
                    "valuation_date": "2026-04-15",
                    "source_version": "2026Q1",
                },
                "sources": [
                    {
                        "id": "SRC-Q1",
                        "source_type": "quarterly_report",
                        "url": "https://example.com/2026-q1",
                        "published_at": "2026-04-10",
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
            self.assertEqual(transition["previous_research"]["data_as_of"], "2025-12-31")
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
                    "incremental",
                    validation,
                    True,
                    False,
                )


if __name__ == "__main__":
    unittest.main()
