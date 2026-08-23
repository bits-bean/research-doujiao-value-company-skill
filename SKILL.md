---
name: research-doujiao-value-company
description: Research, update, audit, repair, freeze, and explicitly authorized GitHub-deliver evidence-driven long-term research for listed companies under this Skill's authoritative protocol and the locked bits-bean/doujiao-value-system company Schema. Use for company research, ten-year financials, FCF/Owner Earnings/financial-company FCFE, ROIC or industry-adapted returns, moat, durability, culture, management, capital allocation, governance, risks, DCF or Reverse DCF, formal research reports, schema-valid company.json, earnings updates, Too Hard decisions, frozen handoff packages, and authorized delivery to bits-bean/doujiao-value-system. Do not use for social-media production, short-term price prediction, trading signals, unsupported recommendations, unapproved GitHub writes, website import, or public publishing.
---

# 豆角长期价值研究

本 Skill 是权威研究层：先从证据和可复算计算形成判断，再交付可独立阅读的报告与结构化数据。传播内容交给下游内容 Skill。

## 1. 权威与边界

- 研究协议唯一可编辑源：本 Skill 的 `references/specs/project-instructions.md`、`research-methodology.md`、`automation-workflow.md`。
- `company.json` Schema 唯一可编辑源：`bits-bean/doujiao-value-system/schemas/company.schema.json`；本 Skill 副本只读且受信任锁保护。
- 不从旧聊天、旧报告或传播内容补事实；事实、管理层主张、第三方观点、推断和估算必须区分。
- 不编造、插值或无声填补缺失数据；`null`、`[]` 和真实零值严格区分。
- 企业质量、估值状态和研究状态分开。诚信、治理、资本韧性和数据可靠性可否决估值吸引力。
- 审查请求只诊断；修复、GitHub 归档、canonical 提升、网站导入和公开发布各需相应授权。

## 2. 模式与读取顺序

模式：首次完整研究、增量更新、审查、修复并重新冻结、Schema 迁移、授权 GitHub 归档。冻结目录不可原地修改。

按 [source-routing.md](references/source-routing.md) 完整读取并锁定：

1. `project-instructions.md`；
2. `research-methodology.md`；
3. 只读 `company.schema.json`；
4. 增量任务再读上一 v2 冻结包与 `automation-workflow.md`。

同时锁定研究协议 commit / digest、Schema commit / blob / SHA-256 / version、公司法定身份、证券、会计准则、财年、币种、单位、数据日、估值日和股价时间戳。任一锚点或关键官方来源不可验证时只能交付计划 / 缺口，不称正式完成。

## 3. 证据和十年财务

完整读取 [evidence-and-calculation.md](references/evidence-and-calculation.md)，先做 `evidence-ledger.json` 和 `calculation-ledger.json`，再写结论。

- 默认十个完整财年 + 最新季度 + TTM，统一财年变化、重述、拆股、并购、币种、单位和正负号。
- 关键数字记录期间、口径、来源 ID 和页码 / 章节；推断和估算记录最强反证与推翻条件。
- 普通企业复算 FCF、Owner Earnings、ROIC、净债务、市值和 EV；金融、保险、REIT、资源等使用行业适配口径。
- 护城河同时读取竞争对手和替代品；文化和管理层比较承诺与实际行动。

## 4. 长期价值判断

完整执行方法论第 1—13 节。每个模块都写清：问题、事实 / 计算、支持证据、最强反证、置信度和推翻条件。至少覆盖商业模式、十年财务、现金质量、回报与再投资、护城河、长期生存、文化 / 不做清单、管理层 / 资本配置、治理 / 债务、估值和 Pre-Mortem。

遇到商业模式无法验证、关键数据缺失、多个低确定性变量决定结果或 DCF 几乎全靠遥远终值时，主动归入 Too Hard，说明难点、缺证、移出条件和不行动理由。

## 5. 现金流估值

完整读取 [valuation-qa.md](references/valuation-qa.md)，以计算台账中唯一的 `valuation_role: starting_cash_flow` 作为 DCF 与 Reverse DCF 共用起点。普通企业使用 FCFF、FCFE 或 Owner Earnings；受资本约束金融企业使用“正常化普通股净利润 − 必要留存资本”的可分配普通股现金。总额先折现、再除以稀释后股数；EPS 与倍数只作交叉验证。

估值正文必须让读者沿一条连续算式复核：估值基准日可分配现金 → 每个预测年度的经营驱动与可分配现金 → 折现因子与现金流现值 → 终值及其现值 → 股权价值 → 稀释后每股价值。悲观、基准、乐观三个情景都必须逐年列示，不得只给增长率与最终答案。任何分段假设都写成“第1—5年”“第6—10年”等明确范围；“初期、前期、中期、后期、第一阶段、长期增长”等词若没有紧邻的起止年度，不得作为估值假设名称。计算台账保存同一组逐年记录和价值桥接，报告展示值必须与其复算一致。

## 6. 正式研究包

按 [research-contract.md](references/research-contract.md) 建立新版本目录；生成 `income_statement_sankey` 时完整执行 [income-statement-sankey.md](references/income-statement-sankey.md)。`research-report.md` 采用方法论第 14 节的固定 16 节，面向没有财务专业背景但愿意认真阅读的投资者；脱离 JSON 和台账仍可独立阅读、理解及核实。先讲“这意味着什么、为什么重要”，再给口径、公式、证据和限制。缩写、行业指标及非通用术语首次出现时，在同一句或相邻括号内给中文全称和一句白话注解。关键主张就地引用直接链接或 `SRC-*`；使用 `SRC-*` 时文末索引给完整 URL 和精确定位。

正文只保留投资判断所需的事实、假设、计算过程、限制与反证。Schema 字段映射、JSON 文件名、验证器兼容、归档或生成流程等内部实现说明写入 `schema-gap-report.md`、`research-completeness.md`、台账或 manifest，不塞进研究叙事；但字段背后的真实经济假设仍须在正文直接说清。例如正文应写“第1—5年收入与普通股利润都按8%增长”，而不是解释某个 Schema 字段为何暂存同一数值。

`company.json` 严格通过锁定 Schema，不新增字段。Schema 暂时无法表达的估值口径保留在报告、计算台账和 `schema-gap-report.md`，不得把旧字段静默改义。新研究的 `company.json` 与 `calculation-ledger.json` 统一存实际原始数值：人民币100万元写 `1000000`，100万股写 `1000000`，比例仍写 `0.25`；不得使用千、百万或十亿缩放值，计算台账也不得逐条添加 `unit`。所有面向中国读者的文字、表格、图表和最终回复再按 [research-contract.md](references/research-contract.md#中文展示单位契约) 换算：公司级金额优先用亿元，超大规模可用万亿元，股数用万股 / 亿股，每股值用原币种 / 股，比例用百分比。

## 7. 验收与冻结

完整执行 [qa-gates.md](references/qa-gates.md)，然后运行：

```bash
python3 scripts/validate_research_package.py <package> \
  --schema references/specs/company.schema.json --mode full \
  --output <package>/validation-report.json
```

零错误并完成语义复核后冻结：

```bash
python3 scripts/freeze_research.py <package> \
  --schema references/specs/company.schema.json \
  --schema-blob-sha <locked-blob> --schema-commit <locked-commit>
```

新 manifest 固定为 v2。警告默认阻断；只有完整度说明逐项解释原因、影响和待补证据时才能 `--allow-warnings`。只有真实人工审核后才使用 `--human-reviewed`。冻结只表示不可变，不等于投资建议。

## 8. 增量与下游

增量只由比上一报告更新的官方财报或重大事件触发，按公司、期间、发布日期和 source ID 去重。复核旧包、更新受影响事实 / 计算 / 估值 / verdict，并明确长期逻辑：增强 / 基本不变 / 削弱 / 被推翻 / 暂无法判断。

下游内容只接收同一冻结版本的报告、company.json、manifest 和完整度说明；下游不得重新研究、重算估值或覆盖结论。

## 9. 授权 GitHub 提交

用户明确要求提交 / 合并时完整读取 [github-archive.md](references/github-archive.md)。只把人工已接受、v2、零错误的冻结包提交到 `bits-bean/doujiao-value-system`。

- GitHub 当前研究目录固定为 `research/<company-slug>/`，不得再增加日期或 `-vN` 子目录；本地冻结目录继续按版本保存，Git 历史承担远端版本追踪。
- 每次获授权提交必须在同一原子变更中同步研究目录与 `companies/<company-slug>/company.json`，两处 `company.json` 必须逐字节一致。
- 研究请求、冻结请求仍不自动授权 GitHub；但“提交到 GitHub”同时授权上述两处目标，不再拆分 `archive-only` 与 canonical 提升权限。
- 用户要求合并到 `main` 时走独立分支和 PR，检查通过后合并；只有明确说“直接提交到 main”才允许原子、非强制、仅快进直写。
- 写入前核对最新 HEAD、Schema blob、slug / identity、远端当前研究目录和 canonical 单调性；写入后按 commit 重读全部文件并核对 SHA-256。

## 10. 完成状态

只有证据、计算、行业适配、现金流估值、16 节报告、Schema、一致性和冻结门禁全部通过，才称正式完成；否则准确标记为计划、草案、证据不完整、待人工复核、Too Hard、审查结果或迁移未完成。
