# 研究包与冻结交接契约

## 目录

- [版本化目录](#版本化目录)
- [必需文件](#必需文件)
- [执行与审计记录](#evidence-ledgerjson)
- [中文展示单位契约](#中文展示单位契约)
- [Schema 迁移](#schema-迁移)
- [冻结语义](#冻结语义)
- [下游交接](#下游交接)
- [视觉素材边界](#视觉素材边界)
- [GitHub 归档](#github-归档)

## 版本化目录

每个研究版本使用独立目录：

```text
research/<company-slug>/<YYYY-MM-DD>/
├── research-report.md
├── company.json
├── research-completeness.md
├── evidence-ledger.json
├── calculation-ledger.json
├── validation-report.json
├── schema-gap-report.md        # 仅发现 Schema 问题时
└── research-manifest.json      # 冻结时生成
```

不得原地修改已冻结目录。日期冲突时追加稳定版本后缀，例如 `2026-08-19-v2`。

`companies/<company-slug>/company.json` 是 system 仓库中的当前正式公司数据路径。只有用户明确授权 GitHub 交付时，才把冻结版本同步到该路径；研究包内的 `company.json` 是本次冻结快照。本 Skill 不调用网站 API、图表渲染器或渠道图片流程。

## 必需文件

### research-report.md

按本 Skill `references/specs/research-methodology.md` 第 14 节的顺序完整包含 16 个部分，每节都有实质正文，不得合并、缺省或用占位文本替代。一页式结论和最终结论必须以明确字段分别给出企业质量、估值状态、研究状态、置信度、2—4 项关键前提和 thesis breakers，且前后一致。最终结论还必须展示方法论第 13 节规定的八维评分；护城河和 Pre-Mortem 必须逐项包含方法论第 5、11、14 节规定的全部字段。

报告必须在脱离 `company.json`、证据台账、计算台账和完整度说明时仍可独立阅读和核实。伴随文件用于补充结构化数据、审计轨迹和机械复算，不得代替关键主张的正文解释、就地引用或来源定位。禁止使用“完整 URL 见 `company.json.sources`”或类似表述。

正式报告的第一读者是假定不了解会计、银行监管或估值模型的长期投资者。每节先用白话回答“公司怎样赚钱、这个数字说明什么、为什么影响股东”，再展开专业口径。缩写、行业指标和非通用术语首次出现时，必须在同一句或紧邻括号内给出中文全称、缩写和一句通俗注解；注解至少说明“它衡量什么”或“它为什么重要”。例如：`投入资本回报率（ROIC：每投入1元经营资本能产生多少税后经营利润）`。公式出现前先解释经济含义，公式中的每个变量在旁边定义，不让读者去其他文件猜。

正文与内部实现分层：`research-report.md` 只写投资者理解结论所需的经济事实、假设、计算、限制、反证和来源，不写 Schema 字段映射、JSON 文件名、验证器规则、兼容策略、冻结或生成流程。这些说明分别进入 `schema-gap-report.md`、`research-completeness.md`、证据/计算台账或 manifest。经济假设不能随实现说明一起移走：若收入与利润采用同一增速，正文应直接写明对应情景、准确年度范围和两个指标的增速；“某字段为了兼容而填成同一数值”则放在 `schema-gap-report.md`。

正式报告使用可见的纯 Markdown；除无属性 `<br>` / `<br/>` 外不得包含原始 HTML，也不得把结构或正文藏进 fenced code、HTML comment 或不可见容器。

关键数字和关键主张在出现处就地引用直接链接或标注 `SRC-*`。采用 `SRC-*` 时，精确定位由文末来源定位索引统一解析，正文不必重复；索引必须对每个 ID 给出标题、发布者与来源类型、发布日期或适用期间、直接 URL，以及页码、监管文件 Item/表号、稳定章节或时间戳中的至少一项。每项结论先给通俗含义，再给技术口径、计算和限制。

报告用白话呈现 2—5 个经营与价值驱动、管理层关键决策的过程与结果、当前关键假设、相对上一版本的论点变化、重要冲突和估值模型边界。能力探针、actor、抽样种子和机器状态只保存在证据台账 / manifest，不写进投资叙事；但它们支持或削弱的经济结论不能从正文消失。

### company.json

严格通过锁定 commit 的 `schemas/company.schema.json`。不得加入研究包状态、冻结哈希、制作说明或平台内容；这些属于 sidecar 文件。

当前 Schema 2.1.0 允许读取历史 2.0.0 包，但新研究固定写 `meta.schema_version: 2.1.0`。财务期在官方披露可得时分别保存总净利润、归属于普通股股东的利润和公司报告的稀释 EPS；缺失使用 `null`。不得用 `net_income ÷ diluted_shares` 生成 `diluted_eps`，也不得把归母口径与总净利润无声混用。

Schema 2.x 的 `classification` 与 `industry_metrics` 必须完整执行 [classification-and-chart-routing.md](classification-and-chart-routing.md)。分类来自官方业务与监管证据；宽 sector 和行业 slug 仅用于标签与检索，只有 `accounting_profile` 和 `returns_profile` 控制会计、回报和下游图表路由。行业指标按 `period + code` 唯一，并保留 `value_type` 与来源。银行与支付信贷的主 ROE / ROTCE 必须是长期序列；资本约束可用最新 CET1 / 资本充足率配合同期管理层目标区间或监管最低要求作当前仪表；第三板块必须在每股权益长期序列和至少三个完整财年的回购对股数影响中二选一。当前资本截面不能冒充长期趋势，须在完整度说明中标明限制。

`durability` 必须以至少二十年为期限，分别记录需求持久性、适应能力和外部冲击的标准化状态、判断、证据、破坏条件及来源，并给出总体状态与结论。长期生存不能由护城河分数、估值终值或一句叙事反推。

管理层承诺必须包含兑现状态、结果和下一验证对象；`pending` 可把尚未发生的结果写为 `null`，其他状态必须记录可观察结果。资本配置必须包含三车道、结果状态、结果和评价；`risks.pre_mortem` 必须是一组完整因果链；概率、影响或缓解措施无证据时写 `null`，不得为图表猜测。每个长期跟踪指标必须包含重要性和复查方法。这些字段是研究事实与判断，不由下游根据文字或缺失字段重建。

`income_statement_sankey` 的提取清单、动态层级模板、计算值来源绑定与逐层勾稽统一执行 [income-statement-sankey.md](income-statement-sankey.md)，不得另建简化口径。

system 图表与下游内容所需的数据、路由和来源必须在冻结前完成。最低交接映射为：

| 展示语义 | 冻结研究数据 |
|---|---|
| 公司身份与路由 | `meta`、`classification`、`brand_identity` |
| 商业模式与收支 | `segments`、`income_statement_sankey` |
| 十年财务与资本回报 | `financials`、`industry_metrics`、`buyback_ledger` |
| 护城河与长期生存 | `moat`、`durability` |
| 文化与资本配置 | `management`、`capital_allocation` |
| 估值 | `valuation` 及计算台账中的起始现金流、逐年折现、终值和股权价值桥接 |
| 风险与长期跟踪 | `risks.pre_mortem`、`risks.monitoring_indicators`、`verdict` |

每个结构化 `source_ids` 必须解析到同一 `company.json.sources`；计算图需要的公式、输入、结果、期间和来源必须在 `calculation-ledger.json` 中可复算。下游不得从报告散文、图像或字段缺失反推公司类型、补数、换模板或重算估值。

### research-completeness.md

至少列出：

- 已取得和缺失的财年、季度、TTM；
- 无法验证或只能估算的字段；
- 低置信度结论及原因；
- 会计口径、重述、拆股、并购或币种可比性限制；
- 对最终结论和估值的影响；
- 尚待取得的关键证据；
- 研究可得性和商业论点确定性各自的限制；
- 能力预检、关键来源审计或独立性存在的任何真实缺口。

### evidence-ledger.json

严格执行 [research-execution-and-audit.md](research-execution-and-audit.md)。根级结构使用：

```json
{
  "ledger_version": "2.0",
  "run": {
    "run_id": "RUN-2026-08-24-001",
    "research_mode": "full",
    "workflow_tier": "standard",
    "data_cutoff_at": "2026-08-24T17:00:00Z",
    "status": "ready_to_freeze",
    "protocol_fingerprint": {},
    "preflight": [],
    "passes": []
  },
  "researchability": {},
  "business_driver_map": {"equation": "", "value_capture_chain": [], "drivers": []},
  "management_decision_ledger": [],
  "thesis": {
    "overall_change": "baseline",
    "assumptions": [],
    "valuation_assumption_changes": [],
    "rejected_claim_ids": [],
    "unresolved_conflicts": [],
    "revision_log": []
  },
  "valuation_review": {
    "model_applicability": [],
    "risk_placements": [],
    "model_conflicts": [],
    "conclusion_stability": {}
  },
  "source_audit": {"audit_pass_id": "PASS-AUDIT", "selection_seed": "...", "checks": []},
  "claims": [
    {
      "id": "CLM-001",
      "claim": "可验证的主张",
      "classification": "fact",
      "research_module": "business",
      "decision_relevance": "critical",
      "period": "FY2025",
      "source_ids": ["SRC-001"],
      "location": "Annual report p. 42",
      "confidence": "high",
      "counterevidence": [],
      "counterevidence_search": "重新检索竞争对手与监管原件",
      "adjudication": "upheld",
      "would_falsify": "什么新证据会推翻该判断"
    }
  ]
}
```

`run` 先完成六项真实能力探针，正式标准档再记录主研究、隔离对抗审查、隔离来源审计与综合四个 pass；审计档至少两个独立对抗审查。`researchability` 把资料可得性与论点确定性分开。驱动图、管理层决策过程 / 结果、关键论断裁决、假设状态、被否决主张、未解冲突、估值适用性、风险归位、模型冲突、九格稳定性与来源抽检都不得省略。

`classification` 只使用 `fact / management_claim / third_party / inference / estimate`；`confidence` 只使用 `high / medium / low`。`decision_relevance: critical` 的论断必须有反面检索、可检验推翻条件并由隔离 pass 裁决。被否决论断保留在 `claims`，不得删除；增量研究的假设与估值参数变化必须连接上一冻结版本和新证据。

`source_audit` 的审计者必须重新打开原始来源，100% 核验身份 / 证券、估值日股价 / 股数 / 市值 / EV、唯一起始现金流、DCF 关键假设、适用的监管资本以及全部关键论断。普通主张以规范化 `company.json` SHA-256 为确定性种子抽检至少 15%，存在普通主张时不少于三条；文件间自洽检查不能替代来源重开。

### calculation-ledger.json

使用：

```json
{
  "numeric_convention": "base_units",
  "calculations": [
    {
      "id": "CALC-001",
      "metric": "free_cash_flow",
      "period": "FY2025",
      "formula": "operating_cash_flow - capex_total",
      "inputs": {"operating_cash_flow": 100000000, "capex_total": 25000000},
      "result": 75000000,
      "tolerance": 100,
      "source_ids": ["SRC-001"]
    }
  ]
}
```

根级 `numeric_convention` 必须且只能是 `base_units`。金额写报告币种的实际数值，股数写实际股数，比例写十进制小数；例如100万美元写 `1000000`，100万股写 `1000000`，25%写 `0.25`。不得用千、百万、十亿缩放数字，也不得在单条计算中添加 `unit` 字段。标准 `metric` 优先使用 `free_cash_flow / net_debt / market_cap / enterprise_value / custom`。每项计算都必须有期间、非空输入、有限数值结果和来源；标准计算结果必须回写并匹配同期间的 `company.json` 字段。`custom` 还必须提供 `review_method`，说明公式、口径与独立复核方法，例如：

```json
{
  "id": "CALC-ROIC-2025",
  "metric": "custom",
  "period": "FY2025",
  "formula": "NOPAT / average_invested_capital",
  "inputs": {"NOPAT": 120000000, "average_invested_capital": 800000000},
  "result": 0.15,
  "review_method": "与年报税前利润、有效税率及期初期末投入资本逐项复核",
  "source_ids": ["SRC-001"]
}
```

非 Too Hard 的完整研究还必须有且只有一个 `valuation_role: "starting_cash_flow"` 的 `custom` 计算，作为 DCF 与 Reverse DCF 的统一起点：

```json
{
  "id": "CALC-DCF-START",
  "metric": "custom",
  "valuation_role": "starting_cash_flow",
  "cash_flow_basis": "distributable_common_cash",
  "period": "FY2025",
  "formula": "normalized_common_net_income - required_retained_common_equity",
  "inputs": {
    "normalized_common_net_income": 10833000000,
    "required_retained_common_equity": 2166600000
  },
  "result": 8666400000,
  "diluted_shares": 679000000,
  "per_share": 12.7635,
  "forecast_years": 10,
  "review_method": "用普通股利润、目标监管资本与风险资产增长需求独立复核，并核对总额除以稀释后股数",
  "source_ids": ["SRC-001"]
}
```

`cash_flow_basis` 只使用 `fcff / fcfe / owner_earnings / distributable_common_cash`。`result` 是报告币种的实际总额，`diluted_shares` 是实际股数，`per_share = result / diluted_shares`；`forecast_years` 是正整数。不得使用 EPS、PE 或退出倍数充当起始现金流。

同一 `calculations[]` 还必须保存三情景的完整估值链，不能只保存最终价值：

| `valuation_role` | 每个情景的最低内容 |
|---|---|
| `annual_discounted_cash_flow` | 从第1年到 `forecast_years` 每年一条；含 `valuation_scenario`、`forecast_year`，并以 `cash_flow * discount_factor` 复算该年现值 |
| `terminal_present_value` | 含最后一年现金流、永续增长率、折现率和末年折现因子，复算终值现值 |
| `equity_value_bridge` | 以显性期现金流现值之和加终值现值、再完成适用的净债务等调整得到股权价值，并以实际稀释后股数复算每股价值 |

`valuation_scenario` 只使用 `bear / base / bull`。三个情景的年度必须连续、无重复且完整覆盖 `1..forecast_years`；每条仍遵守 `custom` 计算的公式、来源和独立复核要求。普通企业的年度计算输入另保留收入、利润率、税率、折旧摊销、资本开支和营运资金等适用驱动；受资本约束金融企业另保留普通股利润、RWA、目标 CET1、必要资本留存和 FCFE。某项驱动不适用时不造数，但应在 `review_method` 说明现金流如何形成。

`formula` 必须是可机械复算的受限算术表达式，可写为纯表达式或 `result = expression`。变量名必须与 `inputs` 完全一致；只允许有限数值、括号和 `+ - * / % **`，不允许函数、属性、索引、条件表达式或未使用输入。`result` 必须在允许误差内与复算结果一致。

Too Hard 研究若存在可豁免的结构缺口，每个 warning code 都必须在 `research-completeness.md` 单独记录，例如：

```text
- empty-sankey｜原因：披露不足，无法可靠重构；影响：资金流方向暂不能确认；待补证据：取得完整分部附注后重建并复核。
```

缺少原因、影响或待补证据/退出条件的笼统确认不能用于 `--allow-warnings`。

### schema-gap-report.md

只有 Schema 无法表达重要信息、字段语义不清、重复或与方法论冲突时生成。说明现状、影响、建议和兼容方案；不得擅自修改 Schema。字段借用、同值映射或兼容性解释也放在这里，不进入面向投资者的研究正文；报告只保留对应的真实经济假设和对估值的影响。

## 中文展示单位契约

展示层与储存层严格分开：

- **面向人的展示层**：`research-report.md`、`research-completeness.md`、`schema-gap-report.md`、研究摘要、最终回复及报告内表格，全部使用中国投资者自然阅读的单位。
- **机器储存层**：新研究的 `company.json` 与 `calculation-ledger.json` 只存实际原始数值；金额为 `report_currency` 的实际数值，股数为实际股数，比例为 decimal。不得使用 thousand / million / billion 缩放值，也不得把展示层“亿、万股、%”写回机器数据。

展示层按下表转换，保留原报告币种，不自动换算人民币：

| 数值类型 | 中文展示 | 示例 |
|---|---|---|
| 公司级金额 | 优先亿元；数万亿元量级可用万亿元；小额才用元 / 万元 | `186800000000` → `1,868亿元` |
| 股数 | 总股本 / 稀释后股数优先亿股，较小变动可用万股 | `9153000000` → `91.53亿股` |
| 股价与每股值 | 人民币用元/股；外币用港元/股、美元/股等 | `20.41` → `20.41元/股` |
| 比例 | decimal 转为百分比；变化量区分百分点和基点 | `0.25` → `25%`；`0.005` 的利润率变化 → `0.5个百分点` |
| 倍数 | 使用“倍” | `12.5x` → `12.5倍` |
| 人数、客户、卡量、交易笔数 | 按规模使用万 / 亿，并写清对象 | `120000000` → `1.2亿用户` |
| 行业实物指标 | 保留可比口径，单位改为中文常用写法 | `mbpd` → `百万桶/日`，首次出现解释 |

同一表格 / 图表使用同一币种、同一缩放单位和一致精度，单位放在标题、表头或图例；叙述中的独立数字必须自身带单位。数字通常保留不超过两位小数并使用千分位，来源要求更多精度时可保留，但不得制造虚假精确。外币换算人民币只有在分析确有需要时进行，并注明汇率、日期与来源。

以下情况一律视为展示错误：把 `million / billion / 百万元 / 百万股` 直接写进中文成品；把底层 `186800000000`、`9153000000` 等裸数字放入金额或股数字段；表格既无统一单位也不给单元格标单位；把 `0.25` 原样展示而不是写成 `25%`；把百分比变化误写成百分点。DCF 输入表必须同时显示已换算的估值基准日现金总额、稀释后股数、基准日每股现金和明确预测年限，并由验证器反向换算到台账值复核。

历史冻结包保持不可变。旧包若由其 manifest 锁定的旧 Schema 声明 `million`、`million_shares` 等缩放单位，审计时必须按旧锁解释；创建新版研究时再把金额和股数机械换算为实际原始数值，重新验证并冻结，禁止原地修改或把旧值直接当作新口径。

## Schema 迁移

- 旧 Schema 冻结包保持不可变，只按其原 manifest 和旧 Schema 审计；不得在旧目录补字段或改版本号。
- 新建迁移目录，从原始来源重新验证分类、行业指标、二十年长期生存三维判断、承诺结果与下一验证、资本配置结果、风险因果链和长期跟踪方法；不得把旧自由文本机械塞入新字段，也不得从网站展示、护城河分数或估值字段反推公司类型与长期生存结论。
- 迁移包必须通过当前锁定 Schema 2.1.0 的 `full` 验证并作为新的完整基线冻结。Schema 1.x 与 2.0.0 manifest 都不能成为 2.1.0 `incremental` 前序；后续增量从这个 2.1.0 基线开始。
- 数据日和估值日不得因迁移回退。只允许从语义版本更低的 Schema 升级到当前锁定版本，禁止降级；同日迁移属于结构化重建，必须经过人工接受，归档时同时显式确认 Schema 迁移和同日修订。
- 远端 `companies/<slug>/` 仍使用整包替换；只替换受管研究文件，保留 `images/` 和其他非研究资产。公司 Logo 由独立单文件门禁决定保留、创建或在另获明确授权后替换。

## 冻结语义

`research-manifest.json` 是 sidecar，不写入 `company.json`。新冻结清单继续固定使用 `manifest_version: 2.0`，以保持现有下游兼容；同时使用 `integrity_profile: execution-bound-v1` 声明当前正式执行，并分别记录：

- `research_protocol`：原样保留 v2 兼容元组，包括 authority、repository、ref、历史发行 commit、`protocol_version`、聚合摘要及三份兼容文档 SHA-256/大小；
- `execution_integrity`：当前规范与工具链的逐文件清单、规范摘要、工具链摘要、聚合摘要和源码绑定验证状态；
- `specification`：只记录权威 Schema 仓库、ref、精确 commit、路径、Schema SHA-256、Git blob SHA 与 `schema_version`；
- `schema_version`、公司身份、数据日、估值日；
- 验证与交付使用的精确 `company_slug`；
- 报告、JSON、台账和验证报告的 SHA-256；
- 验证错误与警告数量，以及验证器 SHA-256、工具链摘要和 `protocol_fingerprint`；
- 冻结时间和人工审核状态。

`execution_integrity` 必须与当前信任锁完全一致；验证器自身和新增执行脚本均在工具链摘要内，不能由未受信脚本自报通过。`evidence-ledger.json.run.protocol_fingerprint`、验证报告与 manifest 的协议 / Schema / 验证器身份必须一致。外部源码 commit 没有实证时记录未验证，不能以格式正确的 commit 字符串替代来源绑定证明。

`status: frozen` 仅表示研究快照不可变。Logo 元数据随 `company.json` 哈希被锁定，但 manifest 不锁定包外 Logo 字节；字节、来源 observation、安全性和实际渲染结果在授权 GitHub 交付规划时另行验证。默认 `human_review_status: pending`；只有实际人工审核后才标为 `accepted`。冻结不代表投资建议、网站已具备 Logo、网站已更新、图表已导出、渠道图片已生成或内容已发布。

历史 `manifest_version: 1.0` 只允许 `audit` 模式复核。它不能成为新增量版本的前序 manifest，不能重新冻结、GitHub 归档或作为当前正式下游交接；要继续使用必须按当前研究协议与 Schema 迁移并新建 v2 版本目录。历史 v2 若缺少当前 `integrity_profile` 或 `execution_integrity`，同样只允许 audit 诊断，不得原地补字段后重新冻结，也不得作为当前 incremental 的前序包。

## 下游交接

交给 `doujiao-value-system` 图表层或 `$produce-doujiao-value-content` 的必须是同一冻结目录中的报告、`company.json`、证据台账、计算台账、完整度说明和 v2 manifest；公司 Logo 作为 manifest 外的单独身份素材交给 system。下游先验证文件哈希、不变的 `research_protocol`、Schema 锚点与版本、公司身份、数据日和估值日一致，再读取或展示数据。当前研究侧在交接前还必须验证 `integrity_profile` 与 `execution_integrity`；旧下游对未知 v2 顶层字段的兼容不能削弱研究侧门禁。

若 manifest 缺失、不是 v2、状态不是 `frozen`、文件集合不完整、哈希不匹配、研究协议或完整执行清单不受信，或 JSON 未通过 manifest `specification` 指定的同一 Schema，只能做草案或审查，不得声称正式交付。研究事实由 manifest 中的兼容研究协议、完整执行锁与 Schema 共同锁定；展示规则可以独立升级，但新研究方法或 Schema 改变事实含义时必须先完成迁移和重新冻结。

研究 Skill 的责任到冻结交接为止。它不调用 system 图表导出代码或接口，不决定最终画布、渠道比例、背景、安全区、品牌元素位置、引流语或社媒文案，也不调用内容 Skill 或发布接口。system 与内容层可以对同一冻结序列做格式化、响应式重排和展示性派生计算，但不得改变研究事实、路由、估值结果或 verdict。

## 视觉素材边界

公司 Logo 是研究 Skill 唯一管理的视觉素材，完整执行 [identity-assets.md](identity-assets.md)。它不是研究事实文件，不写入冻结 manifest；但 `company.json.brand_identity.company_logo` 必须与实际沿用或新增文件一致：

- 先检查并复用同一公司目录内的现有 canonical Logo；增量研究不得静默清空或改写有效 Logo 元数据。
- 新 canonical Logo 固定为 `companies/<slug>/assets/logo.svg` 或 `companies/<slug>/assets/logo.png`（二选一），只从公司官网、IR 或官方品牌中心取得官方原始文件；扩展名必须与实际字节格式一致，不得转换、包裹、清洗、生成、描摹、重绘或使用近似图。
- `asset_path`、公开 `source_url`、准确 `alt` 与 `is_official:true` 必须成套存在；新增 SVG 须通过文件大小、脚本、事件处理器、远程引用、敏感内容与锁定渲染探针门禁，新增 PNG 须通过签名、chunk / CRC、IHDR / IDAT / IEND、解压、像素行与非透明像素门禁。
- 找不到可验证的官方 Logo 时，四元组使用精确空哨兵：`asset_path:null`、`source_url:null`、`alt:null`、`is_official:false`，并在 `research-completeness.md` 说明网站将使用 ticker 回退；这不改变投资研究结论。
- 远端既有 Logo 引用不得静默清空；只有完整记录官方来源尝试、网站影响与待补条件，并另获清除引用授权后才可改为空哨兵。此操作不删除旧文件。远端旧记录本来缺失而新包同样为空时不是清除。

研究包内的 Markdown / JSON 只保存 Logo 元数据，禁止嵌入 Markdown 图片、HTML 图片 / 音视频标签或 `data:` 媒体 URI。产品、服务、人物、门店、业务场景、封面主视觉、背景及其他视觉素材不属于研究包、研究完整度或研究交接。本 Skill 不查找、下载、筛选、核验、生成、暂存或提交这些素材。下游内容生产 Skill 在每个内容任务内独立取得并核验；其台账不得反向改变研究事实或结论。

## GitHub 提交

GitHub 提交是 v2 冻结后的可选交付，不属于研究请求的默认权限。只有用户明确授权时才写入 `bits-bean/doujiao-value-system`；v1 或缺少当前 `execution_integrity` 的历史 v2 研究包不得提交。授权提交后，整个当前研究包作为一个原子变更写入唯一公司目录：

```text
companies/<company-slug>/
├── research-report.md
├── company.json
├── research-completeness.md
├── evidence-ledger.json
├── calculation-ledger.json
├── validation-report.json
├── schema-gap-report.md        # 仅 manifest 列出时
└── research-manifest.json
```

GitHub 路径不得增加日期、`-vN` 或其他版本子目录，也不得再向 `research/` 写入副本。本地冻结目录可继续保存不可变审计快照；远端公司目录中的受管研究文件使用整包替换，Git 历史负责记录版本。远端非研究资产必须原样保留；唯一附加写入例外是本次按 `identity-assets.md` 显式暂存并验证的 `companies/<slug>/assets/logo.svg` 或 `companies/<slug>/assets/logo.png`（二选一）。不得加入发布回执、制作记录或其他未冻结文件。`companies/<company-slug>/company.json` 是唯一正式副本。

归档器只管理冻结研究文件与上述单一 Logo 例外；`images/`、图片 manifest、产品图、网站截图、社媒成品、背景和渠道模板一律不允许作为附加写入。远端已有其他非研究资产不参与 `noop` 比较或删除计划。

最终写入必须在同一最新 `main` SHA 下验证当前公司目录、slug registry 的正向 slug→身份和反向身份→slug 一一绑定，以及目录内 `company.json` 的 canonical 存在/不存在状态；存在时核对文件 hash、大小和身份。缺 observation、wrong slug、身份冲突或 stale head 均不得 `ready_for_write`。当前正式数据的 `data_as_of` 与 `valuation_date` 只允许前进；同一数据日但不同内容默认拒绝，只有人工接受且用户明确授权的修订才允许。公司身份或证券不一致拒绝；Schema 版本不一致默认拒绝，只有显式确认、从较旧版本升级到当前锁定版本的完整迁移可以继续。
