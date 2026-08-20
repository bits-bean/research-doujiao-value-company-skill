#!/usr/bin/env python3
"""Semantic regression tests for research-package validation."""

from __future__ import annotations

import json
import hashlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_research_package import (  # noqa: E402
    FROZEN_HASH_FILES,
    EXPECTED_SCHEMA_PATH,
    EXPECTED_SPEC_REPOSITORY,
    REPORT_SECTIONS,
    Finding,
    FormulaEvaluationError,
    evaluate_custom_formula,
    extract_schema_version,
    file_sha256,
    git_blob_sha1,
    is_official_report_schedule_source,
    load_trusted_spec_lock,
    schema_sha256_candidates,
    validate_evidence,
    validate_calculations,
    validate_manifest,
    validate_report,
    validate_too_hard_acknowledgements,
    validate_valuation,
    validate_verdict_and_risks,
    write_json,
)


class SemanticGateTests(unittest.TestCase):
    def test_trusted_lock_rejects_zero_protocol_commit(self) -> None:
        original = json.loads((ROOT / "references/trusted-spec-lock.json").read_text(encoding="utf-8"))
        original["research_protocol"]["commit"] = "0" * 40
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "trusted-spec-lock.json"
            write_json(lock_path, original)
            findings: list[Finding] = []
            with patch("validate_research_package.TRUSTED_SPEC_LOCK_PATH", lock_path):
                loaded = load_trusted_spec_lock(findings)
        self.assertIsNone(loaded)
        self.assertIn("trusted-research-protocol-shape", {item.code for item in findings})

    def test_trusted_lock_rejects_extra_fields_at_every_level(self) -> None:
        original = json.loads((ROOT / "references/trusted-spec-lock.json").read_text(encoding="utf-8"))
        mutations = {
            "top-level": lambda lock: lock.__setitem__("extra", True),
            "research-protocol": lambda lock: lock["research_protocol"].__setitem__("name", "legacy"),
            "company-schema": lambda lock: lock["company_schema"].__setitem__("extra", True),
            "document": lambda lock: lock["research_protocol"]["documents"][0].__setitem__("extra", True),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                lock = json.loads(json.dumps(original))
                mutate(lock)
                lock_path = Path(temp_dir) / "trusted-spec-lock.json"
                write_json(lock_path, lock)
                findings: list[Finding] = []
                with patch("validate_research_package.TRUSTED_SPEC_LOCK_PATH", lock_path):
                    loaded = load_trusted_spec_lock(findings)
                self.assertIsNone(loaded)
                self.assertTrue(any(item.code.startswith("trusted-") for item in findings), findings)

    def test_schema_sha256_allows_only_one_final_lf_transport_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.json"
            exact = b'{"schema":"trusted"}'
            schema_path.write_bytes(exact)
            expected = {
                hashlib.sha256(exact).hexdigest(),
                hashlib.sha256(exact + b"\n").hexdigest(),
            }
            self.assertEqual(schema_sha256_candidates(schema_path), expected)
            schema_path.write_bytes(exact + b"\n")
            self.assertEqual(schema_sha256_candidates(schema_path), expected)

    def test_custom_formula_is_safely_recomputed(self) -> None:
        self.assertAlmostEqual(
            evaluate_custom_formula(
                "result = NOPAT / average_invested_capital",
                {"NOPAT": 120, "average_invested_capital": 800},
            ),
            0.15,
        )
        blocked = (
            ("__import__('os').system('id')", {"NOPAT": 1}),
            ("NOPAT.real + 1", {"NOPAT": 1}),
            ("NOPAT + unknown", {"NOPAT": 1}),
            ("NOPAT / zero", {"NOPAT": 1, "zero": 0}),
            ("NOPAT + 1e309", {"NOPAT": 1}),
            ("NOPAT", {"NOPAT": 1}),
        )
        for formula, inputs in blocked:
            with self.subTest(formula=formula), self.assertRaises(FormulaEvaluationError):
                evaluate_custom_formula(formula, inputs)

        ledger = {
            "calculations": [{
                "id": "CALC-ROIC-2025",
                "metric": "custom",
                "period": "FY2025",
                "formula": "NOPAT / average_invested_capital",
                "inputs": {"NOPAT": 120, "average_invested_capital": 800},
                "result": 0.25,
                "unit": "decimal ratio",
                "tolerance": 1,
                "review_method": "逐项核对税后经营利润与期初期末投入资本平均值并独立复算",
                "source_ids": ["SRC-001"],
            }]
        }
        findings: list[Finding] = []
        validate_calculations(ledger, {"meta": {}, "financials": [], "valuation": {}}, {"SRC-001"}, "audit", findings)
        codes = {item.code for item in findings}
        self.assertTrue({"calculation-tolerance", "custom-calculation-mismatch"}.issubset(codes))

    def test_evidence_rejects_numeric_template_farming(self) -> None:
        claims = []
        for index in range(10):
            classification = "fact" if index < 8 else "inference"
            claim = {
                "id": f"CLM-{index:03d}",
                "claim": f"公司在20{index:02d}财年确认收入{100 + index}亿元并保持相同披露口径",
                "classification": classification,
                "confidence": "high",
                "source_ids": ["SRC-001"],
                "location": f"年报第{index + 10}页",
            }
            if classification == "inference":
                claim["would_falsify"] = f"若未来第{index}个观察期收入跌破历史区间则推翻该判断"
            claims.append(claim)
        findings: list[Finding] = []
        validate_evidence({"claims": claims}, {"SRC-001"}, "full", findings)
        self.assertIn("repeated-claim-template", {item.code for item in findings})

    def test_reverse_dcf_needs_operating_mix_comparison_and_sensitivity(self) -> None:
        company = {
            "meta": {"report_currency": "USD", "financial_unit": "million", "share_unit": "million_shares"},
            "verdict": {"research_status": "观察名单", "valuation_status": "接近合理"},
            "financials": [],
            "valuation": {
                "market_price": 10,
                "diluted_shares": 100,
                "market_cap": 1000,
                "enterprise_value": 1000,
                "dcf_scenarios": [],
                "dcf_sensitivity": [],
                "reverse_dcf": {"revenue_growth": 0.1, "revenue_cagr": 0.1},
                "multiples": {"pe": 20},
                "fair_value_range": {"low": 8, "base": 10, "high": 12, "currency": "USD"},
                "expected_returns": [],
            },
        }
        findings: list[Finding] = []
        validate_valuation(company, findings)
        codes = {item.code for item in findings}
        self.assertTrue({"missing-reverse-dcf", "reverse-dcf-comparison", "reverse-dcf-sensitivity"}.issubset(codes))

        company["valuation"]["reverse_dcf"] = {
            "implied_revenue_cagr": 0.08,
            "implied_operating_margin": 0.22,
            "comparison_to_history": "隐含增长与历史五年区间接近，但利润率高于行业同业中位水平，需要谨慎判断合理性。",
            "sensitivity_and_threshold": "利润率最敏感；若连续三年低于百分之十八，当前股价将显得偏高并推翻基准判断。",
        }
        valid_findings: list[Finding] = []
        validate_valuation(company, valid_findings)
        reverse_codes = {item.code for item in valid_findings if item.code.startswith("reverse") or item.code == "missing-reverse-dcf"}
        self.assertFalse(reverse_codes, sorted(reverse_codes))

    def test_verdict_risks_and_report_reject_repeated_placeholders(self) -> None:
        company = {
            "meta": {"company_name_cn": "测试公司", "company_name_en": "Test Company", "ticker": "TEST"},
            "verdict": {
                "business_quality": "良好",
                "valuation_status": "接近合理",
                "research_status": "观察名单",
                "confidence": "high",
                "one_sentence": "占位内容占位内容占位内容占位内容",
                "key_assumptions": ["收入增长保持百分之十以上", "收入增长保持百分之二十以上"],
                "thesis_breakers": ["收入增长保持百分之三十以上"],
            },
            "risks": {
                "pre_mortem": [f"同一风险路径在第{index}年发生并导致结论失效" for index in range(5)],
                "bear_case": "占位内容占位内容占位内容占位内容",
                "fragile_assumptions": [f"同一脆弱假设在第{index}年发生变化" for index in range(3)],
                "monitoring_indicators": [
                    {"name": f"指标{index}", "current_status": "当前状态保持稳定", "trigger": f"连续{index}季跌破同一阈值", "source_ids": ["SRC-001"]}
                    for index in range(5)
                ],
            },
            "sources": [{"id": "SRC-001"}],
        }
        findings: list[Finding] = []
        validate_verdict_and_risks(company, findings)
        codes = {item.code for item in findings}
        self.assertTrue({"verdict-summary", "pre_mortem-substance", "bear-case"}.issubset(codes))

        body = "这是一段仅用于检测重复章节的公司研究占位正文，缺少独立证据与不同分析结论。" * 3
        report = "# 测试公司 TEST\n" + "\n".join(f"## {alternatives[0]}\n{body}" for _, alternatives in REPORT_SECTIONS)
        report_findings: list[Finding] = []
        validate_report(company, report, "full", report_findings)
        self.assertIn("repeated-report-section", {item.code for item in report_findings})

    def test_too_hard_warning_needs_code_specific_explanation(self) -> None:
        company = {"verdict": {"research_status": "Too Hard", "valuation_status": "无法判断"}}
        findings = [Finding("warning", "empty-sankey", "company.json", "gap")]
        validate_too_hard_acknowledgements(company, "覆盖、缺口、置信度、影响与下一步均已说明。", findings)
        self.assertIn("unacknowledged-too-hard-warning", {item.code for item in findings})

        acknowledged = [Finding("warning", "empty-sankey", "company.json", "gap")]
        validate_too_hard_acknowledgements(
            company,
            "- empty-sankey：公司未披露可可靠重构的利润表分流，影响资金流结论，待取得分部附注后补充。",
            acknowledged,
        )
        self.assertNotIn("unacknowledged-too-hard-warning", {item.code for item in acknowledged})

    def test_ir_calendar_is_valid_for_official_next_report(self) -> None:
        source = {
            "source_type": "official_website",
            "title": "Investor Relations Events Calendar",
            "url": "https://example.com/investor-relations/events-calendar",
        }
        self.assertTrue(is_official_report_schedule_source(source))
        self.assertFalse(is_official_report_schedule_source({**source, "title": "Home", "url": "https://example.com/"}))

    def test_numeric_suffixes_do_not_evade_repetition_detection(self) -> None:
        claims = {
            "claims": [
                {
                    "id": f"CLM-{index}",
                    "claim": f"xxxxxxxxxxxx{index}",
                    "classification": "fact" if index < 9 else "inference",
                    "source_ids": [f"SRC-{index}"],
                    "location": "Annual report page 42" if index < 9 else None,
                    "would_falsify": "A sustained reversal in the disclosed operating trend" if index == 9 else None,
                }
                for index in range(10)
            ]
        }
        findings: list[Finding] = []
        validate_evidence(claims, {f"SRC-{index}" for index in range(10)}, "full", findings)
        self.assertIn("repeated-claim-template", {item.code for item in findings})

        company = {
            "verdict": {
                "business_quality": "良好",
                "valuation_status": "接近合理",
                "research_status": "观察名单",
                "confidence": "medium",
                "one_sentence": "这是一项具有可验证经营前提且仍需持续跟踪风险的公司判断。",
                "key_assumptions": ["aaaaaaaa0", "aaaaaaaa1"],
                "thesis_breakers": ["bbbbbbbb0"],
            },
            "risks": {
                "pre_mortem": [f"aaaaaaaaaa{index}" for index in range(5)],
                "fragile_assumptions": [f"cccccccc{index}" for index in range(3)],
                "bear_case": "竞争恶化与资本配置失误同时发生将造成长期每股价值损失。",
                "monitoring_indicators": [
                    {
                        "name": f"领先指标{index}",
                        "current_status": f"当前状态保持在历史区间{index}",
                        "trigger": f"若该指标连续四季恶化超过阈值{index}则复核长期结论",
                        "source_ids": ["SRC-001"],
                    }
                    for index in range(5)
                ],
            },
        }
        risk_findings: list[Finding] = []
        validate_verdict_and_risks(company, risk_findings)
        codes = {item.code for item in risk_findings}
        self.assertTrue({"key-assumptions", "pre_mortem-substance", "fragile_assumptions-substance"}.intersection(codes))

    def test_manifest_is_bound_to_bundled_trust_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schema_path = root / "schema.json"
            schema_path.write_text('{"schema":"local test"}\n', encoding="utf-8")
            for name in FROZEN_HASH_FILES:
                if name == "validation-report.json":
                    write_json(root / name, {"validator": "test", "mode": "full", "errors": 0, "warnings": 0})
                else:
                    (root / name).write_text(f"{name}\n", encoding="utf-8")
            company = {
                "meta": {
                    "schema_version": "evil-version",
                    "company_name_cn": "测试公司",
                    "company_name_en": "Test Company",
                    "ticker": "TEST",
                    "exchange": "NYSE",
                    "report_currency": "USD",
                    "data_as_of": "2026-06-30",
                    "valuation_date": "2026-08-19",
                    "source_version": "test",
                }
            }
            files = [
                {"path": name, "sha256": file_sha256(root / name), "size_bytes": (root / name).stat().st_size}
                for name in FROZEN_HASH_FILES
            ]
            manifest = {
                "manifest_version": "2.0",
                "status": "frozen",
                "frozen_at": "2026-08-19T12:00:00Z",
                "human_review_status": "pending",
                "warning_acknowledged": False,
                "specification": {
                    "repository": "attacker/fork",
                    "ref": "feature",
                    "commit": "a" * 40,
                    "schema_path": "schema.json",
                    "schema_blob_sha1": git_blob_sha1(schema_path),
                    "schema_sha256": file_sha256(schema_path),
                    "schema_version": "evil-version",
                },
                "research_protocol": {"authority": "attacker"},
                "research": dict(company["meta"]),
                "validation": {"validator": "test", "mode": "full", "errors": 0, "warnings": 0},
                "files": files,
            }
            write_json(root / "research-manifest.json", manifest)
            findings: list[Finding] = []
            validate_manifest(root, schema_path, company, "full", findings)
            codes = {item.code for item in findings}
            expected = {
                "manifest-repository",
                "manifest-ref",
                "manifest-commit",
                "manifest-schema-path",
                "manifest-schema-blob-sha1",
                "manifest-schema-version",
                "trusted-schema-local-mismatch",
                "manifest-company-schema-version",
                "manifest-research-protocol",
            }
            self.assertTrue(expected.issubset(codes), sorted(codes))

    def test_v1_manifest_is_accepted_only_for_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            schema_path = root / "schema.json"
            shutil.copyfile(ROOT / "references/specs/company.schema.json", schema_path)
            schema_version = extract_schema_version(json.loads(schema_path.read_text(encoding="utf-8")))
            company = {
                "meta": {
                    "schema_version": schema_version,
                    "company_name_cn": "测试公司",
                    "company_name_en": "Test Company",
                    "ticker": "TEST",
                    "exchange": "NYSE",
                    "report_currency": "USD",
                    "data_as_of": "2026-06-30",
                    "valuation_date": "2026-08-19",
                    "source_version": "test",
                }
            }
            for name in FROZEN_HASH_FILES:
                if name == "company.json":
                    write_json(root / name, company)
                elif name == "validation-report.json":
                    write_json(root / name, {"validator": "test", "mode": "full", "errors": 0, "warnings": 0})
                else:
                    (root / name).write_text(f"{name}\n", encoding="utf-8")
            manifest = {
                "manifest_version": "1.0",
                "status": "frozen",
                "frozen_at": "2026-08-19T12:00:00Z",
                "human_review_status": "accepted",
                "warning_acknowledged": False,
                "specification": {
                    "repository": EXPECTED_SPEC_REPOSITORY,
                    "ref": "main",
                    "commit": "a" * 40,
                    "schema_path": EXPECTED_SCHEMA_PATH,
                    "schema_blob_sha1": git_blob_sha1(schema_path),
                    "schema_sha256": file_sha256(schema_path),
                    "schema_version": schema_version,
                },
                "research": dict(company["meta"]),
                "validation": {"validator": "test", "mode": "full", "errors": 0, "warnings": 0},
                "files": [
                    {"path": name, "sha256": file_sha256(root / name), "size_bytes": (root / name).stat().st_size}
                    for name in FROZEN_HASH_FILES
                ],
            }
            write_json(root / "research-manifest.json", manifest)
            audit_findings: list[Finding] = []
            validate_manifest(root, schema_path, company, "audit", audit_findings)
            self.assertNotIn("legacy-manifest-audit-only", {item.code for item in audit_findings})
            full_findings: list[Finding] = []
            validate_manifest(root, schema_path, company, "full", full_findings)
            self.assertIn("legacy-manifest-audit-only", {item.code for item in full_findings})


if __name__ == "__main__":
    unittest.main()
