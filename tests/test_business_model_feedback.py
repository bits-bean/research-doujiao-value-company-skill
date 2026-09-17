"""Optional causal mechanisms require more than a transaction-graph cycle."""
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
from package_fixture import make_business_model_fixture
from validate_business_feedback import canonical_feedback_mechanism_sha256, validate_business_model_feedback
from validate_research_process import LEDGER_ROOT_KEYS, PROTOCOL_FINGERPRINT_KEYS, validate_research_process


class BusinessModelFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.company = {"meta": {"company_name_cn": "测试支付网络", "company_name_en": "Test Payment Network", "ticker": "TPN", "exchange": "TEST"}, "income_statement_sankey": {"fiscal_year": "FY2025"}}
        self.graph = make_business_model_fixture(self.company)
        self.passes = [
            {"id": "PASS-PRIMARY", "role": "primary_research", "actor_id": "primary", "execution": "primary_context", "status": "completed", "source_ids_accessed": ["SRC-FY"]},
            {"id": "PASS-CHALLENGE", "role": "adversarial_review", "actor_id": "challenger", "execution": "isolated_agent", "status": "completed", "source_ids_accessed": ["SRC-FY"]},
            {"id": "PASS-AUDIT", "role": "source_audit", "actor_id": "auditor", "execution": "isolated_context", "status": "completed", "source_ids_accessed": ["SRC-FY"]},
        ]
        self.feedback = {
            "version": "1.0", "status": "supported", "reason": "虚构材料支持逐环解释；最后一环仍是有条件的研究推断。",
            "loops": [{
                "id": "service-learning", "title": "使用记录与服务改善的反馈机制",
                "states": [
                    {"id": "usage", "label": "有效使用增加", "definition": "会员在适用场景中的持续使用次数增加。", "actor_ids": ["cardholders"]},
                    {"id": "observations", "label": "可用记录更丰富", "definition": "授权范围内可用的业务观察覆盖更完整。", "actor_ids": ["company"]},
                    {"id": "relevance", "label": "服务相关性提高", "definition": "服务更符合已验证的会员需求。"},
                ],
                "links": [
                    {"id": "usage-observations", "source": "usage", "target": "observations", "mechanism": "新增实际使用产生可在许可范围内使用的观察。", "evidence_type": "fact", "source_ids": ["SRC-FY"], "source_locations": {"SRC-FY": "Business, Service operations, p. 5"}, "conditions": [], "break_conditions": []},
                    {"id": "observations-relevance", "source": "observations", "target": "relevance", "mechanism": "管理层称观察覆盖改善有助于调整服务。", "evidence_type": "management_claim", "source_ids": ["SRC-FY"], "source_locations": {"SRC-FY": "Management discussion, Service relevance, p. 12"}, "conditions": [], "break_conditions": []},
                    {"id": "relevance-usage", "source": "relevance", "target": "usage", "mechanism": "更相关的服务可能提高适用会员的持续使用。", "evidence_type": "inference", "source_ids": ["SRC-FY"], "source_locations": {"SRC-FY": "Business, Member retention, p. 6"}, "conditions": ["服务改善能被会员感知且使用成本没有同步上升"], "break_conditions": ["服务相关性改善后持续使用仍下降"], "flow_ids": ["member-service"]},
                ],
                "review": {"pass_id": "PASS-CHALLENGE", "mechanism_sha256": "", "verdict": "accepted", "conclusion": "逐环复核来源与因果范围；保留最后一环的推断及失效条件。"},
            }],
        }
        self.rebind()

    @property
    def loop(self):
        return self.feedback["loops"][0]

    def rebind(self):
        for loop in self.feedback["loops"]:
            loop["review"]["mechanism_sha256"] = canonical_feedback_mechanism_sha256(loop)

    def issues(self):
        return validate_business_model_feedback(self.feedback, self.graph, {"SRC-FY"}, self.passes)

    def codes(self):
        return {issue.code for issue in self.issues()}

    def test_supported_mechanism_has_causal_states_and_does_not_mutate_inputs(self):
        before = copy.deepcopy((self.feedback, self.graph, self.passes))
        self.assertEqual(self.issues(), [])
        self.assertEqual((self.feedback, self.graph, self.passes), before)
        self.assertTrue(set(state["id"] for state in self.loop["states"]).isdisjoint(actor["id"] for actor in self.graph["actors"]))

    def test_absence_and_not_established_are_valid_without_warnings(self):
        self.assertEqual(validate_business_model_feedback(None, None, set(), [], declared=False), [])
        self.feedback = {"version": "1.0", "status": "not_established", "reason": "未取得足以支持最后反馈环节的证据，保留已有研究。", "loops": []}
        self.assertEqual(self.issues(), [])

    def test_payment_service_cycle_never_creates_a_feedback_mechanism(self):
        before = copy.deepcopy(self.graph)
        self.assertEqual(validate_business_model_feedback(None, self.graph, {"SRC-FY"}, self.passes, declared=False), [])
        self.assertEqual(self.graph, before)
        self.assertNotIn("business_model_feedback", self.graph)

    def test_no_data_exchange_is_required_for_a_supported_cost_mechanism(self):
        names = ["需求规模增加", "单位采购成本下降", "顾客价格吸引力提高"]
        for state, name in zip(self.loop["states"], names):
            state.update(label=name, definition=f"本环的经营状态为{name}。")
            state.pop("actor_ids", None)
        self.loop["title"] = "规模与成本反馈"
        for link, explanation in zip(self.loop["links"], ["更大的集中订单支持供应折扣。", "在其他成本不变时把节约的一部分体现到顾客价格。", "更具吸引力的价格有条件地支持订单规模回升。"]):
            link["mechanism"] = explanation
            link.pop("flow_ids", None)
        self.rebind()
        self.assertNotIn("data", {flow["kind"] for flow in self.graph["flows"]})
        self.assertEqual(self.issues(), [])

    def test_open_chain_missing_return_link_is_rejected(self):
        self.loop["links"].pop()
        self.rebind()
        self.assertIn("business-model-feedback-cycle", self.codes())
        self.assertIn("business-model-feedback-cycle-order", self.codes())

    def test_return_link_requires_evidence_and_precise_location(self):
        self.loop["links"][-1]["source_ids"] = []
        self.loop["links"][-1]["source_locations"] = {}
        self.rebind()
        self.assertIn("business-model-feedback-sources", self.codes())

    def test_inferences_require_both_conditions_and_break_conditions(self):
        for key in ("conditions", "break_conditions"):
            with self.subTest(key=key):
                original = self.loop["links"][-1][key]
                self.loop["links"][-1][key] = []
                self.rebind()
                self.assertIn("business-model-feedback-inference-conditions", self.codes())
                self.loop["links"][-1][key] = original

    def test_links_must_follow_one_cycle_in_order(self):
        self.loop["links"] = self.loop["links"][1:] + self.loop["links"][:1]
        self.rebind()
        self.assertEqual(self.issues(), [])
        self.loop["links"][1], self.loop["links"][2] = self.loop["links"][2], self.loop["links"][1]
        self.rebind()
        self.assertIn("business-model-feedback-cycle-order", self.codes())

    def test_two_state_cycle_and_separate_complete_mechanisms_are_allowed(self):
        second = copy.deepcopy(self.loop)
        second["id"] = "operating-learning"
        second["states"] = second["states"][:2]
        second["links"] = second["links"][:2]
        second["links"][1].update(target="usage", mechanism="有条件地把经营观察转化为持续使用的改进。")
        self.feedback["loops"].append(second)
        self.rebind()
        self.assertEqual(self.issues(), [])

    def test_two_disjoint_cycles_branching_self_loops_and_unknown_states_fail(self):
        original = copy.deepcopy(self.feedback)
        self.loop["states"] = [{"id": name, "label": name, "definition": "定义明确的经营状态"} for name in ("a", "b", "c", "d")]
        template = self.loop["links"][0]
        self.loop["links"] = [{**template, "id": f"causal-{index}", "source": source, "target": target} for index, (source, target) in enumerate((("a", "b"), ("b", "a"), ("c", "d"), ("d", "c")))]
        self.rebind()
        self.assertIn("business-model-feedback-cycle-connected", self.codes())
        for target in ("usage", "observations", "unknown"):
            self.feedback = copy.deepcopy(original)
            self.loop["links"][-1]["target"] = target
            if target == "usage":
                self.loop["links"][-1]["source"] = "usage"
            self.rebind()
            self.assertTrue(self.codes())

    def test_duplicate_loop_state_and_link_ids_fail(self):
        self.feedback["loops"].append(copy.deepcopy(self.loop))
        self.assertIn("business-model-feedback-loop-id", self.codes())
        self.feedback["loops"].pop()
        self.loop["states"][1]["id"] = self.loop["states"][0]["id"]
        self.loop["links"][1]["id"] = self.loop["links"][0]["id"]
        self.rebind()
        self.assertTrue({"business-model-feedback-state-id", "business-model-feedback-link-id"}.issubset(self.codes()))

    def test_optional_original_graph_references_resolve_but_do_not_define_causation(self):
        self.loop["states"][0]["actor_ids"] = ["foreign-actor"]
        self.loop["links"][-1]["flow_ids"] = ["foreign-flow"]
        self.rebind()
        self.assertIn("business-model-feedback-references", self.codes())
        self.loop["states"][0]["actor_ids"] = []
        self.loop["links"][-1]["flow_ids"] = []
        self.rebind()
        self.assertEqual(self.issues(), [])

    def test_unknown_sources_and_mismatched_locations_fail(self):
        for value in ([], ["SRC-MISSING"], ["SRC-FY", "SRC-FY"], [["bad"]]):
            self.loop["links"][0]["source_ids"] = value
            self.rebind()
            self.assertIn("business-model-feedback-sources", self.codes())
        self.loop["links"][0]["source_ids"] = ["SRC-FY"]
        for value in (None, {}, {"SRC-FY": " "}, {"SRC-FY": "p. 5", "SRC-OTHER": "p. 6"}):
            self.loop["links"][0]["source_locations"] = value
            self.rebind()
            self.assertIn("business-model-feedback-source-locations", self.codes())

    def test_review_hash_binds_conditions_sources_and_every_state_but_excludes_review(self):
        content = {key: value for key, value in self.loop.items() if key != "review"}
        expected = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
        self.assertEqual(canonical_feedback_mechanism_sha256(self.loop), expected)
        self.loop["review"]["conclusion"] = "重新陈述同一审查结论与限制。"
        self.assertEqual(canonical_feedback_mechanism_sha256(self.loop), expected)
        self.loop["links"][-1]["conditions"].append("价格没有显著上涨")
        self.assertIn("business-model-feedback-hash", self.codes())
        self.rebind()
        self.assertEqual(self.issues(), [])
        self.loop["states"][0]["definition"] = "已变更适用范围。"
        self.assertIn("business-model-feedback-hash", self.codes())

    def test_nonfinite_mechanism_is_rejected_without_an_exception(self):
        self.loop["unsupported_extra"] = float("nan")
        self.assertIn("business-model-feedback-hash", self.codes())

    def test_review_requires_real_completed_independent_pass_and_source_access(self):
        for pass_id in ("PASS-MISSING", "PASS-PRIMARY"):
            self.loop["review"]["pass_id"] = pass_id
            self.assertIn("business-model-feedback-review-pass", self.codes())
        self.loop["review"]["pass_id"] = "PASS-CHALLENGE"
        original = copy.deepcopy(self.passes[1])
        for key, value in (("role", "synthesis"), ("execution", "primary_context"), ("actor_id", "primary"), ("status", "failed")):
            self.passes[1] = {**original, key: value}
            self.assertIn("business-model-feedback-review-pass", self.codes())
        self.passes[1] = {**original, "source_ids_accessed": []}
        self.assertIn("business-model-feedback-review-sources", self.codes())
        self.loop["review"]["pass_id"] = "PASS-AUDIT"
        self.assertEqual(self.issues(), [])

    def test_not_established_cannot_keep_hidden_supported_loops(self):
        self.feedback["status"] = "not_established"
        self.assertIn("business-model-feedback-not-established-loops", self.codes())

    def test_completed_review_requires_explicit_accepted_mechanism_verdict(self):
        self.assertEqual(self.passes[1]["status"], "completed")
        for verdict in (None, "pending", "requires_revision", "unknown"):
            with self.subTest(verdict=verdict):
                if verdict is None:
                    self.loop["review"].pop("verdict", None)
                else:
                    self.loop["review"]["verdict"] = verdict
                self.assertIn("business-model-feedback-review-verdict", self.codes())
        self.loop["review"]["verdict"] = "accepted"
        self.assertEqual(self.issues(), [])

    def test_production_process_integrates_optional_gate_without_warnings_for_absence(self):
        evidence = {key: {} for key in LEDGER_ROOT_KEYS}
        evidence.update(ledger_version="2.0", claims=[], business_model=self.graph)
        fingerprint = {key: "locked-test-value" for key in PROTOCOL_FINGERPRINT_KEYS}
        with patch("validate_research_process._validate_run", return_value=("full", "standard", self.passes)):
            for mode in ("full", "incremental", "audit"):
                issues = validate_research_process(evidence, self.company, {}, {"SRC-FY": {}}, mode, fingerprint)
                self.assertFalse(any(issue.code.startswith("business-model-feedback") for issue in issues))
            evidence["business_model_feedback"] = None
            issues = validate_research_process(evidence, self.company, {}, {"SRC-FY": {}}, "audit", fingerprint)
            self.assertIn("business-model-feedback-shape", {issue.code for issue in issues})
            evidence["business_model_feedback"] = self.feedback
            self.loop["links"].pop()
            issues = validate_research_process(evidence, self.company, {}, {"SRC-FY": {}}, "full", fingerprint)
            self.assertIn("business-model-feedback-cycle", {issue.code for issue in issues})

    def test_declared_feedback_cannot_hide_in_legacy_audit(self):
        fingerprint = {key: "locked-test-value" for key in PROTOCOL_FINGERPRINT_KEYS}
        issues = validate_research_process({"claims": [], "business_model_feedback": None}, self.company, {}, {}, "audit", fingerprint)
        self.assertTrue(any(issue.severity == "error" for issue in issues))
        self.assertNotIn("legacy-evidence-process-unverifiable", {issue.code for issue in issues})

    def test_malformed_values_produce_findings_without_exceptions(self):
        original = copy.deepcopy(self.feedback)
        for key in ("version", "status", "reason", "loops"):
            for value in (None, [], {}, " ", 3):
                self.feedback = copy.deepcopy(original)
                self.feedback[key] = value
                self.assertTrue(self.codes())
        for collection, key in (("states", "id"), ("states", "actor_ids"), ("links", "id"), ("links", "source"), ("links", "evidence_type"), ("links", "conditions"), ("links", "flow_ids")):
            for value in (None, {}, [None]):
                self.feedback = copy.deepcopy(original)
                self.loop[collection][0][key] = value
                self.assertTrue(self.codes())
        for key in ("states", "links", "review"):
            for value in (None, "bad", [None]):
                self.feedback = copy.deepcopy(original)
                self.loop[key] = value
                self.assertTrue(self.codes())
        self.assertTrue(validate_business_model_feedback(None, self.graph, {"SRC-FY"}, self.passes))

    def test_malformed_graph_and_review_pass_values_produce_findings(self):
        for graph in (None, [], {"actors": [None], "flows": [{"id": []}]}):
            with self.subTest(graph=graph):
                issues = validate_business_model_feedback(self.feedback, graph, {"SRC-FY"}, self.passes)
                self.assertIn("business-model-feedback-references", {issue.code for issue in issues})
        for passes in (None, {}, [None], [{"id": "PASS-CHALLENGE", "actor_id": {}}]):
            with self.subTest(passes=passes):
                issues = validate_business_model_feedback(self.feedback, self.graph, {"SRC-FY"}, passes)
                self.assertIn("business-model-feedback-review-pass", {issue.code for issue in issues})
        self.passes[1]["source_ids_accessed"] = [["SRC-FY"]]
        self.assertIn("business-model-feedback-review-sources", self.codes())


if __name__ == "__main__":
    unittest.main()
