# 公司 Logo 与来源契约

## 目的与边界

本契约只解决“`doujiao-value-system` 是否拥有网站可直接引用、来源可验证的真实公司 Logo”。公司 Logo 是研究 Skill 唯一可以取得、核验、暂存和在获授权后归档的视觉素材。

不得：

- 除本契约定义、逐像素证明的 PNG → PNG 确定性中心方形裁剪外，转换、包裹、清洗、生成、描摹、重绘或用近似图替代公司 Logo；
- 获取或管理产品、服务、人物、门店、业务场景、封面、背景或其他视觉素材；
- 选择网站或社媒比例、背景、安全区、Logo 位置或视觉模板；
- 调用图表渲染器、网页截图、图片合成或发布流程。

Logo 不是研究事实文件，不写入 `research-manifest.json`。冻结研究包保持不可变；manifest 与 `validation-report.json` 会锁定同一 `company_slug` 和 Logo 元数据，但不声称锁定包外 Logo 字节。新增或获授权替换的 Logo 在冻结目录外单独准备，正式的字节 hash、安全性与非透明像素验证发生在 GitHub 交付规划阶段；在规划器给出 `ready_for_write:true` 并完成提交复核前，不得称该冻结包已具备网站 Logo。

## 现有 Logo 优先

开始获取前，在同一最新 `doujiao-value-system/main` SHA 下依次检查：

1. `company.json.brand_identity.company_logo.asset_path` 指向的精确文件；
2. `companies/<slug>/assets/logo.svg` 或 `companies/<slug>/assets/logo.png`；
3. 仅为兼容保留且可完整验证的 `companies/<slug>/logo-primary.svg` 或 `companies/<slug>/logo-primary.png`。

已有文件的公司身份、来源和内容可验证时沿用，不重新从官网另找替代品、不改路径；这包括画布非方形但仍有效的远端 Logo。正方形偏好不能推导替换权限；只有用户明确授权替换时，才能另找正方形原件或执行本契约的中心裁剪。但归档预检必须把 system 中该精确文件下载到任务临时目录，逐字节核对 hash、大小、安全性与实际非透明像素。`logo-primary.svg` / `logo-primary.png` 只作为已有 legacy 路径保留；其他旧格式必须按明确替换流程迁移为 canonical 路径，不能只改元数据或自行转码。

新公司或新 canonical Logo 统一使用以下两个精确路径之一。优先使用官方原始正方形 SVG / PNG；只有穷尽并记录官方正方形候选后，才允许把官方非方形 PNG 按下文规则裁成同格式正方形 PNG。若官方只提供其他格式，不得为了取得 canonical 路径自行转码。官方候选全部穷尽后，依据本私有 Skill 已记录的用户常设授权，可使用经核验的第三方原始正方形 SVG / PNG，无需仅为第三方资格再次询问；第三方文件不得裁剪、转码、清洗或改写。

```text
companies/<company-slug>/assets/logo.svg
companies/<company-slug>/assets/logo.png
```

`company.json.brand_identity.company_logo.asset_path` 必须与实际沿用或新增的 Logo 路径完全一致。增量研究不得把已有有效 Logo 字段静默改回 `null`。

## 获取与验证

来源按以下顺序处理，不能为了省事跳过官方检索：

1. 公司官网当前运行时资源；
2. Investor Relations；
3. 官方品牌 / 媒体资料；
4. 适用的官方产品、商户、开发者、合作伙伴 / 支持页面；
5. 只有前四类已全部检查、逐项记录且没有通过门禁的候选时，才进入第三方兜底。本私有 Skill 已记录用户“以后找不到可以用第三方”的常设授权；不必仅为第三方资格再次停下询问。仍应优先选择带版本历史、公开来源说明和稳定原始文件 URL 的可信资料库，并用官方页面实际出现的品牌图形或两项相互独立的可靠资料交叉核验身份。

任何采用的 Logo 必须同时满足：

- 图形与公司法定身份一致，并使用公众辨识度最高的主品牌标志；
- `source_url` 是公开、无临时 token、可复核的来源页或原始文件 URL；
- `alt` 准确描述公司和标志，不含投资结论或渠道宣传文案；
- `is_official` 与托管来源事实一致，不能仅凭外观判断：官方来源或官方来源裁剪写 `true`，第三方托管原件必须写 `false`；`false` 不代表未经核验，完整度说明仍须记录身份交叉核验；
- 新增文件是非符号链接、非空且不超过 512,000 字节的官方原始或经授权第三方原始正方形 SVG / PNG，或满足本节全部 provenance 与逐像素门禁的 official-source-derived 正方形 PNG；文件扩展名必须与实际字节格式一致；
- SVG 不含脚本、事件处理器、远程引用、追踪像素、嵌入凭据或外部字体依赖；过滤器、mask、条件渲染、CSS 变量和非标准命名空间也不接受。可沿用只含简单元素 / class / id 选择器与安全 SVG presentation properties 的内联 `<style>`；任何 at-rule、复杂选择器、外部样式或资源、未知属性都拒绝。
- PNG 必须通过签名、chunk 边界与顺序、CRC、IHDR / IDAT / IEND、解压长度、像素行与过滤器验证，并且至少有一个非透明像素。
- 不得在 SVG 与 PNG 之间转换、包裹、清洗、描摹或重绘。中心裁剪仅允许 PNG → PNG，不能用于 SVG、JPEG 或其他格式；canonical 扩展名仍由官方来源文件的真实格式决定。

第一个官方候选不合格时不能直接结束搜索。首次研究至少继续检查并记录以下检索面；某一检索面不存在或不适用时也要明确写出，而不是省略：

1. 公司官网当前页面实际加载的 Logo，包括 DOM、CSS、网络请求和官方静态资源域名；
2. Investor Relations 的首页、年报页、治理页和新闻稿模板；
3. 官方品牌中心、媒体资料、新闻资料或下载中心；
4. 适用的官方产品、商户、开发者、合作伙伴或支持页面；
5. 每个候选的原始 URL、格式、画布尺寸、是否正方形、公司身份核验、是否满足安全门，以及采用或拒绝原因。

只有完成上述记录后，才能判断“当前找不到可验证的官方正方形 Logo”或进入第三方兜底。不得因为一个 SVG 含 DOCTYPE、`foreignObject`、字体或其他不安全结构，或一个 PNG 非方形 / 未通过完整性门禁，就推断该公司没有其他官方安全素材；应继续查找官网实际在用的简化版本或其他官方原始文件。存在通过门禁的官方正方形候选时禁止裁剪或改用第三方；没有正方形候选但存在通过门禁的官方非方形 PNG 时，可执行下述唯一裁剪例外。官方候选与经授权第三方候选都没有通过时才使用空哨兵，不得转换、包裹或清洗不合格文件冒充原件。

采用第三方兜底时，`research-completeness.md` 的可见文本必须同时写明：四类官方来源已穷尽、用户已授权常设第三方兜底、第三方托管事实、具体来源页与原始文件 URL、身份交叉核验依据、文件格式 / 画布 / SHA-256 / 安全与渲染结果，以及交付到 system 后网站不再回退 ticker 或仍受何种限制。第三方来源不得在 `company.json` 或交付说明中被称为官方；即使图形本身与官方品牌一致，`is_official` 仍为 `false`。

公开来源 URL 不得使用 localhost、私网 / link-local IP、旧式数值 IP 写法、保留测试域、用户凭据或 AWS / Google / CDN 签名查询参数。机械 URL 门只负责语法与稳定性约束；实际取得步骤仍须成功打开公开官方页面或文件并核对公司身份，不能用“语法合法”替代可达性和官方性。SVG 必须使用标准命名空间，至少包含可渲染的矢量几何；文本 / 字体节点、XML Events、外部样式、空路径、零尺寸图形、悬空内部引用，以及 `lab()` / `lch()` / `oklab()` / `oklch()` / `hwb()` / `color()` / `device-cmyk()` 等跨渲染器颜色函数都不合格。SVG 归档门还必须使用脚本精确锁定的平台运行时之一：云端主运行时 bundle 26.812.11052，或 macOS ChatGPT App bundle 26.901.41600 内的 `cua_node`；两者都必须提供 Sharp 0.35.3 + libvips 8.18.3 + librsvg 2.62.90 SVG 栅格器。探针使用透明背景并要求至少一个非透明像素；每个受信 profile 的 bundle 版本、Node、Sharp 入口和 package metadata 的绝对路径及 SHA-256 都锁定在脚本中，调用方必须显式注入与其中一个 profile 完全一致的四个 `CODEX_PRIMARY_RUNTIME_*` 值。子进程不按当前工作目录或包名解析模块，也不继承 `NODE_OPTIONS`、preload、调用方 `NODE_PATH` 或动态库注入环境。探针还必须返回匹配随机 challenge、协议名、版本和可见性布尔值的结构化回执，空输出或只返回退出码 0 不构成通过。任一 bundle / 组件版本不符、运行时路径或摘要不受信、回执错误、渲染器缺失、超时、报错或空白都阻断。canonical 或 legacy PNG 都必须通过完整 chunk、CRC、IHDR、IDAT 解压、像素行长度、过滤器和至少一个非透明像素门禁；PNG 不经过 SVG 栅格器，也不得为了绕过运行时门禁转换或包裹成 SVG。

## 正方形选择与唯一裁剪例外

新增或替换时，先比较所有通过官方性和安全门的候选：画布正方形的官方原始 SVG / PNG 优先于任何派生文件或第三方文件；格式偏好不能覆盖正方形与公司身份。官方品牌或媒体资源页明确标识、可准确代表公司的正方形图形标志可作为公司 Logo；不得把只代表某个产品、活动或渠道的 Icon 冒充公司 Logo。没有通过门禁的官方正方形候选后，才允许选择一个通过门禁、公众辨识度最高的官方非方形 PNG 作为裁剪源。只有没有可用的官方正方形原件或可裁剪官方 PNG 时，才可依用户常设授权选择经身份交叉核验、通过同一安全和渲染门的第三方原始正方形 SVG / PNG。

裁剪算法固定为 `center-square-crop-v1`：

```text
side = min(source_width, source_height)
left = (source_width - side) // 2
top = (source_height - side) // 2
crop = (left, top, side, side)
```

奇数差值向下取整，额外像素留在右侧或底部。不得缩放、拉伸、补边、重采样、改色、改变 bit depth / color type / palette / 透明度 / 渲染相关 PNG chunk，或重绘任何像素。APNG 动画 chunk 一律拒绝；修改 IHDR / IDAT 后规范标记为 unsafe-to-copy 且规划器无法证明仍有效的 ancillary chunk 也失败关闭。规划器必须同时解码官方原件与输出，证明输出每个样本都精确等于上述中心区域；只靠尺寸、视觉相似、工具成功回执或 provenance 自报不能通过。

裁剪任务在冻结目录外保留三份相互独立、非符号链接且非硬链接的文件：

```text
<identity-assets-root>/
├── logo.png
├── logo-original.png
└── logo-provenance.json
```

`logo-original.png` 保持官方下载字节；`logo.png` 是唯一准备写入 system 的 canonical 文件；`logo-provenance.json` 使用版本 `1.0`、操作 `center-square-crop-v1`，严格记录 `company_slug`、官方来源页和原始资产 URL、四个必查检索面、全部候选及拒绝原因、输入 / 输出 SHA-256 与大小 / 尺寸、裁剪框，以及 `resampled:false`、`padded:false`、`stretched:false`、`redrawn:false`。每个候选还要用 `source_page_url`绑定某个已检查检索面，以布尔值记录 `identity_verified` / `is_official`，并给出非空 `officiality_evidence`；通过门禁的候选只能是身份和官方性均已核验的 SVG / PNG。四个检索面固定为官网运行时资源、Investor Relations、品牌 / 媒体资料、适用的官方产品 / 支持页面；不适用时也要说明原因。候选 URL 必须唯一，裁剪源必须唯一且与 source 记录精确一致；候选台账中若存在通过门禁的正方形 SVG / PNG，裁剪失败关闭。

裁剪后的 canonical Logo 是 `official-source-derived`，不是公司发布的原始文件字节。`company_logo.source_url` 指向 provenance 中的官方来源页或原始资产 URL；`is_official:true` 表示 Logo 图形及来源为官方，不得将其描述为“官方原始字节”。原件与 provenance 保存在冻结目录外的持久工作目录，不能只保存在会自动清理的临时目录。交付计划只在冻结目录外的任务工作目录生成，可按审计需要保留；上述证据与计划都不进入研究 manifest，也不进入 GitHub 最终差异。

找不到满足条件的官方 Logo，且按常设授权检查后第三方候选也不合格时，`asset_path`、`source_url` 和 `alt` 写 `null`，`is_official:false`；在 `research-completeness.md` 独立说明“公司 Logo 缺失”、尝试过的官方与适用第三方来源及对网站展示的影响。不得生成替代 Logo。

该完整度条目必须逐项写明已检查的官网 / IR / 官方品牌中心或媒体资料、缺失原因、网站 ticker 回退或其他展示影响，以及后续待补证据或重新检查条件。笼统写“已知悉”不能越过警告门禁。`validate_research_package.py` 与 `freeze_research.py` 都必须接收同一 `--company-slug`，以便在冻结前把 Logo 路径绑定到精确公司；非空状态只允许该 slug 的 `assets/logo.svg` / `assets/logo.png` canonical 路径，或可完整验证的既有 SVG / PNG legacy 路径。

## 包外交付与审计目录

新增或明确替换的 Logo 放在冻结研究包之外的持久任务目录。官方原始或经授权第三方原始正方形 SVG / PNG 使用单文件模式：

```text
<identity-assets-root>/
└── logo.svg 或 logo.png（二选一）
```

单文件模式只能包含 `logo.svg` 或 `logo.png` 其中一份，文件名必须与 `company.json` 声明的 canonical 扩展名一致，且画布必须为正方形。第三方文件只允许单文件原始字节模式。只有官方来源按上节完成 `center-square-crop-v1` 时，目录才能且必须精确包含 `logo.png`、`logo-original.png`、`logo-provenance.json` 三份文件。两种模式都不得放入产品图、图片 manifest、网站截图、社媒成品、背景、生成图或未引用附件。

## GitHub 交付

用户明确授权 GitHub 写入后，新增或替换 Logo 时使用 `prepare_github_archive.py --identity-assets-root <dir>`。只要 `company.json` 声明了非空 Logo 路径，无论本次写入还是沿用，都必须同时提供同一 `main` SHA 的 `--remote-identity-assets-state`：

```json
{
  "repository": "bits-bean/doujiao-value-system",
  "branch": "main",
  "base_head": "<40位commit>",
  "company_slug": "example-company",
  "assets": [
    {
      "path": "companies/example-company/assets/logo.png",
      "exists": false,
      "source_path": null,
      "sha256": null,
      "size_bytes": null
    }
  ]
}
```

observation 必须覆盖 `company.json` 声明、准备写入或准备清除引用的每个安全旧路径。`exists:true` 时 `source_path` 指向同一 observation 独立下载的非符号链接临时文件，不能复用本地 staged Logo；其 SHA-256 和大小必须与 JSON 完全一致。`exists:false` 时 `source_path`、hash 和大小都为 `null`。沿用时只有文件内容也通过 SVG / PNG 门禁才可得到 `preserve-existing`；缺 observation 或 `exists:false` 都不能写入，避免悬空引用。新增时远端不存在则创建；内容相同为 `noop`；同一路径内容不同时默认拒绝，只有用户明确授权替换并传入 `--confirm-identity-asset-replacement` 才允许更新。

若精确 observation 证明 `companies/<slug>/company.json` 不存在，而新包仍使用 Logo 空哨兵，归档器默认阻断。普通“提交到 GitHub”、`--confirm-write-authorization`、`--allow-warnings` 或人工接受都不等于接受缺失 Logo；只有用户另外明确说“允许无 Logo 提交”或语义完全等价的话，才可传入 `--confirm-new-company-without-logo`。获此授权后，计划必须记录 `logo_guard: missing-explicitly-authorized` 与 `new_company_without_logo_confirmed:true`，PR 说明也要明确网站将使用 ticker 回退。该例外不放宽搜索记录，也不适用于已有公司、已有有效 Logo、Logo 替换或清除旧引用。

新增或替换为第三方 Logo 时必须传入 `--confirm-third-party-logo`；该参数是对“冻结包已满足常设第三方兜底规则”的机械确认，不是新的第三方许可提问，也不替代普通 GitHub 写入或远端不同 Logo 替换授权。规划器把来源分类记录为 `verified-third-party`，并核对 `company_logo.is_official:false`。这项确认只接受已冻结包中明确记录的第三方兜底，不会把第三方托管改写成官方。沿用远端完全相同的已验证第三方 Logo 不需要再次传该参数，但仍要按 observation 复核字节。

已有非空 Logo 的路径或元数据变化同样属于替换，必须传入明确替换授权。observation 同时覆盖旧路径和新 canonical 路径；旧文件即使已损坏也必须精确下载并核对 hash / 大小，只有新暂存的官方原始正方形 SVG / PNG、经授权第三方原始正方形 SVG / PNG，或已通过完整 provenance 与逐像素门禁的 official-source-derived PNG，字节确有变化且替换已明确授权时，才可放弃旧引用。规划器从不自动转换、删除、改名或覆盖未声明资产。

若远端 canonical 声称 Logo，但当前研究确认没有可验证的官方 Logo 和已授权第三方兜底，可把新四元组冻结为精确 `null/null/null/false`，在完整度说明逐项记录来源尝试、网站 ticker 回退影响和待补条件，并另获“清除旧引用”授权。此时使用 `--confirm-identity-asset-clear`，不是 replacement flag；所有可安全解析的旧路径仍须 observation。旧文件为空、超限或内容损坏时，规划器只允许在明确替换 / 清除中按真实下载字节核对 hash 与大小；沿用仍严格拒绝。`clear-reference` 只把 `company.json` 改为 null 状态，不删除旧文件，也不能用于静默清除有效 Logo。远端旧记录没有 `company_logo`、而新包同样是精确 null 状态时，不属于清除，无需该授权。

研究文件与 Logo 必须在同一个 Git tree / commit 中原子写入。规划器只把 `logo.svg` 或 canonical `logo.png` 写入 GitHub；`logo-original.png` 和 `logo-provenance.json` 仅作为规划时的闭环证据，不得出现在最终差异。提交后按 commit SHA 重读并核对 Logo 路径、SHA-256、`company.json` 的四个 Logo 字段和最终差异；若计划标记 `official_source_derived:true`，还要核对最终 canonical SHA-256 与已保存 provenance 中的输出摘要一致。不得把此动作描述为网站部署或内容发布。
