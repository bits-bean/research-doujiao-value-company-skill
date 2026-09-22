#!/usr/bin/env python3
"""Regression tests for vacuous-package and freeze-bypass attempts."""

from __future__ import annotations

import json
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_research_package import (  # noqa: E402
    EXPECTED_SCHEMA_DRAFT,
    EXPECTED_SCHEMA_ID,
    main,
    validate_research_package,
    write_json,
)


class ValidationGateTests(unittest.TestCase):
    def run_output_check(self, root: Path, schema: Path, output: Path) -> tuple[int, str]:
        """Exercise CLI destination checks and real writes independently of the trust lock."""
        arguments = [
            "validate_research_package.py", str(root), "--schema", str(schema),
            "--company-slug", "test-company", "--output", str(output),
        ]
        stderr = io.StringIO()
        with (
            patch.object(sys, "argv", arguments),
            patch("validate_research_package.validate_research_package", return_value=[]),
            patch("validate_research_package.report_payload", return_value={"errors": 0, "findings": []}),
            redirect_stdout(io.StringIO()),
            redirect_stderr(stderr),
        ):
            try:
                code = main()
            except SystemExit as exc:
                code = exc.code
        return code, stderr.getvalue()

    def test_output_cannot_overwrite_draft_inputs_or_create_other_package_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "package"
            root.mkdir()
            schema = Path(temp_dir) / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            for name in (
                "company.json", "evidence-ledger.json", "calculation-ledger.json",
                "research-report.md", "research-completeness.md", "schema-gap-report.md",
                "research-manifest.json", "nested/output.json", "unexpected.json",
            ):
                with self.subTest(name=name):
                    destination = root / name
                    # A new manifest must also be rejected before it can freeze the draft.
                    if name != "research-manifest.json":
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(b"original research input\n")
                    code, message = self.run_output_check(root, schema, destination)
                    self.assertNotEqual(code, 0)
                    self.assertIn("inside a draft package", message)
                    if name == "research-manifest.json":
                        self.assertFalse(destination.exists())
                    else:
                        self.assertEqual(destination.read_bytes(), b"original research input\n")

    def test_output_cannot_overwrite_input_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "package"
            root.mkdir()
            schema = Path(temp_dir) / "schema.json"
            schema.write_bytes(b"original schema\n")
            code, message = self.run_output_check(root, schema, schema)
            self.assertNotEqual(code, 0)
            self.assertIn("input Schema", message)
            self.assertEqual(schema.read_bytes(), b"original schema\n")

    def test_output_rejects_symlink_without_mutating_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "package"
            root.mkdir()
            schema = Path(temp_dir) / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            target = Path(temp_dir) / "external.json"
            target.write_bytes(b"keep external file\n")
            output = root / "validation-report.json"
            output.symlink_to(target)
            code, message = self.run_output_check(root, schema, output)
            self.assertNotEqual(code, 0)
            self.assertIn("symlink", message)
            self.assertTrue(output.is_symlink())
            self.assertEqual(target.read_bytes(), b"keep external file\n")

    def test_output_writes_draft_validation_report_and_external_frozen_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "package"
            root.mkdir()
            schema = Path(temp_dir) / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            output = root / "validation-report.json"
            code, message = self.run_output_check(root, schema, output)
            self.assertEqual(code, 0, message)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"errors": 0, "findings": []})
            original_report = output.read_bytes()
            manifest = root / "research-manifest.json"
            manifest.write_bytes(b"frozen manifest\n")
            code, message = self.run_output_check(root, schema, output)
            self.assertNotEqual(code, 0)
            self.assertIn("frozen research package", message)
            self.assertEqual(output.read_bytes(), original_report)
            external = Path(temp_dir) / "audit" / "validation-report.json"
            code, message = self.run_output_check(root, schema, external)
            self.assertEqual(code, 0, message)
            self.assertEqual(json.loads(external.read_text(encoding="utf-8")), {"errors": 0, "findings": []})
            self.assertEqual(manifest.read_bytes(), b"frozen manifest\n")

    def test_write_json_uses_deterministic_lf_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.json"

            with patch(
                "validate_research_package.tempfile.NamedTemporaryFile",
                wraps=tempfile.NamedTemporaryFile,
            ) as named_temporary_file:
                write_json(output, {"company": "腾讯", "status": "frozen"})

            encoded = output.read_bytes()
            self.assertEqual(
                encoded,
                '{\n  "company": "腾讯",\n  "status": "frozen"\n}\n'.encode("utf-8"),
            )
            self.assertEqual(named_temporary_file.call_args.kwargs["newline"], "\n")

    def make_vacuous_package(self, root: Path) -> Path:
        schema = {
            "$schema": EXPECTED_SCHEMA_DRAFT,
            "$id": EXPECTED_SCHEMA_ID,
            "type": "object",
            "required": ["meta", "sources"],
            "properties": {
                "meta": {"$ref": "#/$defs/meta"},
                "sources": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": True,
            "$defs": {
                "meta": {
                    "type": "object",
                    "required": ["schema_version"],
                    "properties": {"schema_version": {"type": "string", "const": "test-1"}},
                    "additionalProperties": True,
                }
            },
        }
        source = {
            "id": "SRC-001",
            "title": "Official filing",
            "source_type": "annual_report",
            "url": "https://example.com/report",
        }
        financials = [
            {
                "period": f"FY{year}",
                "period_type": "FY",
                "revenue": None,
                "operating_profit": None,
                "net_income": None,
                "operating_cash_flow": None,
                "capex_total": None,
                "free_cash_flow": None,
                "cash": None,
                "total_debt": None,
                "net_debt": None,
                "diluted_shares": None,
                "source_ids": ["SRC-001"],
            }
            for year in range(2016, 2026)
        ]
        financials.extend(
            [
                {"period": "2026Q2", "period_type": "Q2", "source_ids": ["SRC-001"]},
                {"period": "TTM2026", "period_type": "TTM", "source_ids": ["SRC-001"]},
            ]
        )
        company = {
            "meta": {
                "schema_version": "test-1",
                "company_name_cn": "空壳公司",
                "company_name_en": "Vacuous Co",
                "ticker": "VOID",
                "exchange": "NYSE",
                "report_currency": "USD",
                "financial_unit": "unit",
                "share_unit": "share",
                "ratio_convention": "decimal",
                "data_as_of": "2026-06-30",
                "valuation_date": "2026-08-19",
                "source_version": "test",
            },
            "brand_identity": {"company_logo": {"asset_path": "companies/test-company/assets/logo.svg", "source_url": "https://example.com/logo.svg", "alt": "Test Company official logo", "is_official": True}},
            "verdict": {
                "business_quality": "良好",
                "valuation_status": "接近合理",
                "research_status": "观察名单",
                "confidence": "high",
                "key_assumptions": ["A", "B"],
                "thesis_breakers": ["C"],
            },
            "reporting": {
                "latest_report": {"date_status": "official", "source_ids": ["SRC-001"]},
                "next_expected_report": {"source_ids": []},
            },
            "financials": financials,
            "income_statement_sankey": {"nodes": [], "links": [], "reconciled": False, "source_ids": ["SRC-001"]},
            "segments": [],
            "capital_allocation": [],
            "buyback_ledger": [],
            "debt_maturities": [],
            "moat": [],
            "management": {"scores": [], "commitment_timeline": [], "stop_doing_list": []},
            "valuation": {
                "market_price": None,
                "diluted_shares": None,
                "market_cap": None,
                "enterprise_value": None,
                "multiples": {},
                "dcf_scenarios": [],
                "dcf_sensitivity": [],
                "reverse_dcf": {"x": None},
                "fair_value_range": {},
                "expected_returns": [],
            },
            "risks": {
                "pre_mortem": ["", "", "", "", ""],
                "bear_case": "",
                "fragile_assumptions": ["", "", ""],
                "monitoring_indicators": [{"name": "", "current_status": "", "trigger": ""} for _ in range(5)],
            },
            "sources": [source],
        }
        package = root / "package"
        package.mkdir()
        write_json(root / "schema.json", schema)
        write_json(package / "company.json", company)
        write_json(
            package / "evidence-ledger.json",
            {"claims": [{"id": "CLM-001", "claim": "", "classification": "fact", "confidence": "high", "source_ids": ["SRC-001"]}]},
        )
        write_json(
            package / "calculation-ledger.json",
            {"numeric_convention": "base_units", "calculations": [{"id": "CALC-001", "metric": "custom", "formula": "x", "source_ids": []}]},
        )
        (package / "research-report.md").write_text(
            "# 空壳公司 VOID\n一页式结论 数据截至日 商业模式 十年财务 自由现金流 ROIC 护城河 长期生存 Stop Doing 资本配置 回购明细 治理 债务 Reverse DCF Pre-Mortem 待调查 领先指标 最终结论",
            encoding="utf-8",
        )
        (package / "research-completeness.md").write_text(
            "已覆盖十年期间标签。无关键缺失。置信度写在这里。影响写在这里。下一步待取得证据。" * 8,
            encoding="utf-8",
        )
        return root / "schema.json"

    def test_vacuous_package_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schema = self.make_vacuous_package(root)
            findings = validate_research_package(root / "package", schema, "full", "test-company")
            codes = {item.code for item in findings if item.severity == "error"}
            expected = {
                "insubstantial-financial-history",
                "claim-text",
                "claim-location",
                "calculation-result",
                "custom-calculation-review",
                "empty-sankey",
                "moat-coverage",
                "management-score-coverage",
                "missing-reverse-dcf",
                "report-section-one-page-conclusion",
            }
            self.assertTrue(expected.issubset(codes), sorted(codes))

    def test_audit_cannot_freeze_and_blob_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schema = self.make_vacuous_package(root)
            base = [
                sys.executable,
                str(ROOT / "scripts" / "freeze_research.py"),
                str(root / "package"),
                "--schema",
                str(schema),
                "--schema-blob-sha",
                "b" * 40,
                "--spec-commit",
                "a" * 40,
                "--company-slug",
                "test-company",
            ]
            audit = subprocess.run(base + ["--mode", "audit"], capture_output=True, text=True, check=False)
            self.assertNotEqual(audit.returncode, 0)
            self.assertIn("invalid choice", audit.stderr)
            blob = subprocess.run(base, capture_output=True, text=True, check=False)
            self.assertNotEqual(blob.returncode, 0)
            self.assertTrue("not match" in blob.stderr or "not approved" in blob.stderr, blob.stderr)


if __name__ == "__main__":
    unittest.main()
