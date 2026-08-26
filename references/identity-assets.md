# 公司 Logo 与来源契约

## 目的与边界

本契约只解决“`doujiao-value-system` 是否拥有网站可直接引用、来源可验证的真实公司 Logo”。公司 Logo 是研究 Skill 唯一可以取得、核验、暂存和在获授权后归档的视觉素材。

不得：

- 生成、重绘、描摹或用近似图替代公司 Logo；
- 获取或管理产品、服务、人物、门店、业务场景、封面、背景或其他视觉素材；
- 选择网站或社媒比例、背景、安全区、Logo 位置或视觉模板；
- 调用图表渲染器、网页截图、图片合成或发布流程。

Logo 不是研究事实文件，不写入 `research-manifest.json`。冻结研究包保持不可变；manifest 与 `validation-report.json` 会锁定同一 `company_slug` 和 Logo 元数据，但不声称锁定包外 Logo 字节。新增或获授权替换的 Logo 在冻结目录外单独准备，正式的字节 hash、安全性与非透明像素验证发生在 GitHub 交付规划阶段；在规划器给出 `ready_for_write:true` 并完成提交复核前，不得称该冻结包已具备网站 Logo。

## 现有 Logo 优先

开始获取前，在同一最新 `doujiao-value-system/main` SHA 下依次检查：

1. `company.json.brand_identity.company_logo.asset_path` 指向的精确文件；
2. `companies/<slug>/assets/logo.svg`；
3. 仅为兼容保留且可完整验证的 `companies/<slug>/logo-primary.svg` 或 `companies/<slug>/logo-primary.png`。

已有文件的公司身份、来源和内容可验证时沿用，不重新从官网另找替代品、不改路径；未经明确替换授权不得增加新 Logo 路径。但归档预检必须把 system 中该精确文件下载到任务临时目录，逐字节核对 hash、大小、安全性与实际非透明像素。`logo-primary.svg` / `logo-primary.png` 只作为已有 legacy 路径保留；其他旧格式必须按明确替换流程迁移为 canonical SVG，不能只改元数据。新公司或新 canonical Logo 统一使用：

```text
companies/<company-slug>/assets/logo.svg
```

`company.json.brand_identity.company_logo.asset_path` 必须与实际沿用或新增的 Logo 路径完全一致。增量研究不得把已有有效 Logo 字段静默改回 `null`。

## 获取与验证

只从公司官网、Investor Relations、官方品牌中心或官方媒体资料页取得 Logo。必须同时满足：

- 图形与公司法定身份一致，并使用公众辨识度最高的主品牌标志；
- `source_url` 是公开、无临时 token、可复核的来源页或原始文件 URL；
- `alt` 准确描述公司和标志，不含投资结论或渠道宣传文案；
- `is_official:true` 与来源事实一致，不能仅凭外观判断；
- 新增文件是非符号链接、非空且不超过 512,000 字节的 UTF-8 SVG，与网站运行时上限一致；
- SVG 不含脚本、事件处理器、远程引用、追踪像素、嵌入凭据或外部字体依赖；过滤器、mask、条件渲染、CSS 变量和非标准命名空间也不接受。可沿用只含简单元素 / class / id 选择器与安全 SVG presentation properties 的内联 `<style>`；任何 at-rule、复杂选择器、外部样式或资源、未知属性都拒绝。

第一个官方候选不合格时不能直接结束搜索。首次研究至少继续检查并记录以下检索面；某一检索面不存在或不适用时也要明确写出，而不是省略：

1. 公司官网当前页面实际加载的 Logo，包括 DOM、CSS、网络请求和官方静态资源域名；
2. Investor Relations 的首页、年报页、治理页和新闻稿模板；
3. 官方品牌中心、媒体资料、新闻资料或下载中心；
4. 适用的官方产品、商户、开发者、合作伙伴或支持页面；
5. 每个候选的原始 URL、格式、公司身份核验、是否满足安全门，以及采用或拒绝原因。

只有完成上述记录后，才能判断“当前找不到可验证的官方 Logo”。不得因为一个 SVG 含 DOCTYPE、`foreignObject`、字体或其他不安全结构，就推断该公司没有其他官方安全素材；应继续查找官网实际在用的简化版本或其他官方原始文件，也不得自行清洗不合格文件冒充原件。

公开来源 URL 不得使用 localhost、私网 / link-local IP、旧式数值 IP 写法、保留测试域、用户凭据或 AWS / Google / CDN 签名查询参数。机械 URL 门只负责语法与稳定性约束；实际取得步骤仍须成功打开公开官方页面或文件并核对公司身份，不能用“语法合法”替代可达性和官方性。SVG 必须使用标准命名空间，至少包含可渲染的矢量几何；文本 / 字体节点、XML Events、外部样式、空路径、零尺寸图形、悬空内部引用，以及 `lab()` / `lch()` / `oklab()` / `oklch()` / `hwb()` / `color()` / `device-cmyk()` 等跨渲染器颜色函数都不合格。归档门还必须使用平台主运行时 bundle 26.812.11052 中的 Sharp 0.35.3 + libvips 8.18.3 + librsvg 2.62.90 SVG 栅格器生成透明背景探针，至少存在一个非透明像素；Node、Sharp 入口和 package metadata 的绝对路径及 SHA-256 都锁定在脚本中，子进程不按当前工作目录或包名解析模块，也不继承 `NODE_OPTIONS`、preload、调用方 `NODE_PATH` 或动态库注入环境。探针还必须返回匹配随机 challenge、协议名、版本和可见性布尔值的结构化回执，空输出或只返回退出码 0 不构成通过。任一 bundle / 组件版本不符、运行时路径或摘要不受信、回执错误、渲染器缺失、超时、报错或空白都阻断。legacy PNG 只在完整 chunk、CRC、IHDR、IDAT 解压、像素行长度、过滤器和至少一个非透明像素均通过时沿用。

找不到满足条件的官方 Logo 时，`asset_path`、`source_url` 和 `alt` 写 `null`，`is_official:false`；在 `research-completeness.md` 独立说明“公司 Logo 缺失”、尝试过的官方来源及对网站展示的影响。不得生成替代 Logo。

该完整度条目必须逐项写明已检查的官网 / IR / 官方品牌中心或媒体资料、缺失原因、网站 ticker 回退或其他展示影响，以及后续待补证据或重新检查条件。笼统写“已知悉”不能越过警告门禁。`validate_research_package.py` 与 `freeze_research.py` 都必须接收同一 `--company-slug`，以便在冻结前把 Logo 路径绑定到精确公司；非空状态只允许该 slug 的 canonical 路径或可完整验证的既有 SVG / PNG legacy 路径。

## 临时交付目录

新增或明确替换的 Logo 放在冻结研究包之外的任务临时目录：

```text
<identity-assets-root>/
└── logo.svg
```

目录只能包含这一份 `logo.svg`，不得放入产品图、图片 manifest、网站截图、社媒成品、背景、生成图或未引用附件。

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
      "path": "companies/example-company/assets/logo.svg",
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

已有非空 Logo 的路径或元数据变化同样属于替换，必须传入明确替换授权。observation 同时覆盖旧路径和新 canonical 路径；旧文件即使已损坏也必须精确下载并核对 hash / 大小，只有新暂存 SVG 已通过门禁、字节确有变化且替换已明确授权时，才可放弃旧引用。规划器从不自动删除、改名或覆盖未声明资产。

若远端 canonical 声称 Logo，但当前研究确认没有可验证的官方 Logo，可把新四元组冻结为精确 `null/null/null/false`，在完整度说明逐项记录官方来源尝试、网站 ticker 回退影响和待补条件，并另获“清除旧引用”授权。此时使用 `--confirm-identity-asset-clear`，不是 replacement flag；所有可安全解析的旧路径仍须 observation。旧文件为空、超限或内容损坏时，规划器只允许在明确替换 / 清除中按真实下载字节核对 hash 与大小；沿用仍严格拒绝。`clear-reference` 只把 `company.json` 改为 null 状态，不删除旧文件，也不能用于静默清除有效 Logo。远端旧记录没有 `company_logo`、而新包同样是精确 null 状态时，不属于清除，无需该授权。

研究文件与 Logo 必须在同一个 Git tree / commit 中原子写入。提交后按 commit SHA 重读并核对 Logo 路径、SHA-256、`company.json` 的四个 Logo 字段和最终差异；不得把此动作描述为网站部署或内容发布。
