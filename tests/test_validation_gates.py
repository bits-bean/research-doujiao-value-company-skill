#!/usr/bin/env python3
"""Regression tests for vacuous-package and freeze-bypass attempts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_research_package import (  # noqa: E402
    EXPECTED_SCHEMA_DRAFT,
    EXPECTED_SCHEMA_ID,
    validate_research_package,
    write_json,
)


class ValidationGateTests(unittest.TestCase):
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
            "brand_identity": {"company_logo": {"asset_path": None, "source_url": None, "alt": None, "is_official": False}},
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
        write_json(root / "schema.json", schema)
        write_json(root / "company.json", company)
        write_json(
            root / "evidence-ledger.json",
            {"claims": [{"id": "CLM-001", "claim": "", "classification": "fact", "confidence": "high", "source_ids": ["SRC-001"]}]},
        )
        write_json(
            root / "calculation-ledger.json",
            {"numeric_convention": "base_units", "calculations": [{"id": "CALC-001", "metric": "custom", "formula": "x", "source_ids": []}]},
        )
        (root / "research-report.md").write_text(
            "# 空壳公司 VOID\n一页式结论 数据截至日 商业模式 十年财务 自由现金流 ROIC 护城河 长期生存 Stop Doing 资本配置 回购明细 治理 债务 Reverse DCF Pre-Mortem 待调查 领先指标 最终结论",
            encoding="utf-8",
        )
        (root / "research-completeness.md").write_text(
            "已覆盖十年期间标签。无关键缺失。置信度写在这里。影响写在这里。下一步待取得证据。" * 8,
            encoding="utf-8",
        )
        return root / "schema.json"

    def test_vacuous_package_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schema = self.make_vacuous_package(root)
            findings = validate_research_package(root, schema, "full")
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
                str(root),
                "--schema",
                str(schema),
                "--schema-blob-sha",
                "b" * 40,
                "--spec-commit",
                "a" * 40,
            ]
            audit = subprocess.run(base + ["--mode", "audit"], capture_output=True, text=True, check=False)
            self.assertNotEqual(audit.returncode, 0)
            self.assertIn("invalid choice", audit.stderr)
            blob = subprocess.run(base, capture_output=True, text=True, check=False)
            self.assertNotEqual(blob.returncode, 0)
            self.assertTrue("not match" in blob.stderr or "not approved" in blob.stderr, blob.stderr)


if __name__ == "__main__":
    unittest.main()
