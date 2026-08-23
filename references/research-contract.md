# 研究包与冻结交接契约

## 目录

- [版本化目录](#版本化目录)
- [必需文件](#必需文件)
- [中文展示单位契约](#中文展示单位契约)
- [冻结语义](#冻结语义)
- [下游交接](#下游交接)
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

`companies/<company-slug>/company.json` 是系统中的当前正式公司数据路径。只有用户授权更新规范仓库或网站流程时，才把冻结版本同步到该路径；研究包内的 `company.json` 是本次冻结快照。

## 必需文件

### research-report.md

按本 Skill `references/specs/research-methodology.md` 第 14 节的顺序完整包含 16 个部分，每节都有实质正文，不得合并、缺省或用占位文本替代。一页式结论和最终结论必须以明确字段分别给出企业质量、估值状态、研究状态、置信度、2—4 项关键前提和 thesis breakers，且前后一致。最终结论还必须展示方法论第 13 节规定的八维评分；护城河和 Pre-Mortem 必须逐项包含方法论第 5、11、14 节规定的全部字段。

报告必须在脱离 `company.json`、证据台账、计算台账和完整度说明时仍可独立阅读和核实。伴随文件用于补充结构化数据、审计轨迹和机械复算，不得代替关键主张的正文解释、就地引用或来源定位。禁止使用“完整 URL 见 `company.json.sources`”或类似表述。

正式报告使用可见的纯 Markdown；除无属性 `<br>` / `<br/>` 外不得包含原始 HTML，也不得把结构或正文藏进 fenced code、HTML comment 或不可见容器。

关键数字和关键主张在出现处就地引用直接链接或标注 `SRC-*`。采用 `SRC-*` 时，精确定位由文末来源定位索引统一解析，正文不必重复；索引必须对每个 ID 给出标题、发布者与来源类型、发布日期或适用期间、直接 URL，以及页码、监管文件 Item/表号、稳定章节或时间戳中的至少一项。缩写、行业指标和非通用术语首次出现时必须解释；每项结论先给通俗含义，再给技术口径、计算和限制。

### company.json

严格通过锁定 commit 的 `schemas/company.schema.json`。不得加入研究包状态、冻结哈希、制作说明或平台内容；这些属于 sidecar 文件。

`income_statement_sankey` 必须由同一财年的真实利润表恒等式生成，不按版面需要自由连线。用 `category` 固定节点角色：收入分项为 `revenue_source`，总收入为 `revenue_total`，成本费用为 `expense`，税前利润为 `pretax_profit`，所得税为 `income_tax`，净利润为 `net_income`。只允许以下路径：

`revenue_source → revenue_total → expense + pretax_profit → income_tax + net_income`

其中总收入、税前利润、所得税和净利润各一个，收入分项和成本费用可有多个；不得出现 `revenue_total → income_tax` 或 `revenue_total → net_income`。所有金额使用实际原始数值，`reconciled: true` 只在每个节点值均与相连流量一致、每个中间节点流入等于流出且下列恒等式同时成立时使用：

- 收入分项合计 = 总收入；
- 总收入 = 成本费用合计 + 税前利润；
- 税前利润 = 所得税 + 净利润；
- 总收入和净利润分别与 `financials` 中同财年的 `revenue`、`net_income` 一致。

### research-completeness.md

至少列出：

- 已取得和缺失的财年、季度、TTM；
- 无法验证或只能估算的字段；
- 低置信度结论及原因；
- 会计口径、重述、拆股、并购或币种可比性限制；
- 对最终结论和估值的影响；
- 尚待取得的关键证据。

### evidence-ledger.json

使用：

```json
{
  "claims": [
    {
      "id": "CLM-001",
      "claim": "可验证的主张",
      "classification": "fact",
      "period": "FY2025",
      "source_ids": ["SRC-001"],
      "location": "Annual report p. 42",
      "confidence": "high",
      "counterevidence": [],
      "would_falsify": "什么新证据会推翻该判断"
    }
  ]
}
```

`classification` 只使用 `fact / management_claim / third_party / inference / estimate`；`confidence` 只使用 `high / medium / low`。

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

`formula` 必须是可机械复算的受限算术表达式，可写为纯表达式或 `result = expression`。变量名必须与 `inputs` 完全一致；只允许有限数值、括号和 `+ - * / % **`，不允许函数、属性、索引、条件表达式或未使用输入。`result` 必须在允许误差内与复算结果一致。

Too Hard 研究若存在可豁免的结构缺口，每个 warning code 都必须在 `research-completeness.md` 单独记录，例如：

```text
- empty-sankey｜原因：披露不足，无法可靠重构；影响：资金流方向暂不能确认；待补证据：取得完整分部附注后重建并复核。
```

缺少原因、影响或待补证据/退出条件的笼统确认不能用于 `--allow-warnings`。

### schema-gap-report.md

只有 Schema 无法表达重要信息、字段语义不清、重复或与方法论冲突时生成。说明现状、影响、建议和兼容方案；不得擅自修改 Schema。

## 中文展示单位契约

展示层与储存层严格分开：

- **面向人的展示层**：`research-report.md`、`research-completeness.md`、`schema-gap-report.md`、研究摘要、最终回复及由本 Skill 直接生成的表格 / 图表，全部使用中国投资者自然阅读的单位。
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

以下情况一律视为展示错误：把 `million / billion / 百万元 / 百万股` 直接写进中文成品；把底层 `186800000000`、`9153000000` 等裸数字放入金额或股数字段；表格既无统一单位也不给单元格标单位；把 `0.25` 原样展示而不是写成 `25%`；把百分比变化误写成百分点。DCF 输入表必须同时显示已换算的初期现金总额、稀释后股数、每股现金流和预测年限，并由验证器反向换算到台账值复核。

历史冻结包保持不可变。旧包若由其 manifest 锁定的旧 Schema 声明 `million`、`million_shares` 等缩放单位，审计时必须按旧锁解释；创建新版研究时再把金额和股数机械换算为实际原始数值，重新验证并冻结，禁止原地修改或把旧值直接当作新口径。

## 冻结语义

`research-manifest.json` 是 sidecar，不写入 `company.json`。新冻结清单固定使用 `manifest_version: 2.0`，并分别记录：

- `research_protocol`：当前研究 Skill 的 authority、repository、ref、发行 commit、`protocol_version`、聚合摘要及三份权威文档 SHA-256/大小；
- `specification`：只记录权威 Schema 仓库、ref、精确 commit、路径、Schema SHA-256、Git blob SHA 与 `schema_version`；
- `schema_version`、公司身份、数据日、估值日；
- 报告、JSON、台账和验证报告的 SHA-256；
- 验证错误与警告数量；
- 冻结时间和人工审核状态。

`status: frozen` 仅表示快照不可变。默认 `human_review_status: pending`；只有实际人工审核后才标为 `accepted`。冻结不代表投资建议、网站已更新或内容已发布。

历史 `manifest_version: 1.0` 只允许 `audit` 模式复核。它不能成为新增量版本的前序 manifest，不能重新冻结、GitHub 归档或作为当前正式下游交接；要继续使用必须按当前研究协议与 Schema 迁移并新建 v2 版本目录。

## 下游交接

交给 `$produce-doujiao-value-content` 的必须是同一冻结目录中的报告、`company.json` 和 v2 manifest。下游先验证文件哈希、`research_protocol`、Schema 锚点与版本、公司身份、数据日和估值日一致，再生成内容。

若 manifest 缺失、不是 v2、状态不是 `frozen`、文件集合不完整、哈希不匹配、研究协议不受信，或 JSON 未通过 manifest `specification` 指定的同一 Schema，只能做草案或审查，不得声称正式内容交付。研究事实由 manifest 中的研究协议与 Schema 双重锁定；展示规则可以独立升级，但新研究方法或 Schema 改变事实含义时必须先完成迁移和重新冻结。

## GitHub 归档

GitHub 归档是 v2 冻结后的可选交付，不属于研究请求的默认权限。只有用户明确授权时才写入 `bits-bean/doujiao-value-system`。v1 研究包不得归档。`archive-only` 只写版本快照；用户另行授权“设为当前正式版本”后，`archive-and-promote` 才写 canonical 路径：

```text
research/<company-slug>/<version>/
├── research-report.md
├── company.json
├── research-completeness.md
├── evidence-ledger.json
├── calculation-ledger.json
├── validation-report.json
├── schema-gap-report.md        # 仅 manifest 列出时
└── research-manifest.json

companies/<company-slug>/company.json
```

版本快照必须逐字节保持冻结文件不变；不得向目录加入发布回执、制作记录或其他未冻结文件。若获授权提升，当前正式 `company.json` 必须是同一快照中 `company.json` 的精确副本。

同名版本目录已经存在时，只有远端全部路径和哈希与发布计划完全一致才可视为幂等成功；否则创建新版本后缀，不能覆盖。最终写入还必须在同一最新 `main` SHA 下验证 slug registry 的正向 slug→身份和反向身份→slug 一一绑定；仅通过 slug 正则不构成授权。`archive-and-promote` 的 canonical 存在/不存在 observation 也必须绑定该 SHA，存在时还要核对文件 hash、大小和身份。缺 observation、wrong slug、身份冲突或 stale head 均不得 `ready_for_write`。当前正式数据的 `data_as_of` 与 `valuation_date` 都只允许前进；同一数据日但不同内容默认拒绝，只有人工接受的 `-vN` 修订版获得专项提升确认后才允许。公司身份、证券或 Schema 版本不一致拒绝。
