#!/usr/bin/env python3
"""Semantic regression tests for research-package validation."""

from __future__ import annotations

import json
import hashlib
import copy
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from package_fixture import make_valid_unfrozen_package  # noqa: E402

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
    validate_chinese_display_units,
    validate_too_hard_acknowledgements,
    validate_valuation,
    validate_verdict_and_risks,
    write_json,
)


def replace_h2_body(report: str, heading: str, body: str) -> str:
    marker = f"## {heading}\n"
    start = report.index(marker)
    end = report.find("\n## ", start + len(marker))
    if end < 0:
        end = len(report)
    return report[:start] + marker + body.rstrip() + "\n" + report[end:]


def h2_body(report: str, heading: str) -> str:
    marker = f"## {heading}\n"
    start = report.index(marker) + len(marker)
    end = report.find("\n## ", start)
    return report[start:end if end >= 0 else len(report)].rstrip()


def remove_h2_section(report: str, heading: str) -> str:
    marker = f"## {heading}\n"
    start = report.index(marker)
    end = report.find("\n## ", start + len(marker))
    if end < 0:
        end = len(report)
    return report[:start] + report[end + (1 if end < len(report) else 0):]


class SemanticGateTests(unittest.TestCase):
    def test_chinese_report_rejects_database_scale_display_units(self) -> None:
        findings: list[Finding] = []
        validate_chinese_display_units(
            "这是一份面向中国投资者的正式研究报告。" * 12
            + "初期股东可分配现金为8666.4百万美元，稀释后股数为679 million shares。",
            findings,
        )
        self.assertIn(
            "report-display-units-not-localized",
            {item.code for item in findings},
        )

        findings = []
        validate_chinese_display_units(
            "这是一份面向中国投资者的正式研究报告。" * 12
            + "初期股东可分配现金为86.664亿美元，稀释后股数为6.79亿股。",
            findings,
        )
        self.assertNotIn(
            "report-display-units-not-localized",
            {item.code for item in findings},
        )

        findings = []
        validate_chinese_display_units(
            "这是一份面向中国投资者的正式研究报告。" * 12
            + "初期现金流总额为186800000000，稀释后股数为9153000000，初期每股现金流为20.41。",
            findings,
        )
        self.assertIn("report-display-unit-missing", {item.code for item in findings})

        findings = []
        validate_chinese_display_units(
            "这是一份面向中国投资者的正式研究报告。" * 12
            + "初期现金流总额为1,868亿元，稀释后股数为91.53亿股，初期每股现金流为20.41元/股。",
            findings,
        )
        self.assertNotIn("report-display-unit-missing", {item.code for item in findings})

    def test_chinese_report_tables_require_reader_facing_units(self) -> None:
        bad = """这是一份面向中国投资者的正式研究报告。""" * 12 + """
| 年份 | 营收 | 净利润 | 稀释后股数 | 净利率 |
|---|---:|---:|---:|---:|
| 2025 | 660000000000 | 194000000000 | 9153000000 | 0.29 |
"""
        findings: list[Finding] = []
        validate_chinese_display_units(bad, findings)
        self.assertIn("report-display-unit-missing", {item.code for item in findings})

        good = """这是一份面向中国投资者的正式研究报告。""" * 12 + """
| 年份 | 营收（亿元） | 净利润（亿元） | 稀释后股数（亿股） | 净利率 |
|---|---:|---:|---:|---:|
| 2025 | 6,600 | 1,940 | 91.53 | 29% |
"""
        findings = []
        validate_chinese_display_units(good, findings)
        self.assertNotIn("report-display-unit-missing", {item.code for item in findings})

    def test_cash_flow_first_valuation_gates_reject_missing_or_eps_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, _, company = make_valid_unfrozen_package(Path(temp_dir))
            calculations = json.loads((package / "calculation-ledger.json").read_text(encoding="utf-8"))
            report = (package / "research-report.md").read_text(encoding="utf-8")
        known = {item["id"] for item in company["sources"]}

        missing = copy.deepcopy(calculations)
        missing["calculations"] = [item for item in missing["calculations"] if item.get("valuation_role") != "starting_cash_flow"]
        findings: list[Finding] = []
        validate_calculations(missing, company, known, "full", findings)
        self.assertIn("missing-valuation-starting-cash-flow", {item.code for item in findings})

        eps = copy.deepcopy(calculations)
        start = next(item for item in eps["calculations"] if item.get("valuation_role") == "starting_cash_flow")
        start["cash_flow_basis"] = "eps"
        findings = []
        validate_calculations(eps, company, known, "full", findings)
        self.assertTrue({"valuation-starting-cash-flow-basis", "valuation-starting-cash-flow-eps"}.issubset({item.code for item in findings}))

        input_table = """| 现金流口径 | 基准期间 | 初期现金流总额 | 稀释后股数 | 初期每股现金流 | 显性期 |
|---|---|---|---|---|---|
| FCFF | FY2025 | 0.29亿美元 | 1亿股 | 0.29美元/股 | 10年 |

"""
        no_inputs = report.replace(input_table, "", 1)
        findings = []
        validate_report(company, no_inputs, "full", findings, calculations)
        self.assertIn("report-valuation-inputs", {item.code for item in findings})

        eps_report = report.replace("| FCFF | FY2025 |", "| EPS | FY2025 |", 1)
        findings = []
        validate_report(company, eps_report, "full", findings, calculations)
        self.assertIn("report-valuation-eps-input", {item.code for item in findings})

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
            "numeric_convention": "base_units",
            "calculations": [{
                "id": "CALC-ROIC-2025",
                "metric": "custom",
                "period": "FY2025",
                "formula": "NOPAT / average_invested_capital",
                "inputs": {"NOPAT": 120_000_000, "average_invested_capital": 800_000_000},
                "result": 0.25,
                "tolerance": 1,
                "review_method": "逐项核对税后经营利润与期初期末投入资本平均值并独立复算",
                "source_ids": ["SRC-001"],
            }]
        }
        findings: list[Finding] = []
        validate_calculations(ledger, {"meta": {"financial_unit": "unit", "share_unit": "share"}, "financials": [], "valuation": {}}, {"SRC-001"}, "audit", findings)
        codes = {item.code for item in findings}
        self.assertTrue({"calculation-tolerance", "custom-calculation-mismatch"}.issubset(codes))

    def test_calculation_ledger_requires_unscaled_base_values_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, _, company = make_valid_unfrozen_package(Path(temp_dir))
            ledger = json.loads((package / "calculation-ledger.json").read_text(encoding="utf-8"))
        known = {item["id"] for item in company["sources"]}

        missing_convention = copy.deepcopy(ledger)
        missing_convention.pop("numeric_convention")
        findings: list[Finding] = []
        validate_calculations(missing_convention, company, known, "full", findings)
        self.assertIn("calculation-numeric-convention", {item.code for item in findings})

        scaled_unit_field = copy.deepcopy(ledger)
        scaled_unit_field["calculations"][0]["unit"] = "USD million"
        findings = []
        validate_calculations(scaled_unit_field, company, known, "full", findings)
        self.assertIn("calculation-unit-field", {item.code for item in findings})

        scaled_meta = copy.deepcopy(company)
        scaled_meta["meta"]["financial_unit"] = "million"
        findings = []
        validate_calculations(ledger, scaled_meta, known, "full", findings)
        self.assertIn("company-base-unit-convention", {item.code for item in findings})

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
            "meta": {"report_currency": "USD", "financial_unit": "unit", "share_unit": "share"},
            "verdict": {"research_status": "观察名单", "valuation_status": "接近合理"},
            "financials": [],
            "valuation": {
                "market_price": 10,
                "diluted_shares": 100_000_000,
                "market_cap": 1_000_000_000,
                "enterprise_value": 1_000_000_000,
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

    def test_formal_report_fixture_passes_and_structural_keyword_stuffing_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, _, company = make_valid_unfrozen_package(Path(temp_dir))
            report = (package / "research-report.md").read_text(encoding="utf-8")

        def codes(candidate: str) -> set[str]:
            findings: list[Finding] = []
            validate_report(company, candidate, "full", findings)
            return {item.code for item in findings}

        self.assertEqual(codes(report), set())
        keyword_piles = {
            "summary": (
                replace_h2_body(
                    report,
                    "一页式结论",
                    "企业质量、估值状态、研究状态、置信度、关键假设和 Thesis breakers 都是重要概念，"
                    "但这段文字故意不把结论和值建立结构化对应。保留引用 SRC-FY 和 SRC-Q1 也不应绕过门禁。",
                ),
                "report-one-page-business-quality",
            ),
            "final": (
                replace_h2_body(
                    report,
                    "最终结论",
                    "八维评分矩阵、评分、置信度、核心证据、最强反证、企业质量、估值状态、研究状态、"
                    "关键假设和 Thesis breakers 全部出现，但没有结构化字段或逐维记录，不能视为完整结论。",
                ),
                "report-final-scorecard",
            ),
            "moat": (
                replace_h2_body(
                    report,
                    "护城河",
                    "评分、趋势、置信度、支持证据、最强反证和最可能的破坏因素全部写在一个长段落中，"
                    "没有逐维映射，也没有可验证的分数与互不重复的证据，因此关键词齐全仍应失败。",
                ),
                "report-moat-matrix",
            ),
            "pre-mortem": (
                report.replace(
                    "| 新技术改变客户入口，既有品牌无法转化为下一代产品采用。 | 中 | 高 | 5–10年 | 新入口交易占比上升而本公司采用率落后 | 部分可逆 | 开放接口并通过合作进入下一代入口 |\n",
                    "",
                    1,
                ),
                "report-pre-mortem-substance",
            ),
            "source-index": (
                replace_h2_body(
                    report,
                    "主要来源索引",
                    "SRC-FY 和 SRC-Q1 的标题、发布者、来源类型、日期、期间、URL、页码与章节定位关键词都在此，"
                    "但没有把每个 ID 映射到一条完整可复核记录。",
                ),
                "report-source-index-structure",
            ),
        }
        for label, (candidate, expected) in keyword_piles.items():
            with self.subTest(label=label):
                self.assertIn(expected, codes(candidate))

        invalid_moat_score = report.replace("| 定价权 | 4.0 / 5 |", "| 定价权 | 9 / 5 |", 1)
        self.assertIn("report-moat-matrix-substance", codes(invalid_moat_score))

    def test_formal_report_section_and_source_index_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, _, company = make_valid_unfrozen_package(Path(temp_dir))
            report = (package / "research-report.md").read_text(encoding="utf-8")

        def codes(candidate: str) -> set[str]:
            findings: list[Finding] = []
            validate_report(company, candidate, "full", findings)
            return {item.code for item in findings}

        self.assertIn("report-section-business-model", codes(remove_h2_section(report, "商业模式")))
        swapped = report.replace("## 商业模式", "## __TEMP__", 1).replace("## 十年财务", "## 商业模式", 1).replace("## __TEMP__", "## 十年财务", 1)
        self.assertIn("report-section-order", codes(swapped))

        no_index = remove_h2_section(report, "主要来源索引")
        self.assertIn("report-source-index", codes(no_index))
        direct_links = no_index
        direct_links = direct_links.replace("SRC-FY", "https://example.com/investors/2025-annual-report")
        direct_links = direct_links.replace("SRC-Q1", "https://example.com/investors/2026-q1")
        self.assertEqual(codes(direct_links), set())

        uncited_business = replace_h2_body(
            report,
            "商业模式",
            h2_body(report, "商业模式").replace("就地来源：SRC-FY。", "", 1),
        )
        self.assertIn("report-section-citation", codes(uncited_business))

        final_start = report.index("## 最终结论\n")
        conflicting_final = report[:final_start] + report[final_start:].replace("| 置信度 | 高 |", "| 置信度 | 低 |", 1)
        self.assertIn("report-conclusion-consistency", codes(conflicting_final))
        missing_final_quality = report[:final_start] + report[final_start:].replace("| 企业质量 | 良好 |\n", "", 1)
        self.assertIn("report-final-business-quality", codes(missing_final_quality))

        publisher_only = report.replace("Test Company / annual report", "Test Company", 1)
        self.assertIn("report-source-index-mapping", codes(publisher_only))
        wrong_date_and_period = report.replace("2026-02-15 / FY2025", "2024-01-01 / FY2024", 1)
        self.assertIn("report-source-index-mapping", codes(wrong_date_and_period))
        dated_location = report.replace("pp. 40-74", "2025 Annual Report pp. 40-74", 1)
        self.assertEqual(codes(dated_location), set())
        mapping_mutations = {
            "missing-publisher": report.replace("Test Company / annual report", "annual report", 1),
            "wrong-title": report.replace("Test Company 2025 Annual Report", "Unrelated document", 1),
            "wrong-url": report.replace("https://example.com/investors/2025-annual-report | pp. 40-74", "https://example.com/wrong | pp. 40-74", 1),
            "missing-location": report.replace("| pp. 40-74 |", "| Annual report |", 1),
        }
        for label, candidate in mapping_mutations.items():
            with self.subTest(label=label):
                self.assertIn("report-source-index-mapping", codes(candidate))

        source_marker = "## 主要来源索引\n"
        source_start = report.index(source_marker)
        source_section = report[source_start:]
        without_source = report[:source_start]
        final_start = without_source.index("## 最终结论\n")
        misplaced = without_source[:final_start] + source_section + "\n" + without_source[final_start:]
        self.assertIn("report-source-index-order", codes(misplaced))

    def test_report_bypass_regressions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, _, company = make_valid_unfrozen_package(Path(temp_dir))
            report = (package / "research-report.md").read_text(encoding="utf-8")

        def codes(candidate: str, candidate_company: dict | None = None) -> set[str]:
            findings: list[Finding] = []
            validate_report(candidate_company or company, candidate, "full", findings)
            return {item.code for item in findings}

        final_body = h2_body(report, "最终结论")
        zero_scorecard = re.sub(r"(?m)^(\| [^|\n]+ \| )\d(?:\.\d+)? / 5( \|)", r"\g<1>0 / 5\2", final_body)
        zero_without_row_sources = zero_scorecard.replace("〔SRC-FY〕", "").replace("〔SRC-Q1〕", "")
        self.assertIn(
            "report-final-scorecard-substance",
            codes(replace_h2_body(report, "最终结论", zero_without_row_sources)),
        )

        contradictory_final = final_body.replace(
            "核心客户续费率保持稳定且单位服务收入继续温和增长",
            "核心客户续费率将永久崩溃且单位服务收入停止增长",
            1,
        )
        self.assertIn(
            "report-conclusion-key-assumptions-consistency",
            codes(replace_h2_body(report, "最终结论", contradictory_final)),
        )
        contradictory_breaker = final_body.replace(
            "连续四个季度核心客户净流失并伴随单位经济性恶化",
            "连续四个季度核心客户增长即可推翻长期结论",
            1,
        )
        self.assertIn(
            "report-conclusion-thesis-breakers-consistency",
            codes(replace_h2_body(report, "最终结论", contradictory_breaker)),
        )

        no_index = remove_h2_section(report, "主要来源索引")
        fake_links = no_index.replace("SRC-FY", "https://fake.example/fy").replace("SRC-Q1", "https://fake.example/q1")
        self.assertIn("report-source-url", codes(fake_links))
        implausible_page = report.replace("pp. 40-74", "p. 999999", 1)
        self.assertIn("report-source-index-mapping", codes(implausible_page))
        beyond_disclosed_page_count = report.replace("pp. 40-74", "p. 100", 1)
        self.assertIn("report-source-index-mapping", codes(beyond_disclosed_page_count))

        empty_valuation = replace_h2_body(
            report,
            "Reverse DCF 与估值",
            "这一段只声称公司具有合理价值，却没有给出任何 DCF 情景表、敏感性矩阵或 Reverse DCF 解释。"
            "文字长度足够且保留就地来源 SRC-Q1，但不能替代可独立阅读和复核的估值结构。",
        )
        valuation_codes = codes(empty_valuation)
        self.assertTrue(
            {"report-valuation-scenarios", "report-valuation-sensitivity", "report-valuation-reverse-dcf"}.issubset(valuation_codes)
        )

        moat_body = h2_body(report, "护城河")
        mismatched_moat_score = moat_body.replace("| 定价权 | 4.0 / 5 |", "| 定价权 | 2.0 / 5 |", 1)
        self.assertIn("report-moat-score-consistency", codes(replace_h2_body(report, "护城河", mismatched_moat_score)))
        missing_network = replace_h2_body(report, "护城河", moat_body.replace("| 网络效应 |", "| 规模优势 |", 1))
        self.assertIn("report-moat-core-coverage", codes(missing_network))

        pre_mortem = h2_body(report, "Pre-Mortem 事前验尸")
        combined = pre_mortem.replace(
            "| 失败路径 | 概率 | 影响 | 期限 | 最早预警 | 可逆性 | 管理层缓解 |",
            "| 失败路径 | 概率/影响 | 期限 | 最早预警 | 可逆性 | 管理层缓解 |",
            1,
        ).replace("|---|---|---|---|---|---|---|", "|---|---|---|---|---|---|", 1)
        combined = re.sub(
            r"(?m)^\| (.+?) \| (中|中低|低) \| (高|严重|重大) \|",
            r"| \1 | \2/\3 |",
            combined,
        )
        self.assertIn("report-pre-mortem-matrix", codes(replace_h2_body(report, "Pre-Mortem 事前验尸", combined)))

        unrelated_paths = pre_mortem
        path_replacements = {
            "核心客户因产品体验停滞而迁移，续费下降导致单位经济性失效。": "总部装修延期导致办公桌颜色未按计划更换",
            "商户侧出现更低成本替代网络，覆盖优势逐步转为固定成本负担。": "年度团建地点调整造成员工出行安排短暂变化",
            "监管限制数据使用范围，风控准确性下降并推高信用损失。": "公司食堂菜单轮换降低了午餐选择的稳定程度",
            "管理层在高估值阶段过度回购，削弱应对衰退的资产负债表弹性。": "办公用品供应商更名需要重新打印采购联系人名片",
            "新技术改变客户入口，既有品牌无法转化为下一代产品采用。": "会议室预订系统升级改变内部日历的显示颜色",
        }
        for structured_path, unrelated_path in path_replacements.items():
            unrelated_paths = unrelated_paths.replace(structured_path, unrelated_path, 1)
        self.assertIn(
            "report-pre-mortem-path-mapping",
            codes(replace_h2_body(report, "Pre-Mortem 事前验尸", unrelated_paths)),
        )
        extra_path = pre_mortem.replace(
            "\n\n| 补充诊断 |",
            "\n| 与核心风险无关的额外办公场地搬迁事件 | 低 | 中 | 1年 | 行政通知调整办公地址 | 高 | 重新安排座位与通勤支持 |\n\n| 补充诊断 |",
            1,
        )
        self.assertIn(
            "report-pre-mortem-path-mapping",
            codes(replace_h2_body(report, "Pre-Mortem 事前验尸", extra_path)),
        )

        pre_mortem_supplement_regressions = {
            "bear-case": (
                pre_mortem.replace(
                    "| 最强反方观点 | 最强悲观情形是竞争补贴、监管收紧与错误资本配置同时发生，使增长与利润率永久低于反向估值要求。 |\n",
                    "",
                    1,
                ),
                "report-pre-mortem-bear-case",
            ),
            "fragile-assumptions": (
                pre_mortem.replace(
                    "高价值客户仍愿意为可靠服务与权益组合支付溢价",
                    "高价值客户将永久拒绝任何可靠服务与权益组合",
                    1,
                ),
                "report-pre-mortem-fragile-assumptions",
            ),
            "thesis-breakers": (
                pre_mortem.replace(
                    "连续四个季度核心客户净流失并伴随单位经济性恶化",
                    "连续四个季度核心客户增长即可推翻长期结论",
                    1,
                ),
                "report-pre-mortem-thesis-breakers",
            ),
            "outcome-distinction": (
                pre_mortem.replace(
                    "| 破产路径 | 监管处罚与信用损失同时激增，流动性储备耗尽并触发债务违约，股权价值可能归零。 |\n",
                    "",
                    1,
                ),
                "report-pre-mortem-outcome-distinction",
            ),
        }
        for label, (candidate_body, expected_code) in pre_mortem_supplement_regressions.items():
            with self.subTest(label=label):
                self.assertIn(expected_code, codes(replace_h2_body(report, "Pre-Mortem 事前验尸", candidate_body)))

        bad_final_confidence = final_body.replace("| 生意可理解性 | 4.5 / 5 | 高 |", "| 生意可理解性 | 4.5 / 5 | 高中低均无法判断 |", 1)
        self.assertIn("report-final-scorecard-substance", codes(replace_h2_body(report, "最终结论", bad_final_confidence)))
        bad_moat_confidence = moat_body.replace("| 定价权 | 4.0 / 5 | 稳定 | 高 |", "| 定价权 | 4.0 / 5 | 稳定 | high-confidence-is-unknown |", 1)
        self.assertIn("report-moat-matrix-substance", codes(replace_h2_body(report, "护城河", bad_moat_confidence)))

        uncited_moat_row = moat_body.replace("稳定区间〔SRC-FY〕", "稳定区间", 1)
        self.assertIn("report-moat-matrix-substance", codes(replace_h2_body(report, "护城河", uncited_moat_row)))
        uncited_final_row = final_body.replace("直接解释〔SRC-FY〕", "直接解释", 1)
        self.assertIn("report-final-scorecard-substance", codes(replace_h2_body(report, "最终结论", uncited_final_row)))

    def test_report_visible_markdown_substance_and_canonical_headings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, _, company = make_valid_unfrozen_package(Path(temp_dir))
            report = (package / "research-report.md").read_text(encoding="utf-8")

        def codes(candidate: str, candidate_company: dict | None = None) -> set[str]:
            findings: list[Finding] = []
            validate_report(candidate_company or company, candidate, "full", findings)
            return {item.code for item in findings}

        replace_headings = (
            "身份、日期与完整度", "商业模式", "十年财务", "自由现金流与 Owner Earnings",
            "ROIC 与投入资本回报", "长期生存与十年后需求", "企业文化、管理层与资本配置",
            "回购明细", "治理、债务与红旗", "Reverse DCF 与估值", "待调查与 Open Questions",
            "领先指标与 Monitoring Indicators",
        )
        pseudo_url_report = report
        fake_body = "https://fake.example/only-citation-path-without-visible-analysis" * 3
        for heading in replace_headings:
            pseudo_url_report = replace_h2_body(pseudo_url_report, heading, fake_body)
        pseudo_codes = codes(pseudo_url_report)
        self.assertTrue({"report-section-thin", "repeated-report-section", "report-source-url"}.issubset(pseudo_codes))

        fenced_codes = codes(f"```markdown\n{report}\n```\n")
        self.assertIn("report-section-one-page-conclusion", fenced_codes)
        commented_codes = codes(f"<!--\n{report}\n-->\n")
        self.assertIn("report-section-one-page-conclusion", commented_codes)

        br_variant = report.replace("<br>", "<BR />")
        self.assertEqual(codes(br_variant), set())
        br_with_attributes = report.replace("<br>", "<br hidden>", 1)
        self.assertIn("report-raw-html", codes(br_with_attributes))
        autolink = report.replace(
            "https://example.com/investors/2025-annual-report |",
            "<https://example.com/investors/2025-annual-report> |",
            1,
        )
        self.assertEqual(codes(autolink), set())
        first_h2 = report.index("## ")
        prefix, h2_onward = report[:first_h2], report[first_h2:]
        hidden_html = prefix + "<DiV\n HIDDEN = 'false'>\n" + h2_onward + "\n</dIv>\n"
        self.assertIn("report-section-one-page-conclusion", codes(hidden_html))
        display_none = prefix + '<section STYLE="color:red; DISPLAY : none">\n' + h2_onward + "\n</section>\n"
        self.assertIn("report-section-one-page-conclusion", codes(display_none))
        template_html = prefix + "<TeMpLaTe data-kind='report'>\n" + h2_onward + "\n</tEmPlAtE>\n"
        self.assertIn("report-section-one-page-conclusion", codes(template_html))
        script_html = prefix + "<SCRIPT type='text/markdown'>\n" + h2_onward + "\n</script>\n"
        self.assertIn("report-section-one-page-conclusion", codes(script_html))
        raw_div = prefix + '<div class="report">\n' + h2_onward + "\n</div>\n"
        self.assertIn("report-raw-html", codes(raw_div))

        current_headings = (
            "一页式结论", "身份、日期与完整度", "商业模式", "十年财务", "自由现金流与 Owner Earnings",
            "ROIC 与投入资本回报", "护城河", "长期生存与十年后需求", "企业文化、管理层与资本配置",
            "回购明细", "治理、债务与红旗", "Reverse DCF 与估值", "Pre-Mortem 事前验尸",
            "待调查与 Open Questions", "领先指标与 Monitoring Indicators", "最终结论",
        )
        canonical_headings = (
            "一页式结论", "身份、数据截至日、完整度和缺失项", "商业模式与行业结构", "十年财务表和关键趋势",
            "FCF、股东调整后 FCF 与 Owner Earnings", "ROIC 与再投资跑道", "逐维护城河",
            "十年后需求与长期生存", "文化、不做清单、管理层和资本配置", "回购明细账",
            "会计、治理、负债和红旗", "估值、Reverse DCF、敏感性和情景回报", "完整 Pre-Mortem",
            "尚待调查问题", "未来跟踪的 5—10 个领先指标", "最终结论",
        )
        canonical_report = report
        for index, (current, canonical) in enumerate(zip(current_headings, canonical_headings), start=1):
            canonical_report = canonical_report.replace(f"## {current}\n", f"## {index}. {canonical}\n", 1)
        self.assertEqual(codes(canonical_report), set())

    def test_uniform_scores_and_weighted_final_moat_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, _, company = make_valid_unfrozen_package(Path(temp_dir))
            report = (package / "research-report.md").read_text(encoding="utf-8")

        def findings_for(candidate: str, candidate_company: dict) -> list[Finding]:
            findings: list[Finding] = []
            validate_report(candidate_company, candidate, "full", findings)
            return findings

        all_four_final = re.sub(
            r"(?m)^(\| [^|\n]+ \| )\d(?:\.\d+)? / 5( \|)",
            r"\g<1>4.0 / 5\2",
            h2_body(report, "最终结论"),
        )
        self.assertEqual(findings_for(replace_h2_body(report, "最终结论", all_four_final), company), [])

        uniform_company = copy.deepcopy(company)
        for item in uniform_company["moat"]:
            item["score"] = 4.0
        uniform_moat = h2_body(report, "护城河").replace("| 转换成本 | 3.5 / 5 |", "| 转换成本 | 4.0 / 5 |", 1)
        uniform_moat = uniform_moat.replace("| 网络效应 | 4.5 / 5 |", "| 网络效应 | 4.0 / 5 |", 1)
        uniform_report = replace_h2_body(report, "护城河", uniform_moat)
        self.assertEqual(findings_for(uniform_report, uniform_company), [])

        weighted_final = h2_body(uniform_report, "最终结论").replace("| 护城河 | 4.0 / 5 |", "| 护城河 | 4.5 / 5 |", 1)
        weighted_report = replace_h2_body(uniform_report, "最终结论", weighted_final)
        self.assertEqual(findings_for(weighted_report, uniform_company), [])

    def test_too_hard_report_allows_explicit_sourced_unscored_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            package, _, original_company = make_valid_unfrozen_package(Path(temp_dir))
            report = (package / "research-report.md").read_text(encoding="utf-8")
        company = copy.deepcopy(original_company)
        company["verdict"]["research_status"] = "Too Hard"
        company["moat"][0]["score"] = None
        report = report.replace("| 研究状态 | 观察名单 |", "| 研究状态 | Too Hard |")
        moat_body = h2_body(report, "护城河").replace(
            "| 定价权 | 4.0 / 5 | 稳定 | 高 | 提价后单位服务收入增长且留存仍处稳定区间〔SRC-FY〕 | 竞争者以补贴压低同类服务的有效价格〔SRC-FY〕 |",
            "| 定价权 | 无法判断 | 稳定 | 低 | 公司未披露分层提价留存，存在证据缺口待补〔SRC-FY〕 | 现有年报无法核实细分价格弹性，资料不足〔SRC-FY〕 |",
            1,
        )
        report = replace_h2_body(report, "护城河", moat_body)
        final_body = h2_body(report, "最终结论").replace(
            "| 生意可理解性 | 4.5 / 5 | 高 | 收费方、客户价值和网络反馈机制均可直接解释〔SRC-FY〕 | 信用与服务收入之间仍存在复杂交叉补贴〔SRC-FY〕 |",
            "| 生意可理解性 | 无法判断 | 低 | 分部收费方披露仍有证据缺口待补〔SRC-FY〕 | 现有年报无法核实全部交叉补贴，资料不足〔SRC-FY〕 |",
            1,
        )
        report = replace_h2_body(report, "最终结论", final_body)
        findings: list[Finding] = []
        validate_report(company, report, "full", findings)
        self.assertEqual(findings, [])

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
