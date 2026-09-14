"""Build a substantive package that passes the real full research validator."""

from __future__ import annotations

import shutil
from pathlib import Path

from validate_research_package import load_trusted_spec_lock, protocol_fingerprint, write_json
from validate_research_process import canonical_company_sha256, deterministic_ordinary_claim_sample


ROOT = Path(__file__).resolve().parents[1]
SOURCE_IDS = ["SRC-FY", "SRC-Q1"]
M = 1_000_000


def make_business_model_fixture(company: dict) -> dict:
    return {
        "version": "1.0",
        "period": company["income_statement_sankey"]["fiscal_year"],
        "company_identity": {key: company["meta"][key] for key in ("company_name_en", "ticker", "exchange")},
        "actors": [
            {"id": "company", "label": company["meta"]["company_name_cn"], "label_en": company["meta"]["company_name_en"], "detail": "发行收费卡并提供支付服务", "detail_en": "Issues fee-based cards and provides payments", "illustration": "company", "source_ids": ["SRC-FY"]},
            {"id": "cardholders", "label": "付费持卡会员", "label_en": "Fee-paying card members", "detail": "支付会员费并使用卡片权益", "detail_en": "Pay membership fees and use card benefits", "illustration": "cardholder", "source_ids": ["SRC-FY"]},
        ],
        "flows": [
            {"id": "membership-fee", "source": "cardholders", "target": "company", "label": "卡片会员费", "label_en": "Card membership fees", "kind": "money", "source_ids": ["SRC-FY"]},
            {"id": "member-service", "source": "company", "target": "cardholders", "label": "支付服务与会员权益", "label_en": "Payment services and benefits", "kind": "value", "source_ids": ["SRC-FY"]},
        ],
        "notes": "仅解释已披露的会员服务关系，箭头不是会计流量。",
        "notes_en": "Only disclosed membership relationships; arrows are not accounting flows.",
    }


def make_valid_unfrozen_package(root: Path) -> tuple[Path, Path, dict]:
    """Create real-schema inputs; the caller may add validation report and manifest."""
    schema_path = root / "company.schema.json"
    shutil.copyfile(ROOT / "references/specs/company.schema.json", schema_path)
    package = root / "package"
    package.mkdir()

    financials = []
    for offset, year in enumerate(range(2016, 2026)):
        revenue = (100 + offset * 10) * M
        gross_profit = (60 + offset * 6) * M
        operating_profit = (25 + offset * 2) * M
        net_income = (18 + offset * 2) * M
        operating_cash_flow = (30 + offset * 2) * M
        capex = (10 + offset) * M
        cash = (32 + offset * 2) * M
        debt = (28 - offset) * M
        financials.append(
            {
                "period": f"FY{year}",
                "period_type": "FY",
                "revenue": revenue,
                "gross_profit": gross_profit,
                "operating_profit": operating_profit,
                "net_income": net_income,
                "net_income_attributable_to_common": net_income - 500_000,
                "operating_cash_flow": operating_cash_flow,
                "capex_total": capex,
                "free_cash_flow": operating_cash_flow - capex,
                "cash": cash,
                "total_debt": debt,
                "net_debt": debt - cash,
                "gross_margin": gross_profit / revenue,
                "operating_margin": operating_profit / revenue,
                "net_margin": net_income / revenue,
                "roic": 0.14 + offset * 0.005,
                "roe": 0.18 + offset * 0.004,
                "incremental_roic": 0.16 + offset * 0.004,
                "diluted_shares": (109 - offset) * M,
                "diluted_eps": 0.16 + offset * 0.02,
                "is_estimate": False,
                "source_ids": ["SRC-FY"],
            }
        )
    for period, period_type, revenue_millions, reported_diluted_eps in (
        ("2026Q1", "Q1", 52, 0.10),
        ("TTM2026", "TTM", 202, 0.37),
    ):
        revenue = revenue_millions * M
        financials.append(
            {
                "period": period,
                "period_type": period_type,
                "revenue": revenue,
                "gross_profit": revenue * 0.6,
                "operating_profit": revenue * 0.24,
                "net_income": revenue * 0.18,
                "net_income_attributable_to_common": revenue * 0.18 - 500_000,
                "operating_cash_flow": revenue * 0.28,
                "capex_total": revenue * 0.08,
                "free_cash_flow": revenue * 0.2,
                "cash": 50 * M,
                "total_debt": 20 * M,
                "net_debt": -30 * M,
                "gross_margin": 0.6,
                "operating_margin": 0.24,
                "net_margin": 0.18,
                "roic": 0.19,
                "roe": 0.22,
                "incremental_roic": 0.20,
                "diluted_shares": 100 * M,
                "diluted_eps": reported_diluted_eps,
                "is_estimate": False,
                "source_ids": ["SRC-Q1"],
            }
        )

    starting_fcff = 29 * M
    diluted_shares = 100 * M
    net_debt = -30 * M
    dcf_specs = (
        ("悲观", "bear", 0.03, 0.18, 0.11, 0.02),
        ("基准", "base", 0.07, 0.22, 0.09, 0.025),
        ("乐观", "bull", 0.10, 0.25, 0.08, 0.03),
    )
    dcf_scenarios = []
    dcf_calculations = []
    dcf_display: dict[str, dict] = {}
    for name, scenario_code, growth, margin, discount_rate, terminal_growth in dcf_specs:
        cash_flow = starting_fcff
        annual_records = []
        for forecast_year in range(1, 11):
            cash_flow *= 1 + growth
            discount_factor = (1 + discount_rate) ** (-forecast_year)
            present_value = cash_flow * discount_factor
            record = {
                "id": f"CALC-DCF-{scenario_code.upper()}-Y{forecast_year}",
                "metric": "custom",
                "valuation_role": "annual_discounted_cash_flow",
                "valuation_scenario": scenario_code,
                "forecast_year": forecast_year,
                "period": f"Forecast Year {forecast_year}",
                "formula": "cash_flow * discount_factor",
                "inputs": {"cash_flow": cash_flow, "discount_factor": discount_factor},
                "result": present_value,
                "review_method": "逐年核对现金流增长、折现率与预测年度，并独立复算该年度现金流现值。",
                "source_ids": ["SRC-FY"],
            }
            dcf_calculations.append(record)
            annual_records.append(record)
        explicit_pv = sum(item["result"] for item in annual_records)
        final_factor = annual_records[-1]["inputs"]["discount_factor"]
        terminal_value = cash_flow * (1 + terminal_growth) / (discount_rate - terminal_growth)
        terminal_pv = terminal_value * final_factor
        equity_value = explicit_pv + terminal_pv - net_debt
        per_share_value = equity_value / diluted_shares
        dcf_calculations.extend(
            [
                {
                    "id": f"CALC-DCF-{scenario_code.upper()}-TERMINAL",
                    "metric": "custom",
                    "valuation_role": "terminal_present_value",
                    "valuation_scenario": scenario_code,
                    "period": "Forecast Year 10 Terminal",
                    "formula": "last_year_cash_flow * (1 + terminal_growth_rate) / (discount_rate - terminal_growth_rate) * discount_factor",
                    "inputs": {
                        "last_year_cash_flow": cash_flow,
                        "terminal_growth_rate": terminal_growth,
                        "discount_rate": discount_rate,
                        "discount_factor": final_factor,
                    },
                    "result": terminal_pv,
                    "review_method": "核对第10年现金流、永续增长率、折现率与末年折现因子，并独立复算终值现值。",
                    "source_ids": ["SRC-FY"],
                },
                {
                    "id": f"CALC-DCF-{scenario_code.upper()}-EQUITY",
                    "metric": "custom",
                    "valuation_role": "equity_value_bridge",
                    "valuation_scenario": scenario_code,
                    "period": "Valuation 2026-04-15",
                    "formula": "explicit_period_present_value + terminal_present_value - net_debt",
                    "inputs": {
                        "explicit_period_present_value": explicit_pv,
                        "terminal_present_value": terminal_pv,
                        "net_debt": net_debt,
                    },
                    "result": equity_value,
                    "diluted_shares": diluted_shares,
                    "per_share": per_share_value,
                    "review_method": "核对显性期现值、终值现值与净债务调整，再以稀释后股数独立复算每股价值。",
                    "source_ids": ["SRC-FY", "SRC-Q1"],
                },
            ]
        )
        dcf_scenarios.append(
            {
                "name": name,
                "revenue_growth": growth,
                "margin": margin,
                "discount_rate": discount_rate,
                "terminal_growth": terminal_growth,
                "fair_value_per_share": per_share_value,
                "terminal_value_share": terminal_pv / (explicit_pv + terminal_pv),
            }
        )
        dcf_display[scenario_code] = {
            "name": name,
            "growth": growth,
            "discount_rate": discount_rate,
            "terminal_growth": terminal_growth,
            "annual_records": annual_records,
            "explicit_pv": explicit_pv,
            "last_cash_flow": cash_flow,
            "terminal_value": terminal_value,
            "terminal_pv": terminal_pv,
            "terminal_share": terminal_pv / (explicit_pv + terminal_pv),
            "equity_value": equity_value,
            "per_share_value": per_share_value,
        }

    def sensitivity_value(discount_rate: float, terminal_growth: float) -> float:
        cash_flow = starting_fcff
        explicit_pv = 0.0
        for forecast_year in range(1, 11):
            cash_flow *= 1.07
            explicit_pv += cash_flow * (1 + discount_rate) ** (-forecast_year)
        terminal_pv = (
            cash_flow
            * (1 + terminal_growth)
            / (discount_rate - terminal_growth)
            * (1 + discount_rate) ** -10
        )
        return (explicit_pv + terminal_pv - net_debt) / diluted_shares

    dcf_sensitivity = [
        {"discount_rate": discount_rate, "terminal_growth": terminal_growth, "fair_value_per_share": sensitivity_value(discount_rate, terminal_growth)}
        for discount_rate in (0.08, 0.09, 0.10)
        for terminal_growth in (0.02, 0.025, 0.03)
    ]

    company = {
        "meta": {
            "company_name_cn": "测试公司",
            "company_name_en": "Test Company",
            "ticker": "TEST",
            "exchange": "NYSE",
            "fiscal_year_end": "12-31",
            "report_currency": "USD",
            "financial_unit": "unit",
            "share_unit": "share",
            "ratio_convention": "decimal",
            "valuation_date": "2026-04-15",
            "data_as_of": "2026-03-31",
            "accounting_standard": "US GAAP",
            "display_language": "zh-CN",
            "source_version": "2026Q1",
            "schema_version": "2.3.0",
            "theme": "light",
            "sankey_style": "app-economy-inspired-light",
        },
        "classification": {
            "sector": "information_technology",
            "primary_industry": "transaction_processing",
            "secondary_industries": ["membership_services"],
            "accounting_profile": "standard_corporate",
            "returns_profile": "standard_roic",
            "source_ids": ["SRC-FY"],
        },
        "brand_identity": {
            "company_logo": {
                "asset_path": "companies/test-company/assets/logo.svg",
                "source_url": "https://example.com/investors/logo.svg",
                "alt": "Test Company official logo",
                "is_official": True,
            },
            "brand_palette": {"primary": "#174A7E", "secondary": "#EAF3FA", "accent": "#C79A45"},
            "product_brands": ["Test Network", "Test Membership"],
            "visual_motif": "interlocking network nodes",
            "independent_research_label": "豆角滚雪球｜专注长期价值研究",
        },
        "verdict": {
            "business_quality": "良好",
            "valuation_status": "接近合理",
            "research_status": "观察名单",
            "confidence": "high",
            "one_sentence": "测试公司依靠双边网络与持续复购创造现金流，但当前价格只留下有限安全边际。",
            "key_assumptions": [
                "核心客户续费率保持稳定且单位服务收入继续温和增长",
                "商户覆盖扩大能够抵消竞争补贴带来的利润率压力",
            ],
            "thesis_breakers": [
                "连续四个季度核心客户净流失并伴随单位经济性恶化",
                "监管变化永久削弱网络收费能力且无法通过产品升级弥补",
            ],
        },
        "reporting": {
            "latest_report": {
                "period": "2026Q1",
                "period_type": "Q1",
                "report_date": "2026-03-31",
                "date_status": "official",
                "filing_url": "https://example.com/investors/2026-q1",
                "source_ids": ["SRC-Q1"],
            },
            "next_expected_report": {
                "period": "2026Q2",
                "period_type": "Q2",
                "report_date": "2026-07-20",
                "date_status": "estimated",
                "filing_url": None,
                "source_ids": [],
            },
            "last_checked_at": "2026-04-15T12:00:00Z",
            "monitoring_notes": "下一季度重点核对续费、商户覆盖与单位经济性。",
        },
        "financials": financials,
        "industry_metrics": [],
        "income_statement_sankey": {
            "fiscal_year": "FY2025",
            "basis": "income_statement",
            "nodes": [
                {"id": "product_revenue", "label": "产品收入", "value": 120 * M, "statement_value": 120 * M, "category": "revenue_source"},
                {"id": "subscription_revenue", "label": "订阅收入", "value": 70 * M, "statement_value": 70 * M, "category": "revenue_source"},
                {"id": "revenue", "label": "营业收入", "value": 190 * M, "statement_value": 190 * M, "category": "revenue_total"},
                {"id": "pretax_costs", "label": "税前成本与费用合计（计算值）", "value": 140 * M, "statement_value": 140 * M, "category": "pretax_costs_total"},
                {"id": "fulfillment_cost", "label": "履约成本", "value": 70 * M, "statement_value": 70 * M, "category": "cost_expense"},
                {"id": "product_development", "label": "产品研发", "value": 30 * M, "statement_value": 30 * M, "category": "cost_expense"},
                {"id": "sales_marketing", "label": "销售与营销", "value": 25 * M, "statement_value": 25 * M, "category": "cost_expense"},
                {"id": "general_admin", "label": "管理费用", "value": 15 * M, "statement_value": 15 * M, "category": "cost_expense"},
                {"id": "pretax_profit", "label": "税前利润", "value": 50 * M, "statement_value": 50 * M, "category": "pretax_profit"},
                {"id": "income_tax", "label": "所得税", "value": 14 * M, "statement_value": 14 * M, "category": "income_tax"},
                {"id": "profit", "label": "净利润", "value": 36 * M, "statement_value": 36 * M, "category": "net_income"},
            ],
            "links": [
                {"source": "product_revenue", "target": "revenue", "value": 120 * M},
                {"source": "subscription_revenue", "target": "revenue", "value": 70 * M},
                {"source": "revenue", "target": "pretax_costs", "value": 140 * M},
                {"source": "revenue", "target": "pretax_profit", "value": 50 * M},
                {"source": "pretax_costs", "target": "fulfillment_cost", "value": 70 * M},
                {"source": "pretax_costs", "target": "product_development", "value": 30 * M},
                {"source": "pretax_costs", "target": "sales_marketing", "value": 25 * M},
                {"source": "pretax_costs", "target": "general_admin", "value": 15 * M},
                {"source": "pretax_profit", "target": "income_tax", "value": 14 * M},
                {"source": "pretax_profit", "target": "profit", "value": 36 * M},
            ],
            "reconciled": True,
            "source_ids": ["SRC-FY"],
        },
        "segments": [
            {
                "period": "FY2025",
                "name": "Network Services",
                "revenue": 190 * M,
                "operating_profit": 43 * M,
                "revenue_share": 1.0,
                "growth_rate": 0.08,
                "notes": "核心网络与会员服务合并披露。",
                "source_ids": ["SRC-FY"],
            }
        ],
        "capital_allocation": [
            {
                "period": "FY2025",
                "category": "buyback",
                "amount": 18 * M,
                "lane": "shareholder_return",
                "result_status": "positive",
                "result": "稀释后股份同比净减少百分之二，并且未削弱净现金头寸。",
                "assessment": "回购均价低于当时审慎价值区间，提升了持续股东的每股权益。",
                "commentary": "在低于内部价值区间时回购并保持净现金。",
                "source_ids": ["SRC-FY"],
            }
        ],
        "buyback_ledger": [
            {
                "period": "FY2025",
                "amount": 18 * M,
                "shares_repurchased": 2 * M,
                "average_price": 9,
                "shares_outstanding_change": -0.02,
                "source_ids": ["SRC-FY"],
            }
        ],
        "debt_maturities": [
            {"year": 2028, "amount": 8 * M, "instrument": "senior notes", "interest_rate": 0.035, "source_ids": ["SRC-FY"]}
        ],
        "moat": [
            {
                "dimension": "定价权",
                "assessment": "核心客户重视可靠性，历史提价后续费率保持稳定。",
                "score": 4.0,
                "evidence": ["年报披露单位服务收入与留存率同步改善。"],
                "risks": ["竞争者以补贴换取份额可能压低短期费率。"],
                "source_ids": ["SRC-FY"],
            },
            {
                "dimension": "难复制",
                "assessment": "长期积累的商户接入与风控数据形成复合复制门槛。",
                "score": 4.0,
                "evidence": ["网络覆盖和历史交易样本需要多年持续投入。"],
                "risks": ["大型平台可以利用既有流量快速建设替代入口。"],
                "source_ids": ["SRC-FY"],
            },
            {
                "dimension": "转换成本",
                "assessment": "客户迁移会损失账户历史、权益组合和业务流程连接。",
                "score": 3.5,
                "evidence": ["企业客户把对账与权限管理嵌入日常流程。"],
                "risks": ["标准化接口降低了部分中小客户的迁移难度。"],
                "source_ids": ["SRC-Q1"],
            },
            {
                "dimension": "网络效应",
                "assessment": "客户与商户相互吸引，更多交易又改善风控和产品匹配。",
                "score": 4.5,
                "evidence": ["新增商户覆盖提高客户使用频率并扩大数据反馈。"],
                "risks": ["多归属行为使竞争网络也能分享同一客户群。"],
                "source_ids": ["SRC-Q1"],
            },
        ],
        "durability": {
            "horizon_years": 20,
            "overall_status": "conditional",
            "conclusion": "需求本身可持续，但公司必须持续适配新入口并抵御监管与技术冲击。",
            "demand_durability": {
                "status": "strong",
                "assessment": "可靠交易、短期信用和身份信任在二十年后仍有明确需求。",
                "evidence": ["正式披露显示核心客户持续为可靠性、信用与权益组合付费。"],
                "breaker": "若实时支付与开放身份基础设施使现有服务不再具有独立付费价值。",
                "source_ids": ["SRC-FY"],
            },
            "adaptability": {
                "status": "adequate",
                "assessment": "既有网络和数据能够支持迁移，但下一代入口的采用速度仍需验证。",
                "evidence": ["公司持续扩大数字入口接入并把既有风控能力迁移到新产品。"],
                "breaker": "若新入口交易占比持续上升而公司接入率连续多年落后。",
                "source_ids": ["SRC-Q1"],
            },
            "external_shocks": {
                "status": "uncertain",
                "assessment": "监管、数据使用限制与替代网络可能同时削弱现金流和资本弹性。",
                "evidence": ["季度披露把监管资本、信用损失和数据合规列为持续风险。"],
                "breaker": "若监管变化永久限制关键数据并要求大幅提高资本缓冲。",
                "source_ids": ["SRC-Q1"],
            },
            "source_ids": ["SRC-FY", "SRC-Q1"],
        },
        "management": {
            "scores": [
                {"dimension": "坦诚", "score": 4.0, "assessment": "管理层同时披露增长动力与成本压力，并量化关键偏差。", "source_ids": ["SRC-Q1"]},
                {"dimension": "理性", "score": 3.5, "assessment": "新增投入以单位经济性和客户留存为前置条件。", "source_ids": ["SRC-FY"]},
                {"dimension": "资本配置", "score": 4.0, "assessment": "先保障核心网络投入，再在估值合适时回购股份。", "source_ids": ["SRC-FY"]},
            ],
            "commitment_timeline": [
                {
                    "date": "2025-02-15",
                    "commitment": "管理层承诺保持核心网络投入同时改善经营利润率。",
                    "status": "fulfilled",
                    "outcome": "2025年收入增长并且经营利润率同比提升。",
                    "next_validation": {
                        "method": "下一份年报逐项核对核心网络投入、收入增速与经营利润率。",
                        "condition": "若网络投入保持且经营利润率不低于2025年水平，则承诺继续成立。",
                        "timeframe": "FY2026年报发布后",
                        "source_ids": ["SRC-FY"],
                    },
                    "source_ids": ["SRC-FY"],
                }
            ],
            "stop_doing_list": [
                "不为短期收入进入无法形成客户数据闭环的邻近业务",
                "不在高于审慎内在价值区间时机械扩大股份回购",
            ],
        },
        "valuation": {
            "market_price": 10,
            "diluted_shares": 100 * M,
            "market_cap": 1000 * M,
            "enterprise_value": 970 * M,
            "multiples": {"pe": 25, "fcf_yield": 0.04},
            "dcf_scenarios": dcf_scenarios,
            "dcf_sensitivity": dcf_sensitivity,
            "reverse_dcf": {
                "implied_fcff_cagr": 0.07,
                "implied_reinvestment_rate": 0.22,
                "comparison_to_history": "隐含可分配现金增长接近历史五年区间，资本再投资率略高于历史中位数。",
                "sensitivity_and_threshold": "资本再投资最敏感；若现金流增长连续三年低于百分之三，当前价格将显得高估。",
            },
            "fair_value_range": {
                "low": dcf_display["bear"]["per_share_value"],
                "base": dcf_display["base"]["per_share_value"],
                "high": dcf_display["bull"]["per_share_value"],
                "currency": "USD",
            },
            "expected_returns": [
                {"horizon_years": 5, "scenario": "悲观", "annualized_return": -0.05, "assumptions": ["竞争加剧"]},
                {"horizon_years": 5, "scenario": "基准", "annualized_return": 0.08, "assumptions": ["稳健增长"]},
                {"horizon_years": 5, "scenario": "乐观", "annualized_return": 0.15, "assumptions": ["网络效应增强"]},
            ],
        },
        "risks": {
            "pre_mortem": [
                {
                    "failure_path": "核心客户因产品体验停滞而迁移，续费下降导致单位经济性失效。",
                    "trigger": "核心产品迭代长期落后并使高价值客户连续多个季度流失。",
                    "operating_impact": "续费率和单位服务收入同步下降，获客成本回收期明显拉长。",
                    "capital_cash_impact": "维持客户规模需要加大补贴与营销支出，自由现金流率收缩。",
                    "value_impact": "可分配现金增长转负并压低合理估值区间与长期复利能力。",
                    "probability": "medium",
                    "impact": "high",
                    "time_horizon": "1–3年",
                    "earliest_warning": "续费率连续四季低于长期均值",
                    "reversibility": "partially_reversible",
                    "management_mitigation": "重做核心权益并降低无效获客支出",
                    "source_ids": ["SRC-Q1"],
                },
                {
                    "failure_path": "商户侧出现更低成本替代网络，覆盖优势逐步转为固定成本负担。",
                    "trigger": "替代网络以更低综合成本覆盖核心高频商户并形成规模。",
                    "operating_impact": "活跃商户和交易频次下降，网络收入与数据反馈同时减弱。",
                    "capital_cash_impact": "既有受理基础设施利用率下降，但维护成本难以同步削减。",
                    "value_impact": "网络效应反转并导致利润率和终值增长假设永久下调。",
                    "probability": "medium_low",
                    "impact": "high",
                    "time_horizon": "3–5年",
                    "earliest_warning": "活跃商户下降且新增覆盖连续停滞",
                    "reversibility": "hard_to_reverse",
                    "management_mitigation": "调整受理费率并投资高频使用场景",
                    "source_ids": ["SRC-FY"],
                },
                {
                    "failure_path": "监管限制数据使用范围，风控准确性下降并推高信用损失。",
                    "trigger": "新监管规则禁止关键风险变量用于授信和持续账户管理。",
                    "operating_impact": "风险识别能力下降，批准率、客户体验和信用损失同时承压。",
                    "capital_cash_impact": "拨备和监管资本需求上升，能够返还股东的现金减少。",
                    "value_impact": "正常化股东现金流下降且股权成本上升，内在价值显著受损。",
                    "probability": "low",
                    "impact": "severe",
                    "time_horizon": "1–2年",
                    "earliest_warning": "合规征询文件扩大禁止使用的数据范围",
                    "reversibility": "hard_to_reverse",
                    "management_mitigation": "提前建设替代变量与人工复核流程",
                    "source_ids": ["SRC-Q1"],
                },
                {
                    "failure_path": "管理层在高估值阶段过度回购，削弱应对衰退的资产负债表弹性。",
                    "trigger": "回购金额在估值偏高且宏观风险上升时仍明显扩张。",
                    "operating_impact": "核心经营短期不变，但管理层资本纪律和逆周期能力受到质疑。",
                    "capital_cash_impact": "现金缓冲下降并可能增加举债，使衰退期融资成本上升。",
                    "value_impact": "每股价值被高价回购摧毁，安全边际和长期回报率下降。",
                    "probability": "medium",
                    "impact": "high",
                    "time_horizon": "1–3年",
                    "earliest_warning": "回购均价显著超过基准内在价值区间",
                    "reversibility": "partially_reversible",
                    "management_mitigation": "暂停回购并将自由现金流优先降债",
                    "source_ids": ["SRC-FY"],
                },
                {
                    "failure_path": "新技术改变客户入口，既有品牌无法转化为下一代产品采用。",
                    "trigger": "下一代交易入口快速普及而公司产品接入率持续落后。",
                    "operating_impact": "客户使用频次迁移到新入口，品牌认知无法转化为实际交易。",
                    "capital_cash_impact": "补建技术与渠道需要高额投入，同时旧网络现金贡献衰减。",
                    "value_impact": "竞争优势和长期增长期缩短，终值占比对应的价值大幅下降。",
                    "probability": "medium",
                    "impact": "high",
                    "time_horizon": "5–10年",
                    "earliest_warning": "新入口交易占比上升而本公司采用率落后",
                    "reversibility": "partially_reversible",
                    "management_mitigation": "开放接口并通过合作进入下一代入口",
                    "source_ids": ["SRC-Q1"],
                },
            ],
            "bear_case": "最强悲观情形是竞争补贴、监管收紧与错误资本配置同时发生，使增长与利润率永久低于反向估值要求。",
            "fragile_assumptions": [
                "高价值客户仍愿意为可靠服务与权益组合支付溢价",
                "商户覆盖扩张不会依赖不可持续的获客补贴",
                "管理层能够在增长投资与回购纪律之间保持克制",
            ],
            "monitoring_indicators": [
                {"name": "核心客户续费率", "current_status": "仍处历史稳定区间", "trigger": "若连续四季明显低于长期均值则复核转换成本", "why_it_matters": "它直接检验客户关系和转换成本是否仍能保护经常性收入。", "recheck_method": "每季读取官方客户指标并与过去五年同季区间比较。", "source_ids": ["SRC-Q1"]},
                {"name": "单位服务收入", "current_status": "同比保持温和增长", "trigger": "若提价后收入与留存同时下降则推翻定价权判断", "why_it_matters": "收入与留存同时变化可以区分真实定价权和短期提价幻觉。", "recheck_method": "每次业绩披露后拆分价格、客户数和产品组合变化。", "source_ids": ["SRC-Q1"]},
                {"name": "商户网络覆盖", "current_status": "重点场景继续扩张", "trigger": "若新增覆盖停滞且活跃商户下降则复核网络效应", "why_it_matters": "商户覆盖决定客户使用场景以及双边网络反馈能否继续增强。", "recheck_method": "年报发布后核对活跃商户、重点场景覆盖和交易频次。", "source_ids": ["SRC-FY"]},
                {"name": "信用损失水平", "current_status": "风险指标处于目标范围", "trigger": "若损失率跨周期显著恶化则下调现金流质量", "why_it_matters": "信用损失会直接消耗会计利润、监管资本和股东可分配现金。", "recheck_method": "每季比较净核销率、逾期迁徙和拨备覆盖的跨周期趋势。", "source_ids": ["SRC-Q1"]},
                {"name": "回购价格纪律", "current_status": "回购均价低于基准价值", "trigger": "若高估值阶段仍扩大回购则下调资本配置评分", "why_it_matters": "回购价格决定股份减少是在创造还是毁坏持续股东的每股价值。", "recheck_method": "每年用回购金额除以股数复算均价并与当时价值区间比较。", "source_ids": ["SRC-FY"]},
            ],
        },
        "sources": [
            {
                "id": "SRC-FY",
                "title": "Test Company 2025 Annual Report",
                "source_type": "annual_report",
                "publisher": "Test Company",
                "url": "https://example.com/investors/2025-annual-report",
                "published_at": "2026-02-15",
                "accessed_at": "2026-04-15",
                "notes": "Audited annual filing with 96 pages used for history and capital allocation.",
            },
            {
                "id": "SRC-Q1",
                "title": "Test Company 2026 First Quarter Report",
                "source_type": "quarterly_report",
                "publisher": "Test Company",
                "url": "https://example.com/investors/2026-q1",
                "published_at": "2026-04-10",
                "accessed_at": "2026-04-15",
                "notes": "Official quarterly filing with 32 pages used for current operating evidence.",
            },
        ],
    }
    write_json(package / "company.json", company)

    claims = [
        ("CLM-001", "十年收入记录显示核心网络业务保持持续扩张且没有年度中断。", "fact", "Annual report financial statements pages 40-52", None),
        ("CLM-002", "最新季度核心客户续费仍处历史稳定区间并支持转换成本判断。", "fact", "Quarterly report operating metrics page 12", None),
        ("CLM-003", "商户覆盖增长提高了客户可用场景并形成双边网络反馈。", "fact", "Annual report network overview pages 8-10", None),
        ("CLM-004", "经营现金流长期高于资本开支使自由现金流保持为正。", "fact", "Annual report cash flow statement page 58", None),
        ("CLM-005", "回购均价低于基准价值区间体现了资本配置价格纪律。", "fact", "Annual report equity note page 74", None),
        ("CLM-006", "管理层披露利润率改善目标并在年度结果中实现了承诺。", "management_claim", "Annual report shareholder letter pages 3-5", None),
        ("CLM-007", "净现金状况为经济衰退和信用损失上升提供财务缓冲。", "fact", "Quarterly report balance sheet page 20", None),
        ("CLM-008", "单位服务收入增长而留存稳定，为公司定价能力提供直接证据。", "fact", "Quarterly report KPI table page 9", None),
        ("CLM-009", "双边网络和历史风控数据共同构成难以在短期复制的竞争优势。", "inference", None, "若新进入者两年内以更低成本达到同等覆盖和损失率则推翻该判断。"),
        ("CLM-010", "当前市场价格隐含中个位数增长与稳定利润率，安全边际并不宽。", "estimate", None, "若可验证长期增长低于百分之三或利润率跌破百分之十八则推翻估值判断。"),
    ]
    claim_modules = {
        "CLM-001": "financials",
        "CLM-002": "business",
        "CLM-003": "competition",
        "CLM-004": "financials",
        "CLM-005": "management",
        "CLM-006": "management",
        "CLM-007": "governance",
        "CLM-008": "business",
        "CLM-009": "competition",
        "CLM-010": "valuation",
    }
    critical_claim_ids = {"CLM-009", "CLM-010"}
    extended_claims = []
    for claim_id, claim, classification, location, falsifier in claims:
        source_ids = ["SRC-FY"] if claim_id not in {"CLM-002", "CLM-007", "CLM-008"} else ["SRC-Q1"]
        extended_claims.append(
            {
                "id": claim_id,
                "claim": claim,
                "classification": classification,
                "confidence": "high" if classification != "estimate" else "medium",
                "source_ids": source_ids,
                "research_module": claim_modules[claim_id],
                "decision_relevance": "critical" if claim_id in critical_claim_ids else "supporting",
                "adjudication": "upheld",
                "counterevidence": ["独立复核同时检索了相反经营趋势，但当前原件未显示足以推翻该论断的持续证据。"],
                "counterevidence_search": (
                    "隔离挑战者重新检索竞争者替代路径、监管文件和历史压力期数据，比较最强反例。"
                    if claim_id in critical_claim_ids
                    else None
                ),
                "would_falsify": falsifier or "若后续官方原件连续两个报告期显示相反趋势且无法由口径变化解释，则推翻该论断。",
                **({"location": location} if location is not None else {}),
            }
        )

    trust_findings = []
    trusted_lock = load_trusted_spec_lock(trust_findings)
    if trusted_lock is None:
        raise AssertionError(f"test fixture requires a valid bundled trust lock: {trust_findings!r}")
    all_claim_ids = [item["id"] for item in extended_claims]
    preflight = []
    for capability in (
        "protocol_access",
        "schema_access",
        "official_source_retrieval",
        "challenge_source_retrieval",
        "calculation_runtime",
        "package_write",
    ):
        source_id = {
            "official_source_retrieval": "SRC-FY",
            "challenge_source_retrieval": "SRC-Q1",
        }.get(capability)
        preflight.append(
            {
                "capability": capability,
                "status": "passed",
                "checked_at": "2026-04-15T10:00:00Z",
                "method": f"实际执行 {capability} 探针并保存可复核结果。",
                "source_id": source_id,
                "evidence_sha256": ("a" * 64 if source_id == "SRC-FY" else "b" * 64 if source_id == "SRC-Q1" else None),
                "failure_reason": None,
            }
        )

    management_decisions = [
        {
            "id": "MGT-001",
            "kind": "commitment",
            "date": "2025-02-15",
            "decision": "管理层承诺在维持核心网络投入的同时改善经营利润率。",
            "information_available": "当时收入仍增长，但竞争补贴与开发支出正在压缩利润率。",
            "public_rationale": "管理层认为优先投资高留存客户可以兼顾增长与经营效率。",
            "alternatives": ["削减所有增长投入以短期提高利润率", "维持投入但停止低回报项目"],
            "constraints": ["高价值客户迁移风险", "主要竞争者持续补贴压力", "年度资本预算边界约束"],
            "ex_ante_process": "先比较客户留存与单位经济性，再把预算集中到可验证回报的核心网络项目。",
            "process_quality": "high",
            "outcome": "2025年核心投入保持且经营利润率同比改善。",
            "outcome_quality": "positive",
            "confounders": ["行业需求同期改善也贡献了部分利润率增长"],
            "stakeholder_claim_ids": ["CLM-006"],
            "succession_dependency": "medium",
            "source_ids": ["SRC-FY"],
            "confidence": "high",
        },
        {
            "id": "MGT-002",
            "kind": "capital_allocation",
            "date": "2025-12-31",
            "decision": "公司只在回购价格低于审慎价值区间时返还多余现金。",
            "information_available": "公司拥有净现金、稳定自由现金流和可推迟的非核心投资。",
            "public_rationale": "回购必须提高持续股东每股价值并保留衰退期现金缓冲。",
            "alternatives": ["向全体股东发放特别股息", "提前偿还长期固定利率债务", "扩大外部并购与业务投资"],
            "constraints": ["公开市场估值快速波动", "经济衰退时信用损失上升风险", "董事会设定的最低现金缓冲"],
            "ex_ante_process": "管理层把回购均价与内部价值区间及压力情景流动性逐项比较。",
            "process_quality": "high",
            "outcome": "实际回购均价低于基准价值区间且资产负债表仍为净现金。",
            "outcome_quality": "positive",
            "confounders": ["报告期股价回落改善了可执行的回购价格"],
            "stakeholder_claim_ids": ["CLM-005"],
            "succession_dependency": "low",
            "source_ids": ["SRC-FY"],
            "confidence": "high",
        },
        {
            "id": "MGT-003",
            "kind": "governance",
            "date": "2026-03-31",
            "decision": "董事会维持独立风险监督并要求重大资本行动通过压力情景审查。",
            "information_available": "监管与信用损失不确定性上升，净现金仍提供可观缓冲。",
            "public_rationale": "独立监督用于保护客户承诺、资本韧性和长期股东价值。",
            "alternatives": ["把资本权限集中给首席执行官", "仅依赖年度预算审查"],
            "constraints": ["经营风险信息存在报告时滞", "跨业务风险传导具有复杂性", "关键岗位继任安排仍在推进"],
            "ex_ante_process": "风险委员会按季度审查信用、流动性和高价回购红线，并向全体董事汇报。",
            "process_quality": "mixed",
            "outcome": "截至数据日未发生突破资本红线的重大行动。",
            "outcome_quality": "positive",
            "confounders": ["尚未经历完整衰退周期，因此治理韧性仍需持续验证"],
            "stakeholder_claim_ids": ["CLM-007"],
            "succession_dependency": "medium",
            "source_ids": ["SRC-Q1"],
            "confidence": "medium",
        },
    ]

    risk_placements = []
    for index, risk in enumerate(company["risks"]["pre_mortem"]):
        placement = ("cash_flow", "scenario", "tail_case", "discount_rate", "cash_flow")[index]
        risk_placements.append(
            {
                "risk": risk["failure_path"],
                "placement": placement,
                "scenario": "悲观情景" if placement == "scenario" else "压力尾部情景" if placement == "tail_case" else None,
                "rationale": "该风险只通过这一经济传导位置进入估值，已检查其他现金流、情景和折现率参数以避免重复扣罚。",
                "claim_ids": ["CLM-009" if index < 3 else "CLM-010"],
            }
        )

    sensitivity_cells = [
        {
            "discount_rate": item["discount_rate"],
            "terminal_growth": item["terminal_growth"],
            "valuation_status": "接近合理",
        }
        for item in company["valuation"]["dcf_sensitivity"]
    ]
    seed = canonical_company_sha256(company)
    ordinary_ids = [item["id"] for item in extended_claims if item["decision_relevance"] != "critical"]
    sampled_ids = deterministic_ordinary_claim_sample(ordinary_ids, seed)
    claim_by_id = {item["id"]: item for item in extended_claims}

    def audit_check(
        check_id: str,
        target_type: str,
        target_id: str,
        criticality: str,
        source_ids: list[str],
        observed_value: object,
    ) -> dict:
        return {
            "id": check_id,
            "target_type": target_type,
            "target_id": target_id,
            "criticality": criticality,
            "source_ids": source_ids,
            "status": "pass",
            "checked_at": "2026-04-15T12:00:00Z",
            "location": "重新打开的官方原件对应页码与结构化披露位置",
            "observed": "隔离审计者重新读取原件并复核目标值、口径与期间一致。",
            "observed_value": observed_value,
            "notes": "该检查独立于主研究记录完成并保存了来源定位。",
        }

    source_checks = [
        audit_check("AUD-IDENTITY", "company_field", "company.meta.identity", "critical", ["SRC-FY"], {"company_name_en": "Test Company", "ticker": "TEST", "exchange": "NYSE"}),
        audit_check("AUD-PRICE", "company_field", "company.valuation.market_price", "critical", ["SRC-Q1"], 10),
        audit_check("AUD-SHARES", "company_field", "company.valuation.diluted_shares", "critical", ["SRC-Q1"], 100 * M),
        audit_check("AUD-MCAP", "company_field", "company.valuation.market_cap", "critical", ["SRC-Q1"], 1000 * M),
        audit_check("AUD-EV", "company_field", "company.valuation.enterprise_value", "critical", ["SRC-Q1"], 970 * M),
        audit_check("AUD-START", "calculation", "calculation.starting_cash_flow", "critical", ["SRC-FY"], starting_fcff),
        audit_check(
            "AUD-DCF",
            "valuation_assumption",
            "valuation.dcf_assumptions",
            "critical",
            ["SRC-FY"],
            {
                "scenarios": sorted(
                    [
                        {
                            "name": item["name"],
                            "revenue_growth": item["revenue_growth"],
                            "margin": item["margin"],
                            "discount_rate": item["discount_rate"],
                            "terminal_growth": item["terminal_growth"],
                        }
                        for item in dcf_scenarios
                    ],
                    key=lambda item: item["name"],
                ),
                "equity_bridge_calculation_ids": sorted(
                    item["id"]
                    for item in dcf_calculations
                    if item.get("valuation_role") == "equity_value_bridge"
                ),
            },
        ),
    ]
    for claim_id in sorted(critical_claim_ids):
        claim = claim_by_id[claim_id]
        source_checks.append(audit_check(f"AUD-{claim_id}", "claim", claim_id, "critical", claim["source_ids"], None))
    for claim_id in sampled_ids:
        claim = claim_by_id[claim_id]
        source_checks.append(audit_check(f"AUD-{claim_id}", "claim", claim_id, "ordinary", claim["source_ids"], None))

    evidence = {
        "ledger_version": "2.0",
        "business_model": make_business_model_fixture(company),
        "run": {
            "run_id": "RUN-TEST-2026Q1",
            "research_mode": "full",
            "workflow_tier": "standard",
            "data_cutoff_at": "2026-04-15T12:00:00Z",
            "status": "ready_to_freeze",
            "protocol_fingerprint": protocol_fingerprint(trusted_lock),
            "preflight": preflight,
            "passes": [
                {"id": "PASS-PRIMARY", "role": "primary_research", "actor_id": "researcher-primary", "execution": "primary_context", "status": "completed", "scope": "完成公司身份、财务、经营与估值主研究。", "claim_ids": all_claim_ids, "source_ids_accessed": ["SRC-FY", "SRC-Q1"]},
                {"id": "PASS-CHALLENGE", "role": "adversarial_review", "actor_id": "researcher-challenge", "execution": "isolated_agent", "status": "completed", "scope": "独立检索最强反例并挑战关键竞争与估值论断。", "claim_ids": sorted(critical_claim_ids), "source_ids_accessed": ["SRC-FY", "SRC-Q1"]},
                {"id": "PASS-AUDIT", "role": "source_audit", "actor_id": "researcher-audit", "execution": "isolated_agent", "status": "completed", "scope": "重新打开来源并核验关键值及确定性普通样本。", "claim_ids": sorted(critical_claim_ids | set(sampled_ids)), "source_ids_accessed": ["SRC-FY", "SRC-Q1"]},
                {"id": "PASS-SYNTHESIS", "role": "synthesis", "actor_id": "researcher-synthesis", "execution": "synthesis_context", "status": "completed", "scope": "综合共识、冲突、遗漏与无法裁决项并形成最终结论。", "claim_ids": all_claim_ids, "source_ids_accessed": []},
            ],
        },
        "researchability": {
            "official_source_coverage": "high",
            "operating_kpi_coverage": "medium",
            "third_party_verifiability": "medium",
            "timeliness": "high",
            "opacity": "low",
            "evidence_confidence": "high",
            "thesis_certainty": "medium",
            "assessment": "官方财务和核心经营指标覆盖充分，但长期竞争反事实仍需要跨周期资料验证，资料可得性与论点确定性分别评价。",
            "limitations": ["第三方客户级留存资料有限，当前主要依赖可定位的官方经营指标。"],
        },
        "business_driver_map": {
            "equation": "活跃客户数量乘以单位服务收入，再扣除服务成本与必要资本投入，形成可分配现金。",
            "value_capture_chain": ["可靠服务提高客户留存与使用频率", "更高使用量和单位收入转化为经营现金", "扣除维护投入后形成股东可分配现金"],
            "drivers": [
                {
                    "id": "DRV-RETENTION", "name": "核心客户续费", "metric": "核心客户续费率", "definition": "报告期继续使用核心服务的高价值客户比例", "historical_baseline": "过去五年保持在稳定高位区间", "current_state": "最新季度仍处历史稳定区间", "causal_role": "retention", "direction_and_mechanism": "续费提高会延长客户寿命并降低替换获客成本", "cash_flow_link": "通过经常性收入和较低获客支出提高自由现金流", "moat_link": "持续高续费验证账户历史和流程嵌入形成的转换成本", "valuation_link": "决定基准情景收入增长与利润率持续性", "monitoring_indicator": "每季将续费率与过去五年同季区间比较", "source_ids": ["SRC-Q1"], "confidence": "high", "counterevidence": ["标准化接口可能降低部分客户迁移成本"], "would_falsify": "若续费率连续四季明显低于长期均值且竞争者同步获客，则推翻该驱动。"
                },
                {
                    "id": "DRV-UNIT-REVENUE", "name": "单位服务收入", "metric": "每活跃客户服务收入", "definition": "核心服务收入除以同口径活跃客户数量", "historical_baseline": "过去五年随产品组合温和提升", "current_state": "最新季度仍保持同比增长", "causal_role": "price", "direction_and_mechanism": "在留存稳定时单位收入增长反映定价和产品组合改善", "cash_flow_link": "单位收入增长在固定平台成本下提高经营现金率", "moat_link": "提价后留存稳定可验证可靠性和权益组合的付费价值", "valuation_link": "连接悲观、基准和乐观情景的收入增长假设", "monitoring_indicator": "每季拆分价格、客户数和产品组合对单位收入的贡献", "source_ids": ["SRC-FY", "SRC-Q1"], "confidence": "medium", "counterevidence": ["短期产品组合变化可能制造表面单位收入增长"], "would_falsify": "若单位收入上涨同时续费和使用频率持续下降，则推翻定价能力判断。"
                },
            ],
        },
        "management_decision_ledger": management_decisions,
        "thesis": {
            "overall_change": "baseline",
            "assumptions": [
                {"id": "ASM-RETENTION", "assumption": company["verdict"]["key_assumptions"][0], "importance": "core", "prior_status": None, "current_status": "supported", "change_type": "baseline", "evidence_claim_ids": ["CLM-002", "CLM-008"], "reason": "续费与单位服务收入的历史及最新官方数据共同支持该假设。", "falsifier": "若续费连续四季跌破历史区间且提价不能抵消流失，该假设失效。", "red_lines": ["核心客户续费连续四季明显低于长期均值"], "next_validation": "下一季官方报告发布后重新核对续费与单位收入。"},
                {"id": "ASM-COVERAGE", "assumption": company["verdict"]["key_assumptions"][1], "importance": "core", "prior_status": None, "current_status": "supported", "change_type": "baseline", "evidence_claim_ids": ["CLM-003", "CLM-009"], "reason": "商户覆盖增长和网络反馈证据支持扩张可以抵消竞争压力。", "falsifier": "若新增覆盖依赖持续补贴且活跃商户下降，该假设失效。", "red_lines": ["活跃商户连续下降且新增覆盖停滞"], "next_validation": "下一份年报核对活跃商户、补贴和交易频次。"},
            ],
            "valuation_assumption_changes": [],
            "rejected_claim_ids": [],
            "unresolved_conflicts": [],
            "revision_log": [
                {"id": "REV-BASELINE", "changed_at": "2026-04-15T12:00:00Z", "change_type": "baseline", "summary": "建立首次完整研究的假设状态、估值参数和来源审计基线。", "affected_assumption_ids": ["ASM-RETENTION", "ASM-COVERAGE"], "evidence_claim_ids": ["CLM-002", "CLM-003", "CLM-008", "CLM-009"]}
            ],
        },
        "valuation_review": {
            "model_applicability": [
                {"model": "FCFF DCF", "role": "primary", "status": "appropriate", "reason": "经营现金流和必要资本投入可由十年记录复算，适合作为主模型。", "key_assumptions": ["核心客户续费稳定", "利润率随规模温和改善"], "result_direction": "fair"},
                {"model": "Reverse DCF", "role": "reverse", "status": "appropriate", "reason": "可从现价反推现金增长与再投资组合并与历史事实比较。", "key_assumptions": ["现价与稀释后股数同期", "起始现金流口径与主模型一致"], "result_direction": "fair"},
                {"model": "FCF yield cross-check", "role": "cross_check", "status": "limited", "reason": "倍数可识别主模型异常但无法独立表达长期再投资路径。", "key_assumptions": ["自由现金流口径可比", "净现金调整同期一致"], "result_direction": "fair"},
            ],
            "risk_placements": risk_placements,
            "model_conflicts": [],
            "conclusion_stability": {"cells": sensitivity_cells, "verdict_flip": False, "action": "maintain", "explanation": "九格在审慎参数范围内均保持接近合理，当前结论不依赖单一相邻参数组合。"},
        },
        "source_audit": {"audit_pass_id": "PASS-AUDIT", "selection_seed": seed, "checks": source_checks},
        "claims": extended_claims,
    }
    write_json(package / "evidence-ledger.json", evidence)
    write_json(
        package / "calculation-ledger.json",
        {
            "numeric_convention": "base_units",
            "income_statement_sankey": {
                "fiscal_year": "FY2025",
                "source_ids": ["SRC-FY"],
                "review_method": "逐行核对合并利润表和成本费用附注，确认所有单列项目均已建立节点并复算勾稽。",
                "disclosed_line_items": [
                    {"node_id": "product_revenue", "value": 120 * M, "source_ids": ["SRC-FY"], "location": "Annual report income statement p. 50"},
                    {"node_id": "subscription_revenue", "value": 70 * M, "source_ids": ["SRC-FY"], "location": "Annual report income statement p. 50"},
                    {"node_id": "revenue", "value": 190 * M, "source_ids": ["SRC-FY"], "location": "Annual report income statement p. 50"},
                    {"node_id": "fulfillment_cost", "value": 70 * M, "source_ids": ["SRC-FY"], "location": "Annual report expense note p. 67"},
                    {"node_id": "product_development", "value": 30 * M, "source_ids": ["SRC-FY"], "location": "Annual report expense note p. 67"},
                    {"node_id": "sales_marketing", "value": 25 * M, "source_ids": ["SRC-FY"], "location": "Annual report expense note p. 67"},
                    {"node_id": "general_admin", "value": 15 * M, "source_ids": ["SRC-FY"], "location": "Annual report expense note p. 67"},
                    {"node_id": "pretax_profit", "value": 50 * M, "source_ids": ["SRC-FY"], "location": "Annual report income statement p. 50"},
                    {"node_id": "income_tax", "value": 14 * M, "source_ids": ["SRC-FY"], "location": "Annual report income statement p. 50"},
                    {"node_id": "profit", "value": 36 * M, "source_ids": ["SRC-FY"], "location": "Annual report income statement p. 50"},
                ],
                "calculated_nodes": [
                    {"node_id": "pretax_costs", "calculation_id": "CALC-SANKEY-PRETAX-COSTS"}
                ],
                "calculated_links": [
                    {"source": "revenue", "target": "pretax_profit", "calculation_id": "CALC-SANKEY-REVENUE-TO-PRETAX"}
                ],
                "color_audit": {
                    "contract_version": "1.0.0",
                    "provider": "App Economy Insights",
                    "site_origin": "https://www.appeconomyinsights.com/",
                    "completed_at": "2026-04-15T04:00:00Z",
                    "alias_review": {
                        "completed": True,
                        "review_method": "已核对 company.json 身份字段与官方公司资料中的常用简称和品牌名，本测试公司没有额外可验证别名。",
                        "aliases": [],
                    },
                    "mode": "not_found",
                    "queries": [
                        {
                            "identity_kind": identity_kind,
                            "query_variant": query_variant,
                            "identity_value": identity_value,
                            "query": (
                                f'site:appeconomyinsights.com "{identity_value}" Sankey'
                                if query_variant == "sankey"
                                else f'site:appeconomyinsights.com "{identity_value}" "earnings visuals"'
                            ),
                            "searched_at": "2026-04-15T03:30:00Z",
                            "outcome": "no_match",
                            "checked_urls": [],
                            "blocker_code": None,
                            "notes": "已完成规定检索，未发现可直接核验的该公司利润表桑基图。",
                        }
                        for identity_kind, identity_value in (
                            ("english_name", "Test Company"),
                            ("chinese_name", "测试公司"),
                            ("ticker", "TEST"),
                        )
                        for query_variant in ("sankey", "earnings_visuals")
                    ],
                    "source_page_url": None,
                    "opened_at": None,
                    "direct_verification": None,
                    "source_image": None,
                    "node_samples": [],
                    "default_palette_version": "semantic-default-v1",
                    "blockers": [],
                },
            },
            "calculations": [
                {"id": "CALC-SANKEY-PRETAX-COSTS", "metric": "custom", "sankey_node_id": "pretax_costs", "period": "FY2025", "formula": "total_revenue - pretax_profit", "inputs": {"total_revenue": 190 * M, "pretax_profit": 50 * M}, "result": 140 * M, "review_method": "将总收入减税前利润，并与四项已披露税前成本费用合计交叉复算。", "source_ids": ["SRC-FY"]},
                {"id": "CALC-SANKEY-REVENUE-TO-PRETAX", "metric": "custom", "sankey_source": "revenue", "sankey_target": "pretax_profit", "period": "FY2025", "formula": "total_revenue - pretax_costs", "inputs": {"total_revenue": 190 * M, "pretax_costs": 140 * M}, "result": 50 * M, "review_method": "用总收入扣除已复算税前成本与费用，独立核对利润主链续接金额。", "source_ids": ["SRC-FY"]},
                {"id": "CALC-FCF", "metric": "free_cash_flow", "period": "FY2025", "formula": "operating_cash_flow - capex_total", "inputs": {"operating_cash_flow": 48 * M, "capex_total": 19 * M}, "result": 29 * M, "source_ids": ["SRC-FY"]},
                {"id": "CALC-ND", "metric": "net_debt", "period": "FY2025", "formula": "total_debt - cash", "inputs": {"total_debt": 19 * M, "cash": 50 * M}, "result": -31 * M, "source_ids": ["SRC-FY"]},
                {"id": "CALC-MC", "metric": "market_cap", "period": "2026-04-15", "formula": "market_price * diluted_shares", "inputs": {"market_price": 10, "diluted_shares": 100 * M}, "result": 1000 * M, "source_ids": ["SRC-Q1"]},
                {"id": "CALC-EV", "metric": "enterprise_value", "period": "2026-04-15", "formula": "market_cap + net_debt", "inputs": {"market_cap": 1000 * M, "net_debt": -30 * M}, "result": 970 * M, "source_ids": ["SRC-Q1"]},
                {"id": "CALC-DCF-START", "metric": "custom", "valuation_role": "starting_cash_flow", "cash_flow_basis": "fcff", "period": "FY2025", "formula": "operating_cash_flow - capex_total", "inputs": {"operating_cash_flow": 48 * M, "capex_total": 19 * M}, "result": 29 * M, "diluted_shares": 100 * M, "per_share": 0.29, "forecast_years": 10, "review_method": "逐项核对经营现金流、总资本开支与稀释后股数，并独立复算总额及每股金额。", "source_ids": ["SRC-FY"]},
                *dcf_calculations,
            ]
        },
    )

    scenario_rows = "\n".join(
        "| {name} | {growth:.1%} | {discount:.1%} | {terminal:.1%} | {share:.1%} | {value:.4f}美元/股 |".format(
            name=dcf_display[code]["name"],
            growth=dcf_display[code]["growth"],
            discount=dcf_display[code]["discount_rate"],
            terminal=dcf_display[code]["terminal_growth"],
            share=dcf_display[code]["terminal_share"],
            value=dcf_display[code]["per_share_value"],
        )
        for code in ("bear", "base", "bull")
    )
    annual_rows = "\n".join(
        "| {name} | 第{year}年 | {cash:.6f} | {factor:.6f} | {pv:.6f} |".format(
            name=dcf_display[code]["name"],
            year=record["forecast_year"],
            cash=record["inputs"]["cash_flow"] / 1e8,
            factor=record["inputs"]["discount_factor"],
            pv=record["result"] / 1e8,
        )
        for code in ("bear", "base", "bull")
        for record in dcf_display[code]["annual_records"]
    )
    terminal_rows = "\n".join(
        "| {name} | {last_cash:.6f} | {growth:.1%} | {discount:.1%} | {terminal_value:.6f} | {factor:.6f} | {terminal_pv:.6f} |".format(
            name=dcf_display[code]["name"],
            last_cash=dcf_display[code]["last_cash_flow"] / 1e8,
            growth=dcf_display[code]["terminal_growth"],
            discount=dcf_display[code]["discount_rate"],
            terminal_value=dcf_display[code]["terminal_value"] / 1e8,
            factor=dcf_display[code]["annual_records"][-1]["inputs"]["discount_factor"],
            terminal_pv=dcf_display[code]["terminal_pv"] / 1e8,
        )
        for code in ("bear", "base", "bull")
    )
    value_rows = "\n".join(
        "| {name} | {explicit:.6f} | {terminal:.6f} | -0.300000 | {equity:.6f} | 1 | {value:.4f} |".format(
            name=dcf_display[code]["name"],
            explicit=dcf_display[code]["explicit_pv"] / 1e8,
            terminal=dcf_display[code]["terminal_pv"] / 1e8,
            equity=dcf_display[code]["equity_value"] / 1e8,
            value=dcf_display[code]["per_share_value"],
        )
        for code in ("bear", "base", "bull")
    )
    sensitivity_rows = "\n".join(
        "| {discount:.0%} | {terminal:.1%} | {value:.4f}美元/股 |".format(
            discount=item["discount_rate"],
            terminal=item["terminal_growth"],
            value=item["fair_value_per_share"],
        )
        for item in dcf_sensitivity
    )

    sections = [
        (
            "一页式结论",
            """测试公司 TEST 的价值来自双边网络、复购关系与持续现金流，当前价格只适合观察。论点破坏点（Thesis breakers：一旦发生就会推翻核心投资判断的可验证条件）列在下表。证据见 SRC-FY 和 SRC-Q1。

| 项目 | 结论 |
|---|---|
| 企业质量 | 良好 |
| 估值状态 | 接近合理 |
| 研究状态 | 观察名单 |
| 置信度 | 高 |
| 关键假设 | 1. 核心客户续费率保持稳定且单位服务收入继续温和增长<br>2. 商户覆盖扩大能够抵消竞争补贴带来的利润率压力 |
| Thesis breakers | 1. 连续四个季度核心客户净流失并伴随单位经济性恶化<br>2. 监管变化永久削弱网络收费能力且无法通过产品升级弥补 |""",
        ),
        ("身份、日期与完整度", "本研究对象是纽约证券交易所 TEST，数据截至二零二六年一季度，估值日为四月十五日。法定身份、币种和口径已逐项核对。"),
        ("商业模式", "公司连接高价值客户与商户，从网络服务和会员关系中收费。更多覆盖提升使用频率，交易数据又改善风控与产品匹配。"),
        ("十年财务", "十年收入、利润和现金流均按同一财年口径排列。增长并非直线，但核心年度记录完整，股份数量下降使每股结果优于总量。"),
        ("自由现金流与 Owner Earnings", "自由现金流（FCF：经营现金流扣除资本开支后的余额）长期为正。所有者收益（Owner Earnings：维持竞争力后真正可供股东支配的现金）还要考虑获客投入和信用损失，因此不把全部会计利润视为可分配现金。"),
        ("ROIC 与投入资本回报", "投入资本回报率（ROIC：每投入1元经营资本能产生多少税后经营利润）随网络利用率提高而改善。判断重点是增量资本能否继续带来客户留存和单位利润，而不是只看单年高回报。"),
        (
            "护城河",
            """定价权、难复制、转换成本和网络效应必须分别接受证据与反证检验，不能只用品牌叙事代替验证。

| 维度 | 评分 / 5 | 趋势 | 置信度 | 支持证据 | 最强反证 | 最可能的破坏因素 |
|---|---|---|---|---|---|---|
| 定价权 | 4.0 / 5 | 稳定 | 高 | 提价后单位服务收入增长且留存仍处稳定区间〔SRC-FY〕 | 竞争者以补贴压低同类服务的有效价格〔SRC-FY〕 | 客户认为权益同质化并集体降级套餐 |
| 难复制 | 4.0 / 5 | 稳中增强 | 中 | 长期交易数据改善风控并降低新增客户损失〔SRC-FY〕 | 新进入者可购买外部数据快速训练模型〔SRC-FY〕 | 开放数据规则使历史数据优势失去稀缺性 |
| 转换成本 | 3.5 / 5 | 稳定 | 中 | 核心客户续费稳定且商户受理关系覆盖广泛〔SRC-Q1〕 | 多归属让客户保留竞争网络的使用选择〔SRC-Q1〕 | 新入口自动迁移账户降低主动切换摩擦 |
| 网络效应 | 4.5 / 5 | 增强 | 中 | 商户覆盖增加带来更多使用场景与交易反馈〔SRC-Q1〕 | 平台补贴可能制造缺乏利润的表面增长〔SRC-Q1〕 | 大型钱包封闭流量并绕开现有网络连接 |""",
        ),
        (
            "长期生存与十年后需求",
            """可靠交易、短期信用和身份信任具有长期需求。公司能否生存二十年取决于持续适应新入口，而不是依赖今天的产品形式。

观察期限：20年

总体状态：conditional

结论：需求本身可持续，但公司必须持续适配新入口并抵御监管与技术冲击。

| 维度 | 状态 | 判断 | 证据 | 破坏条件 |
|---|---|---|---|---|
| 需求持久性 | strong | 可靠交易、短期信用和身份信任在二十年后仍有明确需求。 | 正式披露显示核心客户持续为可靠性、信用与权益组合付费〔SRC-FY〕。 | 若实时支付与开放身份基础设施使现有服务不再具有独立付费价值。 |
| 适应能力 | adequate | 既有网络和数据能够支持迁移，但下一代入口的采用速度仍需验证。 | 公司持续扩大数字入口接入并把既有风控能力迁移到新产品〔SRC-Q1〕。 | 若新入口交易占比持续上升而公司接入率连续多年落后。 |
| 外部冲击 | uncertain | 监管、数据使用限制与替代网络可能同时削弱现金流和资本弹性。 | 季度披露把监管资本、信用损失和数据合规列为持续风险〔SRC-Q1〕。 | 若监管变化永久限制关键数据并要求大幅提高资本缓冲。 |""",
        ),
        (
            "企业文化、管理层与资本配置",
            """管理层披露目标时同时说明成本和约束，资本优先投向核心网络。承诺不能只看口号，必须把结果与下一次验证写在同一条时间线上。

| 日期 | 承诺 | 兑现状态 | 实际结果 | 下一次验证 |
|---|---|---|---|---|
| 2025-02-15 | 管理层承诺保持核心网络投入同时改善经营利润率。 | fulfilled | 2025年收入增长并且经营利润率同比提升。 | 下一份年报逐项核对核心网络投入、收入增速与经营利润率。若网络投入保持且经营利润率不低于2025年水平，则承诺继续成立。FY2026年报发布后 |

| 期间 | 类别 | 金额 | 车道 | 结果状态 | 结果 | 评价 |
|---|---|---:|---|---|---|---|
| FY2025 | buyback | 0.18亿美元 | shareholder_return | positive | 稀释后股份同比净减少百分之二，并且未削弱净现金头寸。 | 回购均价低于当时审慎价值区间，提升了持续股东的每股权益。 |

Stop Doing List：不为短期收入进入无法形成客户数据闭环的邻近业务；不在高于审慎内在价值区间时机械扩大股份回购。""",
        ),
        ("回购明细", "回购金额、股份和均价分别入账，避免把减少股数自动视为创造价值。只有均价低于审慎内在价值且不削弱资产负债表时才加分。"),
        ("治理、债务与红旗", "净现金提供缓冲，但监管、数据治理和激励结构仍需季度复核。若管理层改变资本纪律或隐藏关键损失，将构成治理红旗。"),
        (
            "Reverse DCF 与估值",
            f"""现金流折现（DCF：把未来每年的可分配现金换算成估值日价值）用于估算内在价值；反向现金流折现（Reverse DCF：从当前股价反推市场已经计入的经营要求）用于检查现价是否苛刻。现价要求中个位数可分配现金增长和稳定再投资率，与历史大致相符但安全边际有限。

企业自由现金流（FCFF：扣除维持经营和增长所需投入后，可供债权人和股东共同分配的现金）从FY2025经营现金流0.48亿美元减资本开支0.19亿美元得到0.29亿美元。预测期固定为第1—10年；本例收入与FCFF在每个情景中采用相同增速，不假设额外利润率扩张。

| 现金流口径 | 基准期间 | 估值基准日现金总额 | 稀释后股数 | 基准日每股现金 | 显性预测期 |
|---|---|---|---|---|---|
| FCFF | FY2025 | 0.29亿美元 | 1亿股 | 0.29美元/股 | 10年 |

| 情景 | 收入增长与FCFF增长（第1—10年） | 折现率 | 永续增长 | 终值占比 | 每股价值 |
|---|---|---|---|---|---|
{scenario_rows}

逐年计算使用“当年现金流现值 = 可分配现金流 × 折现因子”。折现因子表示未来1元现金换算到估值日还值多少。

| 情景 | 预测年度（年） | 可分配现金流（亿美元） | 折现因子 | 现金流现值（亿美元） |
|---|---|---:|---:|---:|
{annual_rows}

终值表示第10年之后全部现金流在第10年末的合计价值。公式为：预测期末终值 = 第10年现金流 ×（1 + 永续增长率）÷（折现率 − 永续增长率）；终值现值 = 预测期末终值 × 第10年折现因子。

| 情景 | 最后一年现金流（亿美元） | 永续增长 | 折现率 | 预测期末终值（亿美元） | 末年折现因子 | 终值现值（亿美元） |
|---|---:|---:|---:|---:|---:|---:|
{terminal_rows}

因为这里折现的是FCFF，先得到企业经营价值，再减去净债务；负净债务代表净现金，所以会增加股权价值。最后用股权价值除以稀释后股数。

| 情景 | 显性期现金流现值（亿美元） | 终值现值（亿美元） | 净债务调整（亿美元） | 股权价值（亿美元） | 稀释后股数（亿股） | 每股价值（美元/股） |
|---|---:|---:|---:|---:|---:|---:|
{value_rows}

下表是敏感性测试：只改变折现率和永续增长率，观察基准情景每股价值怎样变化，避免只展示最有利的参数组合。

| 折现率 | 永续增长 | 每股价值 |
|---|---|---|
{sensitivity_rows}

| Reverse DCF 假设 | 隐含值 | 历史比较 | 推翻阈值 |
|---|---|---|---|
| FCFF增长 | 7% | 接近历史五年可分配现金增长区间 | 连续三年低于3%则现价要求过高 |
| 资本再投资率 | 22% | 略高于历史资本再投资中位数 | 连续三年高于35%则推翻基准判断 |""",
        ),
        (
            "Pre-Mortem 事前验尸",
            """事前验尸（Pre-Mortem：先假设投资已经失败，再倒推最可能的原因）显示，永久损失往往来自多个变量叠加，因此每条失败路径都预先定义时间与最早预警。

| 失败路径 | 触发因素 | 经营影响 | 资本 / 现金影响 | 价值影响 | 概率 | 影响 | 期限 | 最早预警 | 可逆性 | 管理层缓解 |
|---|---|---|---|---|---|---|---|---|---|---|
| 核心客户因产品体验停滞而迁移，续费下降导致单位经济性失效。 | 核心产品迭代长期落后并使高价值客户连续多个季度流失。 | 续费率和单位服务收入同步下降，获客成本回收期明显拉长。 | 维持客户规模需要加大补贴与营销支出，自由现金流率收缩。 | 可分配现金增长转负并压低合理估值区间与长期复利能力。 | 中 | 高 | 1–3年 | 续费率连续四季低于长期均值 | 部分可逆 | 重做核心权益并降低无效获客支出 |
| 商户侧出现更低成本替代网络，覆盖优势逐步转为固定成本负担。 | 替代网络以更低综合成本覆盖核心高频商户并形成规模。 | 活跃商户和交易频次下降，网络收入与数据反馈同时减弱。 | 既有受理基础设施利用率下降，但维护成本难以同步削减。 | 网络效应反转并导致利润率和终值增长假设永久下调。 | 中低 | 高 | 3–5年 | 活跃商户下降且新增覆盖连续停滞 | 难以逆转 | 调整受理费率并投资高频使用场景 |
| 监管限制数据使用范围，风控准确性下降并推高信用损失。 | 新监管规则禁止关键风险变量用于授信和持续账户管理。 | 风险识别能力下降，批准率、客户体验和信用损失同时承压。 | 拨备和监管资本需求上升，能够返还股东的现金减少。 | 正常化股东现金流下降且股权成本上升，内在价值显著受损。 | 低 | 严重 | 1–2年 | 合规征询文件扩大禁止使用的数据范围 | 难以逆转 | 提前建设替代变量与人工复核流程 |
| 管理层在高估值阶段过度回购，削弱应对衰退的资产负债表弹性。 | 回购金额在估值偏高且宏观风险上升时仍明显扩张。 | 核心经营短期不变，但管理层资本纪律和逆周期能力受到质疑。 | 现金缓冲下降并可能增加举债，使衰退期融资成本上升。 | 每股价值被高价回购摧毁，安全边际和长期回报率下降。 | 中 | 重大 | 1–3年 | 回购均价显著超过基准内在价值区间 | 部分可逆 | 暂停回购并将自由现金流优先降债 |
| 新技术改变客户入口，既有品牌无法转化为下一代产品采用。 | 下一代交易入口快速普及而公司产品接入率持续落后。 | 客户使用频次迁移到新入口，品牌认知无法转化为实际交易。 | 补建技术与渠道需要高额投入，同时旧网络现金贡献衰减。 | 竞争优势和长期增长期缩短，终值占比对应的价值大幅下降。 | 中 | 高 | 5–10年 | 新入口交易占比上升而本公司采用率落后 | 部分可逆 | 开放接口并通过合作进入下一代入口 |

| 补充诊断 | 明确结论 |
|---|---|
| 最强反方观点 | 最强悲观情形是竞争补贴、监管收紧与错误资本配置同时发生，使增长与利润率永久低于反向估值要求。 |
| 三个最脆弱假设 | 1. 高价值客户仍愿意为可靠服务与权益组合支付溢价<br>2. 商户覆盖扩张不会依赖不可持续的获客补贴<br>3. 管理层能够在增长投资与回购纪律之间保持克制 |
| Thesis breakers | 1. 连续四个季度核心客户净流失并伴随单位经济性恶化<br>2. 监管变化永久削弱网络收费能力且无法通过产品升级弥补 |
| 破产路径 | 监管处罚与信用损失同时激增，流动性储备耗尽并触发债务违约，股权价值可能归零。 |
| 存活但股东回报差 | 公司仍能运营，但竞争补贴和高价回购长期压低每股自由现金流，回报低于资本成本。 |""",
        ),
        ("待调查与 Open Questions", "尚待调查企业客户分层留存、商户边际获客成本和新入口使用率。下一轮将优先取得正式分部附注和更细的信用数据，并核对不同客户层的历史迁移与盈利差异。"),
        (
            "领先指标与 Monitoring Indicators",
            """季度跟踪续费、单位收入、商户覆盖、信用损失和回购均价。每项指标都有不同阈值、重要性和复查动作，用于检验护城河、现金流和资本配置。

| 指标 | 当前状态 | 触发阈值 | 为什么重要 | 复查方法 |
|---|---|---|---|---|
| 核心客户续费率 | 仍处历史稳定区间 | 若连续四季明显低于长期均值则复核转换成本 | 它直接检验客户关系和转换成本是否仍能保护经常性收入。 | 每季读取官方客户指标并与过去五年同季区间比较。 |
| 单位服务收入 | 同比保持温和增长 | 若提价后收入与留存同时下降则推翻定价权判断 | 收入与留存同时变化可以区分真实定价权和短期提价幻觉。 | 每次业绩披露后拆分价格、客户数和产品组合变化。 |
| 商户网络覆盖 | 重点场景继续扩张 | 若新增覆盖停滞且活跃商户下降则复核网络效应 | 商户覆盖决定客户使用场景以及双边网络反馈能否继续增强。 | 年报发布后核对活跃商户、重点场景覆盖和交易频次。 |
| 信用损失水平 | 风险指标处于目标范围 | 若损失率跨周期显著恶化则下调现金流质量 | 信用损失会直接消耗会计利润、监管资本和股东可分配现金。 | 每季比较净核销率、逾期迁徙和拨备覆盖的跨周期趋势。 |
| 回购价格纪律 | 回购均价低于基准价值 | 若高估值阶段仍扩大回购则下调资本配置评分 | 回购价格决定股份减少是在创造还是毁坏持续股东的每股价值。 | 每年用回购金额除以股数复算均价并与当时价值区间比较。 |""",
        ),
        (
            "最终结论",
            """公司质量良好但价格接近合理，应等待更宽安全边际，并让八个判断维度分别保留可推翻的反证。

| 项目 | 结论 |
|---|---|
| 企业质量 | 良好 |
| 估值状态 | 接近合理 |
| 研究状态 | 观察名单 |
| 置信度 | 高 |
| 关键假设 | 1. 核心客户续费率保持稳定且单位服务收入继续温和增长<br>2. 商户覆盖扩大能够抵消竞争补贴带来的利润率压力 |
| Thesis breakers | 1. 连续四个季度核心客户净流失并伴随单位经济性恶化<br>2. 监管变化永久削弱网络收费能力且无法通过产品升级弥补 |

| 维度 | 评分 / 5 | 置信度 | 核心证据 | 最强反证 |
|---|---|---|---|---|
| 生意可理解性 | 4.5 / 5 | 高 | 收费方、客户价值和网络反馈机制均可直接解释〔SRC-FY〕 | 信用与服务收入之间仍存在复杂交叉补贴〔SRC-FY〕 |
| 财务与现金流 | 4.0 / 5 | 高 | 十年经营现金流长期覆盖全部资本开支〔SRC-FY〕 | 信用损失恶化会让会计利润领先真实现金回收〔SRC-Q1〕 |
| ROIC与再投资 | 4.0 / 5 | 中 | 网络利用率提高时增量利润快于投入资本增长〔SRC-FY〕 | 新获客成本上升可能压低未来增量资本回报〔SRC-Q1〕 |
| 护城河 | 4.0 / 5 | 中 | 留存、商户覆盖和历史风控数据相互强化〔SRC-Q1〕 | 多归属允许客户和商户同时使用竞争网络〔SRC-Q1〕 |
| 长期生存 | 4.0 / 5 | 中 | 可靠交易、短期信用和身份信任需求持久〔SRC-FY〕 | 下一代入口可能将品牌与网络抽象成后台能力〔SRC-Q1〕 |
| 文化、管理层和资本配置 | 4.0 / 5 | 中 | 已披露目标兑现且回购均价低于基准价值〔SRC-FY〕 | 管理层可能在高估值阶段恢复机械回购〔SRC-FY〕 |
| 会计、治理和资产负债表 | 4.0 / 5 | 高 | 净现金与正式监管披露提供跨周期缓冲〔SRC-Q1〕 | 数据治理处罚可能暴露尚未量化的内部缺陷〔SRC-Q1〕 |
| 估值与安全边际 | 3.0 / 5 | 中 | 反向估值隐含增长接近历史可实现区间〔SRC-Q1〕 | 现价缺少抵御利润率永久下降的宽安全垫〔SRC-Q1〕 |""",
        ),
    ]
    inline_sources = {
        "商业模式": "SRC-FY",
        "十年财务": "SRC-FY",
        "自由现金流与 Owner Earnings": "SRC-FY",
        "ROIC 与投入资本回报": "SRC-FY",
        "护城河": "SRC-Q1",
        "长期生存与十年后需求": "SRC-FY",
        "企业文化、管理层与资本配置": "SRC-FY",
        "回购明细": "SRC-FY",
        "治理、债务与红旗": "SRC-Q1",
        "Reverse DCF 与估值": "SRC-Q1",
        "Pre-Mortem 事前验尸": "SRC-Q1",
        "领先指标与 Monitoring Indicators": "SRC-Q1",
    }
    sections = [
        (heading, f"{body}\n\n就地来源：{inline_sources[heading]}。" if heading in inline_sources else body)
        for heading, body in sections
    ]
    (package / "research-report.md").write_text(
        "# 测试公司 TEST 长期价值研究\n\n"
        + "\n\n".join(f"## {heading}\n{body}" for heading, body in sections)
        + """

## 主要来源索引
| 来源ID | 标题 | 发布者/类型 | 日期/期间 | URL | 页码/章节定位 |
|---|---|---|---|---|---|
| SRC-FY | Test Company 2025 Annual Report | Test Company / annual report | 2026-02-15 / FY2025 | https://example.com/investors/2025-annual-report | pp. 40-74 |
| SRC-Q1 | Test Company 2026 First Quarter Report | Test Company / quarterly report | 2026-04-10 / 2026Q1 | https://example.com/investors/2026-q1 | Quarterly report p. 12 |
""",
        encoding="utf-8",
    )
    (package / "research-completeness.md").write_text(
        "# 研究完整度\n\n"
        "覆盖：已取得十年年度财务、最新季度、资本配置、管理层承诺、竞争优势与估值证据，并核对 SRC-FY 和 SRC-Q1。\n\n"
        "缺口：未发现会改变当前结论的关键缺失；企业客户分层留存和商户边际获客成本仍缺少更细披露。\n\n"
        "置信度：财务与监管申报可信度高，护城河持续性和长期增长的置信度为中等。\n\n"
        "影响：现有缺口限制了对增长上限的判断，因此估值采用较宽区间并不提高结论强度。\n\n"
        "下一步待取得证据：下一份正式季度报告、企业客户留存拆分、信用损失迁徙率和商户覆盖更新。\n",
        encoding="utf-8",
    )
    return package, schema_path, company
