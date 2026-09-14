#!/usr/bin/env python3
"""Adversarial tests for the v2 research-execution process validator."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from package_fixture import make_business_model_coverage_fixture, make_business_model_fixture, make_valid_unfrozen_package  # noqa: E402
from validate_research_process import (  # noqa: E402
    canonical_company_sha256,
    deterministic_ordinary_claim_sample,
    expected_dcf_audit_value,
    validate_research_process,
)


NOW = "2026-04-15T12:00:00+00:00"
HASH_A = "a" * 64
HASH_B = "b" * 64


def _fingerprint() -> dict[str, str]:
    return {
        "research_protocol_digest_sha256": "1" * 64,
        "execution_bundle_digest_sha256": "2" * 64,
        "schema_version": "2.3.0",
        "schema_sha256": "3" * 64,
        "validator_sha256": "4" * 64,
    }


def _preflight(capability: str, source_id: str | None = None, digest: str | None = None) -> dict[str, Any]:
    return {
        "capability": capability,
        "status": "passed",
        "checked_at": NOW,
        "method": f"实际执行并复核 {capability} 探针结果",
        "source_id": source_id,
        "evidence_sha256": digest,
        "failure_reason": None,
    }


def _pass(
    pass_id: str,
    role: str,
    actor_id: str,
    execution: str,
    claim_ids: list[str],
    source_ids: list[str],
) -> dict[str, Any]:
    return {
        "id": pass_id,
        "role": role,
        "actor_id": actor_id,
        "execution": execution,
        "status": "completed",
        "scope": f"独立完成 {role} 的证据复核与结论裁决",
        "claim_ids": claim_ids,
        "source_ids_accessed": source_ids,
    }


def _driver(driver_id: str, role: str, source_id: str) -> dict[str, Any]:
    return {
        "id": driver_id,
        "name": f"{driver_id} 核心经营驱动",
        "metric": f"{driver_id} 可观察指标",
        "definition": "按正式披露口径计算并在每个季度保持一致",
        "historical_baseline": "过去五年保持在可复核的稳定区间",
        "current_state": "最新正式报告仍位于历史正常区间",
        "causal_role": role,
        "direction_and_mechanism": "指标改善会提高单位收入并降低边际获客成本",
        "cash_flow_link": "收入改善通过经营利润率传导至自由现金流",
        "moat_link": "稳定留存和覆盖密度共同检验转换成本",
        "valuation_link": "该指标直接约束显性增长和利润率假设",
        "monitoring_indicator": "每季度核对同比变化及五年历史分位",
        "source_ids": [source_id],
        "confidence": "high",
        "counterevidence": ["竞争补贴可能暂时抬高表面增长并压低真实留存"],
        "would_falsify": "若连续四个季度跌破历史下沿则推翻当前驱动判断",
    }


def _management_decision(
    decision_id: str,
    kind: str,
    source_id: str,
    stakeholder_claim_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": decision_id,
        "kind": kind,
        "date": "2025-02-15",
        "decision": "在保持核心网络投入的同时限制低回报扩张",
        "information_available": "当时收入增长稳定但竞争补贴和监管压力开始上升",
        "public_rationale": "管理层称资源应优先投向可验证的客户留存和网络覆盖",
        "alternatives": ["全面增加营销补贴", "暂停增长投资并集中返还现金"],
        "constraints": ["资本预算有限", "监管资本和服务质量不能下降"],
        "ex_ante_process": "先比较各方案的单位经济性、回收期和最坏现金消耗",
        "process_quality": "high",
        "outcome": "后续披露显示利润率改善且核心网络指标保持稳定",
        "outcome_quality": "positive",
        "confounders": ["同期行业需求回升也可能贡献部分结果"],
        "stakeholder_claim_ids": stakeholder_claim_ids or [],
        "succession_dependency": "low",
        "source_ids": [source_id],
        "confidence": "high",
    }


def _audit_check(
    check_id: str,
    target_type: str,
    target_id: str,
    criticality: str,
    source_id: str,
    observed_value: Any = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "target_type": target_type,
        "target_id": target_id,
        "criticality": criticality,
        "source_ids": [source_id],
        "status": "pass",
        "checked_at": NOW,
        "location": "正式报告第 8 至 12 页的明确披露位置",
        "observed": f"重新打开来源并核对 {target_id} 与记录一致",
        "observed_value": observed_value,
        "notes": None,
    }


def build_valid_process_ledger(
    legacy_evidence: dict[str, Any],
    company: dict[str, Any],
    calculations: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str]]:
    """Upgrade the substantive package fixture to a valid v2 execution ledger."""

    source_records = {item["id"]: item for item in company["sources"]}
    claims = copy.deepcopy(legacy_evidence["claims"])
    critical_ids = {"CLM-009", "CLM-010"}
    modules = (
        "financials",
        "business",
        "competition",
        "financials",
        "management",
        "management",
        "risk",
        "business",
        "competition",
        "valuation",
    )
    for index, claim in enumerate(claims):
        claim["research_module"] = modules[index]
        claim["decision_relevance"] = "critical" if claim["id"] in critical_ids else "supporting"
        claim["adjudication"] = "upheld"
        claim["counterevidence"] = ["独立挑战检索到的相反路径尚未推翻该项证据"]
        claim["counterevidence_search"] = (
            "隔离挑战者检索竞争披露、监管文件和历史失败案例"
            if claim["id"] in critical_ids
            else None
        )
        claim["would_falsify"] = claim.get(
            "would_falsify",
            "若下一份正式披露与当前方向相反并持续两个期间则推翻判断",
        )

    claim_ids = [item["id"] for item in claims]
    passes = [
        _pass("PASS-PRIMARY", "primary_research", "actor-primary", "primary_context", claim_ids, ["SRC-FY", "SRC-Q1"]),
        _pass("PASS-CHALLENGE", "adversarial_review", "actor-challenge", "isolated_agent", sorted(critical_ids), ["SRC-Q1"]),
        _pass("PASS-AUDIT", "source_audit", "actor-audit", "isolated_context", [], ["SRC-FY", "SRC-Q1"]),
        _pass("PASS-SYNTHESIS", "synthesis", "actor-synthesis", "synthesis_context", claim_ids, []),
    ]

    assumptions = [
        {
            "id": f"ASM-{index + 1:03d}",
            "assumption": assumption,
            "importance": "core" if index == 0 else "supporting",
            "prior_status": None,
            "current_status": "supported",
            "change_type": "baseline",
            "evidence_claim_ids": [["CLM-002", "CLM-008"], ["CLM-003", "CLM-009"]][index],
            "reason": "正式披露和历史序列仍支持该项核心经营假设",
            "falsifier": "若连续四季关键指标越过红线则该假设失效",
            "red_lines": ["连续四季客户留存或网络覆盖显著跌破历史下沿"],
            "next_validation": "下一份季度报告发布后重新核对领先指标",
        }
        for index, assumption in enumerate(company["verdict"]["key_assumptions"])
    ]

    risk_placements = []
    placements = ("cash_flow", "scenario", "tail_case", "discount_rate", "scenario")
    for index, risk in enumerate(company["risks"]["pre_mortem"]):
        placement = placements[index]
        risk_placements.append(
            {
                "risk": risk["failure_path"],
                "placement": placement,
                "scenario": f"压力情景 {index + 1}" if placement in {"scenario", "tail_case"} else None,
                "rationale": "该失败路径只在此处计价，避免同时压低现金流和提高折现率",
                "claim_ids": ["CLM-010"],
            }
        )

    models = [
        {
            "model": "DCF",
            "role": "primary",
            "status": "appropriate",
            "reason": "稳定自由现金流和明确资本开支使现金流模型可用",
            "key_assumptions": ["显性期增长和利润率按正式披露校准"],
            "result_direction": "fair",
        },
        {
            "model": "Reverse DCF",
            "role": "reverse",
            "status": "appropriate",
            "reason": "当前价格可反推出市场隐含的现金流增长要求",
            "key_assumptions": ["股价、股份和净债务均使用估值日口径"],
            "result_direction": "fair",
        },
        {
            "model": "FCF Yield Cross-check",
            "role": "cross_check",
            "status": "limited",
            "reason": "收益率只能作为方向性校验，不能替代现金流模型",
            "key_assumptions": ["正常化自由现金流不含一次性营运资本波动"],
            "result_direction": "fair",
        },
    ]

    cells = [
        {
            "discount_rate": item["discount_rate"],
            "terminal_growth": item["terminal_growth"],
            "valuation_status": company["verdict"]["valuation_status"],
        }
        for item in company["valuation"]["dcf_sensitivity"]
    ]

    start_record = next(
        item
        for item in calculations["calculations"]
        if item.get("valuation_role") == "starting_cash_flow"
    )
    meta = company["meta"]
    valuation = company["valuation"]
    checks = [
        _audit_check(
            "AUD-ID",
            "company_field",
            "company.meta.identity",
            "critical",
            "SRC-FY",
            {"company_name_en": meta["company_name_en"], "ticker": meta["ticker"], "exchange": meta["exchange"]},
        ),
        _audit_check("AUD-PRICE", "company_field", "company.valuation.market_price", "critical", "SRC-Q1", valuation["market_price"]),
        _audit_check("AUD-SHARES", "company_field", "company.valuation.diluted_shares", "critical", "SRC-Q1", valuation["diluted_shares"]),
        _audit_check("AUD-MCAP", "company_field", "company.valuation.market_cap", "critical", "SRC-Q1", valuation["market_cap"]),
        _audit_check("AUD-EV", "company_field", "company.valuation.enterprise_value", "critical", "SRC-Q1", valuation["enterprise_value"]),
        _audit_check("AUD-START", "calculation", "calculation.starting_cash_flow", "critical", "SRC-FY", start_record["result"]),
        _audit_check(
            "AUD-DCF",
            "valuation_assumption",
            "valuation.dcf_assumptions",
            "critical",
            "SRC-FY",
            expected_dcf_audit_value(company, calculations),
        ),
    ]
    for claim_id in sorted(critical_ids):
        source_id = next(item["source_ids"][0] for item in claims if item["id"] == claim_id)
        checks.append(_audit_check(f"AUD-{claim_id}", "claim", claim_id, "critical", source_id, None))

    selection_seed = canonical_company_sha256(company)
    ordinary_ids = [item["id"] for item in claims if item["id"] not in critical_ids]
    for claim_id in deterministic_ordinary_claim_sample(ordinary_ids, selection_seed):
        source_id = next(item["source_ids"][0] for item in claims if item["id"] == claim_id)
        checks.append(_audit_check(f"AUD-{claim_id}", "claim", claim_id, "ordinary", source_id, None))

    fingerprint = _fingerprint()
    ledger = {
        "ledger_version": "2.0",
        "business_model": make_business_model_fixture(company),
        "run": {
            "run_id": "RUN-2026-04-15-TEST",
            "research_mode": "full",
            "workflow_tier": "standard",
            "data_cutoff_at": NOW,
            "status": "ready_to_freeze",
            "protocol_fingerprint": copy.deepcopy(fingerprint),
            "preflight": [
                _preflight("protocol_access"),
                _preflight("schema_access"),
                _preflight("official_source_retrieval", "SRC-FY", HASH_A),
                _preflight("challenge_source_retrieval", "SRC-Q1", HASH_B),
                _preflight("calculation_runtime"),
                _preflight("package_write"),
            ],
            "passes": passes,
        },
        "researchability": {
            "official_source_coverage": "high",
            "operating_kpi_coverage": "medium",
            "third_party_verifiability": "medium",
            "timeliness": "high",
            "opacity": "medium",
            "evidence_confidence": "high",
            "thesis_certainty": "medium",
            "assessment": "官方财务证据完整，但经营论点仍受竞争反证与长期不确定性约束",
            "limitations": ["客户分层留存和商户边际获客成本仍缺少更细披露"],
        },
        "business_driver_map": {
            "equation": "客户留存乘以商户覆盖和单位收入，扣除服务成本后形成可分配现金",
            "value_capture_chain": ["更多有效商户覆盖提高客户使用频次", "更高使用频次带来服务收入并摊薄固定成本"],
            "drivers": [
                _driver("DRV-RETENTION", "retention", "SRC-Q1"),
                _driver("DRV-COVERAGE", "volume", "SRC-FY"),
            ],
        },
        "management_decision_ledger": [
            _management_decision("MD-001", "commitment", "SRC-FY", ["CLM-006"]),
            _management_decision("MD-002", "capital_allocation", "SRC-FY", ["CLM-005"]),
            _management_decision("MD-003", "governance", "SRC-Q1"),
        ],
        "thesis": {
            "overall_change": "baseline",
            "assumptions": assumptions,
            "valuation_assumption_changes": [],
            "rejected_claim_ids": [],
            "unresolved_conflicts": [],
            "revision_log": [],
        },
        "valuation_review": {
            "model_applicability": models,
            "risk_placements": risk_placements,
            "model_conflicts": [],
            "conclusion_stability": {
                "cells": cells,
                "verdict_flip": False,
                "action": "maintain",
                "explanation": "九格敏感性均保持接近合理，因此当前结论对所选参数区间稳定",
            },
        },
        "source_audit": {
            "audit_pass_id": "PASS-AUDIT",
            "selection_seed": selection_seed,
            "checks": checks,
        },
        "claims": claims,
    }
    ledger["business_model_coverage"] = make_business_model_coverage_fixture(ledger["business_model"])
    ledger["business_model_coverage"]["review"]["pass_id"] = "PASS-AUDIT"
    return ledger, source_records, fingerprint


class ResearchProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        package, _schema, self.company = make_valid_unfrozen_package(Path(self.temp_dir.name))
        current_evidence = json.loads((package / "evidence-ledger.json").read_text(encoding="utf-8"))
        self.legacy_evidence = {"claims": copy.deepcopy(current_evidence["claims"])}
        self.calculations = json.loads((package / "calculation-ledger.json").read_text(encoding="utf-8"))
        self.ledger, self.source_records, self.fingerprint = build_valid_process_ledger(
            self.legacy_evidence,
            self.company,
            self.calculations,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def validate(self, ledger: dict[str, Any] | None = None, mode: str = "full"):
        return validate_research_process(
            ledger if ledger is not None else self.ledger,
            self.company,
            self.calculations,
            self.source_records,
            mode,
            self.fingerprint,
        )

    @staticmethod
    def error_codes(issues) -> set[str]:
        return {item.code for item in issues if item.severity == "error"}

    def test_valid_process_fixture_has_no_errors(self) -> None:
        self.assertEqual([], [item for item in self.validate() if item.severity == "error"])

    def test_failed_live_preflight_is_blocked(self) -> None:
        probe = next(item for item in self.ledger["run"]["preflight"] if item["capability"] == "official_source_retrieval")
        probe["status"] = "failed"
        probe["failure_reason"] = "官方原件访问返回权限错误，未取得可复核内容"
        self.assertIn("preflight-failed", self.error_codes(self.validate()))

    def test_missing_live_preflight_is_blocked(self) -> None:
        self.ledger["run"]["preflight"] = [
            item for item in self.ledger["run"]["preflight"] if item["capability"] != "challenge_source_retrieval"
        ]
        codes = self.error_codes(self.validate())
        self.assertIn("preflight-coverage", codes)
        self.assertIn("preflight-cardinality", codes)

    def test_official_preflight_cannot_bind_an_aggregator(self) -> None:
        self.source_records["SRC-FY"]["source_type"] = "news"
        self.assertIn("preflight-official-source-type", self.error_codes(self.validate()))

    def test_challenge_pass_must_be_isolated_and_use_a_different_actor(self) -> None:
        for mutation, expected_code in (("same_actor", "research-pass-independence"), ("same_context", "research-pass-isolation")):
            with self.subTest(mutation=mutation):
                ledger = copy.deepcopy(self.ledger)
                challenge = next(item for item in ledger["run"]["passes"] if item["role"] == "adversarial_review")
                if mutation == "same_actor":
                    challenge["actor_id"] = "actor-primary"
                else:
                    challenge["execution"] = "primary_context"
                self.assertIn(expected_code, self.error_codes(self.validate(ledger)))

    def test_unresolved_critical_claim_is_blocked(self) -> None:
        claim = next(item for item in self.ledger["claims"] if item["id"] == "CLM-009")
        claim["adjudication"] = "unresolved"
        self.assertIn("critical-claim-not-adjudicated", self.error_codes(self.validate()))

    def test_source_audit_seed_and_sample_are_deterministic_and_complete(self) -> None:
        bad_seed = copy.deepcopy(self.ledger)
        bad_seed["source_audit"]["selection_seed"] = "0" * 64
        self.assertIn("source-audit-seed", self.error_codes(self.validate(bad_seed)))

        incomplete = copy.deepcopy(self.ledger)
        ordinary_targets = [
            item["target_id"]
            for item in incomplete["source_audit"]["checks"]
            if item["target_type"] == "claim" and item["criticality"] == "ordinary"
        ]
        omitted = ordinary_targets[0]
        incomplete["source_audit"]["checks"] = [
            item for item in incomplete["source_audit"]["checks"] if item["target_id"] != omitted
        ]
        self.assertIn("source-audit-ordinary-sample", self.error_codes(self.validate(incomplete)))

    def test_dcf_source_audit_must_reproduce_assumptions_and_equity_bridges(self) -> None:
        check = next(
            item
            for item in self.ledger["source_audit"]["checks"]
            if item["target_id"] == "valuation.dcf_assumptions"
        )
        check["observed_value"]["scenarios"][0]["discount_rate"] += 0.01
        self.assertIn("source-audit-dcf-value", self.error_codes(self.validate()))

    def test_double_counted_valuation_risk_is_blocked(self) -> None:
        duplicate = copy.deepcopy(self.ledger["valuation_review"]["risk_placements"][0])
        duplicate["placement"] = "discount_rate"
        duplicate["scenario"] = None
        self.ledger["valuation_review"]["risk_placements"].append(duplicate)
        self.assertIn("risk-double-count", self.error_codes(self.validate()))

    def test_unresolved_model_conflict_is_blocked(self) -> None:
        models = self.ledger["valuation_review"]["model_applicability"]
        models[0]["result_direction"] = "undervalued"
        models[1]["result_direction"] = "overvalued"
        self.ledger["valuation_review"]["model_conflicts"] = [
            {
                "id": "MC-001",
                "models": ["DCF", "Reverse DCF"],
                "applicability_boundary": "DCF 对远期现金流敏感，反向模型只描述当前市场要求",
                "authoritative_value_basis": "以可分配现金和保守资本需求作为最终价值依据",
                "explanation": "两个模型方向相反且当前证据尚不足以判断哪个边界更可靠",
                "impact_on_conclusion": "冲突会直接改变安全边际和当前估值状态判断",
                "resolved": False,
            }
        ]
        self.assertIn("model-conflict-unresolved", self.error_codes(self.validate()))

    def test_sensitivity_verdict_flip_without_downgrade_is_blocked(self) -> None:
        stability = self.ledger["valuation_review"]["conclusion_stability"]
        stability["cells"][0]["valuation_status"] = "偏高"
        stability["verdict_flip"] = True
        stability["action"] = "maintain"
        self.assertIn("conclusion-stability-action", self.error_codes(self.validate()))

    def test_audit_mode_legacy_ledger_warns_without_process_error(self) -> None:
        issues = self.validate(copy.deepcopy(self.legacy_evidence), mode="audit")
        self.assertEqual([], [item for item in issues if item.severity == "error"])
        self.assertIn(
            "legacy-evidence-process-unverifiable",
            {item.code for item in issues if item.severity == "warning"},
        )


if __name__ == "__main__":
    unittest.main()
