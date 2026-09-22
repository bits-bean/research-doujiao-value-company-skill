# 研究执行、论点状态与独立审计契约

## 目录

- [适用范围](#适用范围)
- [能力预检与执行档位](#能力预检与执行档位)
- [研究可得性与论点确定性](#研究可得性与论点确定性)
- [经营与价值驱动图](#经营与价值驱动图)
- [管理层决策质量台账](#管理层决策质量台账)
- [关键论断与裁决](#关键论断与裁决)
- [论点状态与增量漂移](#论点状态与增量漂移)
- [估值模型审查](#估值模型审查)
- [风险加权独立来源审计](#风险加权独立来源审计)
- [正式准出](#正式准出)

## 适用范围

本文件定义正式研究如何运行、挑战、裁决和独立复核。新结构全部写入
`evidence-ledger.json`，不修改或借用 `company.json` Schema 字段。报告只解释对投资者有意义的
结论、证据、限制和变化；运行记录、审计轨迹及机器状态留在台账和 manifest。

正式研究的状态顺序固定为：

`preflight → collecting → reconciled → modeled → audited → ready_to_freeze`

任何关键能力预检失败、关键论断未裁决、关键来源审计未通过、估值冲突未解释或结论稳定性未处理，
都不得进入 `ready_to_freeze`。

## 能力预检与执行档位

`evidence-ledger.json` 根级必须包含 `ledger_version: "2.0"`、`run`、`researchability`、
`business_driver_map`、`management_decision_ledger`、`thesis`、`valuation_review`、`source_audit` 和
`claims`。新正式交接还必须包含 [商业模式具体对象图谱及关系覆盖清单](business-model-actors.md) `business_model` 和 `business_model_coverage`，与经营驱动方程分别表达实际交换/权利/责任关系和价值驱动。覆盖清单来自取证，不能从成图倒填；其关闭审查绑定真实隔离 pass 和最终图谱摘要。`run` 必须包含：

- `run_id`：当前执行的稳定唯一标识；
- `research_mode`：`full / incremental / repair / migration`；
- `workflow_tier`：`standard / audit`；
- `data_cutoff_at`：带时区的 ISO 8601 时间；
- `status`：上述状态机之一；冻结前必须是 `ready_to_freeze`；
- `protocol_fingerprint`：当前兼容研究协议摘要、完整执行摘要、Schema 版本与 SHA-256、验证器 SHA-256；
- `preflight[]`：实际能力探针；
- `passes[]`：研究、挑战、审计与综合记录。

`preflight[]` 至少实测并通过：

1. `protocol_access`：能读取并核对当前研究协议；
2. `schema_access`：能读取并核对锁定 Schema；
3. `official_source_retrieval`：主研究实际打开一份与目标公司相关的官方原件，不以权限配置代替真实访问；
4. `challenge_source_retrieval`：隔离的挑战步骤实际打开另一条来源路径；
5. `calculation_runtime`：实际运行一个无害的确定性计算；
6. `package_write`：能在目标草稿目录创建并读取临时探针，随后移除。

每项保存 `capability / status / checked_at / method / source_id / evidence_sha256 / failure_reason`。
`status` 只能为 `passed / failed`；正式研究必须全部 `passed`。两个来源访问探针都必须绑定已解析且不同的
`company.json.sources[].id` 与实际取回内容 SHA-256。官方原件不可访问时停止正式研究并列缺口，不能用训练知识、
聚合网站或旧报告静默替代。

`passes[]` 每项保存 `id / role / actor_id / execution / status / scope / claim_ids /
source_ids_accessed`。正式标准档至少包含：

- `primary_research`；
- `adversarial_review`；
- `source_audit`；
- `synthesis`。

挑战和来源审计的 `actor_id` 必须与主研究不同，并使用 `isolated_agent` 或 `isolated_context`，不能在已看到主结论的同一上下文中自我确认。
审计档至少包含两个相互独立的 `adversarial_review`。各角色提交主张、证据、反证和置信度，不分别撰写完整
最终报告；综合角色必须列出共识、冲突、遗漏和无法裁决项。

## 研究可得性与论点确定性

`researchability` 分别记录：

- `official_source_coverage`；
- `operating_kpi_coverage`；
- `third_party_verifiability`；
- `timeliness`；
- `opacity`；
- `evidence_confidence`；
- `thesis_certainty`；
- `assessment`；
- `limitations[]`。

覆盖度、时效性、证据置信度和论点确定性使用 `high / medium / low`；`opacity` 使用
`low / medium / high`。资料丰富不自动代表商业论点确定，资料稀缺也不自动代表公司差；两种判断必须分别解释。
关键官方原件缺失时不得给出高 `evidence_confidence`。

## 经营与价值驱动图

`business_driver_map` 包含：

- `equation`：用一条可读关系概括价值如何形成；
- `value_capture_chain[]`：从客户行为到可分配现金的连续步骤；
- `drivers[]`：2—5 个真正改变利润或可分配现金的驱动。

每个驱动保存 `id / name / metric / definition / historical_baseline / current_state / causal_role /
direction_and_mechanism / cash_flow_link / moat_link / valuation_link / monitoring_indicator / source_ids /
confidence / counterevidence / would_falsify`。`causal_role` 只使用
`volume / price / mix / take_rate / retention / margin / capital_intensity / other`。
驱动必须可观察并连接历史证据、护城河、估值假设和后续监控；不能把“品牌强”“行业好”当作经营方程。

## 管理层决策质量台账

`management_decision_ledger[]` 至少覆盖三类长期行为：

1. `commitment / forecast / aspiration` 中至少一类；
2. `capital_allocation / crisis_response / stop_doing` 中至少一类；
3. `governance / succession` 中至少一类。

每项保存 `id / kind / date / decision / information_available / public_rationale / alternatives /
constraints / ex_ante_process / process_quality / outcome / outcome_quality / confounders /
stakeholder_claim_ids / succession_dependency / source_ids / confidence`。

- `process_quality`：`high / mixed / low / uncertain`；
- `outcome_quality`：`positive / mixed / negative / pending / uncertain`；
- `succession_dependency`：`high / medium / low / unknown`。

评价时把当时信息下的决策过程和事后结果分开，不以好结果倒推好过程，也不以坏结果自动否定合理过程。
区分可检验承诺、数值预测和方向性愿景；使用员工、客户、供应商、监管者或竞争对手证据时，必须通过
`stakeholder_claim_ids` 指向相应主张。资料不足时写 `unknown / uncertain`，不猜测。

## 关键论断与裁决

`claims[]` 在原字段基础上必须增加：

- `research_module`：`business / financials / competition / management / governance / industry /
valuation / risk`；
- `decision_relevance`：`critical / supporting / context`；
- `adjudication`：`upheld / narrowed / conflicted / rejected / unresolved`；
- `counterevidence`：数组，可为空但不得省略；
- `counterevidence_search`：关键论断必须说明实际查找了哪些反面来源或路径。

所有关键论断都必须有可检验 `would_falsify`；关键推断、估算、管理层主张和第三方观点必须由隔离的挑战
步骤复核。`rejected` 论断保留在台账并进入 `thesis.rejected_claim_ids`，不得删除后假装从未出现。
非 Too Hard 的正式研究若仍存在 `critical + unresolved/rejected`，必须改写或降低结论；
`critical + conflicted` 必须列入未解冲突并降低置信度或阻断冻结。

## 论点状态与增量漂移

`thesis` 必须包含：

- `overall_change`：`baseline / strengthened / unchanged / weakened / broken / uncertain`；
- `assumptions[]`：与 `company.json.verdict.key_assumptions` 一一对应的 2—4 条假设；
- `valuation_assumption_changes[]`；
- `rejected_claim_ids[]`；
- `unresolved_conflicts[]`；
- `revision_log[]`。

每条假设保存 `id / assumption / importance / prior_status / current_status / change_type /
evidence_claim_ids / reason / falsifier / red_lines / next_validation`。

- `importance`：`core / supporting`；
- 状态：`supported / strained / broken / uncertain`；首次基线的 `prior_status` 为 `null`；
- `change_type`：`baseline / fundamental / market_price / accounting_restatement / methodology /
correction / wording / none`。

增量研究不得使用 `baseline`，必须带上上一冻结版本状态。状态变化必须绑定新主张并解释原因；只有价格变化或
措辞变化时，不得无证据改变商业假设。估值参数相对上一版本发生变化时，逐项写入
`valuation_assumption_changes[]`，记录情景、参数、前值、现值、变化类型、理由和证据主张；不得让悲观、基准、
乐观参数跟随现价无声漂移。

`valuation_assumption_changes[]` 每项固定保存 `scenario / parameter / previous_value / current_value /
change_type / reason / evidence_claim_ids`；`parameter` 只使用 `revenue_growth / margin / discount_rate /
terminal_growth`。`revision_log[]` 每项固定保存 `id / changed_at / change_type / summary /
affected_assumption_ids / evidence_claim_ids`。新增或移除假设、假设状态变化、估值参数变化都必须能由该日志解释；
无实际参数变化时不得伪造 `valuation_assumption_changes` 记录。

`unresolved_conflicts[]` 每项保存 `id / topic / evidence_claim_ids / status / resolution /
impact_on_conclusion`；`status` 为 `resolved / unresolved`。未解决且足以翻转结论的冲突阻断冻结。

## 估值模型审查

`valuation_review` 必须包含：

- `model_applicability[]`；
- `risk_placements[]`；
- `model_conflicts[]`；
- `conclusion_stability`。

`model_applicability[]` 对主 DCF、Reverse DCF 和至少一种交叉验证逐项记录
`model / role / status / reason / key_assumptions / result_direction`。角色使用
`primary / reverse / cross_check`；适用状态使用 `appropriate / limited / inappropriate`；结果方向使用
`undervalued / fair / overvalued / indeterminate`。先判断模型是否适用，再解释输出；不强迫不同模型收敛。

`risk_placements[]` 必须逐项覆盖 Pre-Mortem 的重大失败路径，并保存
`risk / placement / scenario / rationale / claim_ids`。`placement` 只使用
`cash_flow / scenario / tail_case / discount_rate`。同一风险只能归位一次；已压低现金流或进入悲观/尾部情景的
离散风险，不得再次通过折现率重复扣罚。系统性、不可分散风险进入折现率时必须说明理由。

不同模型给出相反方向时，`model_conflicts[]` 必须记录冲突模型、适用边界、权威价值依据、解释、对结论影响及
`resolved` 状态；未解决不得冻结。

`conclusion_stability.cells[]` 必须与 DCF 3×3 敏感性九格一一对应，并为每格给出估值状态。
同时记录 `verdict_flip / action / explanation`；若九格会翻转估值状态，`action` 只能是
`downgrade / too_hard`，不能维持高置信度。结论稳定性是对参数脆弱性的披露，不是人为修改九格以得到一致答案。

## 风险加权独立来源审计

`source_audit` 必须包含 `audit_pass_id / selection_seed / checks[]`。审计者重新打开来源，不能只比较报告、
JSON 和台账之间是否一致。`selection_seed` 使用规范化 `company.json` 的 SHA-256，使普通样本可复现。

`checks[]` 每项保存 `id / target_type / target_id / criticality / source_ids / status /
checked_at / location / observed / observed_value / notes`；`observed_value` 在数值检查中保存原始基准单位值，文本检查可为
`null`：

`valuation.dcf_assumptions` 的 `observed_value` 固定保存按情景名排序的 `scenarios[]`（每项仅含
`name / revenue_growth / margin / discount_rate / terminal_growth`）和排序后的
`equity_bridge_calculation_ids[]`；必须与 `company.json` 和计算台账完全一致，不能只写“已核对”。

- `target_type`：`claim / calculation / company_field / valuation_assumption`；
- `criticality`：`critical / ordinary`；
- `status`：`pass / fail / unavailable`。

以下目标必须 100% 重新核验并通过：

- 公司身份与主要证券；
- 估值日股价、稀释后股数、市值和企业价值；
- 唯一起始可分配现金及其来源输入；
- DCF 折现率、显性增长、终值增长和股权价值桥接；
- 受监管金融企业的监管资本、目标资本和必要留存；
- 所有 `decision_relevance: critical` 的论断。

其余主张按 `selection_seed` 做确定性抽检，至少覆盖普通主张的 15%，且在存在普通主张时不少于三条。
关键检查出现 `fail / unavailable` 一律阻断；普通检查失败必须先修正或形成明确冲突裁决，不能以另一来源通过
抵消。全部取数缺失、只有一个来源通过或漏做样本都不能判定审计通过。

## 正式准出

机械门禁必须同时确认：

1. 所有真实能力探针通过，执行状态为 `ready_to_freeze`；
2. 研究可得性与论点确定性分开披露；
3. 驱动图、管理层决策台账、关键论断裁决和假设状态完整；
4. 被否决论断、未解冲突、模型限制和修订记录没有被隐藏；
5. 估值风险没有重复扣罚，模型冲突和九格翻转已处理；
6. 风险加权独立来源审计完成且关键目标全部通过；
7. manifest 保存当前完整研究协议摘要和验证器代码 SHA-256。

程序只能验证记录结构、内部一致性和部分算术，不能证明探针或独立性陈述真实。冻结前仍需模型或人工语义复核；若记录
与实际执行不符，应视为研究诚信失败，而不是格式问题。模型复核通过不等于人工接受：未经真实人工审核时，
`human_review_status` 保持 `pending`，不得使用 `--human-reviewed`，也不得进入要求人工已接受的 GitHub 交付。
