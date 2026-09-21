# 公司分类、行业指标与图表路由契约

## 目的

在研究开始时先形成有来源的 `classification`，再决定会计口径、资本回报研究框架和下游图表。不得根据某个财务字段是否存在、估值倍数、公司名称或模型猜测来反推公司类型。

`sector`、`primary_industry` 和 `secondary_industries` 用于标签、检索和同业选择；公司类型驱动的会计计算与资本回报图表路由只由 `accounting_profile` 与 `returns_profile` 控制。行业标签与路由字段冲突时阻断冻结，不能让网站或内容层自行猜测。

## classification

- `sector`：使用 Schema 的宽行业枚举。
- `primary_industry`：只填一个最能解释主要经济来源的 snake_case slug。
- `secondary_industries`：补充确有实质收入、资本约束或竞争意义的行业 slug；不得堆砌搜索关键词。
- `accounting_profile`：决定现金流、资本和资产负债表解释框架。
- `returns_profile`：决定资本回报主指标与图表模板。
- `source_ids`：至少引用一份能验证主要业务与监管身份的官方来源；公司业务与监管身份来自不同文件时同时引用。

允许的会计框架：

| `accounting_profile` | 适用边界 |
|---|---|
| `standard_corporate` | 普通非金融企业，以及不以监管资本为核心约束的支付网络、软件和平台 |
| `regulated_bank` | 银行、银行控股公司及以监管资本约束的支付信贷企业 |
| `insurer` | 保险与再保险企业 |
| `reit` | 以 REIT 口径披露和分配的房地产信托 |
| `resource_cycle` | 资源与强周期企业，需要周期中枢和成本曲线 |

允许的回报框架与最低图表数据：

| `returns_profile` | 主指标 | 资本约束 / 辅助指标 | 每股结果 / 增量结果 |
|---|---|---|---|
| `standard_roic` | `financials.roe`、`financials.roic` | 不适用 | `financials.incremental_roic`，优先滚动 3 年和 5 年 |
| `payments_network` | `financials.roe`、`financials.roic` | 不适用 | `financials.incremental_roic` 与真实稀释 |
| `software_platform` | `financials.roe`、调整后 `financials.roic` | SBC、费用化研发和负营运资本说明 | 增量 ROIC 与稀释后每股结果 |
| `regulated_bank` | 至少八个完整财年的 `roe` 或 `industry_metrics.rotce` 长期折线 | 最新报告期 `cet1_ratio` 或 `capital_adequacy_ratio`，连同管理层目标上下限或监管最低要求组成当前仪表 | 至少八个完整财年的 `tangible_book_value_per_share` / `common_equity_per_share` / `book_value_per_share` 长期序列，或至少三个完整财年的 `buyback_ledger.shares_outstanding_change` / `buyback_impact_per_share` 回购影响 |
| `payments_credit` | 至少八个完整财年的 `roe` 或 `industry_metrics.rotce` 长期折线 | 最新报告期 `cet1_ratio` 或 `capital_adequacy_ratio`，连同管理层目标上下限或监管最低要求组成当前仪表 | 至少八个完整财年的每股权益长期序列，或至少三个完整财年的回购对股数影响；必须解释回购 / 稀释而不能只展示回购金额 |
| `insurer` | `roe` | `solvency_ratio` 或适用监管资本指标 | `book_value_per_share` 或 `tangible_book_value_per_share` |
| `reit` | `industry_metrics.affo` / `affo_per_share` | `occupancy_rate`、杠杆和债务期限 | `affo_per_share` 增长与分配覆盖 |
| `resource_cycle` | 周期中枢 `financials.roic` | `reserve_life`、成本曲线与维持性资本开支 | 跨周期增量回报，不使用周期顶部单年值 |

兼容关系：

- `regulated_bank` 只能路由到 `regulated_bank` 或 `payments_credit`。
- `insurer`、`reit`、`resource_cycle` 必须分别路由到同名回报框架。
- `payments_network` 和 `software_platform` 使用 `standard_corporate`。
- `payments_credit` 可使用 `regulated_bank`；只有能够证明不受银行监管资本约束时才可使用 `standard_corporate`，并在完整度说明中解释。
- `standard_roic` 默认使用 `standard_corporate`。

## 十年营收结构图

所有会计框架均须执行 [revenue-mix-history.md](revenue-mix-history.md)，以官方披露决定一个互斥的主拆分维度，再按完整性、符号和可比性选择图形。商业模式下的最新收入来源采用环形图与动态数量的说明卡；十年收入结构默认只用一张水平金额堆积图，柱长体现年度总额差异，并直接显示各项金额与占比、年度总额及明细表。读图、口径和经营解读默认折叠；负调整、缺失和分类断点按该契约处理。这不改变上述会计与资本回报路由，也不在十年财务重复展示同图。

## industry_metrics

把 Schema 通用财务字段无法稳定表达的行业指标写入顶层 `industry_metrics[]`。每一项必须有：

- `period`：与 `financials` 的财务期标签或 `reporting.latest_report.period` 保持一致，例如 `FY2025`、`2026Q2`；
- `code`：稳定 snake_case 代码；同一 `period + code` 只出现一次；
- `label`：面向读者的中文名称；
- `value`：实际数值或真实缺失 `null`；
- `value_type`：`amount / ratio / per_share / multiple / count / index`；
- `source_ids`：直接来源。

数值规则：`amount` 使用报告币种实际数值，`ratio` 使用 decimal，`per_share` 使用报告币种/股，`count` 使用实际数量。禁止在 `code` 中嵌入年份或单位，禁止把同一指标因中英文名称不同拆成两个 code。

优先使用以下稳定代码；确需新增时采用 snake_case，并在报告首次出现处解释：

- 银行 / 支付信贷：`rotce`、`cet1_ratio`、`cet1_target_low`、`cet1_target_high`、`cet1_regulatory_minimum`、`capital_adequacy_ratio`、`capital_adequacy_target_low`、`capital_adequacy_target_high`、`capital_adequacy_regulatory_minimum`、`risk_weighted_assets`、`net_interest_margin`、`deposit_cost`、`net_charge_off_rate`、`tangible_book_value_per_share`、`common_equity_per_share`、`book_value_per_share`、`buyback_impact_per_share`。
- 保险：`combined_ratio`、`solvency_ratio`、`float_amount`、`float_cost`、`book_value_per_share`、`tangible_book_value_per_share`。
- REIT：`ffo`、`affo`、`ffo_per_share`、`affo_per_share`、`same_store_noi_growth`、`occupancy_rate`、`distribution_coverage`。
- 资源周期：`reserve_life`、`unit_cash_cost`、`maintenance_capex`、`midcycle_roic`。
- 软件 / 平台：`net_revenue_retention`、`gross_retention`、`sbc_to_revenue`、`adjusted_roic_after_r_and_d`。

## 覆盖与缺失

### 增量投入资本非正时的可审计空值

`standard_roic / payments_network / software_platform` 仍至少需要三个完整财年的增量回报证据。回购、分配或资产变化使滚动投入资本增量非正时，不把机械相除值当成新增项目回报，也不把缺数据当成不适用。可保持 `financials.incremental_roic: null`，但计入该财年覆盖的前提是 **3 年和 5 年两个窗口都通过以下证据门**：

- `industry_metrics` 分别保存 `incremental_roic_3y / incremental_roic_5y`，`value: null`、`value_type: ratio`；`label` 简述非正分母原因，`source_ids` 覆盖窗口来源。Schema 没有 metric notes 字段，不自行添加。
- `calculation-ledger.json.incremental_roic_windows[]` 每项恰含 `period / window_years / start_period / status / reason_code / capital_basis / economic_reason / delta_nopat_calculation_id / delta_invested_capital_calculation_id / source_ids`。窗口年数只能为 3 或 5，`start_period` 与结束 FY 的年份差必须相符；`status: unavailable`、`reason_code: non_positive_invested_capital_change`。
- 两个计算 ID 绑定同一结束 FY 的 `metric: custom` 数字计算。NOPAT 的输入恰为 `beginning_nopat / ending_nopat`，公式 `ending_nopat - beginning_nopat`；投入资本输入恰为 `beginning_invested_capital / ending_invested_capital`，公式 `ending_invested_capital - beginning_invested_capital`。两条 `result` 均保留有限数字并按实际金额复算，不能用 null 跳过计算；投入资本差额必须 `<= 0`。
- 两条计算均须有年报或监管原始披露来源；窗口和指标来源覆盖计算来源。`capital_basis` 说明窗口两端一致的资本定义，`economic_reason` 说明具体资本分配或资产变化如何使增量比率失去解释力，报告说明由此不能识别新增项目回报。

单个窗口不适用仍应记录，但不能单独替代该财年的两个窗口覆盖。正的资本增量无论多小，都不自动适用该豁免；保留机械计算和解释，不设无来源的通用“小分母”阈值。缺少窗口输入、只写“资料不足”、缺官方来源、公式不符、正分母或不足三个不同 FY，均不能通过覆盖门。下游保留空值断点，不补成 0，不从 null 推断回报良好。

- 正式完整研究默认给主指标和普通行业的辅助 / 增量结果各至少八个完整财年；上市不足八年时覆盖全部可得完整财年，并在完整度说明中解释。
- `regulated_bank` 与 `payments_credit` 采用明确例外：ROE / ROTCE 主指标仍须长期序列；资本约束板块允许使用最新报告期的 CET1 / 资本充足率加管理层目标区间或监管最低要求作当前仪表，不要求伪造八年资本序列；第三板块可在每股权益长期序列与至少三个完整财年的回购对股数影响之间二选一。
- 当前资本仪表必须把实绩值与同一报告期的目标上下限或监管最低要求一起冻结。只有一个孤立 CET1 / 资本充足率数值不满足路由；完整度说明须明确当前截面不能代表长期资本趋势。
- 回购替代路径至少覆盖三个不同完整财年，并使用 `buyback_ledger.shares_outstanding_change` 或 `industry_metrics.buyback_impact_per_share`；回购金额、回购股数或管理层口号不能替代净股数影响。
- 若官方只披露更短历史，不得插值或用第三方估算冒充披露值；使用 `null` 或缩短序列，并明确对结论和图表的影响。
- 研究包必须冻结路由所需原始序列。下游可以格式化、计算同一序列的增长率或滚动窗口，但不得补研究事实、替换口径或根据缺失字段切换公司类型。
- 分类、行业指标或路由最低数据不完整时，图表应明确缺口或拒绝生成，不得改用与行业不匹配的普通企业模板。
