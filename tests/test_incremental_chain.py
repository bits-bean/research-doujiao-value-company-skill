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
    validate_incremental_research_drift,
    validate_incremental_transition,
    verify_previous_manifest,
)
from package_fixture import make_valid_unfrozen_package  # noqa: E402
from validate_research_package import (  # noqa: E402
    file_sha256,
    git_blob_sha1_candidates,
    load_json,
    protocol_fingerprint,
    report_payload,
    validate_research_package,
    write_json,
)


class IncrementalChainTests(unittest.TestCase):
    def make_drift_pair(self, root: Path) -> tuple[Path, Path, dict, dict]:
        baseline_root = root / "baseline"
        baseline_root.mkdir()
        previous, _schema_path, _ = make_valid_unfrozen_package(baseline_root)
        current = root / "current"
        current.mkdir()
        company = copy.deepcopy(load_json(previous / "company.json"))
        evidence = copy.deepcopy(load_json(previous / "evidence-ledger.json"))
        evidence["run"]["research_mode"] = "incremental"
        evidence["run"]["run_id"] = "RUN-DRIFT-CHECK"
        evidence["thesis"]["overall_change"] = "unchanged"
        for assumption in evidence["thesis"]["assumptions"]:
            assumption["prior_status"] = assumption["current_status"]
            assumption["change_type"] = "none"
        evidence["thesis"]["valuation_assumption_changes"] = []
        evidence["thesis"]["revision_log"] = [
            {
                "id": "REV-DRIFT-CHECK",
                "changed_at": "2026-07-15T12:00:00Z",
                "change_type": "none",
                "summary": "建立增量比较记录并逐项承接上一冻结版本的假设状态。",
                "affected_assumption_ids": ["ASM-RETENTION", "ASM-COVERAGE"],
                "evidence_claim_ids": ["CLM-002", "CLM-003"],
            }
        ]
        write_json(current / "company.json", company)
        write_json(current / "evidence-ledger.json", evidence)
        return previous, current, company, evidence

    def make_predecessor(self, root: Path, *, with_gap: bool = False) -> tuple[Path, Path, dict, dict]:
        package, schema_path, _ = make_valid_unfrozen_package(root)
        trusted_lock = load_json(ROOT / "references/trusted-spec-lock.json")
        findings = validate_research_package(package, schema_path, "full", "test-company")
        validation = report_payload(package, schema_path, "full", findings, "test-company")
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
            execution_integrity=trusted_lock["execution_integrity"],
            company_slug="test-company",
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
            _, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock, "test-company")
            self.assertTrue(any("audit-only" in item for item in errors), errors)

    def test_schema_2_1_predecessor_cannot_start_schema_2_2_incremental(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path, schema_path, trusted_lock, manifest = self.make_predecessor(Path(temp_dir))
            company_path = manifest_path.parent / "company.json"
            company = load_json(company_path)
            company["meta"]["schema_version"] = "2.1.0"
            write_json(company_path, company)
            company_entry = next(item for item in manifest["files"] if item["path"] == "company.json")
            company_entry["sha256"] = file_sha256(company_path)
            company_entry["size_bytes"] = company_path.stat().st_size
            manifest["specification"]["schema_version"] = "2.1.0"
            self.write_manifest(manifest_path, manifest)

            _, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock, "test-company")
            self.assertTrue(any("schema_version" in item for item in errors), errors)
            self.assertTrue(any("new full package" in item for item in errors), errors)

    def test_logo_metadata_must_be_complete_or_use_exact_empty_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema_path, _ = make_valid_unfrozen_package(Path(temp_dir))
            company = load_json(package / "company.json")
            company["brand_identity"]["company_logo"] = {
                "asset_path": "companies/test-company/assets/logo.svg",
                "source_url": None,
                "alt": "Test Company official logo",
                "is_official": True,
            }
            write_json(package / "company.json", company)
            findings = validate_research_package(package, schema_path, "full", "test-company")
            self.assertIn("official-logo-metadata", {item.code for item in findings})

            company["brand_identity"]["company_logo"] = {
                "asset_path": "companies/test-company/assets/logo.svg",
                "source_url": "https://example.com/logo.svg",
                "alt": "Test Company logo",
                "is_official": False,
            }
            write_json(package / "company.json", company)
            findings = validate_research_package(package, schema_path, "full", "test-company")
            self.assertIn("company-logo-sentinel", {item.code for item in findings})

            for asset_path in (
                "../../evil.svg",
                "companies/other-company/assets/logo.svg",
                "https://evil.example/logo.svg",
                "companies/test-company/assets/logo.jpg",
                "companies/test-company/logo-primary.exe",
            ):
                with self.subTest(asset_path=asset_path):
                    company["brand_identity"]["company_logo"] = {
                        "asset_path": asset_path,
                        "source_url": "https://example.com/logo.svg",
                        "alt": "Test Company logo",
                        "is_official": True,
                    }
                    write_json(package / "company.json", company)
                    findings = validate_research_package(package, schema_path, "full", "test-company")
                    self.assertIn("company-logo-path", {item.code for item in findings})

            company["brand_identity"]["company_logo"] = {
                "asset_path": "companies/test-company/assets/logo.png",
                "source_url": "https://example.com/logo.png",
                "alt": "Test Company official logo",
                "is_official": True,
            }
            write_json(package / "company.json", company)
            findings = validate_research_package(package, schema_path, "full", "test-company")
            self.assertNotIn("company-logo-path", {item.code for item in findings})

            company["brand_identity"]["company_logo"] = {
                "asset_path": "companies/test-company/assets/logo.svg",
                "source_url": "https://example.com/logo.svg",
                "alt": "Test Company logo",
                "is_official": True,
            }
            for source_url in (
                "https://[:::]/logo.svg",
                "https://exa mple.com/logo.svg",
                "https://example.com:bad/logo.svg",
                "http://127.0.0.1/logo.svg",
                "http://2130706433/logo.svg",
                "https://example.com/%zz",
                "https://example.com/logo.svg?token=secret",
            ):
                with self.subTest(source_url=source_url):
                    company["brand_identity"]["company_logo"]["source_url"] = source_url
                    write_json(package / "company.json", company)
                    findings = validate_research_package(package, schema_path, "full", "test-company")
                    self.assertIn("official-logo-source", {item.code for item in findings})

    def test_missing_logo_requires_specific_completeness_acknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema_path, _ = make_valid_unfrozen_package(Path(temp_dir))
            company = load_json(package / "company.json")
            company["brand_identity"]["company_logo"] = {
                "asset_path": None,
                "source_url": None,
                "alt": None,
                "is_official": False,
            }
            write_json(package / "company.json", company)
            findings = validate_research_package(package, schema_path, "full", "test-company")
            codes = {item.code for item in findings}
            self.assertIn("unofficial-logo", codes)
            self.assertIn("unacknowledged-logo-warning", codes)

            completeness_path = package / "research-completeness.md"
            base_completeness = completeness_path.read_text(encoding="utf-8")
            hidden_disclosures = (
                "<!-- Logo 缺失：已检查官网 IR；网站展示回退 ticker；后续待补。 -->",
                "```text\nLogo 缺失：已检查官网 IR；网站展示回退 ticker；后续待补。\n```",
                "    Logo 缺失：已检查官网 IR；网站展示回退 ticker；后续待补。",
                "<pre>Logo 缺失：已检查官网 IR；网站展示回退 ticker；后续待补。</pre>",
                "[说明](https://example.com/Logo缺失已检查官网IR网站展示回退ticker后续待补)",
                '<span title="Logo 缺失 已检查 官网 IR 网站展示回退 ticker 后续待补">说明</span>',
            )
            for disclosure in hidden_disclosures:
                with self.subTest(disclosure=disclosure):
                    completeness_path.write_text(base_completeness + "\n" + disclosure + "\n", encoding="utf-8")
                    findings = validate_research_package(package, schema_path, "full", "test-company")
                    self.assertTrue(
                        {"unacknowledged-logo-warning", "embedded-visual-asset"}
                        & {item.code for item in findings}
                    )

            incomplete_search_disclosures = (
                "Logo 缺失：尚未检查公司官网、投资者关系 IR 与官方品牌中心；网站展示回退 ticker，后续待补。",
                "Logo 缺失：计划下一步检查公司官网、投资者关系 IR 与官方品牌中心；网站展示回退 ticker，后续待补。",
            )
            for disclosure in incomplete_search_disclosures:
                with self.subTest(disclosure=disclosure):
                    completeness_path.write_text(base_completeness + "\n" + disclosure + "\n", encoding="utf-8")
                    findings = validate_research_package(package, schema_path, "full", "test-company")
                    self.assertIn("unacknowledged-logo-warning", {item.code for item in findings})

            completeness_path.write_text(
                base_completeness
                + "\nLogo 缺失：已检查公司官网、投资者关系 IR 与官方品牌中心，均未提供可核验文件；网站展示将回退 ticker，后续待补官方媒体资料。\n",
                encoding="utf-8",
            )
            findings = validate_research_package(package, schema_path, "full", "test-company")
            codes = {item.code for item in findings}
            self.assertIn("unofficial-logo", codes)
            self.assertNotIn("unacknowledged-logo-warning", codes)

            company["brand_identity"]["company_logo"] = {
                "asset_path": "companies/test-company/assets/logo.svg",
                "source_url": "https://example.com/logo.svg",
                "alt": "Test Company official logo",
                "is_official": True,
            }
            write_json(package / "company.json", company)
            findings = validate_research_package(package, schema_path, "full", "test-company")
            self.assertIn(
                "company-logo-completeness-contradiction",
                {item.code for item in findings},
            )

            completeness_path.write_text(
                base_completeness
                + "\nLogo 尚未取得：网站继续回退 ticker，后续待补官方来源。\n",
                encoding="utf-8",
            )
            findings = validate_research_package(package, schema_path, "full", "test-company")
            self.assertIn(
                "company-logo-completeness-contradiction",
                {item.code for item in findings},
            )

            completeness_path.write_text(
                base_completeness
                + "\nLogo 不再缺失：此前官网未提供的素材现已取得并核验，网站不再使用 ticker 回退。\n",
                encoding="utf-8",
            )
            findings = validate_research_package(package, schema_path, "full", "test-company")
            self.assertNotIn(
                "company-logo-completeness-contradiction",
                {item.code for item in findings},
            )

    def test_visual_assets_must_stay_outside_research_package(self) -> None:
        for relative in ("assets", "product.png", "visuals/logo.svg", "brandmark.svg", "company-logo", "brand/logo.dat"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temp_dir:
                package, schema_path, _ = make_valid_unfrozen_package(Path(temp_dir))
                target = package / relative
                if target.suffix:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(b"visual")
                else:
                    target.mkdir()
                findings = validate_research_package(package, schema_path, "full", "test-company")
                self.assertTrue(
                    {"visual-asset-in-package", "unexpected-package-entry"} & {item.code for item in findings}
                )

    def test_managed_research_files_cannot_embed_visual_or_media_assets(self) -> None:
        cases = (
            ("research-report.md", "\n![product](https://example.com/product.png)\n"),
            ("research-completeness.md", "\n![Logo 缺失，已检查官网，网站回退 ticker，后续待补](x.png)\n"),
            ("research-completeness.md", "\n![alt]\nordinary prose\n[alt]: https://example.com/product.png\n"),
            ("research-completeness.md", "\n![foo [bar]](https://example.com/product.png)\n"),
            ("research-completeness.md", "\n<img src=\"https://example.com/product.png\">\n"),
            ("research-completeness.md", "\n<image src='https://example.com/product.png'>\n"),
            ("research-completeness.md", "\n<input type='image' src='https://example.com/product.png'>\n"),
            ("research-completeness.md", "\n<div style='background-image:url(https://example.com/product.png)'>probe</div>\n"),
            ("evidence-ledger.json", '"data:image/svg+xml;base64,PHN2Zz4="'),
            ("evidence-ledger.json", '"data\\u003aimage/svg+xml;base64,PHN2Zz4="'),
            ("evidence-ledger.json", '"<image src=https://example.com/product.png>"'),
        )
        for filename, payload in cases:
            with self.subTest(filename=filename, payload=payload), tempfile.TemporaryDirectory() as temp_dir:
                package, schema_path, _ = make_valid_unfrozen_package(Path(temp_dir))
                target = package / filename
                if filename.endswith(".json"):
                    value = load_json(target)
                    value["embedded_media_probe"] = payload
                    write_json(target, value)
                else:
                    target.write_text(target.read_text(encoding="utf-8") + payload, encoding="utf-8")
                findings = validate_research_package(package, schema_path, "full", "test-company")
                self.assertIn("embedded-visual-asset", {item.code for item in findings})

        encoded_data_uris = (
            r"d\u0061ta:image/png;base64,AAAA",
            r"data:\u0069mage/png;base64,AAAA",
            r"data:image\u002fpng;base64,AAAA",
        )
        for encoded in encoded_data_uris:
            with self.subTest(encoded=encoded), tempfile.TemporaryDirectory() as temp_dir:
                package, schema_path, _ = make_valid_unfrozen_package(Path(temp_dir))
                target = package / "evidence-ledger.json"
                original = target.read_text(encoding="utf-8")
                self.assertTrue(original.startswith("{"))
                target.write_text(
                    '{"embedded_media_probe":"' + encoded + '",' + original[1:],
                    encoding="utf-8",
                )
                findings = validate_research_package(package, schema_path, "full", "test-company")
                self.assertIn("embedded-visual-asset", {item.code for item in findings})

    def test_manifest_builder_refuses_unacknowledged_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, schema_path, _ = make_valid_unfrozen_package(Path(temp_dir))
            trusted_lock = load_json(ROOT / "references/trusted-spec-lock.json")
            findings = validate_research_package(package, schema_path, "full", "test-company")
            validation = report_payload(package, schema_path, "full", findings, "test-company")
            validation["warnings"] = 1
            company_schema = trusted_lock["company_schema"]
            with self.assertRaisesRegex(ValueError, "warnings must be acknowledged"):
                build_manifest(
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
                    execution_integrity=trusted_lock["execution_integrity"],
                    company_slug="test-company",
                )

    def test_manifest_validator_refuses_unacknowledged_recorded_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path, schema_path, _trusted_lock, manifest = self.make_predecessor(Path(temp_dir))
            manifest["validation"]["warnings"] = 1
            manifest["warning_acknowledged"] = False
            self.write_manifest(manifest_path, manifest)
            findings = validate_research_package(manifest_path.parent, schema_path, "full", "test-company")
            self.assertIn("manifest-warning-acknowledgement", {item.code for item in findings})

    def write_manifest(self, path: Path, manifest: dict) -> None:
        write_json(path, manifest)

    def test_complete_predecessor_and_optional_gap_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path, schema_path, trusted_lock, _ = self.make_predecessor(Path(temp_dir), with_gap=True)
            _, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock, "test-company")
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
            _, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock, "test-company")
            self.assertTrue(any("fresh full validation failed" in item for item in errors), errors)

    def test_manifest_symlink_is_rejected_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path, schema_path, trusted_lock, _ = self.make_predecessor(root)
            link = root / "research-manifest.json"
            try:
                link.symlink_to(manifest_path)
            except OSError as error:
                if sys.platform == "win32" and getattr(error, "winerror", None) == 1314:
                    self.skipTest(
                        "Windows symbolic-link creation requires Developer Mode or elevation",
                    )
                raise
            previous, errors = verify_previous_manifest(link, schema_path, trusted_lock, "test-company")
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
                _, errors = verify_previous_manifest(manifest_path, schema_path, trusted_lock, "test-company")
                self.assertTrue(errors, label)

    def test_incremental_transition_records_verified_ancestry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            previous_path, schema_path, trusted_lock, _ = self.make_predecessor(root)
            current = root / "current"
            current.mkdir()
            current_company = load_json(previous_path.parent / "company.json")
            current_company["meta"].update(
                {
                    "data_as_of": "2026-06-30",
                    "valuation_date": "2026-07-15",
                    "source_version": "2026Q2",
                }
            )
            current_company["sources"].append(
                {
                    "id": "SRC-Q2",
                    "title": "Test Company 2026 Second Quarter Report",
                    "source_type": "quarterly_report",
                    "publisher": "Test Company",
                    "url": "https://example.com/2026-q2",
                    "published_at": "2026-07-10",
                    "accessed_at": "2026-07-15",
                    "notes": "Official second-quarter trigger for the incremental transition test.",
                }
            )
            current_company["reporting"]["latest_report"].update(
                {"date_status": "official", "source_ids": ["SRC-Q2"]}
            )
            write_json(current / "company.json", current_company)
            current_evidence = load_json(previous_path.parent / "evidence-ledger.json")
            current_evidence["run"]["research_mode"] = "incremental"
            current_evidence["run"]["run_id"] = "RUN-TEST-2026Q2"
            current_evidence["thesis"]["overall_change"] = "unchanged"
            for assumption in current_evidence["thesis"]["assumptions"]:
                assumption["prior_status"] = assumption["current_status"]
                assumption["change_type"] = "none"
            current_evidence["thesis"]["revision_log"] = [
                {
                    "id": "REV-2026Q2",
                    "changed_at": "2026-07-15T12:00:00Z",
                    "change_type": "none",
                    "summary": "复核新季度官方资料后，长期假设与估值参数均保持不变。",
                    "affected_assumption_ids": ["ASM-RETENTION", "ASM-COVERAGE"],
                    "evidence_claim_ids": ["CLM-002", "CLM-003"],
                }
            ]
            write_json(current / "evidence-ledger.json", current_evidence)
            errors, transition = validate_incremental_transition(
                current,
                previous_path,
                "SRC-Q2",
                schema_path,
                trusted_lock,
                "test-company",
            )
            self.assertEqual(errors, [])
            self.assertIsNotNone(transition)
            assert transition is not None
            self.assertEqual(transition["previous_manifest_sha256"], file_sha256(previous_path))
            self.assertEqual(transition["previous_research"]["ticker"], "TEST")
            self.assertEqual(transition["previous_research"]["data_as_of"], "2026-03-31")
            self.assertEqual(transition["official_trigger_source_id"], "SRC-Q2")

    def test_full_manifest_omits_incremental_provenance_and_incremental_requires_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path, schema_path, _, _ = self.make_predecessor(root)
            package = manifest_path.parent
            trusted_lock = load_json(ROOT / "references/trusted-spec-lock.json")
            fingerprint = protocol_fingerprint(trusted_lock)
            validation = {
                "validator": "v",
                "mode": "full",
                "errors": 0,
                "warnings": 0,
                "integrity_profile": "execution-bound-v1",
                "validator_sha256": fingerprint["validator_sha256"],
                "toolchain_digest_sha256": trusted_lock["execution_integrity"]["toolchain_digest_sha256"],
                "protocol_fingerprint": fingerprint,
                "company_slug": "test-company",
            }
            full = build_manifest(
                package,
                schema_path,
                "a" * 40,
                "main",
                next(iter(git_blob_sha1_candidates(schema_path))),
                trusted_lock["research_protocol"],
                "full",
                validation,
                True,
                False,
                execution_integrity=trusted_lock["execution_integrity"],
                company_slug="test-company",
            )
            self.assertNotIn("incremental_transition", full)
            with self.assertRaises(ValueError):
                build_manifest(
                    package,
                    schema_path,
                    "a" * 40,
                    "main",
                    next(iter(git_blob_sha1_candidates(schema_path))),
                    trusted_lock["research_protocol"],
                    "incremental",
                    validation,
                    True,
                    False,
                    execution_integrity=trusted_lock["execution_integrity"],
                    company_slug="test-company",
                )

    def test_incremental_dcf_parameter_drift_requires_exact_change_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            previous, current, company, evidence = self.make_drift_pair(Path(temp_dir))
            base = next(item for item in company["valuation"]["dcf_scenarios"] if item["name"] == "基准")
            old_value = base["revenue_growth"]
            base["revenue_growth"] = old_value + 0.01
            write_json(current / "company.json", company)
            errors = validate_incremental_research_drift(current, previous)
            self.assertTrue(any("DCF parameter drift" in item for item in errors), errors)

            evidence["thesis"]["valuation_assumption_changes"] = [
                {
                    "scenario": "基准",
                    "parameter": "revenue_growth",
                    "previous_value": old_value,
                    "current_value": old_value + 0.01,
                    "change_type": "fundamental",
                    "reason": "新季度客户量和单位收入证据支持上调基准显性增长。",
                    "evidence_claim_ids": ["CLM-002", "CLM-008"],
                }
            ]
            write_json(current / "evidence-ledger.json", evidence)
            self.assertEqual(validate_incremental_research_drift(current, previous), [])

    def test_incremental_assumption_status_cannot_reset_silently(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            previous, current, _company, evidence = self.make_drift_pair(Path(temp_dir))
            evidence["thesis"]["assumptions"][0]["prior_status"] = "strained"
            evidence["thesis"]["assumptions"][0]["current_status"] = "broken"
            evidence["thesis"]["assumptions"][0]["change_type"] = "none"
            write_json(current / "evidence-ledger.json", evidence)
            errors = validate_incremental_research_drift(current, previous)
            self.assertTrue(any("prior_status" in item for item in errors), errors)
            self.assertTrue(any("substantive change_type" in item for item in errors), errors)


if __name__ == "__main__":
    unittest.main()
