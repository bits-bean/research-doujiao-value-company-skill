#!/usr/bin/env python3
"""Regression tests for the fail-closed GitHub delivery planning gate."""

from __future__ import annotations

import copy
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_github_archive import (  # noqa: E402
    ArchivePlanError,
    TRUSTED_DESKTOP_RUNTIME_BUNDLE_VERSION,
    TRUSTED_DESKTOP_RUNTIME_NODE,
    TRUSTED_DESKTOP_RUNTIME_NODE_MODULES,
    TRUSTED_DESKTOP_RUNTIME_ROOT,
    TRUSTED_RUNTIME_BUNDLE_VERSION,
    _decode_png,
    _public_http_url,
    _validate_observed_logo,
    main as archive_main,
    build_archive_plan,
    canonical_action,
    package_action,
)
from validate_research_package import (  # noqa: E402
    EXPECTED_SCHEMA_PATH,
    EXPECTED_SPEC_REPOSITORY,
    FROZEN_HASH_FILES,
    Finding,
    INTEGRITY_PROFILE,
    file_sha256,
    git_blob_sha1_candidates,
    protocol_fingerprint,
    write_json,
)


class GithubDeliveryTests(unittest.TestCase):
    def make_package(self, root: Path) -> tuple[Path, Path, dict]:
        schema_path = root / "company.schema.json"
        write_json(schema_path, {"$schema": "test", "version": "test-1"})
        schema_blob = next(iter(git_blob_sha1_candidates(schema_path)))
        research_protocol = {
            "authority": "research-doujiao-value-company",
            "repository": "bits-bean/research-doujiao-value-company-skill",
            "ref": "main",
            "commit": "c" * 40,
            "protocol_version": "test-1",
            "digest_sha256": "d" * 64,
            "documents": [],
        }
        execution_integrity = {
            "profile": INTEGRITY_PROFILE,
            "normative_digest_sha256": "e" * 64,
            "toolchain_digest_sha256": "f" * 64,
            "bundle_digest_sha256": "1" * 64,
            "artifacts": [],
            "source_binding": {
                "repository": "bits-bean/research-doujiao-value-company-skill",
                "ref": "main",
                "payload_commit": None,
                "verification_status": "unverified",
            },
        }
        trusted_lock = {
            "lock_version": "3.0",
            "research_protocol": research_protocol,
            "execution_integrity": execution_integrity,
            "company_schema": {
                "repository": EXPECTED_SPEC_REPOSITORY,
                "ref": "main",
                "commit": "a" * 40,
                "path": EXPECTED_SCHEMA_PATH,
                "blob_sha1": schema_blob,
                "schema_version": "test-1",
            },
        }
        fingerprint = protocol_fingerprint(trusted_lock)
        validation_integrity = {
            "company_slug": "test-company",
            "integrity_profile": INTEGRITY_PROFILE,
            "validator_sha256": fingerprint["validator_sha256"],
            "toolchain_digest_sha256": execution_integrity["toolchain_digest_sha256"],
            "protocol_fingerprint": fingerprint,
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
        write_json(
            package / "company.json",
            {
                "meta": meta,
                "brand_identity": {
                    "company_logo": {
                        "asset_path": None,
                        "source_url": None,
                        "alt": None,
                        "is_official": False,
                    }
                },
                "sources": [],
            },
        )
        for name in FROZEN_HASH_FILES:
            if name == "company.json":
                continue
            if name == "validation-report.json":
                write_json(
                    package / name,
                    {
                        "validator": "doujiao-research-validator",
                        "mode": "full",
                        "errors": 0,
                        "warnings": 0,
                        **validation_integrity,
                    },
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
            "integrity_profile": INTEGRITY_PROFILE,
            "execution_integrity": execution_integrity,
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
            } | {"company_slug": "test-company"},
            "update_mode": "full",
            "validation": {
                "validator": "doujiao-research-validator",
                "mode": "full",
                "errors": 0,
                "warnings": 0,
                **validation_integrity,
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

    @staticmethod
    def identity_asset_state(paths: list[dict], base_head: str = "c" * 40) -> dict:
        return {
            "repository": EXPECTED_SPEC_REPOSITORY,
            "branch": "main",
            "base_head": base_head,
            "company_slug": "test-company",
            "assets": paths,
        }

    @staticmethod
    def existing_identity_asset(path: str, source_path: Path) -> dict:
        return {
            "path": path,
            "exists": True,
            "source_path": str(source_path),
            "sha256": file_sha256(source_path),
            "size_bytes": source_path.stat().st_size,
        }

    @staticmethod
    def png_chunk(name: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)

    @classmethod
    def write_png(cls, path: Path) -> None:
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + cls.png_chunk(b"IHDR", ihdr)
            + cls.png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\xff"))
            + cls.png_chunk(b"IEND", b"")
        )

    @classmethod
    def write_rgba_png(
        cls,
        path: Path,
        width: int,
        height: int,
        rows: list[list[tuple[int, int, int, int]]],
    ) -> None:
        if len(rows) != height or any(len(row) != width for row in rows):
            raise ValueError("RGBA fixture rows must match the declared dimensions")
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        decoded = b"".join(
            b"\x00" + bytes(channel for pixel in row for channel in pixel)
            for row in rows
        )
        path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + cls.png_chunk(b"IHDR", ihdr)
            + cls.png_chunk(b"IDAT", zlib.compress(decoded))
            + cls.png_chunk(b"IEND", b"")
        )

    def write_center_crop_assets(
        self,
        assets: Path,
        *,
        width: int = 4,
        height: int = 2,
    ) -> tuple[dict, list[list[tuple[int, int, int, int]]], list[list[tuple[int, int, int, int]]]]:
        assets.mkdir()
        original_rows = [
            [
                ((x + 1) * 20, (y + 1) * 30, (x + y + 1) * 10, 255)
                for x in range(width)
            ]
            for y in range(height)
        ]
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        output_rows = [row[left : left + side] for row in original_rows[top : top + side]]
        original = assets / "logo-original.png"
        output = assets / "logo.png"
        self.write_rgba_png(original, width, height, original_rows)
        self.write_rgba_png(output, side, side, output_rows)
        provenance = {
            "version": "1.0",
            "company_slug": "test-company",
            "operation": "center-square-crop-v1",
            "source": {
                "file": "logo-original.png",
                "page_url": "https://example.com/brand",
                "asset_url": "https://example.com/logo-original.png",
                "sha256": file_sha256(original),
                "size_bytes": original.stat().st_size,
                "width": width,
                "height": height,
            },
            "selection": {
                "square_official_candidate_found": False,
                "search_surfaces": [
                    {
                        "surface": surface,
                        "status": "checked",
                        "urls": [
                            "https://example.com/brand"
                            if surface == "brand-media"
                            else f"https://example.com/{surface}"
                        ],
                        "note": "checked official source",
                    }
                    for surface in (
                        "official-site-runtime-assets",
                        "investor-relations",
                        "brand-media",
                        "official-product-support",
                    )
                ],
                "candidates": [
                    {
                        "asset_url": "https://example.com/logo-original.png",
                        "source_page_url": "https://example.com/brand",
                        "format": "png",
                        "width": width,
                        "height": height,
                        "gate_status": "pass",
                        "identity_verified": True,
                        "is_official": True,
                        "officiality_evidence": "official brand page identifies the company Logo",
                        "decision": "selected-crop-source",
                        "reason": "official non-square source selected after square search",
                    }
                ],
            },
            "crop": {
                "left": left,
                "top": top,
                "width": side,
                "height": side,
                "resampled": False,
                "padded": False,
                "stretched": False,
                "redrawn": False,
            },
            "output": {
                "file": "logo.png",
                "sha256": file_sha256(output),
                "size_bytes": output.stat().st_size,
                "width": side,
                "height": side,
            },
        }
        write_json(assets / "logo-provenance.json", provenance)
        return provenance, original_rows, output_rows

    @staticmethod
    def set_company_logo(package: Path, asset_path: str | None) -> None:
        company_path = package / "company.json"
        company = json.loads(company_path.read_text(encoding="utf-8"))
        company["brand_identity"]["company_logo"] = {
            "asset_path": asset_path,
            "source_url": "https://example.com/brand",
            "alt": "Test Company official logo",
            "is_official": True,
        }
        write_json(company_path, company)
        manifest_path = package / "research-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            if entry["path"] == "company.json":
                entry["sha256"] = file_sha256(company_path)
                entry["size_bytes"] = company_path.stat().st_size
        write_json(manifest_path, manifest)

    def plan(self, package: Path, schema: Path, lock: dict, **kwargs: object) -> dict:
        with (
            patch("freeze_research.validate_research_package", return_value=[]),
            patch("prepare_github_archive.validate_research_package", return_value=[]),
            patch("prepare_github_archive._validate_svg_render", return_value=None),
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

            delivery_kwargs = {
                "write_authorized": True,
                "remote_company_state": self.company_state(),
                "remote_slug_registry_state": self.registry_state(),
                "remote_canonical_state": self.canonical_absent_state(),
            }
            with self.assertRaisesRegex(ArchivePlanError, "explicit no-Logo delivery authorization"):
                self.plan(package, schema, lock, **delivery_kwargs)

            manifest_path = package / "research-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["warning_acknowledged"] = True
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ArchivePlanError, "explicit no-Logo delivery authorization"):
                self.plan(package, schema, lock, **delivery_kwargs)

            ready = self.plan(
                package,
                schema,
                lock,
                confirm_new_company_without_logo=True,
                **delivery_kwargs,
            )
            self.assertTrue(ready["ready_for_write"])
            self.assertEqual(ready["delivery_mode"], "single-company-directory")
            self.assertEqual(ready["company_package"]["remote_action"], "create")
            self.assertEqual(ready["canonical_guard"]["action"], "create")
            self.assertEqual(ready["identity_assets"]["logo_guard"], "missing-explicitly-authorized")
            self.assertTrue(ready["identity_assets"]["new_company_without_logo_confirmed"])

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

    def test_frozen_manifest_slug_cannot_be_reused_for_another_delivery_slug(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            manifest_path = package / "research-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["research"]["company_slug"] = "other-company"
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(ArchivePlanError, "company_slug"):
                self.plan(package, schema, lock)

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
            remote_company = self.company_state(
                exists=True,
                files=[
                    {
                        "path": "company.json",
                        "sha256": file_sha256(existing),
                        "size_bytes": existing.stat().st_size,
                    }
                ],
            )
            with self.assertRaisesRegex(ArchivePlanError, "same data_as_of"):
                self.plan(
                    package,
                    schema,
                    lock,
                    remote_company_state=remote_company,
                    remote_slug_registry_state=self.registry_state(slug_exists=True),
                    remote_canonical_state=state,
                )
            plan = self.plan(
                package,
                schema,
                lock,
                write_authorized=True,
                remote_company_state=remote_company,
                remote_slug_registry_state=self.registry_state(slug_exists=True),
                remote_canonical_state=state,
                confirm_same_date_revision=True,
            )
            self.assertTrue(plan["ready_for_write"])
            self.assertEqual(plan["canonical_guard"]["action"], "update-confirmed-revision")

    def test_schema_2_0_to_2_1_migration_requires_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, _, _ = self.make_package(root)
            new_path = package / "company.json"
            new_company = json.loads(new_path.read_text(encoding="utf-8"))
            new_company["meta"]["schema_version"] = "2.1.0"
            new_company["meta"]["data_as_of"] = "2026-03-31"
            new_company["meta"]["valuation_date"] = "2026-04-15"
            write_json(new_path, new_company)
            existing = root / "existing-schema-2-0.json"
            company = json.loads(new_path.read_text(encoding="utf-8"))
            company["meta"]["schema_version"] = "2.0.0"
            company["meta"]["data_as_of"] = "2025-12-31"
            company["meta"]["valuation_date"] = "2026-01-15"
            write_json(existing, company)

            with self.assertRaisesRegex(ArchivePlanError, "Schema migration requires explicit confirmation"):
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=False,
                    locked_schema_version="2.1.0",
                )
            self.assertEqual(
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=False,
                    confirm_schema_migration=True,
                    locked_schema_version="2.1.0",
                ),
                "update-confirmed-schema-migration",
            )

            company["meta"]["data_as_of"] = "2026-03-31"
            company["meta"]["valuation_date"] = "2026-04-15"
            write_json(existing, company)
            with self.assertRaisesRegex(ArchivePlanError, "same data_as_of"):
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=False,
                    confirm_schema_migration=True,
                    locked_schema_version="2.1.0",
                )
            self.assertEqual(
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=True,
                    confirm_schema_migration=True,
                    locked_schema_version="2.1.0",
                ),
                "update-confirmed-schema-migration",
            )

    def test_schema_migration_rejects_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, _, _ = self.make_package(root)
            new_path = package / "company.json"
            new_company = json.loads(new_path.read_text(encoding="utf-8"))
            new_company["meta"]["schema_version"] = "2.1.0"
            new_company["meta"]["data_as_of"] = "2026-03-31"
            new_company["meta"]["valuation_date"] = "2026-04-15"
            write_json(new_path, new_company)
            existing = root / "existing-newer-schema.json"
            company = copy.deepcopy(new_company)
            company["meta"]["schema_version"] = "2.2.0"
            company["meta"]["data_as_of"] = "2025-12-31"
            company["meta"]["valuation_date"] = "2026-01-15"
            write_json(existing, company)
            with self.assertRaisesRegex(ArchivePlanError, "current locked Schema version"):
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=False,
                    confirm_schema_migration=True,
                    locked_schema_version="2.1.0",
                )

    def test_schema_1_x_to_2_1_migration_is_a_confirmed_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, _, _ = self.make_package(root)
            new_path = package / "company.json"
            new_company = json.loads(new_path.read_text(encoding="utf-8"))
            new_company["meta"]["schema_version"] = "2.1.0"
            new_company["meta"]["data_as_of"] = "2026-03-31"
            new_company["meta"]["valuation_date"] = "2026-04-15"
            write_json(new_path, new_company)

            existing = root / "existing-schema-1-x.json"
            old_company = copy.deepcopy(new_company)
            old_company["meta"]["schema_version"] = "1.9.0"
            old_company["meta"]["data_as_of"] = "2025-12-31"
            old_company["meta"]["valuation_date"] = "2026-01-15"
            write_json(existing, old_company)

            self.assertEqual(
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=False,
                    confirm_schema_migration=True,
                    locked_schema_version="2.1.0",
                ),
                "update-confirmed-schema-migration",
            )

    def test_schema_migration_rejects_unsupported_legacy_or_noncurrent_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, _, _ = self.make_package(root)
            new_path = package / "company.json"
            new_company = json.loads(new_path.read_text(encoding="utf-8"))
            new_company["meta"]["schema_version"] = "2.1.0"
            new_company["meta"]["data_as_of"] = "2026-03-31"
            new_company["meta"]["valuation_date"] = "2026-04-15"
            write_json(new_path, new_company)

            for legacy_version in ("0.9.0", "2.0.1"):
                with self.subTest(legacy_version=legacy_version):
                    existing = root / f"existing-{legacy_version}.json"
                    old_company = copy.deepcopy(new_company)
                    old_company["meta"]["schema_version"] = legacy_version
                    old_company["meta"]["data_as_of"] = "2025-12-31"
                    old_company["meta"]["valuation_date"] = "2026-01-15"
                    write_json(existing, old_company)
                    with self.assertRaisesRegex(ArchivePlanError, "current locked Schema version"):
                        canonical_action(
                            new_path,
                            existing_company_path=existing,
                            canonical_absent=False,
                            confirm_same_date_revision=False,
                            confirm_schema_migration=True,
                            locked_schema_version="2.1.0",
                        )

            noncurrent = copy.deepcopy(new_company)
            noncurrent["meta"]["schema_version"] = "2.2.0"
            write_json(new_path, noncurrent)
            existing = root / "existing-schema-2-0.json"
            old_company = copy.deepcopy(new_company)
            old_company["meta"]["schema_version"] = "2.0.0"
            old_company["meta"]["data_as_of"] = "2025-12-31"
            old_company["meta"]["valuation_date"] = "2026-01-15"
            write_json(existing, old_company)
            with self.assertRaisesRegex(ArchivePlanError, "current locked Schema version"):
                canonical_action(
                    new_path,
                    existing_company_path=existing,
                    canonical_absent=False,
                    confirm_same_date_revision=False,
                    confirm_schema_migration=True,
                    locked_schema_version="2.1.0",
                )

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

            zero_head = "0" * 40
            with self.assertRaisesRegex(ArchivePlanError, "exact base_head"):
                self.plan(
                    package,
                    schema,
                    lock,
                    write_authorized=True,
                    remote_company_state=self.company_state(base_head=zero_head),
                    remote_slug_registry_state=self.registry_state(zero_head),
                    remote_canonical_state=self.canonical_absent_state(zero_head),
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

    def test_new_company_declared_logo_requires_verified_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            self.set_company_logo(package, "companies/test-company/assets/logo.svg")
            with self.assertRaisesRegex(ArchivePlanError, "no verified logo was staged"):
                self.plan(
                    package,
                    schema,
                    lock,
                    write_authorized=True,
                    remote_company_state=self.company_state(),
                    remote_slug_registry_state=self.registry_state(),
                    remote_canonical_state=self.canonical_absent_state(),
                )

    def test_existing_company_logo_clear_requires_confirmation_and_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            existing = root / "existing.json"
            company = json.loads((package / "company.json").read_text(encoding="utf-8"))
            company["meta"]["data_as_of"] = "2025-09-30"
            company["meta"]["valuation_date"] = "2025-10-15"
            company["brand_identity"]["company_logo"] = {
                "asset_path": "companies/test-company/assets/logo.svg",
                "source_url": "https://example.com/brand",
                "alt": "Test Company official logo",
                "is_official": True,
            }
            write_json(existing, company)
            remote_company = self.company_state(
                exists=True,
                files=[
                    {
                        "path": "company.json",
                        "sha256": file_sha256(existing),
                        "size_bytes": existing.stat().st_size,
                    }
                ],
            )
            kwargs = {
                "write_authorized": True,
                "remote_company_state": remote_company,
                "remote_slug_registry_state": self.registry_state(slug_exists=True),
                "remote_canonical_state": self.canonical_present_state(existing),
            }
            with self.assertRaisesRegex(ArchivePlanError, "clear.*explicit authorization"):
                self.plan(
                    package,
                    schema,
                    lock,
                    **kwargs,
                )
            preflight = self.plan(
                package,
                schema,
                lock,
                confirm_identity_asset_clear=True,
                **kwargs,
            )
            self.assertFalse(preflight["ready_for_write"])
            self.assertEqual(preflight["identity_assets"]["remote_action"], "remote-preflight-required")

            remote_logo = root / "old-logo.svg"
            remote_logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>\n',
                encoding="utf-8",
            )
            confirmed = self.plan(
                package,
                schema,
                lock,
                confirm_identity_asset_clear=True,
                remote_identity_assets_state=self.identity_asset_state(
                    [self.existing_identity_asset("companies/test-company/assets/logo.svg", remote_logo)]
                ),
                **kwargs,
            )
            self.assertTrue(confirmed["ready_for_write"])
            self.assertEqual(confirmed["identity_assets"]["remote_action"], "clear-reference")
            self.assertEqual(confirmed["identity_assets"]["logo_guard"], "cleared-explicitly")
            self.assertEqual(confirmed["identity_assets"]["delete_paths"], [])

    def test_legacy_company_without_logo_record_can_migrate_to_null_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            existing = root / "existing.json"
            company = json.loads((package / "company.json").read_text(encoding="utf-8"))
            company["meta"]["data_as_of"] = "2025-09-30"
            company["meta"]["valuation_date"] = "2025-10-15"
            company["brand_identity"] = {}
            write_json(existing, company)
            plan = self.plan(
                package,
                schema,
                lock,
                write_authorized=True,
                remote_company_state=self.company_state(
                    exists=True,
                    files=[
                        {
                            "path": "company.json",
                            "sha256": file_sha256(existing),
                            "size_bytes": existing.stat().st_size,
                        }
                    ],
                ),
                remote_slug_registry_state=self.registry_state(slug_exists=True),
                remote_canonical_state=self.canonical_present_state(existing),
            )
            self.assertTrue(plan["ready_for_write"])
            self.assertEqual(plan["identity_assets"]["remote_action"], "preserve")
            self.assertEqual(plan["identity_assets"]["logo_guard"], "not-declared")

    def test_existing_company_logo_requires_exact_remote_file_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            target = "companies/test-company/assets/logo.svg"
            self.set_company_logo(package, target)
            existing = root / "existing.json"
            existing.write_bytes((package / "company.json").read_bytes())
            remote_logo = root / "remote-logo.svg"
            remote_logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>\n',
                encoding="utf-8",
            )
            local_plan = self.plan(package, schema, lock)
            remote_files = [
                {
                    "path": Path(item["target_path"]).name,
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                }
                for item in local_plan["company_package"]["files"]
            ]
            kwargs = {
                "write_authorized": True,
                "remote_company_state": self.company_state(exists=True, files=remote_files),
                "remote_slug_registry_state": self.registry_state(slug_exists=True),
                "remote_canonical_state": self.canonical_present_state(existing),
            }

            preflight = self.plan(package, schema, lock, **kwargs)
            self.assertFalse(preflight["ready_for_write"])
            self.assertEqual(preflight["identity_assets"]["remote_action"], "remote-preflight-required")
            self.assertEqual(preflight["identity_assets"]["logo_guard"], "remote-preflight-required")

            with self.assertRaisesRegex(ArchivePlanError, "missing from the observed remote path"):
                self.plan(
                    package,
                    schema,
                    lock,
                    remote_identity_assets_state=self.identity_asset_state(
                        [{"path": target, "exists": False, "source_path": None, "sha256": None, "size_bytes": None}]
                    ),
                    **kwargs,
                )

            ready = self.plan(
                package,
                schema,
                lock,
                remote_identity_assets_state=self.identity_asset_state(
                    [self.existing_identity_asset(target, remote_logo)]
                ),
                **kwargs,
            )
            self.assertTrue(ready["ready_for_write"])
            self.assertEqual(ready["identity_assets"]["remote_action"], "preserve")
            self.assertEqual(ready["identity_assets"]["logo_guard"], "preserve-existing")

            conflicting_company_state = copy.deepcopy(kwargs["remote_company_state"])
            for item in conflicting_company_state["files"]:
                if item["path"] == "company.json":
                    item["sha256"] = "f" * 64
            with self.assertRaisesRegex(ArchivePlanError, "disagree on company.json bytes"):
                self.plan(
                    package,
                    schema,
                    lock,
                    remote_identity_assets_state=self.identity_asset_state(
                        [self.existing_identity_asset(target, remote_logo)]
                    ),
                    **{**kwargs, "remote_company_state": conflicting_company_state},
                )

    def test_company_logo_path_cannot_escape_or_cross_company(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema, lock = self.make_package(Path(temp_dir))
            self.set_company_logo(package, "companies/other-company/assets/logo.svg")
            with self.assertRaisesRegex(ArchivePlanError, "different company"):
                self.plan(package, schema, lock)

    def test_verified_logo_is_planned_as_atomic_single_asset_create(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.svg")
            assets = root / "identity-assets"
            assets.mkdir()
            logo = assets / "logo.svg"
            logo.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1v1z"/></svg>\n', encoding="utf-8")
            target = "companies/test-company/assets/logo.svg"
            ready = self.plan(
                package,
                schema,
                lock,
                write_authorized=True,
                remote_company_state=self.company_state(),
                remote_slug_registry_state=self.registry_state(),
                remote_canonical_state=self.canonical_absent_state(),
                identity_assets_root=assets,
                remote_identity_assets_state=self.identity_asset_state(
                    [{"path": target, "exists": False, "source_path": None, "sha256": None, "size_bytes": None}]
                ),
            )
            self.assertTrue(ready["ready_for_write"])
            self.assertEqual(ready["plan_version"], "9.4")
            self.assertEqual(ready["identity_assets"]["remote_action"], "create")
            self.assertEqual(ready["identity_assets"]["logo_guard"], "staged")
            self.assertEqual([item["target_path"] for item in ready["identity_assets"]["files"]], [target])
            self.assertEqual(ready["identity_assets"]["delete_paths"], [])

    def test_verified_png_logo_is_planned_without_rewriting_original_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            target = "companies/test-company/assets/logo.png"
            self.set_company_logo(package, target)
            assets = root / "identity-assets"
            assets.mkdir()
            logo = assets / "logo.png"
            self.write_png(logo)
            original_bytes = logo.read_bytes()
            original_sha256 = file_sha256(logo)

            ready = self.plan(
                package,
                schema,
                lock,
                write_authorized=True,
                remote_company_state=self.company_state(),
                remote_slug_registry_state=self.registry_state(),
                remote_canonical_state=self.canonical_absent_state(),
                identity_assets_root=assets,
                remote_identity_assets_state=self.identity_asset_state(
                    [{"path": target, "exists": False, "source_path": None, "sha256": None, "size_bytes": None}]
                ),
            )

            self.assertTrue(ready["ready_for_write"])
            self.assertEqual(ready["identity_assets"]["remote_action"], "create")
            self.assertEqual(ready["identity_assets"]["logo_guard"], "staged")
            self.assertEqual(len(ready["identity_assets"]["files"]), 1)
            planned = ready["identity_assets"]["files"][0]
            self.assertEqual(planned["target_path"], target)
            self.assertEqual(planned["source_path"], str(logo.resolve()))
            self.assertEqual(planned["sha256"], original_sha256)
            self.assertEqual(planned["size_bytes"], len(original_bytes))
            self.assertEqual(Path(planned["source_path"]).read_bytes(), original_bytes)
            self.assertEqual(logo.read_bytes(), original_bytes)

    def test_verified_png_center_crop_is_planned_with_external_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            target = "companies/test-company/assets/logo.png"
            self.set_company_logo(package, target)
            assets = root / "identity-assets"
            provenance, _original_rows, _output_rows = self.write_center_crop_assets(assets)

            ready = self.plan(
                package,
                schema,
                lock,
                write_authorized=True,
                remote_company_state=self.company_state(),
                remote_slug_registry_state=self.registry_state(),
                remote_canonical_state=self.canonical_absent_state(),
                identity_assets_root=assets,
                remote_identity_assets_state=self.identity_asset_state(
                    [{"path": target, "exists": False, "source_path": None, "sha256": None, "size_bytes": None}]
                ),
            )

            self.assertTrue(ready["ready_for_write"])
            self.assertEqual(ready["plan_version"], "9.4")
            self.assertEqual(ready["identity_assets"]["preparation"], "verified-center-square-crop")
            self.assertTrue(ready["identity_assets"]["official_source_derived"])
            self.assertEqual(
                [item["target_path"] for item in ready["identity_assets"]["files"]],
                [target],
            )
            crop_record = ready["identity_assets"]["crop_provenance"]
            self.assertEqual(crop_record["record"], provenance)
            self.assertTrue(crop_record["verification"]["pixel_exact_center_crop"])
            self.assertEqual(crop_record["original_source_path"], str((assets / "logo-original.png").resolve()))
            self.assertNotIn("logo-original.png", [Path(item["target_path"]).name for item in ready["identity_assets"]["files"]])
            self.assertNotIn("logo-provenance.json", [Path(item["target_path"]).name for item in ready["identity_assets"]["files"]])

    def test_non_square_direct_png_requires_verified_crop_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.png")
            assets = root / "identity-assets"
            assets.mkdir()
            rows = [[(20 * (x + 1), 30 * (y + 1), 10, 255) for x in range(4)] for y in range(2)]
            self.write_rgba_png(assets / "logo.png", 4, 2, rows)
            with self.assertRaisesRegex(ArchivePlanError, "official square original or a verified deterministic"):
                self.plan(package, schema, lock, identity_assets_root=assets)

    def test_center_crop_uses_floor_offset_for_odd_difference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.png")
            assets = root / "identity-assets"
            provenance, _original_rows, _output_rows = self.write_center_crop_assets(
                assets,
                width=5,
                height=2,
            )
            plan = self.plan(package, schema, lock, identity_assets_root=assets)
            self.assertEqual(provenance["crop"], {
                "left": 1,
                "top": 0,
                "width": 2,
                "height": 2,
                "resampled": False,
                "padded": False,
                "stretched": False,
                "redrawn": False,
            })
            self.assertTrue(plan["identity_assets"]["crop_provenance"]["verification"]["pixel_exact_center_crop"])

    def test_center_crop_proves_non_byte_aligned_one_bit_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.png")
            assets = root / "identity-assets"
            provenance, _original_rows, _output_rows = self.write_center_crop_assets(
                assets,
                width=5,
                height=3,
            )

            source_bits = (
                (1, 0, 1, 0, 1),
                (0, 1, 1, 0, 0),
                (1, 1, 0, 1, 0),
            )
            output_bits = tuple(tuple(row[1:4]) for row in source_bits)

            def write_one_bit_png(path: Path, rows: tuple[tuple[int, ...], ...]) -> None:
                width = len(rows[0])
                height = len(rows)
                decoded = bytearray()
                for row in rows:
                    packed = sum(bit << (7 - index) for index, bit in enumerate(row))
                    decoded.extend((0, packed))
                path.write_bytes(
                    b"\x89PNG\r\n\x1a\n"
                    + self.png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0))
                    + self.png_chunk(b"IDAT", zlib.compress(bytes(decoded)))
                    + self.png_chunk(b"IEND", b"")
                )

            original = assets / "logo-original.png"
            output = assets / "logo.png"
            write_one_bit_png(original, source_bits)
            write_one_bit_png(output, output_bits)
            for path, record_key in ((original, "source"), (output, "output")):
                provenance[record_key]["sha256"] = file_sha256(path)
                provenance[record_key]["size_bytes"] = path.stat().st_size
            write_json(assets / "logo-provenance.json", provenance)
            plan = self.plan(package, schema, lock, identity_assets_root=assets)
            self.assertTrue(plan["identity_assets"]["crop_provenance"]["verification"]["pixel_exact_center_crop"])

            changed = list(map(list, output_bits))
            changed[-1][-1] ^= 1
            write_one_bit_png(output, tuple(tuple(row) for row in changed))
            provenance["output"]["sha256"] = file_sha256(output)
            provenance["output"]["size_bytes"] = output.stat().st_size
            write_json(assets / "logo-provenance.json", provenance)
            with self.assertRaisesRegex(ArchivePlanError, "pixels are not the exact deterministic center crop"):
                self.plan(package, schema, lock, identity_assets_root=assets)

    def test_center_crop_rejects_changed_pixels_even_when_output_hash_matches_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.png")
            assets = root / "identity-assets"
            provenance, _original_rows, output_rows = self.write_center_crop_assets(assets)
            changed_rows = copy.deepcopy(output_rows)
            changed_rows[0][0] = (255, 0, 0, 255)
            self.write_rgba_png(assets / "logo.png", 2, 2, changed_rows)
            provenance["output"]["sha256"] = file_sha256(assets / "logo.png")
            provenance["output"]["size_bytes"] = (assets / "logo.png").stat().st_size
            write_json(assets / "logo-provenance.json", provenance)
            with self.assertRaisesRegex(ArchivePlanError, "pixels are not the exact deterministic center crop"):
                self.plan(package, schema, lock, identity_assets_root=assets)

    def test_center_crop_rejects_changed_pixel_after_first_visible_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.png")
            assets = root / "identity-assets"
            provenance, _original_rows, output_rows = self.write_center_crop_assets(assets)
            changed_rows = copy.deepcopy(output_rows)
            changed_rows[-1][-1] = (255, 0, 0, 255)
            self.write_rgba_png(assets / "logo.png", 2, 2, changed_rows)
            provenance["output"]["sha256"] = file_sha256(assets / "logo.png")
            provenance["output"]["size_bytes"] = (assets / "logo.png").stat().st_size
            write_json(assets / "logo-provenance.json", provenance)
            with self.assertRaisesRegex(ArchivePlanError, "pixels are not the exact deterministic center crop"):
                self.plan(package, schema, lock, identity_assets_root=assets)

    def test_center_crop_rejects_unknown_unsafe_to_copy_png_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.png")
            assets = root / "identity-assets"
            provenance, _original_rows, _output_rows = self.write_center_crop_assets(assets)
            for filename, record_key in (("logo-original.png", "source"), ("logo.png", "output")):
                path = assets / filename
                data = path.read_bytes()
                idat_type_offset = data.index(b"IDAT")
                idat_chunk_offset = idat_type_offset - 4
                path.write_bytes(
                    data[:idat_chunk_offset]
                    + self.png_chunk(b"aaAA", b"opaque-copy-semantics")
                    + data[idat_chunk_offset:]
                )
                provenance[record_key]["sha256"] = file_sha256(path)
                provenance[record_key]["size_bytes"] = path.stat().st_size
            write_json(assets / "logo-provenance.json", provenance)
            with self.assertRaisesRegex(ArchivePlanError, "unsafe to copy after cropping"):
                self.plan(package, schema, lock, identity_assets_root=assets)

    def test_center_crop_rejects_false_box_or_transform_claims(self) -> None:
        mutations = {
            "wrong crop box": lambda record: record["crop"].__setitem__("left", 0),
            "resampled": lambda record: record["crop"].__setitem__("resampled", True),
            "numeric false": lambda record: record["crop"].__setitem__("padded", 0),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                package, schema, lock = self.make_package(root)
                self.set_company_logo(package, "companies/test-company/assets/logo.png")
                assets = root / "identity-assets"
                provenance, _original_rows, _output_rows = self.write_center_crop_assets(assets)
                mutate(provenance)
                write_json(assets / "logo-provenance.json", provenance)
                with self.assertRaisesRegex(ArchivePlanError, "exact deterministic center-square crop"):
                    self.plan(package, schema, lock, identity_assets_root=assets)

    def test_center_crop_rejects_verified_square_candidate_or_incomplete_search(self) -> None:
        mutations = {
            "square candidate": lambda record: record["selection"]["candidates"].append(
                {
                    "asset_url": "https://example.com/square-logo.png",
                    "source_page_url": "https://example.com/brand",
                    "format": "png",
                    "width": 64,
                    "height": 64,
                    "gate_status": "pass",
                    "identity_verified": True,
                    "is_official": True,
                    "officiality_evidence": "official brand page identifies the company Logo",
                    "decision": "rejected",
                    "reason": "would have been usable",
                }
            ),
            "missing surface": lambda record: record["selection"]["search_surfaces"].pop(),
            "unbound source page": lambda record: record["selection"]["search_surfaces"][2].__setitem__(
                "urls", ["https://example.com/unrelated-brand-page"]
            ),
            "selected source mismatch": lambda record: record["source"].__setitem__(
                "asset_url", "https://example.com/different-original.png"
            ),
            "unverified selected candidate": lambda record: record["selection"]["candidates"][0].__setitem__(
                "identity_verified", False
            ),
            "unsupported passing format": lambda record: record["selection"]["candidates"][0].__setitem__(
                "format", "other"
            ),
            "duplicate candidate": lambda record: record["selection"]["candidates"].append(
                copy.deepcopy(record["selection"]["candidates"][0])
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                package, schema, lock = self.make_package(root)
                self.set_company_logo(package, "companies/test-company/assets/logo.png")
                assets = root / "identity-assets"
                provenance, _original_rows, _output_rows = self.write_center_crop_assets(assets)
                mutate(provenance)
                write_json(assets / "logo-provenance.json", provenance)
                with self.assertRaises(ArchivePlanError):
                    self.plan(package, schema, lock, identity_assets_root=assets)

    def test_center_crop_rejects_already_square_source_and_file_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.png")
            assets = root / "identity-assets"
            self.write_center_crop_assets(assets, width=2, height=2)
            with self.assertRaisesRegex(ArchivePlanError, "already-square official PNG"):
                self.plan(package, schema, lock, identity_assets_root=assets)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.png")
            assets = root / "identity-assets"
            provenance, _original_rows, _output_rows = self.write_center_crop_assets(assets)
            (assets / "logo.png").unlink()
            os.link(assets / "logo-original.png", assets / "logo.png")
            provenance["output"]["sha256"] = file_sha256(assets / "logo.png")
            provenance["output"]["size_bytes"] = (assets / "logo.png").stat().st_size
            provenance["output"]["width"] = 4
            write_json(assets / "logo-provenance.json", provenance)
            with self.assertRaisesRegex(ArchivePlanError, "must be distinct files"):
                self.plan(package, schema, lock, identity_assets_root=assets)

    def test_existing_non_square_png_can_be_preserved_without_silent_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            target = "companies/test-company/assets/logo.png"
            self.set_company_logo(package, target)
            existing = root / "existing-company.json"
            existing.write_bytes((package / "company.json").read_bytes())
            remote_logo = root / "remote-logo.png"
            rows = [[(20 * (x + 1), 30 * (y + 1), 10, 255) for x in range(4)] for y in range(2)]
            self.write_rgba_png(remote_logo, 4, 2, rows)
            plan = self.plan(
                package,
                schema,
                lock,
                remote_company_state=self.company_state(
                    exists=True,
                    files=[{
                        "path": "company.json",
                        "sha256": file_sha256(existing),
                        "size_bytes": existing.stat().st_size,
                    }],
                ),
                remote_slug_registry_state=self.registry_state(slug_exists=True),
                remote_canonical_state=self.canonical_present_state(existing),
                remote_identity_assets_state=self.identity_asset_state(
                    [self.existing_identity_asset(target, remote_logo)]
                ),
            )
            self.assertEqual(plan["identity_assets"]["remote_action"], "preserve")
            self.assertEqual(plan["identity_assets"]["logo_guard"], "preserve-existing")
            self.assertEqual(plan["identity_assets"]["preparation"], "not-staged")
            self.assertFalse(plan["identity_assets"]["official_source_derived"])

    def test_non_square_staged_svg_is_rejected_but_square_original_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.svg")
            assets = root / "identity-assets"
            assets.mkdir()
            logo = assets / "logo.svg"
            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 1"><path d="M0 0h2v1z"/></svg>\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ArchivePlanError, "official square original"):
                self.plan(package, schema, lock, identity_assets_root=assets)
            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"><path d="M0 0h2v2z"/></svg>\n',
                encoding="utf-8",
            )
            plan = self.plan(package, schema, lock, identity_assets_root=assets)
            self.assertEqual(plan["identity_assets"]["preparation"], "official-original-square")
            self.assertIsNone(plan["identity_assets"]["crop_provenance"])

    def test_svg_square_canvas_uses_resolved_outer_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.svg")
            assets = root / "identity-assets"
            assets.mkdir()
            logo = assets / "logo.svg"

            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="1in" height="1cm" viewBox="0 0 100 100"><path d="M0 0h100v100z"/></svg>\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ArchivePlanError, "official square original"):
                self.plan(package, schema, lock, identity_assets_root=assets)

            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" style="width:200px;height:100px" viewBox="0 0 100 100"><path d="M0 0h100v100z"/></svg>\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ArchivePlanError, "canvas dimensions ambiguous"):
                self.plan(package, schema, lock, identity_assets_root=assets)

            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" style="inline-size:200px;block-size:100px" viewBox="0 0 100 100"><path d="M0 0h100v100z"/></svg>\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ArchivePlanError, "canvas dimensions ambiguous"):
                self.plan(package, schema, lock, identity_assets_root=assets)

            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 1000 300"><path d="M0 0h1000v300z"/></svg>\n',
                encoding="utf-8",
            )
            plan = self.plan(package, schema, lock, identity_assets_root=assets)
            self.assertEqual(plan["identity_assets"]["preparation"], "official-original-square")

            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 100 100"><path d="M0 0h100v100z"/></svg>\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ArchivePlanError, "context-dependent canvas dimension"):
                self.plan(package, schema, lock, identity_assets_root=assets)

    def test_verified_logo_accepts_safe_inline_class_stylesheet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logo = Path(temp_dir) / "logo.svg"
            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="45" height="45" viewBox="0 0 45 45">'
                '<style>.st0{fill:#fff}.st1{fill:#006fcf}</style>'
                '<path class="st0" d="M0 0h45v45H0z"/>'
                '<path class="st1" d="M5 5h35v35H5z"/>'
                '</svg>\n',
                encoding="utf-8",
            )
            with patch("prepare_github_archive._validate_svg_render", return_value=None):
                _validate_observed_logo(logo, "companies/test-company/logo-primary.svg")

    def test_company_logo_replacement_requires_explicit_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.svg")
            assets = root / "identity-assets"
            assets.mkdir()
            logo = assets / "logo.svg"
            logo.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"><path d="M0 0h2v2z"/></svg>\n', encoding="utf-8")
            target = "companies/test-company/assets/logo.svg"
            remote_logo = root / "remote-logo.svg"
            remote_logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>\n',
                encoding="utf-8",
            )
            state = self.identity_asset_state(
                [self.existing_identity_asset(target, remote_logo)]
            )
            kwargs = {
                "remote_company_state": self.company_state(exists=True),
                "remote_slug_registry_state": self.registry_state(),
                "remote_canonical_state": self.canonical_absent_state(),
                "identity_assets_root": assets,
                "remote_identity_assets_state": state,
            }
            with self.assertRaisesRegex(ArchivePlanError, "replacement requires explicit"):
                self.plan(package, schema, lock, **kwargs)
            confirmed = self.plan(
                package,
                schema,
                lock,
                confirm_identity_asset_replacement=True,
                **kwargs,
            )
            self.assertEqual(confirmed["identity_assets"]["remote_action"], "update")
            self.assertTrue(confirmed["identity_assets"]["replacement_confirmed"])

    def test_logo_path_switch_requires_explicit_replacement_and_observes_both_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            canonical_target = "companies/test-company/assets/logo.svg"
            legacy_target = "companies/test-company/logo-primary.png"
            self.set_company_logo(package, canonical_target)
            assets = root / "identity-assets"
            assets.mkdir()
            (assets / "logo.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"><path d="M0 0h2v2z"/></svg>\n',
                encoding="utf-8",
            )

            existing = root / "existing.json"
            existing_company = json.loads((package / "company.json").read_text(encoding="utf-8"))
            existing_company["meta"]["data_as_of"] = "2025-09-30"
            existing_company["meta"]["valuation_date"] = "2025-10-15"
            existing_company["brand_identity"]["company_logo"] = {
                "asset_path": legacy_target,
                "source_url": "https://example.com/legacy-logo.png",
                "alt": "Test Company legacy official logo",
                "is_official": True,
            }
            write_json(existing, existing_company)
            remote_png = root / "remote-logo.png"
            self.write_png(remote_png)
            state = self.identity_asset_state(
                [
                    self.existing_identity_asset(legacy_target, remote_png),
                    {
                        "path": canonical_target,
                        "exists": False,
                        "source_path": None,
                        "sha256": None,
                        "size_bytes": None,
                    },
                ]
            )
            kwargs = {
                "write_authorized": True,
                "remote_company_state": self.company_state(
                    exists=True,
                    files=[
                        {
                            "path": "company.json",
                            "sha256": file_sha256(existing),
                            "size_bytes": existing.stat().st_size,
                        }
                    ],
                ),
                "remote_slug_registry_state": self.registry_state(slug_exists=True),
                "remote_canonical_state": self.canonical_present_state(existing),
                "identity_assets_root": assets,
                "remote_identity_assets_state": state,
            }
            with self.assertRaisesRegex(ArchivePlanError, "path or metadata replacement requires explicit"):
                self.plan(package, schema, lock, **kwargs)
            confirmed = self.plan(
                package,
                schema,
                lock,
                confirm_identity_asset_replacement=True,
                **kwargs,
            )
            self.assertTrue(confirmed["ready_for_write"])
            self.assertEqual(confirmed["identity_assets"]["remote_action"], "create")
            self.assertEqual(confirmed["identity_assets"]["logo_guard"], "staged")

    def test_explicit_replacement_can_remove_empty_or_oversized_invalid_old_logo(self) -> None:
        for label, old_bytes in (("empty", b""), ("oversized", b"x" * 512_001)):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                package, schema, lock = self.make_package(root)
                canonical_target = "companies/test-company/assets/logo.svg"
                legacy_target = "companies/test-company/logo-primary.svg"
                self.set_company_logo(package, canonical_target)
                assets = root / "identity-assets"
                assets.mkdir()
                (assets / "logo.svg").write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"><path d="M0 0h2v2z"/></svg>\n',
                    encoding="utf-8",
                )
                existing = root / "existing.json"
                existing_company = json.loads((package / "company.json").read_text(encoding="utf-8"))
                existing_company["meta"]["data_as_of"] = "2025-09-30"
                existing_company["meta"]["valuation_date"] = "2025-10-15"
                existing_company["brand_identity"]["company_logo"] = {
                    "asset_path": legacy_target,
                    "source_url": "https://example.com/legacy-logo.svg",
                    "alt": "Test Company legacy official logo",
                    "is_official": True,
                }
                write_json(existing, existing_company)
                old_logo = root / "old-logo.svg"
                old_logo.write_bytes(old_bytes)
                plan = self.plan(
                    package,
                    schema,
                    lock,
                    write_authorized=True,
                    remote_company_state=self.company_state(
                        exists=True,
                        files=[
                            {
                                "path": "company.json",
                                "sha256": file_sha256(existing),
                                "size_bytes": existing.stat().st_size,
                            }
                        ],
                    ),
                    remote_slug_registry_state=self.registry_state(slug_exists=True),
                    remote_canonical_state=self.canonical_present_state(existing),
                    identity_assets_root=assets,
                    remote_identity_assets_state=self.identity_asset_state(
                        [
                            self.existing_identity_asset(legacy_target, old_logo),
                            {
                                "path": canonical_target,
                                "exists": False,
                                "source_path": None,
                                "sha256": None,
                                "size_bytes": None,
                            },
                        ]
                    ),
                    confirm_identity_asset_replacement=True,
                )
                self.assertTrue(plan["ready_for_write"])
                self.assertEqual(plan["identity_assets"]["remote_action"], "create")

    def test_remote_logo_observation_cannot_alias_staged_file_or_use_non_string_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            target = "companies/test-company/assets/logo.svg"
            self.set_company_logo(package, target)
            assets = root / "identity-assets"
            assets.mkdir()
            logo = assets / "logo.svg"
            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1v1z"/></svg>\n',
                encoding="utf-8",
            )
            kwargs = {
                "identity_assets_root": assets,
                "remote_company_state": self.company_state(),
                "remote_slug_registry_state": self.registry_state(),
                "remote_canonical_state": self.canonical_absent_state(),
            }
            with self.assertRaisesRegex(ArchivePlanError, "cannot alias"):
                self.plan(
                    package,
                    schema,
                    lock,
                    remote_identity_assets_state=self.identity_asset_state(
                        [self.existing_identity_asset(target, logo)]
                    ),
                    **kwargs,
                )
            observed_hardlink = root / "observed-hardlink.svg"
            os.link(logo, observed_hardlink)
            with self.assertRaisesRegex(ArchivePlanError, "cannot alias"):
                self.plan(
                    package,
                    schema,
                    lock,
                    remote_identity_assets_state=self.identity_asset_state(
                        [self.existing_identity_asset(target, observed_hardlink)]
                    ),
                    **kwargs,
                )
            malformed = {
                "path": [],
                "exists": False,
                "source_path": None,
                "sha256": None,
                "size_bytes": None,
            }
            with self.assertRaisesRegex(ArchivePlanError, "unexpected path"):
                self.plan(
                    package,
                    schema,
                    lock,
                    remote_identity_assets_state=self.identity_asset_state([malformed]),
                    **kwargs,
                )

    def test_logo_source_url_must_be_stable_public_and_well_formed(self) -> None:
        invalid = (
            "https://[:::]/logo.svg",
            "https://exa mple.com/logo.svg",
            "https://example.com:bad/logo.svg",
            "http://127.0.0.1/logo.svg",
            "http://2130706433/logo.svg",
            "https://user:pass@example.com/logo.svg",
            "https://example.com/logo.svg?X-Amz-Signature=secret",
            "https://example.com/%zz",
            "https://nonexistent.invalid/logo.svg",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ArchivePlanError):
                _public_http_url(value, "company_logo.source_url")
        self.assertEqual(
            _public_http_url("https://ir.example.com/brand/logo.svg?version=2", "company_logo.source_url"),
            "https://ir.example.com/brand/logo.svg?version=2",
        )

    def test_legacy_png_rejects_duplicate_headers_and_invalid_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            signature = b"\x89PNG\r\n\x1a\n"
            rgba_ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
            rgba_data = self.png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
            iend = self.png_chunk(b"IEND", b"")
            duplicate_ihdr = root / "duplicate-ihdr.png"
            duplicate_ihdr.write_bytes(
                signature
                + self.png_chunk(b"IHDR", rgba_ihdr)
                + self.png_chunk(b"IHDR", rgba_ihdr)
                + rgba_data
                + iend
            )
            with self.assertRaisesRegex(ArchivePlanError, "duplicate IHDR"):
                _validate_observed_logo(duplicate_ihdr, "companies/test-company/logo-primary.png")

            indexed_ihdr = struct.pack(">IIBBBBB", 1, 1, 1, 3, 0, 0, 0)
            palette = self.png_chunk(b"PLTE", b"\x00\x00\x00\xff\xff\xff")
            duplicate_plte = root / "duplicate-plte.png"
            duplicate_plte.write_bytes(
                signature
                + self.png_chunk(b"IHDR", indexed_ihdr)
                + palette
                + palette
                + self.png_chunk(b"IDAT", zlib.compress(b"\x00\x00"))
                + iend
            )
            with self.assertRaisesRegex(ArchivePlanError, "duplicate PLTE"):
                _validate_observed_logo(duplicate_plte, "companies/test-company/logo-primary.png")

            invalid_depth = root / "invalid-depth.png"
            invalid_depth.write_bytes(
                signature
                + self.png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 1, 6, 0, 0, 0))
                + rgba_data
                + iend
            )
            with self.assertRaisesRegex(ArchivePlanError, "IHDR encoding"):
                _validate_observed_logo(invalid_depth, "companies/test-company/logo-primary.png")

            transparent = root / "transparent.png"
            transparent.write_bytes(
                signature
                + self.png_chunk(b"IHDR", rgba_ihdr)
                + self.png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
                + iend
            )
            with self.assertRaisesRegex(ArchivePlanError, "no visible Logo pixel"):
                _validate_observed_logo(transparent, "companies/test-company/logo-primary.png")

            invalid_chunk = root / "invalid-chunk.png"
            invalid_chunk.write_bytes(
                signature
                + self.png_chunk(b"IHDR", rgba_ihdr)
                + self.png_chunk(b"abcd", b"")
                + self.png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\xff"))
                + iend
            )
            with self.assertRaisesRegex(ArchivePlanError, "invalid chunk type"):
                _validate_observed_logo(invalid_chunk, "companies/test-company/logo-primary.png")

            animated = root / "animated.png"
            animated.write_bytes(
                signature
                + self.png_chunk(b"IHDR", rgba_ihdr)
                + self.png_chunk(b"acTL", struct.pack(">II", 1, 0))
                + self.png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\xff"))
                + iend
            )
            with self.assertRaisesRegex(ArchivePlanError, "animated PNG chunks"):
                _validate_observed_logo(animated, "companies/test-company/logo-primary.png")

            noncontiguous_after_empty_idat = root / "noncontiguous-after-empty-idat.png"
            noncontiguous_after_empty_idat.write_bytes(
                signature
                + self.png_chunk(b"IHDR", rgba_ihdr)
                + self.png_chunk(b"IDAT", b"")
                + self.png_chunk(b"tEXt", b"note\x00value")
                + self.png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\xff"))
                + iend
            )
            with self.assertRaisesRegex(ArchivePlanError, "IDAT ordering"):
                _validate_observed_logo(
                    noncontiguous_after_empty_idat,
                    "companies/test-company/logo-primary.png",
                )

            gray_ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
            invalid_transparency_sample = root / "invalid-transparency-sample.png"
            invalid_transparency_sample.write_bytes(
                signature
                + self.png_chunk(b"IHDR", gray_ihdr)
                + self.png_chunk(b"tRNS", struct.pack(">H", 256))
                + self.png_chunk(b"IDAT", zlib.compress(b"\x00\xff"))
                + iend
            )
            with self.assertRaisesRegex(ArchivePlanError, "transparency sample is out of range"):
                _validate_observed_logo(
                    invalid_transparency_sample,
                    "companies/test-company/logo-primary.png",
                )

            truecolor_ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            palette_after_transparency = root / "palette-after-transparency.png"
            palette_after_transparency.write_bytes(
                signature
                + self.png_chunk(b"IHDR", truecolor_ihdr)
                + self.png_chunk(b"tRNS", b"\x00\x00\x00\x00\x00\x00")
                + self.png_chunk(b"PLTE", b"\x00\x00\x00")
                + self.png_chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
                + iend
            )
            with self.assertRaisesRegex(ArchivePlanError, "invalid PLTE"):
                _validate_observed_logo(
                    palette_after_transparency,
                    "companies/test-company/logo-primary.png",
                )

    def test_png_decoder_keeps_large_high_compression_rows_packed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logo = Path(temp_dir) / "large-solid.png"
            width = 1024
            height = 1024
            ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
            decoded = (b"\x00" + b"\x20\x80\xff\xff" * width) * height
            logo.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + self.png_chunk(b"IHDR", ihdr)
                + self.png_chunk(b"IDAT", zlib.compress(decoded, 9))
                + self.png_chunk(b"IEND", b"")
            )
            self.assertLess(logo.stat().st_size, 512_000)
            raster = _decode_png(logo)
            self.assertEqual((raster.width, raster.height), (width, height))
            self.assertEqual(len(raster.rows), height)
            self.assertIsInstance(raster.rows[0], bytes)
            self.assertEqual(len(raster.rows[0]), width * 4)

    def test_logo_staging_rejects_active_svg_and_extra_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package, schema, lock = self.make_package(root)
            self.set_company_logo(package, "companies/test-company/assets/logo.svg")
            assets = root / "identity-assets"
            assets.mkdir()
            logo = assets / "logo.svg"
            logo.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>\n', encoding="utf-8")
            with self.assertRaisesRegex(ArchivePlanError, "active content"):
                self.plan(package, schema, lock, identity_assets_root=assets)

            logo.write_text('<svg xmlns="http://www.w3.org/2000/svg"><style>.x{fill:url(https://example.com/x)}</style></svg>\n', encoding="utf-8")
            with self.assertRaisesRegex(ArchivePlanError, "resource"):
                self.plan(package, schema, lock, identity_assets_root=assets)

            unsafe_documents = {
                "spaced href": '<svg xmlns="http://www.w3.org/2000/svg"><image href=" https://evil.example/x"/></svg>',
                "encoded href": '<svg xmlns="http://www.w3.org/2000/svg"><image href="&#x68;ttps://evil.example/x"/></svg>',
                "style import": '<svg xmlns="http://www.w3.org/2000/svg"><style>@import "https://evil.example/x";</style></svg>',
                "image set": '<svg xmlns="http://www.w3.org/2000/svg"><style>.x{background:image-set("https://evil.example/x" 1x)}</style></svg>',
                "malformed root": '<not-svg title="svg"></not-svg>',
                "external stylesheet": '<?xml-stylesheet href="https://evil.example/x"?><svg xmlns="http://www.w3.org/2000/svg"></svg>',
                "wrong namespace": '<svg xmlns="https://evil.example/not-svg"></svg>',
                "xml events": '<svg xmlns="http://www.w3.org/2000/svg" xmlns:ev="http://www.w3.org/2001/xml-events"><handler type="application/ecmascript" ev:event="load">alert(1)</handler></svg>',
                "font text": '<svg xmlns="http://www.w3.org/2000/svg"><text font-family="Acme Corporate">ACME</text></svg>',
                "empty svg": '<svg xmlns="http://www.w3.org/2000/svg"/>',
                "style-hidden geometry": '<svg xmlns="http://www.w3.org/2000/svg"><style>path{display:none}</style><path d="M0 0h1v1z"/></svg>',
                "stylesheet at-rule": '<svg xmlns="http://www.w3.org/2000/svg"><style>@media all{path{fill:#000}}</style><path d="M0 0h1v1z"/></svg>',
                "stylesheet complex selector": '<svg xmlns="http://www.w3.org/2000/svg"><style>.x path{fill:#000}</style><path class="x" d="M0 0h1v1z"/></svg>',
                "stylesheet active property": '<svg xmlns="http://www.w3.org/2000/svg"><style>.x{animation:pulse 1s}</style><path class="x" d="M0 0h1v1z"/></svg>',
                "stylesheet dangling paint": '<svg xmlns="http://www.w3.org/2000/svg"><style>.x{fill:url(#missing)}</style><path class="x" d="M0 0h1v1z"/></svg>',
                "zero width": '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="10"><path d="M0 0h1v1z"/></svg>',
                "zero viewBox": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 10"><path d="M0 0h1v1z"/></svg>',
                "invisible paint": '<svg xmlns="http://www.w3.org/2000/svg" fill="none" stroke="none"><path d="M0 0h1v1z"/></svg>',
                "invalid path": '<svg xmlns="http://www.w3.org/2000/svg"><path d="L0"/></svg>',
                "encoded credential": '<svg xmlns="http://www.w3.org/2000/svg"><metadata>api&#95;key=ABCDEFGHIJKLMNOPQRSTUVWX</metadata><path d="M0 0h1v1z"/></svg>',
                "collapsed scale": '<svg xmlns="http://www.w3.org/2000/svg"><path transform="scale(0)" d="M0 0h1v1z"/></svg>',
                "collapsed matrix": '<svg xmlns="http://www.w3.org/2000/svg"><path transform="matrix(1 0 0 0 0 0)" d="M0 0h1v1z"/></svg>',
                "open fill-only line": '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1"/></svg>',
                "collinear polygon": '<svg xmlns="http://www.w3.org/2000/svg"><polygon points="0,0 1,1 2,2"/></svg>',
                "empty clip path": '<svg xmlns="http://www.w3.org/2000/svg"><defs><clipPath id="c"><rect width="0" height="1"/></clipPath></defs><path clip-path="url(#c)" d="M0 0h1v1z"/></svg>',
                "missing paint server": '<svg xmlns="http://www.w3.org/2000/svg"><path fill="url(#missing)" d="M0 0h1v1z"/></svg>',
                "transparent hex": '<svg xmlns="http://www.w3.org/2000/svg"><path fill="#00000000" d="M0 0h1v1z"/></svg>',
                "transparent rgba": '<svg xmlns="http://www.w3.org/2000/svg"><path fill="rgba(0,0,0,0)" d="M0 0h1v1z"/></svg>',
                "renderer-divergent color function": '<svg xmlns="http://www.w3.org/2000/svg"><path fill="lab(50% 0 0 / 0)" d="M0 0h1v1z"/></svg>',
                "transparent gradient": '<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g"><stop stop-opacity="0"/></linearGradient></defs><path fill="url(#g)" d="M0 0h1v1z"/></svg>',
                "unsupported mask": '<svg xmlns="http://www.w3.org/2000/svg"><defs><mask id="m"><rect width="1" height="1"/></mask></defs><path mask="url(#m)" d="M0 0h1v1z"/></svg>',
                "important hidden": '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1" style="display:none!important"/></svg>',
                "transparent current color": '<svg xmlns="http://www.w3.org/2000/svg" color="transparent"><path fill="currentColor" d="M0 0h1v1z"/></svg>',
                "css variable paint": '<svg xmlns="http://www.w3.org/2000/svg" style="--logo:#000"><path fill="var(--logo)" d="M0 0h1v1z"/></svg>',
                "zero-area closed path": '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1Z"/></svg>',
                "outside viewBox": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect x="100" y="100" width="1" height="1"/></svg>',
                "conditional language": '<svg xmlns="http://www.w3.org/2000/svg"><path systemLanguage="zz-NeverLanguage" d="M0 0h1v1z"/></svg>',
                "foreign namespace geometry": '<svg xmlns="http://www.w3.org/2000/svg" xmlns:e="urn:evil"><e:path d="M0 0L10 0L0 10Z"/></svg>',
                "xml base fragment": '<svg xmlns="http://www.w3.org/2000/svg" xml:base="file:/tmp/remote.svg"><defs><path id="p" d="M0 0h1v1z"/></defs><use href="#p"/></svg>',
                "excessive nesting": '<svg xmlns="http://www.w3.org/2000/svg">' + '<g>' * 300 + '<path d="M0 0h1v1z"/>' + '</g>' * 300 + '</svg>',
                "foreign href attribute": '<svg xmlns="http://www.w3.org/2000/svg" xmlns:e="urn:evil"><defs><path id="p" d="M0 0L10 0L0 10Z"/></defs><use e:href="#p"/></svg>',
                "deep gradient reference graph": '<svg xmlns="http://www.w3.org/2000/svg"><defs>' + ''.join(f'<linearGradient id="g{i}" href="#g{i + 1}"/>' for i in range(300)) + '<linearGradient id="g300"><stop/></linearGradient></defs><rect width="10" height="10" fill="url(#g0)"/></svg>',
            }
            for label, document in unsafe_documents.items():
                with self.subTest(label=label):
                    logo.write_text(document, encoding="utf-8")
                    with self.assertRaises(ArchivePlanError):
                        self.plan(package, schema, lock, identity_assets_root=assets)

            renderer_only_documents = {
                "offscreen path": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M100 100L110 100L100 110Z"/></svg>',
                "offscreen transformed rect": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect x="100" y="100" width="1" height="1" transform="translate(1)"/></svg>',
                "zero-area line clip": '<svg xmlns="http://www.w3.org/2000/svg"><defs><clipPath id="c"><line x2="10" y2="10"/></clipPath></defs><path clip-path="url(#c)" d="M0 0h10v10z"/></svg>',
                "disjoint clip": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><clipPath id="c"><rect x="8" y="8" width="1" height="1"/></clipPath></defs><rect clip-path="url(#c)" width="1" height="1"/></svg>',
                "empty pattern": '<svg xmlns="http://www.w3.org/2000/svg"><defs><pattern id="p" width="1" height="1"><rect width="1" height="1" fill="none"/></pattern></defs><rect width="10" height="10" fill="url(#p)"/></svg>',
                "collinear cubic": '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0C1 1 2 2 3 3"/></svg>',
                "metadata geometry": '<svg xmlns="http://www.w3.org/2000/svg"><metadata><path d="M0 0L10 0L0 10Z"/></metadata></svg>',
            }
            for label, document in renderer_only_documents.items():
                with self.subTest(label=label):
                    logo.write_text(document, encoding="utf-8")
                    with self.assertRaises(ArchivePlanError):
                        _validate_observed_logo(logo, "companies/test-company/assets/logo.svg")

            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><defs><linearGradient id="g"><stop offset="0"/></linearGradient><clipPath id="c"><rect width="1" height="1"/></clipPath></defs><path clip-path="url(#c)" fill="url(#g)" d="M0 0h1v1z"/></svg>\n',
                encoding="utf-8",
            )
            accepted = self.plan(package, schema, lock, identity_assets_root=assets)
            self.assertEqual(accepted["identity_assets"]["remote_action"], "remote-preflight-required")
            (assets / "product.png").write_bytes(b"not allowed")
            with self.assertRaisesRegex(ArchivePlanError, r"exactly one logo\.svg"):
                self.plan(package, schema, lock, identity_assets_root=assets)

            (assets / "product.png").unlink()
            self.write_png(assets / "logo.png")
            with self.assertRaisesRegex(ArchivePlanError, r"exactly one logo\.svg"):
                self.plan(package, schema, lock, identity_assets_root=assets)

    def test_svg_renderer_fails_closed_without_trusted_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logo = Path(temp_dir) / "logo.svg"
            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ArchivePlanError, "trusted SVG raster runtime is unavailable"):
                    _validate_observed_logo(logo, "companies/test-company/assets/logo.svg")

    def test_svg_renderer_accepts_locked_desktop_runtime(self) -> None:
        required = (
            TRUSTED_DESKTOP_RUNTIME_ROOT,
            TRUSTED_DESKTOP_RUNTIME_NODE,
            TRUSTED_DESKTOP_RUNTIME_NODE_MODULES,
        )
        if not all(path.exists() for path in required):
            self.skipTest("locked desktop SVG runtime is unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            logo = Path(temp_dir) / "logo.svg"
            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                '<path fill="#006fcf" d="M0 0h16v16H0z"/>'
                '</svg>\n',
                encoding="utf-8",
            )
            runtime_env = {
                "CODEX_PRIMARY_RUNTIME_ROOT": str(TRUSTED_DESKTOP_RUNTIME_ROOT),
                "CODEX_PRIMARY_RUNTIME_NODE": str(TRUSTED_DESKTOP_RUNTIME_NODE),
                "CODEX_PRIMARY_RUNTIME_NODE_MODULES": str(TRUSTED_DESKTOP_RUNTIME_NODE_MODULES),
                "CODEX_PRIMARY_RUNTIME_BUNDLE_VERSION": TRUSTED_DESKTOP_RUNTIME_BUNDLE_VERSION,
            }
            with patch.dict(os.environ, runtime_env, clear=True):
                _validate_observed_logo(logo, "companies/test-company/assets/logo.svg")

    def test_svg_renderer_does_not_inherit_node_preload_options(self) -> None:
        if os.environ.get("CODEX_PRIMARY_RUNTIME_BUNDLE_VERSION") not in {
            TRUSTED_RUNTIME_BUNDLE_VERSION,
            TRUSTED_DESKTOP_RUNTIME_BUNDLE_VERSION,
        }:
            self.skipTest("locked SVG runtime is unavailable, so the NODE_OPTIONS path cannot be exercised")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logo = root / "offscreen.svg"
            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">'
                '<path transform="translate(1000 1000)" d="M0 0h1v1z"/>'
                '</svg>\n',
                encoding="utf-8",
            )
            preload = root / "preload.js"
            preload.write_text(
                "const original = process.exit; process.exit = (code) => original(code === 2 ? 0 : code);\n",
                encoding="utf-8",
            )
            fake_sharp = root / "node_modules" / "sharp"
            fake_sharp.mkdir(parents=True)
            (fake_sharp / "package.json").write_text(
                '{"name":"sharp","main":"index.js"}\n',
                encoding="utf-8",
            )
            (fake_sharp / "index.js").write_text(
                "function sharp(){return {resize(){return this},ensureAlpha(){return this},"
                "raw(){return this},async toBuffer(){return {data:Buffer.from([0,0,0,255]),"
                "info:{channels:4}}}}};"
                "sharp.versions={sharp:'0.35.3',vips:'8.18.3',rsvg:'2.62.90'};module.exports=sharp;\n",
                encoding="utf-8",
            )
            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {"NODE_OPTIONS": f"--require={preload}"}, clear=False):
                    with self.assertRaisesRegex(
                        ArchivePlanError,
                        "trusted SVG raster runtime is unavailable|no visible Logo pixel",
                    ):
                        _validate_observed_logo(logo, "companies/test-company/assets/logo.svg")
            finally:
                os.chdir(previous_cwd)

    def test_svg_renderer_rejects_unlocked_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            logo = root / "logo.svg"
            logo.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>\n',
                encoding="utf-8",
            )
            fake_runtime = root / "fake-runtime"
            fake_node = fake_runtime / "dependencies" / "node" / "bin" / "node"
            fake_modules = fake_runtime / "dependencies" / "node" / "node_modules"
            (fake_modules / "sharp" / "dist").mkdir(parents=True)
            fake_node.parent.mkdir(parents=True)
            fake_node.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_node.chmod(0o755)
            (fake_modules / "sharp" / "dist" / "index.cjs").write_text("", encoding="utf-8")
            (fake_modules / "sharp" / "package.json").write_text("{}\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "CODEX_PRIMARY_RUNTIME_ROOT": str(fake_runtime),
                    "CODEX_PRIMARY_RUNTIME_NODE": str(fake_node),
                    "CODEX_PRIMARY_RUNTIME_NODE_MODULES": str(fake_modules),
                    "CODEX_PRIMARY_RUNTIME_BUNDLE_VERSION": "26.812.11052",
                },
                clear=False,
            ):
                with self.assertRaisesRegex(
                    ArchivePlanError,
                    "cannot traverse symbolic links|locked platform release",
                ):
                    _validate_observed_logo(logo, "companies/test-company/assets/logo.svg")

    def test_cli_output_cannot_overwrite_observed_logo_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "package"
            package.mkdir()
            schema = root / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            observed_logo = root / "observed-logo.svg"
            original = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>\n'
            observed_logo.write_bytes(original)
            state_path = root / "identity-state.json"
            write_json(
                state_path,
                self.identity_asset_state(
                    [self.existing_identity_asset("companies/test-company/assets/logo.svg", observed_logo)]
                ),
            )
            fake_plan = {
                "company_package": {"files": []},
                "identity_assets": {"files": []},
            }
            argv = [
                "prepare_github_archive.py",
                str(package),
                "--schema",
                str(schema),
                "--company-slug",
                "test-company",
                "--remote-identity-assets-state",
                str(state_path),
                "--output",
                str(observed_logo),
            ]
            with patch("sys.argv", argv), patch("prepare_github_archive.build_archive_plan", return_value=fake_plan):
                self.assertEqual(archive_main(), 1)
            self.assertEqual(observed_logo.read_bytes(), original)

            output_hardlink = root / "delivery-plan.json"
            os.link(observed_logo, output_hardlink)
            argv[-1] = str(output_hardlink)
            with patch("sys.argv", argv), patch("prepare_github_archive.build_archive_plan", return_value=fake_plan):
                self.assertEqual(archive_main(), 1)
            self.assertEqual(observed_logo.read_bytes(), original)

    def test_cli_wires_explicit_new_company_without_logo_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "package"
            package.mkdir()
            schema = root / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            argv = [
                "prepare_github_archive.py",
                str(package),
                "--schema",
                str(schema),
                "--company-slug",
                "test-company",
                "--confirm-new-company-without-logo",
            ]
            with patch("sys.argv", argv), patch(
                "prepare_github_archive.build_archive_plan",
                return_value={},
            ) as build:
                self.assertEqual(archive_main(), 0)
            self.assertTrue(build.call_args.kwargs["confirm_new_company_without_logo"])

    def test_cli_wires_explicit_schema_migration_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "package"
            package.mkdir()
            schema = root / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            argv = [
                "prepare_github_archive.py",
                str(package),
                "--schema",
                str(schema),
                "--company-slug",
                "test-company",
                "--confirm-schema-migration",
            ]
            with patch("sys.argv", argv), patch(
                "prepare_github_archive.build_archive_plan",
                return_value={},
            ) as build:
                self.assertEqual(archive_main(), 0)
            self.assertTrue(build.call_args.kwargs["confirm_schema_migration"])

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
