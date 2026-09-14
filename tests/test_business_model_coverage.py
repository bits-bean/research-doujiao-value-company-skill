"""Relationship inventories detect omission without prescribing an industry graph."""
from pathlib import Path
import copy
import hashlib
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from package_fixture import make_business_model_coverage_fixture, make_business_model_fixture
from validate_research_process import (
    canonical_business_model_sha256,
    validate_business_model,
    validate_business_model_coverage,
    validate_research_process,
    LEDGER_ROOT_KEYS,
    PROTOCOL_FINGERPRINT_KEYS,
)


class BusinessModelCoverageTests(unittest.TestCase):
    def setUp(self):
        self.company = {"meta": {"company_name_cn": "测试支付网络", "company_name_en": "Test Payment Network", "ticker": "TPN", "exchange": "TEST"}, "income_statement_sankey": {"fiscal_year": "FY2025"}}
        self.graph = make_business_model_fixture(self.company)
        self.coverage = make_business_model_coverage_fixture(self.graph)
        self.passes = [
            {"id": "PASS-PRIMARY", "role": "primary_research", "actor_id": "primary", "execution": "primary_context", "status": "completed", "source_ids_accessed": ["SRC-FY"]},
            {"id": "PASS-CHALLENGE", "role": "adversarial_review", "actor_id": "challenger", "execution": "isolated_agent", "status": "completed", "source_ids_accessed": ["SRC-FY"]},
            {"id": "PASS-AUDIT", "role": "source_audit", "actor_id": "auditor", "execution": "isolated_context", "status": "completed", "source_ids_accessed": ["SRC-FY"]},
        ]

    def issues(self, mode="full"):
        return validate_business_model_coverage(self.coverage, self.graph, {"SRC-FY"}, self.passes, mode)

    def codes(self, mode="full"):
        return {issue.code for issue in self.issues(mode)}

    def rebind(self):
        self.coverage["review"]["graph_sha256"] = canonical_business_model_sha256(self.graph)

    def add_actor(self, actor_id="merchants", candidate_id="accepting-merchants"):
        self.graph["actors"].append({"id": actor_id, "label": "受理商户", "label_en": "Accepting merchants", "detail": "受理卡片并向会员交付商品", "detail_en": "Accept cards and deliver goods to members", "illustration": "merchant", "source_ids": ["SRC-FY"]})
        self.coverage["participants"].append({"id": candidate_id, "label": "受理商户", "disposition": "included", "actor_id": actor_id, "reason": "业务章节明确描述商户与会员之间的交易。", "source_ids": ["SRC-FY"], "source_locations": {"SRC-FY": "Business, Merchant acceptance, p. 5"}})

    def add_flow(self, flow_id, source, target, candidate_source, candidate_target, exchange_type, kind="value"):
        self.graph["flows"].append({"id": flow_id, "source": source, "target": target, "label": exchange_type, "label_en": "Sourced relationship", "exchange_type": exchange_type, "kind": kind, "source_ids": ["SRC-FY"]})
        self.coverage["relationships"].append({"id": flow_id + "-evidence", "source": candidate_source, "target": candidate_target, "exchange_type": exchange_type, "disposition": "drawn", "flow_id": flow_id, "reason": "具体业务安排由来源章节支持，已核对履约方向。", "source_ids": ["SRC-FY"], "source_locations": {"SRC-FY": "Business, Merchant acceptance, p. 5"}})

    def test_accepts_no_data_feedback_and_does_not_mutate_inputs(self):
        before = copy.deepcopy((self.graph, self.coverage, self.passes))
        self.assertEqual(self.issues(), [])
        self.assertEqual((self.graph, self.coverage, self.passes), before)
        self.assertNotIn("data", {flow["kind"] for flow in self.graph["flows"]})

    def test_removed_drawn_edge_fails_even_when_remaining_graph_is_connected(self):
        self.graph["flows"].pop()
        self.rebind()
        self.assertEqual(validate_business_model(self.graph, self.company, {"SRC-FY"}), [])
        self.assertIn("business-model-coverage-relationship-flow", self.codes())

    def test_missing_either_counterparty_data_edge_is_detected(self):
        self.add_actor()
        self.add_flow("member-data", "cardholders", "company", "fee-paying-members", "network-operator", "消费与还款记录", "data")
        self.add_flow("merchant-data", "merchants", "company", "accepting-merchants", "network-operator", "交易与受理记录", "data")
        self.add_flow("goods", "merchants", "cardholders", "accepting-merchants", "fee-paying-members", "商品交付")
        complete = copy.deepcopy(self.graph)
        for flow_id in ("member-data", "merchant-data"):
            with self.subTest(flow_id=flow_id):
                self.graph = copy.deepcopy(complete)
                self.graph["flows"] = [flow for flow in self.graph["flows"] if flow["id"] != flow_id]
                self.rebind()
                self.assertEqual(validate_business_model(self.graph, self.company, {"SRC-FY"}), [])
                self.assertIn("business-model-coverage-relationship-flow", self.codes())

    def test_missing_participant_or_relationship_inventory_entry_is_detected(self):
        self.coverage["participants"].pop()
        self.assertIn("business-model-coverage-actor-omission", self.codes())
        self.coverage = make_business_model_coverage_fixture(self.graph)
        self.coverage["relationships"].pop()
        self.assertIn("business-model-coverage-flow-omission", self.codes())

    def test_removed_actor_still_referenced_by_inventory_is_detected(self):
        self.graph["actors"].pop()
        self.rebind()
        self.assertIn("business-model-coverage-participant-actor", self.codes())

    def test_reversed_direction_and_changed_exchange_type_are_detected(self):
        flow = self.graph["flows"][0]
        flow["source"], flow["target"] = flow["target"], flow["source"]
        self.rebind()
        self.assertIn("business-model-coverage-relationship-direction", self.codes())
        flow["source"], flow["target"] = flow["target"], flow["source"]
        flow["exchange_type"] = "承保责任"
        self.rebind()
        self.assertIn("business-model-coverage-relationship-type", self.codes())

    def test_open_types_peer_trades_and_parallel_relations_are_accepted(self):
        self.add_actor()
        self.add_flow("goods", "merchants", "cardholders", "accepting-merchants", "fee-paying-members", "商品交付")
        self.add_flow("retail-payment", "cardholders", "merchants", "fee-paying-members", "accepting-merchants", "零售货款", "money")
        for index, exchange_type in enumerate(("许可使用权", "承保责任", "风险承担", "售后履约义务", "设备回收与再利用")):
            self.add_flow(f"special-{index}", "company", "cardholders", "network-operator", "fee-paying-members", exchange_type)
        self.rebind()
        self.assertEqual(validate_business_model(self.graph, self.company, {"SRC-FY"}), [])
        self.assertEqual(self.issues(), [])

    def test_legacy_display_groups_cannot_replace_actual_exchange_types(self):
        for exchange_type in ("money", "value", "data", "资金", "价值", "数据", " VALUE "):
            with self.subTest(exchange_type=exchange_type):
                self.graph["flows"][0]["exchange_type"] = exchange_type
                self.coverage["relationships"][0]["exchange_type"] = exchange_type
                self.rebind()
                self.assertIn("business-model-exchange-type", {issue.code for issue in validate_business_model(self.graph, self.company, {"SRC-FY"})})
                self.assertIn("business-model-coverage-exchange-type", self.codes())

    def test_excluded_candidates_and_reasoned_aggregation_are_accepted(self):
        self.coverage["participants"].append({"id": "small-rewards-vendor", "label": "次要权益供应商", "disposition": "excluded", "actor_id": None, "reason": "规模次要，不改变当前会员收费机制，保留候选及排除依据。", "source_ids": ["SRC-FY"], "source_locations": {"SRC-FY": "Business, Other benefits, p. 6"}})
        self.coverage["relationships"].append({"id": "minor-supply", "source": "small-rewards-vendor", "target": "network-operator", "exchange_type": "次要权益供应", "disposition": "excluded", "flow_id": None, "reason": "该次要供应安排不影响主要价值机制，省略绘图但保留来源。", "source_ids": ["SRC-FY"], "source_locations": {"SRC-FY": "Business, Other benefits, p. 6"}})
        self.coverage["participants"][1]["disposition"] = "aggregated"
        self.coverage["participants"][1]["reason"] = "不同级别会员的收费与服务方向相同，按同一种交易身份归并。"
        self.assertEqual(self.issues(), [])

    def test_unresolved_candidates_and_exclusions_without_reasons_block(self):
        for collection, mapping in (("participants", "actor_id"), ("relationships", "flow_id")):
            with self.subTest(collection=collection):
                self.coverage = make_business_model_coverage_fixture(self.graph)
                item = self.coverage[collection][0]
                item.update(disposition="unresolved", **{mapping: None})
                self.assertTrue(any("unresolved" in code for code in self.codes()))
                self.assertTrue(all(issue.severity == "error" for issue in self.issues("audit")))
                item.update(disposition="excluded", reason=" ")
                self.assertTrue(self.codes())

    def test_excluded_records_require_explicit_null_mapping(self):
        for collection, mapping in (("participants", "actor_id"), ("relationships", "flow_id")):
            with self.subTest(collection=collection):
                self.coverage = make_business_model_coverage_fixture(self.graph)
                self.coverage[collection][0]["disposition"] = "excluded"
                self.assertTrue(self.codes())
                del self.coverage[collection][0][mapping]
                self.assertTrue(self.codes())

    def test_reviewer_is_bound_to_entire_graph_not_just_flow_ids(self):
        self.graph["actors"][1]["detail"] = "修改了参与者业务范围"
        self.assertIn("business-model-coverage-graph-hash", self.codes())
        self.rebind()
        self.assertEqual(self.codes(), set())
        reordered = dict(reversed(list(self.graph.items())))
        expected = hashlib.sha256(json.dumps(self.graph, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        self.assertEqual(canonical_business_model_sha256(reordered), expected)

    def test_fake_primary_failed_and_unisolated_review_passes_are_rejected(self):
        for pass_id in ("PASS-MISSING", "PASS-PRIMARY"):
            self.coverage["review"]["pass_id"] = pass_id
            self.assertIn("business-model-coverage-review-pass", self.codes())
        self.coverage["review"]["pass_id"] = "PASS-CHALLENGE"
        original = copy.deepcopy(self.passes[1])
        for key, value in (("status", "failed"), ("execution", "primary_context"), ("actor_id", "primary"), ("role", "synthesis")):
            with self.subTest(key=key):
                self.passes[1] = {**original, key: value}
                self.assertIn("business-model-coverage-review-pass", self.codes())
        self.passes[1] = original
        self.coverage["review"]["pass_id"] = "PASS-AUDIT"
        self.assertEqual(self.issues(), [])

    def test_review_cannot_claim_unaccessed_sources_or_duplicate_pass_identity(self):
        self.passes[1]["source_ids_accessed"] = []
        self.assertIn("business-model-coverage-review-sources", self.codes())
        self.passes.append(copy.deepcopy(self.passes[1]))
        self.assertIn("business-model-coverage-review-pass", self.codes())

    def test_unknown_sources_and_imprecise_source_location_shape_are_rejected(self):
        for collection in ("participants", "relationships", "value_logic"):
            for value in ([], ["SRC-MISSING"], ["SRC-FY", "SRC-FY"], [["SRC-FY"]]):
                with self.subTest(collection=collection, value=value):
                    self.coverage = make_business_model_coverage_fixture(self.graph)
                    self.coverage[collection][0]["source_ids"] = value
                    self.assertIn("business-model-coverage-sources", self.codes())
        for collection in ("participants", "relationships"):
            for value in (None, {}, {"SRC-FY": " "}, {"SRC-FY": "p. 4", "SRC-OTHER": "p. 5"}, "p. 4"):
                with self.subTest(collection=collection, value=value):
                    self.coverage = make_business_model_coverage_fixture(self.graph)
                    self.coverage[collection][0]["source_locations"] = value
                    self.assertIn("business-model-coverage-source-locations", self.codes())

    def test_unknown_candidate_flow_and_value_logic_references_are_rejected(self):
        self.coverage["relationships"][0]["source"] = "unknown-participant"
        self.coverage["relationships"][1]["flow_id"] = "unknown-flow"
        self.coverage["value_logic"][0]["flow_ids"] = ["unknown-flow"]
        self.assertTrue({"business-model-coverage-relationship-endpoints", "business-model-coverage-relationship-flow", "business-model-coverage-value-flows"}.issubset(self.codes()))

    def test_value_logic_requires_all_three_unique_stages_and_real_flows(self):
        self.coverage["value_logic"][0]["stage"] = "delivery"
        self.assertIn("business-model-coverage-value-stage-coverage", self.codes())
        self.coverage["value_logic"][0]["flow_ids"] = []
        self.assertIn("business-model-coverage-value-flows", self.codes())

    def test_only_absent_historical_coverage_and_types_receive_warnings(self):
        for mode in ("full", "incremental", "audit"):
            issues = validate_business_model_coverage(None, self.graph, {"SRC-FY"}, self.passes, mode, declared=False)
            self.assertEqual(issues[0].severity, "warning" if mode == "audit" else "error")
            malformed = validate_business_model_coverage(None, self.graph, {"SRC-FY"}, self.passes, mode)
            self.assertEqual(malformed[0].severity, "error")
        del self.graph["flows"][0]["exchange_type"]
        for mode in ("full", "incremental", "audit"):
            issues = validate_business_model(self.graph, self.company, {"SRC-FY"}, mode)
            self.assertEqual(issues[0].severity, "warning" if mode == "audit" else "error")
        for value in (None, " ", [], {}):
            self.graph["flows"][0]["exchange_type"] = value
            self.assertEqual(validate_business_model(self.graph, self.company, {"SRC-FY"}, "audit")[0].severity, "error")

    def test_process_validator_routes_presence_and_review_passes_to_coverage_gate(self):
        # Isolate unrelated financial gates to check the production orchestration
        # actually invokes coverage and preserves missing versus malformed state.
        evidence = {key: {} for key in LEDGER_ROOT_KEYS}
        evidence.update(ledger_version="2.0", claims=[], business_model=self.graph, business_model_coverage=self.coverage)
        fingerprint = {key: "locked-test-value" for key in PROTOCOL_FINGERPRINT_KEYS}
        self.graph["flows"].pop()
        self.rebind()
        with patch("validate_research_process._validate_run", return_value=("full", "standard", self.passes)):
            issues = validate_research_process(evidence, self.company, {}, {"SRC-FY": {}}, "full", fingerprint)
            self.assertIn("business-model-coverage-relationship-flow", {issue.code for issue in issues})
            del evidence["business_model_coverage"]
            for mode in ("full", "incremental", "audit"):
                issues = validate_research_process(evidence, self.company, {}, {"SRC-FY": {}}, mode, fingerprint)
                missing = [issue for issue in issues if issue.code == "business-model-coverage-missing"]
                self.assertEqual(len(missing), 1)
                self.assertEqual(missing[0].severity, "warning" if mode == "audit" else "error")
            evidence["business_model_coverage"] = None
            issues = validate_research_process(evidence, self.company, {}, {"SRC-FY": {}}, "audit", fingerprint)
            self.assertIn("business-model-coverage-shape", {issue.code for issue in issues})

    def test_declared_coverage_cannot_hide_behind_legacy_claims_only_audit(self):
        fingerprint = {key: "locked-test-value" for key in PROTOCOL_FINGERPRINT_KEYS}
        issues = validate_research_process({"claims": [], "business_model_coverage": None}, self.company, {}, {}, "audit", fingerprint)
        self.assertTrue(any(issue.severity == "error" for issue in issues))
        self.assertNotIn("legacy-evidence-process-unverifiable", {issue.code for issue in issues})

    def test_malformed_values_produce_findings_without_exceptions(self):
        for collection in ("participants", "relationships", "value_logic"):
            for value in (None, "wrong", {}, [None, [], "bad"]):
                with self.subTest(collection=collection, value=value):
                    self.coverage = make_business_model_coverage_fixture(self.graph)
                    self.coverage[collection] = value
                    self.assertTrue(self.codes())
        mutations = [
            ("participants", "id", []), ("participants", "actor_id", {}), ("participants", "disposition", []),
            ("relationships", "id", []), ("relationships", "source", []), ("relationships", "flow_id", []),
            ("relationships", "exchange_type", {}), ("value_logic", "stage", {}), ("value_logic", "flow_ids", [["bad"]]),
        ]
        for collection, key, value in mutations:
            with self.subTest(collection=collection, key=key):
                self.coverage = make_business_model_coverage_fixture(self.graph)
                self.coverage[collection][0][key] = value
                self.assertTrue(self.codes())
        for value in (None, [], "review"):
            self.coverage = make_business_model_coverage_fixture(self.graph)
            self.coverage["review"] = value
            self.assertTrue(self.codes())
        self.coverage = make_business_model_coverage_fixture(self.graph)
        self.coverage["review"]["pass_id"] = []
        self.assertTrue(self.codes())


if __name__ == "__main__":
    unittest.main()
