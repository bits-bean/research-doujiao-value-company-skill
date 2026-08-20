"""Build a substantive package that passes the real full research validator."""

from __future__ import annotations

import shutil
from pathlib import Path

from validate_research_package import write_json


ROOT = Path(__file__).resolve().parents[1]
SOURCE_IDS = ["SRC-FY", "SRC-Q1"]


def make_valid_unfrozen_package(root: Path) -> tuple[Path, Path, dict]:
    """Create real-schema inputs; the caller may add validation report and manifest."""
    schema_path = root / "company.schema.json"
    shutil.copyfile(ROOT / "references/specs/company.schema.json", schema_path)
    package = root / "package"
    package.mkdir()

    financials = []
    for offset, year in enumerate(range(2016, 2026)):
        revenue = 100 + offset * 10
        gross_profit = 60 + offset * 6
        operating_profit = 25 + offset * 2
        net_income = 18 + offset * 2
        operating_cash_flow = 30 + offset * 2
        capex = 10 + offset
        cash = 32 + offset * 2
        debt = 28 - offset
        financials.append(
            {
                "period": f"FY{year}",
                "period_type": "FY",
                "revenue": revenue,
                "gross_profit": gross_profit,
                "operating_profit": operating_profit,
                "net_income": net_income,
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
                "diluted_shares": 109 - offset,
                "is_estimate": False,
                "source_ids": ["SRC-FY"],
            }
        )
    for period, period_type, revenue in (("2026Q1", "Q1", 52), ("TTM2026", "TTM", 202)):
        financials.append(
            {
                "period": period,
                "period_type": period_type,
                "revenue": revenue,
                "gross_profit": revenue * 0.6,
                "operating_profit": revenue * 0.24,
                "net_income": revenue * 0.18,
                "operating_cash_flow": revenue * 0.28,
                "capex_total": revenue * 0.08,
                "free_cash_flow": revenue * 0.2,
                "cash": 50,
                "total_debt": 20,
                "net_debt": -30,
                "gross_margin": 0.6,
                "operating_margin": 0.24,
                "net_margin": 0.18,
                "roic": 0.19,
                "roe": 0.22,
                "diluted_shares": 100,
                "is_estimate": False,
                "source_ids": ["SRC-Q1"],
            }
        )

    company = {
        "meta": {
            "company_name_cn": "测试公司",
            "company_name_en": "Test Company",
            "ticker": "TEST",
            "exchange": "NYSE",
            "fiscal_year_end": "12-31",
            "report_currency": "USD",
            "financial_unit": "million",
            "share_unit": "million_shares",
            "ratio_convention": "decimal",
            "valuation_date": "2026-04-15",
            "data_as_of": "2026-03-31",
            "accounting_standard": "US GAAP",
            "display_language": "zh-CN",
            "source_version": "2026Q1",
            "schema_version": "1.1.0",
            "theme": "light",
            "sankey_style": "app-economy-inspired-light",
        },
        "brand_identity": {
            "company_logo": {
                "asset_path": "assets/test-company-logo.svg",
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
        "income_statement_sankey": {
            "fiscal_year": "FY2025",
            "basis": "income_statement",
            "nodes": [
                {"id": "revenue", "label": "营业收入", "value": 190},
                {"id": "costs", "label": "经营成本与费用", "value": 154},
                {"id": "profit", "label": "净利润", "value": 36},
            ],
            "links": [
                {"source": "revenue", "target": "costs", "value": 154},
                {"source": "revenue", "target": "profit", "value": 36},
            ],
            "reconciled": True,
            "source_ids": ["SRC-FY"],
        },
        "segments": [
            {
                "period": "FY2025",
                "name": "Network Services",
                "revenue": 190,
                "operating_profit": 43,
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
                "amount": 18,
                "commentary": "在低于内部价值区间时回购并保持净现金。",
                "source_ids": ["SRC-FY"],
            }
        ],
        "buyback_ledger": [
            {
                "period": "FY2025",
                "amount": 18,
                "shares_repurchased": 2,
                "average_price": 9,
                "shares_outstanding_change": -0.02,
                "source_ids": ["SRC-FY"],
            }
        ],
        "debt_maturities": [
            {"year": 2028, "amount": 8, "instrument": "senior notes", "interest_rate": 0.035, "source_ids": ["SRC-FY"]}
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
                    "status": "已兑现",
                    "outcome": "2025年收入增长并且经营利润率同比提升。",
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
            "diluted_shares": 100,
            "market_cap": 1000,
            "enterprise_value": 970,
            "multiples": {"pe": 25, "fcf_yield": 0.04},
            "dcf_scenarios": [
                {"name": "悲观", "revenue_growth": 0.03, "margin": 0.18, "discount_rate": 0.11, "terminal_growth": 0.02, "fair_value_per_share": 7},
                {"name": "基准", "revenue_growth": 0.07, "margin": 0.22, "discount_rate": 0.09, "terminal_growth": 0.025, "fair_value_per_share": 10},
                {"name": "乐观", "revenue_growth": 0.1, "margin": 0.25, "discount_rate": 0.08, "terminal_growth": 0.03, "fair_value_per_share": 14},
            ],
            "dcf_sensitivity": [
                {"discount_rate": 0.08, "terminal_growth": 0.02, "fair_value_per_share": 12},
                {"discount_rate": 0.08, "terminal_growth": 0.03, "fair_value_per_share": 14},
                {"discount_rate": 0.1, "terminal_growth": 0.02, "fair_value_per_share": 8},
                {"discount_rate": 0.1, "terminal_growth": 0.03, "fair_value_per_share": 9},
            ],
            "reverse_dcf": {
                "implied_revenue_cagr": 0.07,
                "implied_operating_margin": 0.22,
                "comparison_to_history": "隐含增长接近历史五年区间，利润率略高于历史中位数但仍低于优秀同业。",
                "sensitivity_and_threshold": "利润率最敏感；若连续三年低于百分之十八，当前价格将显得高估并推翻基准判断。",
            },
            "fair_value_range": {"low": 7, "base": 10, "high": 14, "currency": "USD"},
            "expected_returns": [
                {"horizon_years": 5, "scenario": "悲观", "annualized_return": -0.05, "assumptions": ["竞争加剧"]},
                {"horizon_years": 5, "scenario": "基准", "annualized_return": 0.08, "assumptions": ["稳健增长"]},
                {"horizon_years": 5, "scenario": "乐观", "annualized_return": 0.15, "assumptions": ["网络效应增强"]},
            ],
        },
        "risks": {
            "pre_mortem": [
                "核心客户因产品体验停滞而迁移，续费下降导致单位经济性失效。",
                "商户侧出现更低成本替代网络，覆盖优势逐步转为固定成本负担。",
                "监管限制数据使用范围，风控准确性下降并推高信用损失。",
                "管理层在高估值阶段过度回购，削弱应对衰退的资产负债表弹性。",
                "新技术改变客户入口，既有品牌无法转化为下一代产品采用。",
            ],
            "bear_case": "最强悲观情形是竞争补贴、监管收紧与错误资本配置同时发生，使增长与利润率永久低于反向估值要求。",
            "fragile_assumptions": [
                "高价值客户仍愿意为可靠服务与权益组合支付溢价",
                "商户覆盖扩张不会依赖不可持续的获客补贴",
                "管理层能够在增长投资与回购纪律之间保持克制",
            ],
            "monitoring_indicators": [
                {"name": "核心客户续费率", "current_status": "仍处历史稳定区间", "trigger": "若连续四季明显低于长期均值则复核转换成本", "source_ids": ["SRC-Q1"]},
                {"name": "单位服务收入", "current_status": "同比保持温和增长", "trigger": "若提价后收入与留存同时下降则推翻定价权判断", "source_ids": ["SRC-Q1"]},
                {"name": "商户网络覆盖", "current_status": "重点场景继续扩张", "trigger": "若新增覆盖停滞且活跃商户下降则复核网络效应", "source_ids": ["SRC-FY"]},
                {"name": "信用损失水平", "current_status": "风险指标处于目标范围", "trigger": "若损失率跨周期显著恶化则下调现金流质量", "source_ids": ["SRC-Q1"]},
                {"name": "回购价格纪律", "current_status": "回购均价低于基准价值", "trigger": "若高估值阶段仍扩大回购则下调资本配置评分", "source_ids": ["SRC-FY"]},
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
    write_json(
        package / "evidence-ledger.json",
        {
            "claims": [
                {
                    "id": claim_id,
                    "claim": claim,
                    "classification": classification,
                    "confidence": "high" if classification != "estimate" else "medium",
                    "source_ids": ["SRC-FY"] if claim_id not in {"CLM-002", "CLM-007", "CLM-008"} else ["SRC-Q1"],
                    **({"location": location} if location is not None else {}),
                    **({"would_falsify": falsifier} if falsifier is not None else {}),
                }
                for claim_id, claim, classification, location, falsifier in claims
            ]
        },
    )
    write_json(
        package / "calculation-ledger.json",
        {
            "calculations": [
                {"id": "CALC-FCF", "metric": "free_cash_flow", "period": "FY2025", "formula": "operating_cash_flow - capex_total", "inputs": {"operating_cash_flow": 48, "capex_total": 19}, "result": 29, "unit": "USD million", "source_ids": ["SRC-FY"]},
                {"id": "CALC-ND", "metric": "net_debt", "period": "FY2025", "formula": "total_debt - cash", "inputs": {"total_debt": 19, "cash": 50}, "result": -31, "unit": "USD million", "source_ids": ["SRC-FY"]},
                {"id": "CALC-MC", "metric": "market_cap", "period": "2026-04-15", "formula": "market_price * diluted_shares", "inputs": {"market_price": 10, "diluted_shares": 100}, "result": 1000, "unit": "USD million", "source_ids": ["SRC-Q1"]},
                {"id": "CALC-EV", "metric": "enterprise_value", "period": "2026-04-15", "formula": "market_cap + net_debt", "inputs": {"market_cap": 1000, "net_debt": -30}, "result": 970, "unit": "USD million", "source_ids": ["SRC-Q1"]},
            ]
        },
    )

    sections = [
        (
            "一页式结论",
            """测试公司 TEST 的价值来自双边网络、复购关系与持续现金流，当前价格只适合观察。证据见 SRC-FY 和 SRC-Q1。

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
        ("自由现金流与 Owner Earnings", "经营现金流扣除维持性资本开支后持续为正。所有者收益仍需关注获客投入和信用损失，因此不把全部会计利润视为可分配现金。"),
        ("ROIC 与投入资本回报", "投入资本回报率随网络利用率提高而改善。判断重点是增量资本能否继续带来客户留存和单位利润，而不是只看单年高回报。"),
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
        ("长期生存与十年后需求", "可靠交易、短期信用和身份信任具有长期需求。公司能否生存二十年取决于持续适应新入口，而不是依赖今天的产品形式。"),
        ("企业文化、管理层与资本配置", "管理层披露目标时同时说明成本和约束，资本优先投向核心网络。Stop Doing List 限制追逐邻近收入与高价机械回购。"),
        ("回购明细", "回购金额、股份和均价分别入账，避免把减少股数自动视为创造价值。只有均价低于审慎内在价值且不削弱资产负债表时才加分。"),
        ("治理、债务与红旗", "净现金提供缓冲，但监管、数据治理和激励结构仍需季度复核。若管理层改变资本纪律或隐藏关键损失，将构成治理红旗。"),
        (
            "Reverse DCF 与估值",
            """Reverse DCF 显示现价要求中个位数增长和稳定利润率，与历史大致相符但安全边际有限。DCF 情景与敏感性逐项对应 company.json 的结构化估值输入。

| 情景 | 收入增长 | 利润率 | 折现率 | 永续增长 | 每股价值 |
|---|---|---|---|---|---|
| 悲观 | 3% | 18% | 11% | 2% | 7 |
| 基准 | 7% | 22% | 9% | 2.5% | 10 |
| 乐观 | 10% | 25% | 8% | 3% | 14 |

| 折现率 | 永续增长 | 每股价值 |
|---|---|---|
| 8% | 2% | 12 |
| 8% | 3% | 14 |
| 10% | 2% | 8 |
| 10% | 3% | 9 |

| Reverse DCF 假设 | 隐含值 | 历史比较 | 推翻阈值 |
|---|---|---|---|
| 收入增长 | 7% | 接近历史五年中位增长区间 | 连续三年低于3%则现价要求过高 |
| 经营利润率 | 22% | 略高于历史利润率中位数 | 连续三年低于18%则推翻基准判断 |""",
        ),
        (
            "Pre-Mortem 事前验尸",
            """最可能的永久损失来自多个变量叠加，因此每条失败路径都预先定义时间与最早预警。

| 失败路径 | 概率 | 影响 | 期限 | 最早预警 | 可逆性 | 管理层缓解 |
|---|---|---|---|---|---|---|
| 核心客户因产品体验停滞而迁移，续费下降导致单位经济性失效。 | 中 | 高 | 1–3年 | 续费率连续四季低于长期均值 | 中 | 重做核心权益并降低无效获客支出 |
| 商户侧出现更低成本替代网络，覆盖优势逐步转为固定成本负担。 | 中低 | 高 | 3–5年 | 活跃商户下降且新增覆盖连续停滞 | 低 | 调整受理费率并投资高频使用场景 |
| 监管限制数据使用范围，风控准确性下降并推高信用损失。 | 低 | 严重 | 1–2年 | 合规征询文件扩大禁止使用的数据范围 | 低 | 提前建设替代变量与人工复核流程 |
| 管理层在高估值阶段过度回购，削弱应对衰退的资产负债表弹性。 | 中 | 重大 | 1–3年 | 回购均价显著超过基准内在价值区间 | 中 | 暂停回购并将自由现金流优先降债 |
| 新技术改变客户入口，既有品牌无法转化为下一代产品采用。 | 中 | 高 | 5–10年 | 新入口交易占比上升而本公司采用率落后 | 部分可逆 | 开放接口并通过合作进入下一代入口 |

| 补充诊断 | 明确结论 |
|---|---|
| 最强反方观点 | 最强悲观情形是竞争补贴、监管收紧与错误资本配置同时发生，使增长与利润率永久低于反向估值要求。 |
| 三个最脆弱假设 | 1. 高价值客户仍愿意为可靠服务与权益组合支付溢价<br>2. 商户覆盖扩张不会依赖不可持续的获客补贴<br>3. 管理层能够在增长投资与回购纪律之间保持克制 |
| Thesis breakers | 1. 连续四个季度核心客户净流失并伴随单位经济性恶化<br>2. 监管变化永久削弱网络收费能力且无法通过产品升级弥补 |
| 破产路径 | 监管处罚与信用损失同时激增，流动性储备耗尽并触发债务违约，股权价值可能归零。 |
| 存活但股东回报差 | 公司仍能运营，但竞争补贴和高价回购长期压低每股自由现金流，回报低于资本成本。 |""",
        ),
        ("待调查与 Open Questions", "尚待调查企业客户分层留存、商户边际获客成本和新入口使用率。下一轮将优先取得正式分部附注和更细的信用数据，并核对不同客户层的历史迁移与盈利差异。"),
        ("领先指标与 Monitoring Indicators", "季度跟踪续费、单位收入、商户覆盖、信用损失和回购均价。每项指标都有不同阈值，用于检验护城河、现金流和资本配置。"),
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
