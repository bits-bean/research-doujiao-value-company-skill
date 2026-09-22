---
name: research-doujiao-value-company
description: Research, update, audit, repair, migrate, and freeze evidence-driven long-term company research for 豆角 under its locked company Schema. Produces sourced reports, company.json, evidence/calculation ledgers, verified company Logos, and company-level Sankey color audits. Use for company fundamentals, industry-adapted financials, moat, management, cash-flow valuation, Too Hard decisions, and explicitly authorized GitHub research delivery. Excludes short-term price predictions, visual production, social copy, and publishing.
---

# 豆角长期价值研究

从原始证据和可复算计算形成长期判断，交付独立可读的报告、结构化数据与台账。先确定任务模式，再读取对应契约；不能把审查、研究、冻结或交付混为同一动作。

## 1. 先确定任务与权限

| 用户任务 | 执行范围与终点 | 首先读取 |
|---|---|---|
| 首次完整研究 | 在新目录建立证据、计算、报告与结构化数据，按请求完成至草稿或冻结 | [source-routing.md](references/source-routing.md) 的首次完整研究路径 |
| 更新财报 / 重大事件 | 核验上一冻结包与新官方触发，保留逐项变化归因 | 同上，再读上一完整冻结包与增量路径 |
| 审查 / 审计 | 只读诊断；报告发现、影响、证据和修复建议，输出放在被审包外 | 原 manifest、原冻结文件与来源路由的旧包审查路径 |
| 修复 / 迁移 | 草稿可修复；已冻结包必须在新目录重建，不原地补字段或改版本 | 当前协议、相关专项契约、原包与差异 |
| 冻结 | 先完整验收与语义复核，再生成不可变 manifest | [qa-gates.md](references/qa-gates.md)、第 6 节命令 |
| GitHub 提交 / 合并 | 人工已接受的合格冻结包，按已获授权完成交付 | [github-archive.md](references/github-archive.md) |
| 优化 / 维护本 Skill | 修改指令、脚本或测试，验证后更新本地 Skill；不启动公司研究 | [skill-maintenance.md](references/skill-maintenance.md) |

审查请求只诊断；修复、冻结和 GitHub 交付须在用户请求或已有授权范围内。已有明确授权时连续完成相应工作，不重复询问。缺少授权时先完成已获授权且可审阅的本地工作，再说明尚需授权的具体动作。研究或冻结请求本身不授权 GitHub 写入。

`run.research_mode`（`full / incremental / repair / migration`）、`run.workflow_tier`（`standard / audit`）和命令行 `--mode` 是三个不同概念；映射见第 6 节。专项审计使用 `audit` 档，不伪造 `research_mode: audit`。

## 2. 不可变的边界

- manifest v2 兼容研究协议由 `references/specs/` 下三份锁定文档定义，不改写 `research_protocol` 元组。当前执行规范、脚本和验证器由 `trusted-spec-lock.json.execution_integrity` 绑定；新冻结包固定为 `manifest_version: 2.0`、`integrity_profile: execution-bound-v1`。
- `company.json` Schema 唯一可编辑源是 `bits-bean/doujiao-value-system/schemas/company.schema.json`；本 Skill 副本只读。新研究使用信任锁的当前活动/default 版本，不能从兼容 enum 任选旧版本。
- 不从旧聊天、旧报告或传播内容补事实。区分事实、管理层主张、第三方观点、推断和估算；不编造、插值或无声补缺，严格区分 `null`、`[]` 和真实零值。企业质量、估值状态、研究状态分别判断；诚信、治理、资本韧性与数据可靠性可否决估值吸引力。
- 本 Skill 不调用 `doujiao-value-system` 的图表导出命令或接口，不生成网站图、社媒图或背景，不选择平台比例、安全区、Logo 位置和引流文案，不调用内容 Skill 或发布接口。下游只消费同一冻结版本，不补研究事实、重算估值、改变路由、覆盖配色或覆盖结论。
- 公司 Logo 是唯一可交付视觉素材例外，取得或更换前完整执行 [identity-assets.md](references/identity-assets.md)。优先复用已验证 canonical Logo；缺失、品牌重塑或获授权替换时继续穷尽官方来源，不能遇到首个不合格候选就停止。本私有 Skill 已记录用户常设授权：官方来源穷尽且留证后，可用身份交叉核验通过的第三方原始正方形 SVG / PNG，无需仅因第三方资格再次询问，必须保留原字节并写 `is_official:false`。唯一转换例外是契约规定的官方 PNG 确定性中心方形裁剪；原件与 provenance 持久保存在冻结包外。不得生成、重绘或用近似图替代公司 Logo。
- 除公司 Logo 与 [income-statement-sankey.md](references/income-statement-sankey.md) 限定的 App Economy Insights 配色核验外，不搜索、下载、管理或交付其他视觉素材。配色原始 PNG 只作冻结包外私有证据；研究包仅保存摘要和逐节点样本。`company.json.income_statement_sankey.nodes[].color` 是网站与导出器唯一渲染真相；不得建立任务级 palette sidecar。
- 无合格 Logo 时四元组精确写为 `asset_path:null / source_url:null / alt:null / is_official:false`，在 `research-completeness.md` 记录缺口及网站影响；不得静默清空远端已有引用。报告不写 Logo 或配色的元数据、状态与流程，研究包不嵌入媒体。Logo 字节留在冻结包外。

## 3. 启动与按阶段读取

完整执行 [source-routing.md](references/source-routing.md)：读取三份兼容协议、当前 Schema 和执行协议，验证兼容摘要、完整执行摘要、验证器 SHA-256 与 Schema commit / blob / SHA-256 / version。锁定公司法定身份、证券、会计准则、财年、币种、单位、数据日、估值日和股价时间戳。

正式批量取证前实测协议、Schema、官方来源、挑战来源、计算运行时和草稿写入六项能力。来源预检本身允许访问最小官方原件与不同的挑战来源，并登记稳定 source ID 和实际取回内容 SHA-256。能力、锚点或关键来源不能验证时保留诊断 / 缺口，不称正式完成；具体失败路径按来源路由执行。

正式研究使用 `standard` 档：主研究、隔离的对抗审查、隔离的来源审计、综合四个 pass 缺一不可；专项审计使用 `audit` 档并至少安排两个相互独立的对抗审查。各 pass 提交主张、证据、反证与置信度，综合 pass 裁决冲突，不让各角色各写整份报告。真实独立性与记录结构分别核验，不能把同一上下文自审记成隔离审查。

以下契约在对应工作开始前完整读取；同一任务中已读且未变的文件不重复加载。首次正式研究最终须覆盖所有适用行，按阶段读取不等于省略模块。

| 工作阶段 | 必读契约 | 关键产出 |
|---|---|---|
| 分类与行业框架 | [classification-and-chart-routing.md](references/classification-and-chart-routing.md) | 先用官方证据确定 `classification`；会计与回报路由仅由 `accounting_profile / returns_profile` 驱动 |
| 取证、计算与独立审查 | [evidence-and-calculation.md](references/evidence-and-calculation.md)、[research-execution-and-audit.md](references/research-execution-and-audit.md) | 先建证据 / 计算台账，再形成结论；保存驱动、管理层决策、假设变化、裁决和来源审计 |
| 收入构成与商业模式 | [revenue-mix-history.md](references/revenue-mix-history.md)、[business-model-actors.md](references/business-model-actors.md)、[business-model-feedback.md](references/business-model-feedback.md) | 十年收入构成、实际参与者及关系覆盖裁决、有证据才建立的可选闭环 |
| 现金流估值 | [valuation-qa.md](references/valuation-qa.md) | 共用起点、三情景逐年路径、价值桥接、Reverse DCF、九格及风险归位 |
| 利润表桑基与配色 | [income-statement-sankey.md](references/income-statement-sankey.md) | 有符号报表值、守恒流量、continuation 复算与配色三态 |
| 报告与研究包 | [research-contract.md](references/research-contract.md) | 16 节可独立阅读报告、Schema 数据、台账、完整度说明 |
| 验收与冻结 | [qa-gates.md](references/qa-gates.md) | 完整机器门禁、语义复核、准确完成状态 |

## 4. 研究与估值的核心要求

完整执行方法论第 1—13 节。各模块给出问题、事实 / 计算、支持证据、最强反证、置信度与推翻条件；至少覆盖商业模式、十年财务、现金质量、回报与再投资、护城河、长期生存、文化 / 不为清单、管理层 / 资本配置、治理 / 债务、估值和 Pre-Mortem。

- 默认十个完整财年 + 最新季度 + TTM，统一财年变化、重述、拆股、并购、币种、单位和正负号。收入构成逐年金额 / 占比与总营收勾稽，解释赚钱方式与战略重心的变化，不能只交最新构成或总营收趋势。
- 普通企业复算 FCF、Owner Earnings、ROIC、净债务、市值与 EV；金融、保险、REIT、资源等按分类契约适配，必要序列写入 `industry_metrics`。银行与支付信贷按专属回报路由，不能因 CET1 年数不足或选择回购替代路径退回普通企业模板。
- 先从业务证据建立参与者与关系候选，再写 `business_model` 与 `business_model_coverage`；检查不经过公司的关系，不按固定角色数套图。用开放的 `exchange_type` 与具体标签表达经济语义，兼容 `kind` 不能代替语义或删边。商业反馈写入独立的 `business_model_feedback`，不强凑闭环；可选 `official_logos` 仅交接已确认品牌身份，素材交下游管理。
- 护城河同时查竞争对手和替代品；长期生存分别验证需求持久性、适应能力和外部冲击；管理层比较承诺与行动，区分当时决策过程和事后结果。资料可得性与商业论点确定性分开评级。
- 在台账中建立 2—5 项经营与价值驱动、管理层决策、关键论断裁决、假设状态、被否决主张、未解冲突及修订记录。增量变化绑定新证据与原因，不能随现价无声漂移。
- DCF 与 Reverse DCF 共用计算台账中唯一的 `valuation_role: starting_cash_flow`。普通企业使用 FCFF、FCFE 或 Owner Earnings；受资本约束金融企业用“正常化普通股净利润 − 必要留存资本”。总额先折现，再除稀释后股数；EPS / 倍数只作交叉验证。
- 悲观、基准、乐观均展示连续计算链：基准日现金 → 每年经营驱动与现金 → 折现因子与现值 → 终值及现值 → 股权价值 → 稀释后每股价值。分段假设必须明确“第1—5年”等起止年度，报告与计算台账逐年一致。
- 先判断模型适用性，再裁决模型冲突；Pre-Mortem 每项重大风险只归入现金流、情景、尾部情景或折现率之一，避免重复扣罚。DCF 九格逐格给估值状态，翻转结论时降级置信度或归入 Too Hard。

商业模式无法验证、核心数据缺失、多个低确定性变量主导或 DCF 几乎全靠遥远终值时，主动给出 Too Hard，说明难点、缺证、移出条件与不行动理由。Too Hard 是研究判断，不自动豁免数据、来源、Schema 或冻结门禁。

## 5. 形成可交接的研究包

按研究包契约创建新版本目录。`company.json` 严格通过锁定 Schema，不新增字段、不借旧字段改义；无法表达的重要口径留在报告、台账和 `schema-gap-report.md`，阻断项未解决前不冻结。每个 `source_ids` 解析到同一 `company.json.sources`，关键计算保存公式、输入与来源。

机器层统一实际原始数值：100万元写 `1000000`，100万股写 `1000000`，比例写 `0.25`；计算台账声明 `numeric_convention: base_units`，每条计算不加 `unit`。人类读物与最终回复按 [中文展示单位契约](references/research-contract.md#中文展示单位契约) 转成亿元 / 万亿元、万股 / 亿股、原币种每股值及百分比，不自动换人民币。

报告按方法论第 14 节固定 16 节写作，脱离 JSON 与台账仍能阅读、理解和核实。先解释含义与重要性，再给口径、公式、证据与限制；术语首次出现给中文全称及白话注解。关键主张就地引用直接链接或 `SRC-*`；文末索引为每个 ID 给完整 URL 与精确定位。报告只写经济事实、假设、计算、限制和反证；Schema 映射、验证 / 归档流程留在 sidecar。报告可见文本及来源索引不出现 Logo / `company_logo` / 公司标志 / 公司标识等资产词；有实质经济影响的变化用“品牌重塑”或“视觉识别变化”说明事实和影响。

桑基使用 `statement_value` 保留报表原符号，严格正值 `value = abs(statement_value)` 表示流量；收入抵减、成本抵减、利润加项和利润扣减按专项契约路由，不用负连线或静默净额化。勾稽绝对差 `<= 0.01`；`calculated_links` 恰好覆盖收入小计及利润主链每条 continuation 边。交接包含 [X 型布局与最少交叉意图](references/income-statement-sankey.md#下游-x-型布局与最少交叉)，不写坐标、不为造型改拓扑、金额、符号或颜色。

配色审计必须查规范身份与官方可验证别名，并裁决 `matched / not_found / blocked`：匹配时逐节点取样；完整检索无匹配时节点色留空，由 System 使用统一默认色；检索受阻是 error，不得冒充未找到或用 `--allow-warnings` 绕过。

## 6. 验证、冻结与历史包

命令从实际 Skill 根目录运行，`scripts/` 和 `references/` 均相对此目录；研究包、前序 manifest 和外部审计输出使用绝对路径。尖括号内容是待替换参数，不要原样执行。先完整执行 QA，再使用对应命令。

| 任务 | 台账 research_mode | 验证命令 | 冻结命令 |
|---|---|---|---|
| 首次完整研究 | `full` | `--mode full` | `--mode full` |
| 增量更新 | `incremental` | 最终仍用 `--mode full` | `--mode incremental` + 前序 manifest + 官方触发 ID |
| 修复 / Schema 迁移 | `repair / migration` | `--mode full` | 在新目录用 `--mode full` |
| 只读审查 | 不改原包台账 | `--mode audit`，输出在包外 | 不冻结 |

CLI 验证器的 `--mode incremental` 仅用于过程检查，不能替代最终 `full`；冻结器也会强制执行 `full` 门禁。

```bash
# 未冻结草稿：完整验证
python3 scripts/validate_research_package.py <absolute-package> \
  --schema references/specs/company.schema.json --company-slug <company-slug> \
  --mode full --output <absolute-package>/validation-report.json

# 获授权且零错误、语义复核完成后：首次 / 修复 / 迁移冻结
python3 scripts/freeze_research.py <absolute-package> \
  --schema references/specs/company.schema.json \
  --schema-blob-sha <locked-blob> --schema-commit <locked-commit> \
  --company-slug <company-slug> --mode full

# 增量冻结：不可省略前序与新官方触发
python3 scripts/freeze_research.py <absolute-new-package> \
  --schema references/specs/company.schema.json \
  --schema-blob-sha <locked-blob> --schema-commit <locked-commit> \
  --company-slug <company-slug> --mode incremental \
  --previous-manifest <absolute-previous-package>/research-manifest.json \
  --official-trigger-source-id <SRC-new-official-trigger>

# 只读诊断：历史包按 source-routing 的旧锁策略解释结果
python3 scripts/validate_research_package.py <absolute-frozen-package> \
  --schema <absolute-schema-for-audit> --company-slug <company-slug> \
  --mode audit --output <absolute-audit-directory>/validation-report.json
```

警告默认阻断；只有完整度说明逐项写明 finding code、原因、影响和待补证据时，才可按 QA 规则使用 `--allow-warnings`。只有真实人工审核才使用 `--human-reviewed`；自动审查不能冒充人工接受。风险加权来源审计必须实际重开关键来源，普通主张按确定性种子抽检，不能只检查多个文件互相一致。

旧 manifest v1、缺少当前完整性 profile 的历史 v2，以及 Schema 版本与当前锁不一致的包只读审查；不能作为当前 incremental 前序。迁移回原始来源重建新目录，通过当前 `full` 后重新冻结，不只改版本号、不向旧包补锁。历史审计结果不等于通过当前正式门禁，具体工具限制见来源路由。

## 7. 授权 GitHub 交付与完成状态

只有明确要求提交 / 合并时执行 [github-archive.md](references/github-archive.md)。目标固定为 `bits-bean/doujiao-value-system/companies/<company-slug>/`，整套受管研究文件以同一原子变更替换；不增加日期或版本子目录、不再向 `research/` 写副本。最终 diff 仅含 manifest 声明的研究文件、manifest，以及本次显式暂存且验收通过的一个 canonical Logo；其他资产保留。

新 Logo 路径固定为 `assets/logo.svg` 或 `assets/logo.png`，已验证 legacy 文件可原样沿用。第三方常设兜底仍传 `--confirm-third-party-logo` 作机械确认；远端不同 Logo 的替换、清除旧引用和新公司无 Logo 交付各遵守归档契约的独立授权。普通提交、人工接受和 warning 确认不能代替“允许无 Logo 提交”。要求合并到 `main` 时走独立分支和 PR，检查通过后合并；只有明确要求“直接提交到 main”才允许原子、非强制、仅快进直写。写前核最新 HEAD、Schema blob、slug / identity 与单调性，写后按 commit 重读并核对全部 SHA-256。

最终回复分别说明研究判断、包状态和交付状态。只有全部研究、Schema、一致性、配色与冻结门禁通过才称正式研究完成；否则写清草稿、证据缺口、待人工复核、审查结果或迁移未完成。Too Hard 可与合格冻结并存；冻结只表示不可变，不表示人工已接受、GitHub 已提交或网站已更新。Logo 缺口不改投资结论，但必须另报网站身份素材未完整。
