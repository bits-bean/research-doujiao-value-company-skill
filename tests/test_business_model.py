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

    def test_text_participant_preserves_roles_without_a_matching_illustration(self):
        self.graph["actors"][1].update(
            label="专利许可使用方", label_en="Patent licensees", illustration="participant",
        )
        self.assertEqual(self.codes(), set())
        self.graph["actors"][0]["illustration"] = "participant"
        self.assertIn("business-model-company-illustration", self.codes())
        self.graph["actors"][1]["illustration"] = "unregistered-licensee-icon"
        self.assertIn("business-model-illustration", self.codes())

    def test_missing_handoff_blocks_new_research_but_remains_auditable(self):
        self.assertEqual(validate_business_model(None, self.company, set())[0].severity, "error")
        self.assertEqual(validate_business_model(None, self.company, set(), "audit")[0].severity, "warning")

    def brand(self, asset_id="sample-search", **changes):
        return {"asset_id": asset_id, "brand_name": "示例搜索", "brand_name_en": "Sample Search", "source_ids": ["SRC-FY"], **changes}

    def test_optional_brands_preserve_legacy_fallback_and_multiple_role_identities(self):
        self.graph["actors"][1]["official_logos"] = []
        self.assertEqual(self.codes(), set())
        self.graph["actors"][1]["official_logos"] = [self.brand(), self.brand("sample-video", brand_name="示例视频", brand_name_en="Sample Video")]
        before = copy.deepcopy(self.graph)
        self.assertEqual(self.codes(), set())
        self.assertEqual(self.graph, before)
        del self.graph["actors"][1]["illustration"]
        self.assertIn("business-model-illustration", self.codes())

    def test_brand_references_cannot_replace_the_canonical_company_identity(self):
        self.graph["actors"][0]["official_logos"] = [self.brand()]
        self.assertIn("business-model-company-official-logos", self.codes())

    def test_brand_asset_keys_reject_urls_paths_and_duplicate_assets(self):
        for value in ["https://example.test/logo.svg", "../logo", "/logo.svg", "logo.svg", "Uppercase", "a" * 65, ["bad"]]:
            with self.subTest(value=value):
                self.graph["actors"][1]["official_logos"] = [self.brand(value)]
                self.assertIn("business-model-official-logo-id", self.codes())
        self.graph["actors"][1]["official_logos"] = [self.brand(), self.brand()]
        self.assertIn("business-model-official-logo-id", self.codes())

    def test_brands_require_bilingual_identity_and_resolved_business_evidence(self):
        for key in ["brand_name", "brand_name_en"]:
            self.graph["actors"][1]["official_logos"] = [self.brand(**{key: " "})]
            self.assertIn("business-model-official-logo-brand", self.codes())
        for sources in [[], ["SRC-MISSING"], ["SRC-FY", "SRC-FY"], [{"bad": True}]]:
            with self.subTest(sources=sources):
                self.graph["actors"][1]["official_logos"] = [self.brand(source_ids=sources)]
                self.assertIn("business-model-sources", self.codes())

    def test_brand_metadata_does_not_embed_assets_or_skip_required_fields(self):
        for extra in [{"source_url": "https://example.test/logo.svg"}, {"path": "assets/logo.svg"}, {"data": "data:image/svg+xml;base64,PHN2Zz4="}]:
            self.graph["actors"][1]["official_logos"] = [self.brand(**extra)]
            self.assertIn("business-model-official-logo", self.codes())
        for key in ["asset_id", "brand_name", "brand_name_en", "source_ids"]:
            value = self.brand()
            del value[key]
            self.graph["actors"][1]["official_logos"] = [value]
            self.assertIn("business-model-official-logo", self.codes())

    def test_malformed_brand_collections_return_findings_without_throwing(self):
        for value in [None, "sample-search", {}, 1]:
            self.graph["actors"][1]["official_logos"] = value
            self.assertIn("business-model-official-logos", self.codes())
        for value in [None, "sample-search", [], 1]:
            self.graph["actors"][1]["official_logos"] = [value]
            self.assertIn("business-model-official-logo", self.codes())


if __name__ == "__main__":
    unittest.main()
