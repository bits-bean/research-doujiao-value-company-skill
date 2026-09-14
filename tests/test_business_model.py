"""Company-specific actor graphs reject fabricated generic or broken handoffs."""
from pathlib import Path
import copy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from package_fixture import make_business_model_fixture
from validate_research_process import validate_business_model


class BusinessModelTests(unittest.TestCase):
    def setUp(self):
        self.company = {"meta": {"company_name_cn": "测试支付网络", "company_name_en": "Test Payment Network", "ticker": "TPN", "exchange": "TEST"}, "income_statement_sankey": {"fiscal_year": "FY2025"}}
        self.graph = make_business_model_fixture(self.company)

    def codes(self, graph=None):
        return {x.code for x in validate_business_model(self.graph if graph is None else graph, self.company, {"SRC-FY"})}

    def test_accepts_actual_variable_actor_graph_without_changing_inputs(self):
        before = copy.deepcopy(self.graph)
        self.assertEqual(self.codes(), set())
        self.assertEqual(self.graph, before)
        actor = {**self.graph["actors"][1], "id": "retail-merchants", "label": "线下受理商户", "label_en": "In-store accepting merchants", "illustration": "merchant"}
        self.graph["actors"].append(actor)
        self.graph["flows"].append({**self.graph["flows"][0], "id": "merchant-fee", "source": actor["id"], "label": "商户受理手续费", "label_en": "Merchant acceptance fees"})
        self.assertEqual(self.codes(), set())

    def test_rejects_generic_roles_even_when_the_graph_is_valid(self):
        for label in ["客户", "产品与渠道", "生态伙伴", "合作伙伴", "公司", "Customers", "Partners"]:
            with self.subTest(label=label):
                graph = copy.deepcopy(self.graph)
                graph["actors"][1]["label"] = label
                self.assertIn("business-model-generic-label", self.codes(graph))

    def test_rejects_foreign_identity_stale_period_and_unknown_sources(self):
        self.graph["company_identity"]["ticker"] = "OTHER"
        self.graph["period"] = "FY2024"
        self.graph["flows"][0]["source_ids"] = ["SRC-MISSING"]
        self.assertTrue({"business-model-identity", "business-model-period", "business-model-sources"}.issubset(self.codes()))

    def test_rejects_wrong_endpoints_duplicate_ids_and_disconnected_actor(self):
        self.graph["flows"][0]["target"] = "unresearched-supplier"
        self.graph["flows"][1]["id"] = self.graph["flows"][0]["id"]
        self.graph["actors"].append({**self.graph["actors"][1], "id": "unconnected"})
        self.assertTrue({"business-model-endpoints", "business-model-flow-id", "business-model-disconnected"}.issubset(self.codes()))

    def test_malformed_values_produce_findings_not_exceptions(self):
        self.graph["actors"][1]["id"] = ["bad"]
        self.graph["actors"][1]["source_ids"] = [{"bad": True}]
        self.graph["flows"][0]["source"] = ["bad"]
        self.assertTrue(self.codes())

    def test_company_asset_cannot_be_used_for_counterparty(self):
        self.graph["actors"][1]["illustration"] = "company"
        self.assertIn("business-model-company-illustration", self.codes())
        self.graph["actors"][1]["illustration"] = "made-up-icon"
        self.assertIn("business-model-illustration", self.codes())

    def test_missing_handoff_blocks_new_research_but_remains_auditable(self):
        self.assertEqual(validate_business_model(None, self.company, set())[0].severity, "error")
        self.assertEqual(validate_business_model(None, self.company, set(), "audit")[0].severity, "warning")


if __name__ == "__main__":
    unittest.main()
