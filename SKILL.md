---
name: research-doujiao-value-company
description: Research, update, audit, repair, freeze, and explicitly authorized GitHub-deliver evidence-driven long-term company research under this Skill's authoritative protocol and the locked bits-bean/doujiao-value-system company Schema. Use for sourced company classification and chart-routing inputs, ten-year financials, industry metrics, ledgers, moat, durability, culture, management, capital allocation, risks, DCF or Reverse DCF, formal reports, schema-valid company.json, Too Hard decisions, frozen research handoffs, official-first company Logo handling with an authorized verified-third-party fallback, and company-level App Economy Insights Sankey color audits. Do not use to generate or redraw a Logo; manage other publishable visuals; render website or social images; call chart renderers or website APIs; choose channel ratios or layouts; produce social copy; publish content; predict short-term prices; or make unapproved GitHub writes.
---

# 豆角长期价值研究

本 Skill 是权威研究层：先从证据和可复算计算形成判断，再交付可独立阅读的报告、结构化数据、台账、网站所需的已验证公司 Logo，以及供网站与导出器共同消费的公司级桑基节点色。网站图表仍由 system 代码渲染；本 Skill 不制作发布用视觉成品。

## 1. 权威与边界

- manifest v2 的兼容研究协议由 `references/specs/project-instructions.md`、`research-methodology.md`、`automation-workflow.md` 三份锁定文档定义；不得改写其 `research_protocol` 元组。
- 当前正式执行另受 [research-execution-and-audit.md](references/research-execution-and-audit.md) 约束。`trusted-spec-lock.json.execution_integrity` 对规范、运行脚本和验证器建立完整性摘要；冻结包仍使用 `manifest_version: 2.0`，并以 `integrity_profile: execution-bound-v1` 和 `execution_integrity` 记录当前执行边界。
- `company.json` Schema 唯一可编辑源：`bits-bean/doujiao-value-system/schemas/company.schema.json`；本 Skill 副本只读且受信任锁保护。
- 不从旧聊天、旧报告或传播内容补事实；事实、管理层主张、第三方观点、推断和估算必须区分。
- 不编造、插值或无声填补缺失数据；`null`、`[]` 和真实零值严格区分。
- 企业质量、估值状态和研究状态分开。诚信、治理、资本韧性和数据可靠性可否决估值吸引力。
- 审查请求只诊断；修复、冻结和 GitHub 交付各需相应授权。网站导入、图表渲染、内容生产和公开发布不属于本 Skill。
- 本 Skill 不调用 `doujiao-value-system` 的图表导出命令或接口，不生成网站图、社媒图或背景，不选择平台比例、安全区、Logo 位置和引流文案，也不调用内容 Skill 代替用户生产或发布内容。
- 公司 Logo 是唯一可交付视觉素材例外。首次研究缺少 Logo、公司已重塑品牌，或用户明确授权替换时，完整执行 [identity-assets.md](references/identity-assets.md)：先复用 system 中已验证的 canonical Logo，否则依次检查公司官网、Investor Relations、官方品牌 / 媒体资料和适用的官方产品 / 商户 / 开发者 / 支持页面。本私有 Skill 已记录用户常设授权：官方来源全部穷尽且已记录后，可使用出处稳定、身份可交叉核验的第三方原始正方形 SVG / PNG；无需仅因第三方资格再次询问，但每项资产仍须逐项留证、保留原字节并在 `company.json.brand_identity.company_logo` 中如实使用 `is_official:false`。不得生成、重绘或用近似图替代公司 Logo，也不得清洗来源文件。
- 首次研究不能因第一个官方候选文件不安全、格式不合格或画布非方形就停止 Logo 搜索。按 `identity-assets.md` 继续检查官网当前页面实际加载的 DOM / CSS / 静态资源、IR、官方品牌或媒体资料，以及适用的官方产品、商户或支持页面；逐项记录候选 URL、格式、尺寸、是否正方形、核验结果和拒绝原因。官方原始正方形 SVG / PNG 始终优先；穷尽官方正方形候选后，才可对安全的官方非方形 PNG 做确定性中心方形裁剪。第三方兜底只接受通过同一安全与渲染门的原始正方形 SVG / PNG，不得裁剪、转码或改写。
- 除公司 Logo 与 [income-statement-sankey.md](references/income-statement-sankey.md) 明确限定的 App Economy Insights 配色核验外，本 Skill 不搜索、下载、筛选、核验、生成、暂存或提交产品、服务、人物、门店、业务场景、封面主视觉、背景及其他视觉素材。配色原始 PNG 只是冻结包外私有研究证据，绝不作为视觉资产交付；研究包只保存其摘要和逐节点样本审计。内容生产所需其他素材仍由 `$produce-doujiao-value-content` 在其任务内独立完成。
- 找不到可验证的官方 Logo，且仍找不到可验证的第三方原始正方形 Logo 时，写入 `asset_path:null`、`source_url:null`、`alt:null`、`is_official:false`，并在 `research-completeness.md` 记录 Logo 缺口；不得合成替代 Logo，也不得声称网站身份素材完整。采用第三方时，完整度说明必须显式记录官方来源穷尽、用户已授权常设兜底、第三方托管事实、身份交叉核验和网站展示影响。
- `research-report.md` 不保存 Logo 元数据、状态或流程；其余指定 sidecar / JSON 只保存所需 Logo 元数据，不嵌入 Logo、图片、视频、音频、HTML 媒体标签或 `data:` 媒体 URI。Logo 字节只存在于冻结目录外的交付 / 审计目录或 system 仓库。发生裁剪时，官方原件与 provenance 必须留在冻结目录外的持久工作目录，不能只依赖会被清理的临时文件。

## 2. 模式与读取顺序

模式：首次完整研究、增量更新、审查、修复并重新冻结、Schema 迁移、授权 GitHub 归档。冻结目录不可原地修改。

按 [source-routing.md](references/source-routing.md) 完整读取并锁定：

1. `project-instructions.md`；
2. `research-methodology.md`；
3. 只读 `company.schema.json`；
4. [research-execution-and-audit.md](references/research-execution-and-audit.md)；
5. 增量任务再读上一 v2 冻结包与 `automation-workflow.md`。

同时锁定兼容研究协议摘要、完整执行摘要、验证器 SHA-256、Schema commit / blob / SHA-256 / version、公司法定身份、证券、会计准则、财年、币种、单位、数据日、估值日和股价时间戳。`company_schema.schema_version` 表示新研究必须输出的当前活动/default 版本；Schema enum 中保留的旧版本只用于读取历史冻结包。先实测协议、Schema、官方来源、挑战来源、计算运行时和草稿目录写入六项能力；任一能力、锚点或关键官方来源不可验证时只能交付计划 / 缺口，不称正式完成。

正式研究使用 `standard` 档：主研究、隔离的对抗审查、隔离的来源审计和综合四个 pass 缺一不可；专项审计使用 `audit` 档并至少安排两个相互独立的对抗审查。各 pass 只提交主张、证据、反证和置信度，由综合 pass 裁决冲突，不让多个角色分别生成整份报告。

研究开始时完整读取 [classification-and-chart-routing.md](references/classification-and-chart-routing.md)，先用官方证据确定 `classification`，再选择会计、回报和行业指标框架。`sector` 与行业标签只用于检索；公司类型驱动的会计计算与资本回报图表路由只由 `accounting_profile` 和 `returns_profile` 控制。银行与支付信贷的回报图固定为长期 ROE / ROTCE 主序列、最新 CET1 / 资本充足率加目标或监管区间的当前仪表，以及“每股权益长期序列”或“至少三个完整财年的回购对股数影响”二选一；不得因缺少八年 CET1 或选择回购替代路径而改用普通企业模板。

## 3. 证据和十年财务

完整读取 [evidence-and-calculation.md](references/evidence-and-calculation.md) 与 [research-execution-and-audit.md](references/research-execution-and-audit.md)，先做 `evidence-ledger.json` 和 `calculation-ledger.json`，再写结论。

- 默认十个完整财年 + 最新季度 + TTM，统一财年变化、重述、拆股、并购、币种、单位和正负号。
- 按 [revenue-mix-history.md](references/revenue-mix-history.md) 查齐十年官方收入构成、金额与占比，逐年勾稽总营收并核对官方重列范围；最新财年补齐每类收入的付款方、付费原因、增长驱动及口径说明。商业模式章节交接收入来源、价值交换、利润流向、收入结构演变四部分；最新环形图及说明卡、十年水平金额与占比堆积图消费同一冻结数据，结构演变须解释赚钱方式及战略重心的变化。网站默认折叠经营解读，不在十年财务重复放图；不能只交总营收趋势或最新一年构成。
- 关键数字记录期间、口径、来源 ID 和页码 / 章节；推断和估算记录最强反证与推翻条件。
- 资料可得性与商业论点确定性分开评级；资料多不自动等于论点可靠，资料少也不自动等于公司差。
- 在证据台账中建立 2—5 项经营与价值驱动、管理层决策过程 / 结果台账、关键论断裁决、论点假设状态、被否决主张、未解冲突和版本修订记录。增量更新必须把假设及估值参数相对上一冻结版本的变化逐项归因，不能随现价无声漂移。
- 普通企业复算 FCF、Owner Earnings、ROIC、净债务、市值和 EV；金融、保险、REIT、资源等使用分类契约指定的行业适配口径，并把通用财务字段无法表达的序列写入 `industry_metrics`。
- 护城河同时读取竞争对手和替代品；长期生存把需求持久性、适应能力和外部冲击拆开验证；文化和管理层比较承诺与实际行动。

研究价值交换时同时读取 [business-model-actors.md](references/business-model-actors.md)：按当前公司的实际使用者、付款方、产品与交付渠道、供给与合作对象生成具体名称和关系，不套“客户 / 产品与渠道 / 生态伙伴”四角色模板。把有来源的对象、连线及插图语义写入证据台账 `business_model`，由下游按真实对象数量和身份渲染。

## 4. 长期价值判断

完整执行方法论第 1—13 节。每个模块都写清：问题、事实 / 计算、支持证据、最强反证、置信度和推翻条件。至少覆盖商业模式、十年财务、现金质量、回报与再投资、护城河、长期生存、文化 / 不为清单、管理层 / 资本配置、治理 / 债务、估值和 Pre-Mortem。把当时信息下的管理层决策过程与事后结果分开评价；任何关键论断未经隔离挑战和裁决都不能进入最终结论。

遇到商业模式无法验证、关键数据缺失、多个低确定性变量决定结果或 DCF 几乎全靠遥远终值时，主动归入 Too Hard，说明难点、缺证、移出条件和不行动理由。

## 5. 现金流估值

完整读取 [valuation-qa.md](references/valuation-qa.md)，以计算台账中唯一的 `valuation_role: starting_cash_flow` 作为 DCF 与 Reverse DCF 共用起点。普通企业使用 FCFF、FCFE 或 Owner Earnings；受资本约束金融企业使用“正常化普通股净利润 − 必要留存资本”的可分配普通股现金。总额先折现、再除以稀释后股数；EPS 与倍数只作交叉验证。

先登记主 DCF、Reverse DCF 与交叉验证的适用性，再比较结果。Pre-Mortem 的每项重大风险只能归入现金流、情景、尾部情景或折现率之一，避免重复扣罚；模型方向冲突必须解释适用边界并裁决。DCF 3×3 九格逐格给出估值状态；若会翻转结论，只能降级置信度或归入 Too Hard。

估值正文必须让读者沿一条连续算式复核：估值基准日可分配现金 → 每个预测年度的经营驱动与可分配现金 → 折现因子与现金流现值 → 终值及其现值 → 股权价值 → 稀释后每股价值。悲观、基准、乐观三个情景都必须逐年列示，不得只给增长率与最终答案。任何分段假设都写成“第1—5年”“第6—10年”等明确范围；“初期、前期、中期、后期、第一阶段、长期增长”等词若没有紧邻的起止年度，不得作为估值假设名称。计算台账保存同一组逐年记录和价值桥接，报告展示值必须与其复算一致。

## 6. 正式研究包

按 [research-contract.md](references/research-contract.md) 建立新版本目录；生成 `income_statement_sankey` 时完整执行 [income-statement-sankey.md](references/income-statement-sankey.md)，并在计算台账完成 App Economy Insights 规范身份与官方可验证别名检索、`matched / not_found / blocked` 三态裁决和逐节点取样审计。`company.json.income_statement_sankey.nodes[].color` 是网站与导出器唯一渲染真相；不得建立任务级 palette sidecar。`classification`、`financials`、`industry_metrics`、`income_statement_sankey`、`segments`、二十年以上的结构化 `durability` 判断、承诺的下次验证、资本配置结果、风险因果链、估值敏感性和长期跟踪方法必须是有来源的研究产出，不能留给网站或内容层猜测。证据台账还必须保存预检、独立 pass、研究可得性、驱动图、管理层决策、论点状态、估值审查与来源审计。每个结构化 `source_ids` 必须解析到同一 `company.json.sources`，关键计算另由计算台账提供公式、输入和来源，使 system 图表和下游内容无需重新研究即可追溯。`research-report.md` 采用方法论第 14 节的固定 16 节，面向没有财务专业背景但愿意认真阅读的投资者；脱离 JSON 和台账仍可独立阅读、理解及核实。先讲“这意味着什么、为什么重要”，再给口径、公式、证据和限制。缩写、行业指标及非通用术语首次出现时，在同一句或相邻括号内给中文全称和一句白话注解。关键主张就地引用直接链接或 `SRC-*`；使用 `SRC-*` 时文末索引给完整 URL 和精确定位。

Schema 2.3.0 的每个桑基节点以 `statement_value` 保留报表原符号，以严格正值 `value = abs(statement_value)` 作为守恒流量；`profit_addition` 必须严格为正，`cost_offset / revenue_offset` 必须严格为负。收入抵减只能由 `revenue_subtotal` 以终端分流表达，不能作为正流量源接入净收入；只有 `profit_subtotal` 可在后续利润节点另有受控正收益加项时无成本分支续接，`revenue_total` 首层仍必须分出成本。不得用负连线或静默净额化。金额勾稽只允许绝对差 `<= 0.01`；台账 `calculated_links` 必须恰好覆盖收入小计和利润主链的每条 continuation 边并绑定可复算记录。

研究层不写死节点坐标，也不调用图表渲染器；但桑基交接必须携带 [income-statement-sankey.md](references/income-statement-sankey.md#下游-x-型布局与最少交叉) 的下游布局意图：入口侧最上 / 最下分支尽量落在左上角 / 左下角，出口侧最上 / 最下分支尽量落在右上角 / 右下角，中间主干居中，使整体尽量呈 X 型；下游必须通过节点顺序、端口顺序和局部路由走廊优先消除可避免的连线交叉。不得为造型改变会计拓扑、连接关系、金额、有符号语义、利润层级或节点配色。

正文只保留投资判断所需的事实、假设、计算过程、限制与反证。Schema 字段映射、JSON 文件名、验证器兼容、归档或生成流程等内部实现说明写入 `schema-gap-report.md`、`research-completeness.md`、台账或 manifest，不塞进研究叙事。Logo 的搜索、取得、核验、文件规格或路径、缺失、回退、归档和交付状态，以及桑基配色的检索、取样、原图、默认色和渲染状态，一律不写入 `research-report.md`；报告可见文本和来源定位索引都不得出现 Logo / `company_logo` / 公司标志 / 公司标识等资产词。若品牌或视觉识别变化本身对生意、护城河或股东价值有实质影响，改用“品牌重塑”或“视觉识别变化”等面向读者的经济表述，只写可验证的事实与影响，不写资产处理过程。字段背后的真实经济假设仍须在正文直接说清。例如正文应写“第1—5年收入与普通股利润都按8%增长”，而不是解释某个 Schema 字段为何暂存同一数值。

`company.json` 严格通过锁定 Schema，不新增字段。Schema 暂时无法表达的估值口径保留在报告、计算台账和 `schema-gap-report.md`，不得把旧字段静默改义。新研究的 `company.json` 与 `calculation-ledger.json` 统一存实际原始数值：人民币100万元写 `1000000`，100万股写 `1000000`，比例仍写 `0.25`；不得使用千、百万或十亿缩放值，计算台账也不得逐条添加 `unit`。所有面向中国读者的文字、表格、图表和最终回复再按 [research-contract.md](references/research-contract.md#中文展示单位契约) 换算：公司级金额优先用亿元，超大规模可用万亿元，股数用万股 / 亿股，每股值用原币种 / 股，比例用百分比。

## 7. 验收与冻结

完整执行 [qa-gates.md](references/qa-gates.md)，然后运行：

```bash
python3 scripts/validate_research_package.py <package> \
  --schema references/specs/company.schema.json --company-slug <company-slug> --mode full \
  --output <package>/validation-report.json
```

零错误并完成语义复核后冻结：

```bash
python3 scripts/freeze_research.py <package> \
  --schema references/specs/company.schema.json \
  --schema-blob-sha <locked-blob> --schema-commit <locked-commit> \
  --company-slug <company-slug>
```

新 manifest 固定为 v2，保留既有 `research_protocol` 兼容块，并新增 `integrity_profile: execution-bound-v1` 与当前 `execution_integrity`；验证报告与 manifest 同时锁定精确 `company_slug`，并记录验证器、工具链和协议指纹。Logo 元数据与桑基节点色随 `company.json` 被锁定，配色检索和取样摘要随 `calculation-ledger.json` 被锁定；私有 App Economy Insights PNG 永不进入冻结包。`blocked` 配色审计必须产生 error，不能用 `--allow-warnings` 绕过。包外 Logo 字节要到授权归档规划时才按 observation、hash、安全门和固定渲染运行时验证。风险加权来源审计必须重新打开公司身份、估值输入、起始现金流、DCF 假设、适用的监管资本及全部关键论断来源，并按确定性种子抽检普通主张。警告默认阻断；只有完整度说明逐项解释原因、影响和待补证据时才能 `--allow-warnings`。该通用 warning 确认只允许冻结研究，不构成新公司无 Logo 的 GitHub 交付授权。只有真实人工审核后才使用 `--human-reviewed`。冻结只表示不可变，不等于投资建议、网站已具备 Logo 或网站已更新。

旧 Schema → 当前锁定 Schema 2.3.0 是显式迁移：旧冻结包保持不可变且只按旧 manifest 审计；从原始来源重建当前协议要求的结构字段，在新目录按 2.3.0 完整验证后以 `full` 模式冻结。Schema 1.x、2.0.0、2.1.0 与 2.2.0 包都不得直接作为当前 2.3.0 `incremental` 的前序包，也不得仅改 `schema_version`。

## 8. 增量与下游

增量只由比上一报告更新的官方财报或重大事件触发，按公司、期间、发布日期和 source ID 去重。复核旧包、更新受影响事实 / 计算 / 估值 / verdict，并在 `thesis` 中明确长期逻辑：增强 / 基本不变 / 削弱 / 被推翻 / 暂无法判断；假设状态或估值参数的每一处变化都必须绑定新证据和修订原因。

system 图表层与内容层只接收同一冻结版本的报告、`company.json`、manifest、完整度说明、证据台账和计算台账；桑基网页与导出器必须共同消费 `company.json` 节点色，并用计算台账审计其 `matched / not_found` 来源，不得在内容任务重新搜索或覆盖。公司 Logo 作为 manifest 外的已验证身份素材按 `identity-assets.md` 单独交接，供 system 网站身份展示直接读取。社媒内容任务的其他素材仍按内容 Skill 自身契约独立核验，本 Skill 不把研究归档路径解释为内容制作授权。下游可以格式化、重排或用同一冻结序列计算展示派生值，但不得补研究事实、重算估值、改变路由、覆盖配色或覆盖结论。本 Skill 在交接完成后停止，不调用渲染器、内容 Skill 或发布接口。

## 9. 授权 GitHub 提交

用户明确要求提交 / 合并时完整读取 [github-archive.md](references/github-archive.md)。只把人工已接受、v2、零错误的冻结包提交到 `bits-bean/doujiao-value-system`。

- GitHub 当前研究包固定为 `companies/<company-slug>/`，报告、`company.json`、台账、验证结果与 manifest 全部直接放在该目录；不得增加日期、`-vN` 或其他版本子目录，远端版本只由 Git 历史追踪。
- 每次获授权提交都以同一原子变更创建或替换 `companies/<company-slug>/` 内的整套研究文件；`company.json` 只保留这一份正式副本，不再同步写入 `research/`。已有且与 `company.json` 一致的 Logo 原样保留；缺失或明确授权替换的 Logo 按 `identity-assets.md` 验证后与研究文件进入同一原子提交。
- 新 canonical Logo 固定使用 `companies/<slug>/assets/logo.svg` 或 `companies/<slug>/assets/logo.png`；已有 `logo-primary.svg` 或 `logo-primary.png` 只作为 legacy 沿用。官方或依常设授权采用的第三方原始正方形文件都保持原字节；第三方必须记录 `is_official:false`。归档规划时仍传 `--confirm-third-party-logo`，用于机械确认冻结包确实满足常设规则，不构成新的第三方许可提问；GitHub 写入、远端不同 Logo 替换和直接 main 仍分别遵守其独立授权门。唯一转换例外仍是经 `identity-assets.md` 证明的官方 PNG → PNG 确定性中心方形裁剪，计划必须明确标记 `official_source_derived:true`。不得在 SVG 与 PNG 之间转换、包裹、清洗或重绘。最终差异白名单仍只包含冻结 manifest 声明的直接研究文件、`research-manifest.json`，以及本次显式暂存且通过门禁的一个 canonical Logo；原件与 provenance 不写入 GitHub。任何 `images/*`、产品图、图片 manifest、封面、背景或其他素材仍禁止进入研究归档。
- 远端已有 Logo 只能精确沿用或经另行授权替换；若已确认没有可验证的官方 Logo 和已授权第三方兜底，可在完整记录缺口后用独立的“清除旧引用”授权把四元组改为精确空哨兵。清除只更新 `company.json` 引用，不删除旧文件，也不能代替 Logo 替换授权。
- system 中尚不存在的新公司若仍为 Logo 空哨兵，普通“提交到 GitHub”授权必须停止；只有用户另外明确说“允许无 Logo 提交”或语义完全等价的话，才可使用 `--confirm-new-company-without-logo`。`--allow-warnings`、人工接受或普通写入授权均不得推导该确认。
- 禁止把任何网站截图、渠道成品、`images/` 生成图、背景、比例模板或平台文案作为研究提交的一部分。
- 研究请求、冻结请求仍不自动授权 GitHub；“提交到 GitHub”授权的唯一目标是上述公司目录。
- 用户要求合并到 `main` 时走独立分支和 PR，检查通过后合并；只有明确说“直接提交到 main”才允许原子、非强制、仅快进直写。
- 写入前核对最新 HEAD、Schema blob、slug / identity、远端当前公司目录和 `company.json` 单调性；写入后按 commit 重读全部文件并核对 SHA-256。

## 10. 完成状态

只有证据、计算、行业适配、现金流估值、16 节报告、Schema、一致性、桑基配色三态和冻结门禁全部通过，才称正式研究完成；否则准确标记为计划、草案、证据不完整、待人工复核、Too Hard、审查结果或迁移未完成。App Economy Insights 检索若 `blocked`，只能保留草稿，不能冻结；`not_found` 是完成态并由 System 使用统一默认色。Logo 缺失不改变投资研究结论，但必须在 `company.json` 与 `research-completeness.md`（必要时台账、manifest 或归档输出）明确标记网站身份素材未完整；`research-report.md` 不出现 Logo 或配色状态与流程。新公司的首次 GitHub 归档仍默认阻断，除非用户独立明确接受无 Logo 交付。
