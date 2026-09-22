# 利润表桑基生成契约

## 目标与顺序

先逐行提取同一财年年报利润表及相关附注，再生成节点；禁止先画图再凑数。把提取结果写入 `calculation-ledger.json.income_statement_sankey`，逐项保存 `node_id / value / source_ids / location`，其中台账 `value` 必须保留报表原始符号。年报单列的收入、成本、费用、所得税和利润不得遗漏或自行合并；只有年报本身合并披露时才能沿用合并口径。

节点 `category` 只使用：`revenue_source / revenue_subtotal / revenue_offset / revenue_total / cost_expense / cost_offset / cost_subtotal / pretax_costs_total / profit_addition / profit_deduction / profit_subtotal / pretax_profit / income_tax / net_income`。Schema 2.2.0 及以后每个节点同时保存：

- `statement_value`：披露或计算值的实际原始数值，保留正负号；只有 `cost_offset`、Schema 2.3.0 起的 `revenue_offset` 与 Schema 2.4.0 起的 `profit_deduction` 可以为负；
- `value`：仅作为桑基宽度与流量守恒值，必须为正数且等于 `abs(statement_value)`；
- `links[].value`：必须为正数，不得用负连线、零宽连线或改号后的净额伪造守恒。

Schema 2.0.0 / 2.1.0 历史包在审计时可没有 `statement_value`；Schema 2.2.0 保留有符号成本抵减和利润加项，但没有收入抵减角色。Schema 2.3.0 没有利润扣减角色。历史版本不得作为当前 2.4.0 正式冻结或增量链的前序包。

## 生成模板

收入起点按披露结构二选一：

1. 年报收入分项没有中间小计或负收入抵减时，每项 `revenue_source → revenue_total`；
2. 年报披露收入层级或负收入抵减时，使用 `revenue_source → revenue_subtotal* → revenue_total`。每个 `revenue_source` 必须无流入且恰有一条收入主链流出；每个 `revenue_subtotal` 只接收 `revenue_source / revenue_subtotal`，恰有一条流向下一 `revenue_subtotal / revenue_total` 的 continuation 边，其余流出只能是终端 `revenue_offset`。每个收入来源和小计都必须沿各自唯一的 continuation 路径到达同一个 `revenue_total`，Schema 2.4.0 允许总收入同时接收互不重叠的直接来源和小计，例如产品分项经产品小计汇入总收入、服务来源直接汇入总收入；不新增虚构小计，不让同一来源同时走直接和间接路径。Schema 2.3.0 及以前仍保留不混接两类父节点的历史约束。

`revenue_offset` 用于年报单列的负收入调整。它必须保留负 `statement_value`，以正的绝对值作为几何流量，只能由 `revenue_subtotal` 流入且必须无流出。于是抵减前收入小计的正流量分成“披露净收入 + 抵减绝对额”，机械等价于 `净收入 = 抵减前收入 + 负收入抵减`。不得把抵减改成正收入源流入 `revenue_total`，也不得把它分摊进某个正收入分项。`revenue_total` 仍是唯一与 `financials[].revenue` 勾稽的披露净收入节点。

共同终点固定为 `pretax_profit → income_tax + net_income`。

中间部分二选一，不能并画而造成重复分流：

- **最低层级**：年报没有可用的毛利润、营业利润等中间利润时，使用 `revenue_total → pretax_costs_total + pretax_profit`，再由 `pretax_costs_total` 展开至每项 `cost_expense` 或披露的 `cost_subtotal`。
- **逐级利润桥**：年报披露中间利润时，按真实计算顺序使用 `revenue_total → 成本项目 + profit_subtotal → 后续成本项目 + 下一层 profit_subtotal → pretax_profit`。例如 `总收入 → 营业成本 + 毛利润 → 营业费用 + 营业利润 → 利息及其他税前项目 + 税前利润`。此时税前成本总额在计算台账中复算，不再作为第二条并列流量重复进入图。

逐级利润桥可在下一个 `profit_subtotal` 或 `pretax_profit` 接收受控的 `profit_addition` 根节点。该节点的 `statement_value` 必须严格为正，必须无流入、恰有一条正值连线指向对应利润节点。上一利润节点与下一利润节点之间的桥接连线使用扣除本层正成本后的余额；下一利润节点的流入合计则包含该余额与全部正收益加项。

Schema 2.4.0 的 `profit_deduction` 表达报表原值为负的利润扣减。它必须保留严格负的 `statement_value`、正的绝对值几何流量，只有一个 `profit_subtotal` 父节点且无流出；不得由收入、成本或税前利润节点流入。父节点仍须保留唯一的后续利润 continuation。该 continuation 的计算输入键必须恰好对应父利润节点、所有直接正成本子节点与所有直接利润扣减子节点，数值均保留节点原始符号；公式为“父利润 − 正成本 + 负利润扣减”。例如负的其他净收支不能改成正费用、改用 `cost_offset`、删去或静默净额化。

年报披露的净成本 subtotal 含负费用时，使用 `cost_offset`。它必须保留负 `statement_value`，无流入、恰有一条正值连线指向 `cost_subtotal`；该目标 subtotal 还必须有恰一个非 offset 的结构父节点。这允许“披露净成本 + 负费用的绝对值 → 正成本合计（计算值） → 各正成本子项”，既不重复计量负费用，也不改号或静默净额化。`cost_offset` 不得指向 `pretax_costs_total`。

`cost_subtotal` 必须继续展开到已披露子项；`profit_subtotal` 每层必须恰有一个后续利润节点。通常还须有至少一个成本/费用或利润扣减分支；若两者都没有，只有后续利润节点另有至少一个受控 `profit_addition` 流入时才允许主链原额续接。最低层级的 `revenue_total → pretax_profit` 仍必须同时分出唯一 `pretax_costs_total`。禁止总收入直接连接所得税或净利润，禁止把多项已披露费用合并成“其他费用”，也禁止用净利润替代税前利润桥。

## 计算值与来源

年报未直接披露、由底层项目推导的汇总节点，标签追加“（计算值）”，并在 `calculations[]` 中建立 `metric: custom` 记录，写明 `sankey_node_id`、公式、输入、结果、复核方法和非空 `source_ids`。同时在 `income_statement_sankey.calculated_nodes` 绑定 `node_id` 与 `calculation_id`。年报直接披露的节点进入 `disclosed_line_items`，逐项记录精确位置和来源；每个 `revenue_offset` 披露项的 `source_ids` 至少有一个必须解析到 `company.json.sources[].source_type: annual_report`，普通 `regulatory_filing` 或第三方研究来源不能代替年报。

Schema 2.2.0 及以后必须把利润主链的每条 continuation 边（`revenue_total / profit_subtotal → 下一 profit_subtotal / pretax_profit`）写入 `income_statement_sankey.calculated_links[]`；Schema 2.3.0 还必须覆盖每条收入小计 continuation 边（`revenue_subtotal → 下一 revenue_subtotal / revenue_total`）。每项使用唯一 `source / target / calculation_id`，并绑定一条 `metric: custom` 记录；记录的 `sankey_source / sankey_target`、财年、结果和来源必须与实际连线精确对应。若一个 `revenue_subtotal` 直接分流至 `revenue_offset`，其 continuation 计算的 `inputs` 键集合必须恰好等于该 subtotal 节点 ID 与全部直接 offset 节点 ID，值逐项等于对应节点的带符号 `statement_value`；这些参与计算的节点 ID 因此必须是合法公式变量名。收入抵减桥的公式必须使用这些负数 offset 输入，例如 `gross_revenue + hedging_loss`，其中 `inputs.hedging_loss = -127000000`，不得改用正绝对值或未绑定别名。2.0.0 / 2.1.0 历史审计不强制该数组。所有带 `sankey_node_id` 或 `sankey_source / sankey_target` 的计算，以及桑基节点、连线、台账和报表勾稽金额，均使用 Decimal 精确到分比较（绝对差 `<= 0.01`），不使用百分比容差；普通非桑基 custom 计算仍使用通用相对容差。

```json
{
  "income_statement_sankey": {
    "fiscal_year": "FY2025",
    "source_ids": ["SRC-FY"],
    "review_method": "逐行核对合并利润表和费用附注，确认未遗漏或合并单列项目。",
    "disclosed_line_items": [
      {"node_id": "revenue_a", "value": 120000000, "source_ids": ["SRC-FY"], "location": "Annual report p. 80"}
    ],
    "calculated_nodes": [
      {"node_id": "pretax_costs", "calculation_id": "CALC-SANKEY-PRETAX-COSTS"}
    ],
    "calculated_links": [
      {"source": "total_revenue", "target": "pretax_profit", "calculation_id": "CALC-SANKEY-REVENUE-TO-PRETAX"}
    ]
  },
  "calculations": [
    {
      "id": "CALC-SANKEY-PRETAX-COSTS",
      "metric": "custom",
      "sankey_node_id": "pretax_costs",
      "period": "FY2025",
      "formula": "total_revenue - pretax_profit",
      "inputs": {"total_revenue": 190000000, "pretax_profit": 50000000},
      "result": 140000000,
      "review_method": "与各项已披露税前成本费用合计交叉复算。",
      "source_ids": ["SRC-FY"]
    },
    {
      "id": "CALC-SANKEY-REVENUE-TO-PRETAX",
      "metric": "custom",
      "sankey_source": "total_revenue",
      "sankey_target": "pretax_profit",
      "period": "FY2025",
      "formula": "total_revenue - pretax_costs",
      "inputs": {"total_revenue": 190000000, "pretax_costs": 140000000},
      "result": 50000000,
      "review_method": "独立复算利润主链续接连线。",
      "source_ids": ["SRC-FY"]
    }
  ]
}
```

## 下游 X 型布局与最少交叉

研究层只定义可追溯的节点、连接和值，不写死节点坐标，也不调用图表渲染器。冻结交接必须明确以下展示意图，由 System 网页与导出器在同一数据拓扑上实现：

- 入口侧最上分支尽量靠左上角，最下分支尽量靠左下角；出口侧最上分支尽量靠右上角，最下分支尽量靠右下角；中间主干与中间层级居中，使整体尽量呈清晰 X 型，而不是让同侧不同语义的分支被迫排成一条水平线。
- 线条尽量不交叉。先优化同列节点顺序，再优化同一节点的输入 / 输出端口顺序，最后使用不穿节点和标签的局部路由走廊；能由这三种手段消除的交叉必须为 0。若真实拓扑使全部零交叉不可能，则最小化交叉数，并让剩余交叉远离节点、标签、金额文字和粗主带。
- “尽量”受真实会计拓扑、金额守恒、画布安全区和标签可读性约束。优先级固定为：会计真实性与守恒 > 标签及非零小额支线可读 > 减少交叉 > X 型造型。不得为了 X 型或零交叉删除、合并、改号、改额或改边，不得交换具有会计意义的利润层级、覆盖节点配色或隐藏非零节点。
- 下游预览至少检查四角分支是否落在对应象限、可通过排序 / 端口 / 走廊消除的交叉是否为 0，以及连线是否穿过节点、标签、金额文字或粗主带。没有实际预览时，研究层只声明交接约束，不得声称该视觉验收已经通过。

## 公司级配色三态

桑基结构和金额完成后、正式验证前，对 [App Economy Insights](https://www.appeconomyinsights.com/) 完成一次公司级配色审计。配色属于冻结研究输入，不是内容任务的临时参数：网站与图表导出器都只读取 `company.json.income_statement_sankey.nodes[].color`，不得各自重新搜索、重采样或覆盖。检索与取样审计写入同一 `calculation-ledger.json.income_statement_sankey.color_audit`；不得另建 `sankey-palette.json` 等旁路文件。

检索至少完成六项规范身份查询：冻结英文全名、中文名、ticker 分别搭配 `Sankey` 与 `earnings visuals`。同时核对 `company.json` 与官方来源中的常用简称、品牌名和可解析英文简称；把每个经官方 `source_ids` 验证的非规范别名写入 `alias_review.aliases`，并对每个别名继续执行两种查询。例如规范名称查询无结果时，`Tencent` 这类官方可验证品牌名不能省略。`alias_review` 必须说明审查方法，即使没有额外别名也要明确完成。每项查询保存身份种类、身份值、规范化 query、带时区时间戳、`matched / no_match / blocked`、实际检查过的 App Economy Insights URL、阻断码和观察说明。搜索结果页摘要、相似公司图、文章封面或未经打开的候选不算匹配；必须实际打开完整公司利润表桑基图并核对公司身份。

三态只能按以下规则裁决：

- `matched`：至少一项实际打开并直接核验为该公司的完整利润表桑基图。该匹配一旦完成公司身份、原图和逐节点样本核验，就优先于其他查询中的 `no_match` 或访问阻断；其他查询仍照实记录，但 `decision.blockers` 不得保留公司级未解决阻断。取得公开可直接下载的原始 PNG，在冻结包外的私有证据目录逐节点取样；每个 `company.json` 桑基节点必须恰有一个样本。样本保存 `node_id / source_label / mapping_note / color / sample_x / sample_y`，颜色规范化为大写 `#RRGGBB`，坐标必须落在至少 `3×3` 的完全不透明纯色节点内部。把每个样本颜色逐 ID 写回对应 `nodes[].color`，两者必须完全相等。审计只保存原图 URL、抓取时间、SHA-256、媒体类型、尺寸和字节数；私有文件路径与原图字节不得进入研究包、manifest 或 GitHub。
- `not_found`：规范身份集合与全部已验证别名的查询都得到 `no_match`，且别名审查已完成、没有候选无法访问或其他阻断。所有节点 `color` 必须为 `null` 或缺省，审计绑定 `default_palette_version: semantic-default-v1`；统一默认配色由 System 单一实现，研究层不复制默认色值。
- `blocked`：没有已直接核验的匹配图，且任一检索、候选页或原图无法核验。可以把 `blocked` 及原因写入草稿台账便于续做，但所有节点色保持空、不得选择默认配色，正式验证、冻结和归档必须失败关闭。不得把访问失败写成 `not_found`。

使用确定性辅助工具先预览，再显式写回：

```bash
python3 scripts/prepare_sankey_color_audit.py \
  --package <draft-package> --input <audit-draft.json> \
  --evidence-root <private-evidence-root>

python3 scripts/prepare_sankey_color_audit.py \
  --package <draft-package> --input <audit-draft.json> \
  --evidence-root <private-evidence-root> --write
```

`not_found` 或 `blocked` 不需要 `--evidence-root`。工具的非写入模式输出标准化审计和建议节点色；`--write` 才同时更新 `company.json` 与计算台账。`research-report.md` 只写投资判断，不写检索、取样、私有证据、默认配色或渲染流程。

## 勾稽与完整性

只有下列条件全部成立才写 `reconciled: true`：

- 每个节点值同时等于其流入合计和流出合计（根节点/叶节点按存在的一侧校验）；
- 图无环且整体弱连通；平面收入图的 `revenue_source` 直接连到唯一 `revenue_total`，层级收入图则经 `revenue_subtotal` 唯一续接到该节点；`revenue_offset` 是小计的受控终端抵减，`profit_addition` 与 `cost_offset` 只能按上述受控方向接入；
- `revenue_total → profit_subtotal* → pretax_profit` 形成唯一利润主链，每层的正成本流出、桥接余额和受控加项流入分别与前后节点守恒；
- 税前利润 = 所得税 + 净利润；
- 总收入、净利润与同财年 `financials` 一致；
- Schema 2.2.0 及以后每个节点都有有限且非零的 `statement_value`，`value = abs(statement_value)`；当前版本只有 `cost_offset / revenue_offset / profit_deduction` 为负（历史角色适用版本见本文件开头），披露台账值与 `statement_value` 同号同值，计算记录 `result` 与计算节点 `statement_value` 一致；
- Schema 2.3.0 的收入小计与抵减逐层守恒，`revenue_total` 与同财年 `financials[].revenue` 相等，每条收入与利润 continuation 边都有精确计算绑定；
- 图中每个节点恰好在披露清单或计算值清单中出现一次，披露清单每一项也都有节点和连线；
- 桑基根级 `source_ids` 覆盖全部披露项和计算项来源。
- `color_audit` 覆盖三项规范身份和每个官方可验证别名的两种查询；`matched` 的逐节点样本与 `nodes[].color` 完全一致，`not_found` 的节点色全空并绑定 System 默认版本，`blocked` 不得通过正式门禁。

当前锁定 Schema 放行本契约定义的有符号利润加项、成本抵减、收入抵减与利润扣减，流量仍为严格正值。所得税收益、负的利润 subtotal、负的净利润或非控股权益归属等本契约未定义的关系，仍不得改符号或硬塞入图；记录 Schema Gap 并阻断正式冻结。

## FY2025 收入抵减示例

Alphabet：Google Services `3427.21亿美元`、Google Cloud `587.05亿美元`、Other Bets `15.37亿美元`先汇入抵减前收入计算值 `4029.63亿美元`；该小计再分为披露净收入 `4028.36亿美元`与 Hedging gains (losses) 收入抵减 `1.27亿美元`，后者的 `statement_value = -127000000`、`value = 127000000`。披露净收入再分为总成本费用 `2737.97亿美元`与进入营业利润的 continuation `1290.39亿美元`；营业利润原额续接，和正的其他收入加项 `297.87亿美元`共同形成税前利润 `1588.26亿美元`。

## FY2025 最低层级示例

美国运通：四项收入合计 `722.29亿美元`；五项披露的税前成本费用分别为会员奖励 `184.09亿美元`、会员服务/获客/营销 `187.66亿美元`、薪酬福利 `90.16亿美元`、其他费用 `69.87亿美元`、信用损失拨备 `52.56亿美元`，合计计算值 `584.34亿美元`；税前利润 `137.95亿美元`，再分为所得税 `29.62亿美元`和净利润 `108.33亿美元`。图中必须保留五个费用节点，不得只显示一个“成本费用”。
