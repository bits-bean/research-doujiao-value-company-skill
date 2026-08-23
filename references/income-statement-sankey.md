# 利润表桑基生成契约

## 目标与顺序

先逐行提取同一财年年报利润表及相关附注，再生成节点；禁止先画图再凑数。把提取结果写入 `calculation-ledger.json.income_statement_sankey`，逐项保存 `node_id / value / source_ids / location`。年报单列的收入、成本、费用、所得税和利润不得遗漏或自行合并；只有年报本身合并披露时才能沿用合并口径。

节点 `category` 只使用：`revenue_source / revenue_total / cost_expense / cost_subtotal / pretax_costs_total / profit_subtotal / pretax_profit / income_tax / net_income`。金额使用实际原始数值。

## 生成模板

共同首尾固定为：

1. 每项 `revenue_source → revenue_total`；
2. `pretax_profit → income_tax + net_income`。

中间部分二选一，不能并画而造成重复分流：

- **最低层级**：年报没有可用的毛利润、营业利润等中间利润时，使用 `revenue_total → pretax_costs_total + pretax_profit`，再由 `pretax_costs_total` 展开至每项 `cost_expense` 或披露的 `cost_subtotal`。
- **逐级利润桥**：年报披露中间利润时，按真实计算顺序使用 `revenue_total → 成本项目 + profit_subtotal → 后续成本项目 + 下一层 profit_subtotal → pretax_profit`。例如 `总收入 → 营业成本 + 毛利润 → 营业费用 + 营业利润 → 利息及其他税前项目 + 税前利润`。此时税前成本总额在计算台账中复算，不再作为第二条并列流量重复进入图。

`cost_subtotal` 必须继续展开到已披露子项；`profit_subtotal` 每层必须恰有一个后续利润节点及至少一个成本/费用分支。禁止总收入直接连接所得税或净利润，禁止把多项已披露费用合并成“其他费用”，也禁止用净利润替代税前利润桥。

## 计算值与来源

年报未直接披露、由底层项目推导的汇总节点，标签追加“（计算值）”，并在 `calculations[]` 中建立 `metric: custom` 记录，写明 `sankey_node_id`、公式、输入、结果、复核方法和非空 `source_ids`。同时在 `income_statement_sankey.calculated_nodes` 绑定 `node_id` 与 `calculation_id`。年报直接披露的节点进入 `disclosed_line_items`，逐项记录精确位置和来源。

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
    }
  ]
}
```

## 勾稽与完整性

只有下列条件全部成立才写 `reconciled: true`：

- 每个节点值同时等于其流入合计和流出合计（根节点/叶节点按存在的一侧校验）；
- 图无环，所有非收入来源节点均可从总收入沿真实计算路径到达；
- 收入来源合计 = 总收入；全部底层税前成本费用 + 税前利润 = 总收入；
- 税前利润 = 所得税 + 净利润；
- 总收入、净利润与同财年 `financials` 一致；
- 图中每个节点恰好在披露清单或计算值清单中出现一次，披露清单每一项也都有节点和连线；
- 桑基根级 `source_ids` 覆盖全部披露项和计算项来源。

负数、税收收益或非控股权益等关系若无法在当前非负流量 Schema 下真实表达，不得改符号或硬塞入图；记录 Schema Gap 并阻断正式冻结。

## FY2025 最低层级示例

美国运通：四项收入合计 `722.29亿美元`；五项披露的税前成本费用分别为会员奖励 `184.09亿美元`、会员服务/获客/营销 `187.66亿美元`、薪酬福利 `90.16亿美元`、其他费用 `69.87亿美元`、信用损失拨备 `52.56亿美元`，合计计算值 `584.34亿美元`；税前利润 `137.95亿美元`，再分为所得税 `29.62亿美元`和净利润 `108.33亿美元`。图中必须保留五个费用节点，不得只显示一个“成本费用”。
