# 研究包与冻结交接契约

## 目录

- [版本化目录](#版本化目录)
- [必需文件](#必需文件)
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

按本 Skill `references/specs/research-methodology.md` 第 14 节的顺序覆盖 16 个部分，并包含来源 ID 或直接链接。报告必须分别给出企业质量、估值状态、研究状态、置信度、2—4 个关键前提和 thesis breakers。

### company.json

严格通过锁定 commit 的 `schemas/company.schema.json`。不得加入研究包状态、冻结哈希、制作说明或平台内容；这些属于 sidecar 文件。

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
  "calculations": [
    {
      "id": "CALC-001",
      "metric": "free_cash_flow",
      "period": "FY2025",
      "formula": "operating_cash_flow - capex_total",
      "inputs": {"operating_cash_flow": 100, "capex_total": 25},
      "result": 75,
      "unit": "million USD",
      "tolerance": 0.01,
      "source_ids": ["SRC-001"]
    }
  ]
}
```

标准 `metric` 优先使用 `free_cash_flow / net_debt / market_cap / enterprise_value / custom`。每项计算都必须有期间、非空输入、有限数值结果、单位和来源；标准计算结果必须回写并匹配同期间的 `company.json` 字段。`custom` 还必须提供 `review_method`，说明公式、口径与独立复核方法，例如：

```json
{
  "id": "CALC-ROIC-2025",
  "metric": "custom",
  "period": "FY2025",
  "formula": "NOPAT / average_invested_capital",
  "inputs": {"NOPAT": 120, "average_invested_capital": 800},
  "result": 0.15,
  "unit": "decimal ratio",
  "review_method": "与年报税前利润、有效税率及期初期末投入资本逐项复核",
  "source_ids": ["SRC-001"]
}
```

`formula` 必须是可机械复算的受限算术表达式，可写为纯表达式或 `result = expression`。变量名必须与 `inputs` 完全一致；只允许有限数值、括号和 `+ - * / % **`，不允许函数、属性、索引、条件表达式或未使用输入。`result` 必须在允许误差内与复算结果一致。

Too Hard 研究若存在可豁免的结构缺口，每个 warning code 都必须在 `research-completeness.md` 单独记录，例如：

```text
- empty-sankey｜原因：披露不足，无法可靠重构；影响：资金流方向暂不能确认；待补证据：取得完整分部附注后重建并复核。
```

缺少原因、影响或待补证据/退出条件的笼统确认不能用于 `--allow-warnings`。

### schema-gap-report.md

只有 Schema 无法表达重要信息、字段语义不清、重复或与方法论冲突时生成。说明现状、影响、建议和兼容方案；不得擅自修改 Schema。

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
