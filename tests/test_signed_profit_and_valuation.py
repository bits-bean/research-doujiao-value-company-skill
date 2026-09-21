#!/usr/bin/env python3
"""Regression boundaries for signed deductions, mixed revenues and disclosed bridges."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import test_semantic_gates as semantic
from package_fixture import make_valid_unfrozen_package
from validate_research_package import (
    validate_sankey, validate_calculations, validate_classification_and_industry_metrics,
    validate_incremental_roic_unavailability, validate_report,
    validate_schema, validate_schema_keywords,
)


class SignedProfitAndValuationTests(unittest.TestCase):
    def test_exclusive_maximum_checks_negative_zero_and_positive_boundaries(self):
        schema = {"type": "number", "exclusiveMaximum": 0}
        self.assertFalse(validate_schema_keywords(schema))
        for value in (-0.01, 0, 0.01):
            findings = validate_schema(value, schema, schema, "value")
            self.assertEqual("schema-exclusive-maximum" in {f.code for f in findings}, value >= 0)

    def fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            package, _, company = make_valid_unfrozen_package(Path(directory))
            calculations = json.loads((package / "calculation-ledger.json").read_text())
            report = (package / "research-report.md").read_text()
        return company, calculations, report

    def signed_case(self):
        company, calculations, known = semantic.SemanticGateTests().make_signed_sankey_case()
        company["meta"]["schema_version"] = "2.4.0"
        node = next(n for n in company["income_statement_sankey"]["nodes"] if n["id"] == "nonoperating_expense")
        node.update(category="profit_deduction", statement_value=-10_000_000)
        next(n for n in calculations["income_statement_sankey"]["disclosed_line_items"] if n["node_id"] == node["id"])["value"] = -10_000_000
        calculation = next(c for c in calculations["calculations"] if c["id"] == "CALC-SIGNED-TO-PRETAX")
        calculation["formula"] = "operating_profit + nonoperating_expense"
        calculation["inputs"]["nonoperating_expense"] = -10_000_000
        return company, calculations, known

    def sankey_codes(self, company, calculations, known):
        findings = []
        validate_sankey(company, findings, calculations, known)
        validate_calculations(calculations, company, known, "incremental", findings)
        return {finding.code for finding in findings}

    def test_negative_profit_line_preserves_source_sign_and_positive_geometry(self):
        company, calculations, known = self.signed_case()
        self.assertFalse(self.sankey_codes(company, calculations, known))
        for version in ("2.0.0", "2.1.0", "2.2.0", "2.3.0"):
            old = copy.deepcopy(company)
            old["meta"]["schema_version"] = version
            self.assertIn("sankey-role-version", self.sankey_codes(old, calculations, known))

    def test_profit_deduction_rejects_wrong_sign_parent_direction_and_forged_input(self):
        company, calculations, known = self.signed_case()
        for sign in (0, 10_000_000):
            candidate = copy.deepcopy(company)
            next(n for n in candidate["income_statement_sankey"]["nodes"] if n["id"] == "nonoperating_expense")["statement_value"] = sign
            self.assertIn("sankey-signed-role", self.sankey_codes(candidate, calculations, known))
        for parent in ("total_revenue", "positive_costs", "pretax_profit"):
            candidate = copy.deepcopy(company)
            next(e for e in candidate["income_statement_sankey"]["links"] if e["target"] == "nonoperating_expense")["source"] = parent
            self.assertIn("sankey-profit-deduction", self.sankey_codes(candidate, calculations, known))
        candidate = copy.deepcopy(company)
        edge = next(e for e in candidate["income_statement_sankey"]["links"] if e["target"] == "nonoperating_expense")
        edge["source"], edge["target"] = edge["target"], edge["source"]
        self.assertIn("sankey-profit-deduction", self.sankey_codes(candidate, calculations, known))
        ledger = copy.deepcopy(calculations)
        calc = next(c for c in ledger["calculations"] if c["id"] == "CALC-SIGNED-TO-PRETAX")
        calc["formula"] = "operating_profit - expense_magnitude"
        calc["inputs"] = {"operating_profit": 125_000_000, "expense_magnitude": 10_000_000}
        self.assertIn("sankey-profit-deduction-calculation-inputs", self.sankey_codes(company, ledger, known))
        candidate = copy.deepcopy(company)
        next(e for e in candidate["income_statement_sankey"]["links"] if e["source"] == "operating_profit" and e["target"] == "pretax_profit")["value"] += 0.02
        self.assertIn("sankey-node-value-mismatch", self.sankey_codes(candidate, calculations, known))

    def test_mixed_revenue_hierarchy_requires_unique_conserving_paths_and_24(self):
        company, calculations, known = self.signed_case()
        graph = company["income_statement_sankey"]
        graph["nodes"].append({"id": "products", "label": "披露产品收入小计", "category": "revenue_subtotal", "value": 190_000_000, "statement_value": 190_000_000})
        next(e for e in graph["links"] if e["source"] == "product_revenue")["target"] = "products"
        graph["links"].append({"source": "products", "target": "total_revenue", "value": 190_000_000})
        calculations["income_statement_sankey"]["disclosed_line_items"].append({"node_id": "products", "value": 190_000_000, "source_ids": ["SRC-FY"], "location": "Annual report product revenue note p. 60"})
        calculations["income_statement_sankey"]["calculated_links"].append({"source": "products", "target": "total_revenue", "calculation_id": "CALC-PRODUCTS-CONTINUATION"})
        calculations["calculations"].append({"id": "CALC-PRODUCTS-CONTINUATION", "metric": "custom", "sankey_source": "products", "sankey_target": "total_revenue", "period": "FY2025", "formula": "product_revenue + 0", "inputs": {"product_revenue": 190_000_000}, "result": 190_000_000, "review_method": "逐项核对产品来源及收入小计，复算进入总收入的金额，确保每个原始来源仅计量一次。", "source_ids": ["SRC-FY"]})
        self.assertFalse(self.sankey_codes(company, calculations, known))
        old = copy.deepcopy(company)
        old["meta"]["schema_version"] = "2.3.0"
        self.assertIn("sankey-revenue-chain", self.sankey_codes(old, calculations, known))
        graph["links"].append({"source": "product_revenue", "target": "total_revenue", "value": 190_000_000})
        self.assertIn("sankey-revenue-chain", self.sankey_codes(company, calculations, known))

    def bridge_case(self):
        company, calculations, report = self.fixture()
        rows = []
        for record in calculations["calculations"]:
            if record.get("valuation_role") != "equity_value_bridge":
                continue
            record["inputs"].update(nonoperating_securities=20_000_000, nonoperating_assets=5_000_000, minority_interests=3_000_000, preferred_equity=2_000_000)
            record["formula"] += " + nonoperating_securities + nonoperating_assets - minority_interests - preferred_equity"
            record["result"] += 20_000_000
            record["per_share"] = record["result"] / record["diluted_shares"]
            kind = record["valuation_scenario"]
            label = {"bear": "悲观", "base": "基准", "bull": "乐观"}[kind]
            next(s for s in company["valuation"]["dcf_scenarios"] if s["name"] == label)["fair_value_per_share"] = record["per_share"]
            i = record["inputs"]
            row = [label] + [f"{v / 1e8:.8f}" for v in (i["explicit_period_present_value"], i["terminal_present_value"], i["net_debt"], 20_000_000, 5_000_000, 3_000_000, 2_000_000, record["result"], record["diluted_shares"])] + [f"{record['per_share']:.8f}"]
            rows.append("| " + " | ".join(row) + " |")
        lines = report.splitlines()
        start = next(n for n, line in enumerate(lines) if line.startswith("|") and "显性期现金流现值" in line)
        stop = start + 1
        while stop < len(lines) and lines[stop].startswith("|"):
            stop += 1
        headers = "| 情景 | 显性期现金流现值（亿美元） | 终值现值（亿美元） | 净债务调整（亿美元） | 加回非经营证券（亿美元） | 加回其他非经营资产（亿美元） | 扣减少数股东权益（亿美元） | 扣减优先股权益（亿美元） | 股权价值（亿美元） | 稀释后股数（亿股） | 每股价值（美元/股） |"
        lines[start:stop] = [headers, "|" + "---|" * 11] + rows
        return company, calculations, "\n".join(lines)

    def report_codes(self, company, calculations, report):
        findings = []
        validate_report(company, report, "full", findings, calculations)
        return {finding.code for finding in findings}

    def test_value_bridge_accepts_separately_bound_adjustments_and_rejects_omissions(self):
        company, calculations, report = self.bridge_case()
        self.assertNotIn("report-valuation-value-bridge", self.report_codes(company, calculations, report))
        for old, new in (("加回非经营证券", "未识别资产"), ("扣减少数股东权益", "未经绑定扣项")):
            self.assertIn("report-valuation-value-bridge", self.report_codes(company, calculations, report.replace(old, new)))
        for mutation in ("sign", "unknown", "net_debt", "formula"):
            ledger = copy.deepcopy(calculations)
            record = next(c for c in ledger["calculations"] if c.get("valuation_role") == "equity_value_bridge")
            if mutation == "sign": record["inputs"]["nonoperating_securities"] *= -1
            elif mutation == "unknown": record["inputs"]["unexplained_asset"] = 1
            elif mutation == "net_debt": record["inputs"]["net_debt"] -= 20_000_000
            else: record["formula"] = "explicit_period_present_value + terminal_present_value - net_debt"
            self.assertIn("report-valuation-value-bridge", self.report_codes(company, ledger, report))

    def test_reverse_margin_semantics_precede_revenue_path_context(self):
        company, calculations, report = self.fixture()
        company["valuation"]["reverse_dcf"] = {"constant_cash_flow_growth_required": 0.07, "base_revenue_path_required_operating_margin": 0.22}
        report = report.replace("资本再投资率", "基准收入路径经营利润率")
        self.assertNotIn("report-valuation-reverse-dcf", self.report_codes(company, calculations, report))
        company["valuation"]["reverse_dcf"]["base_revenue_path_required_operating_margin"] = 0.40
        self.assertIn("report-valuation-reverse-dcf", self.report_codes(company, calculations, report))


class IncrementalRoicUnavailabilityTests(unittest.TestCase):
    def fixture(self):
        company = {
            "sources": [{"id": "FY", "source_type": "annual_report"}],
            "classification": {"sector": "technology", "accounting_profile": "standard_corporate", "returns_profile": "standard_roic", "source_ids": ["FY"]},
            "financials": [{"period": f"FY{year}", "period_type": "FY", "roe": 0.2, "roic": 0.2, "incremental_roic": None} for year in (2023, 2024, 2025)],
            "industry_metrics": [],
        }
        calculations = {"calculations": [], "incremental_roic_windows": []}
        for year in (2023, 2024, 2025):
            for years in (3, 5):
                ids = {}
                for kind, start, end in (("nopat", 25_000_000, 30_000_000), ("invested_capital", 150_000_000, 140_000_000)):
                    ids[kind] = f"CALC-{kind}-{year}-{years}"
                    calculations["calculations"].append({"id": ids[kind], "metric": "custom", "period": f"FY{year}", "formula": f"ending_{kind} - beginning_{kind}", "inputs": {f"beginning_{kind}": start, f"ending_{kind}": end}, "result": end-start, "source_ids": ["FY"]})
                calculations["incremental_roic_windows"].append({"period": f"FY{year}", "start_period": f"FY{year-years}", "window_years": years, "status": "unavailable", "reason_code": "non_positive_invested_capital_change", "capital_basis": "统一使用普通股权益加有息债务减现金及现金等价物，保持窗口两端定义一致。", "economic_reason": "回购和资本分配使资产负债表投入资本收缩，负的增量分母无法衡量新增项目回报。", "delta_nopat_calculation_id": ids["nopat"], "delta_invested_capital_calculation_id": ids["invested_capital"], "source_ids": ["FY"]})
                company["industry_metrics"].append({"period": f"FY{year}", "code": f"incremental_roic_{years}y", "label": f"{years}年增量资本非正，回报不适用", "value": None, "value_type": "ratio", "source_ids": ["FY"]})
        return company, calculations

    def test_complete_three_and_five_year_evidence_can_satisfy_three_fy_coverage(self):
        company, calculations = self.fixture()
        findings = []
        self.assertEqual(validate_incremental_roic_unavailability(company, calculations, findings), {"FY2023", "FY2024", "FY2025"})
        self.assertFalse(findings)
        validate_classification_and_industry_metrics(company, "完整披露滚动增量投入资本为负的经济原因。", "full", findings, calculations)
        self.assertNotIn("returns-chart-coverage", {f.code for f in findings})
        calculations["incremental_roic_windows"].pop()
        findings = []
        validate_classification_and_industry_metrics(company, "完整披露滚动增量投入资本为负的经济原因。", "full", findings, calculations)
        self.assertIn("returns-chart-coverage", {f.code for f in findings})

    def test_missing_data_generic_excuses_positive_denominator_and_bad_math_fail(self):
        for mutation in ("missing_inputs", "positive", "bad_math", "no_official_source", "wrong_year", "generic", "missing_metric", "duplicate", "malformed"):
            company, calculations = self.fixture()
            window = calculations["incremental_roic_windows"][0]
            calc = calculations["calculations"][1]
            if mutation == "missing_inputs": del calc["inputs"]["beginning_invested_capital"]
            elif mutation == "positive":
                calc["inputs"]["ending_invested_capital"] = 160_000_000
                calc["result"] = 10_000_000
            elif mutation == "bad_math": calc["result"] += 0.02
            elif mutation == "no_official_source": company["sources"][0]["source_type"] = "third_party"
            elif mutation == "wrong_year": window["start_period"] = "FY2021"
            elif mutation == "generic": window["economic_reason"] = "数据暂不可得"
            elif mutation == "missing_metric": company["industry_metrics"].pop(0)
            elif mutation == "duplicate": calculations["incremental_roic_windows"].append(copy.deepcopy(window))
            else: window["window_years"] = []
            findings = []
            validate_incremental_roic_unavailability(company, calculations, findings)
            self.assertIn("incremental-roic-unavailability", {f.code for f in findings}, mutation)


if __name__ == "__main__":
    unittest.main()
