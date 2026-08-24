# 公司身份素材与来源契约

## 目的与边界

本契约只解决“system 仓库是否拥有可验证的真实公司身份素材”。研究 Skill 可以在素材缺失或用户明确授权替换时获取、核验和 GitHub 交付素材，但不得：

- 生成或重绘公司 Logo、产品、门店、人物或业务身份；
- 选择小红书、X、网站等渠道比例、背景、安全区、Logo 位置或视觉模板；
- 调用图表渲染器、网页截图、图片合成或内容发布流程；
- 把辨识度不明的图库图、拼图或 AI 图冒充公司标志性产品。

身份素材不是研究事实文件，不写入 `research-manifest.json`。冻结研究包保持不可变；素材在单独的任务临时目录中准备，由 GitHub 交付规划器逐文件验证并与研究文件进入同一原子提交。

## 现有素材优先

开始获取前，在同一最新 `doujiao-value-system/main` SHA 下检查：

1. `company.json.brand_identity.company_logo.asset_path` 指向的精确文件；
2. `companies/<slug>/assets/logo.svg`；
3. `companies/<slug>/assets/visual-assets.json` 及其声明的产品素材；
4. 仅为兼容而存在的 `companies/<slug>/logo-primary.*`。

已有文件的 SHA-256、来源和公司身份均可验证时沿用，不下载另一份，不改路径，不创建并行 Logo。`logo-primary.*` 只作为已有 legacy 路径保留；新公司或新 canonical Logo 统一使用：

```text
companies/<company-slug>/assets/logo.svg
```

`company.json.brand_identity.company_logo.asset_path` 必须与实际沿用或新增的 Logo 路径完全一致。

## Logo 验证

优先使用公司官网、Investor Relations、官方品牌中心或监管文件中的官方素材。必须同时满足：

- 图形与该公司法定身份一致，并优先选择公众辨识度最高的主品牌标志；
- `company.json.brand_identity.company_logo.source_url` 是可长期访问的来源页或原始文件 URL；
- `alt` 准确描述公司和标志，不含渠道宣传文案；
- `is_official` 与来源事实一致，不能因素材“看起来像”而写 `true`；
- 新增文件为非符号链接的真实 SVG，内部不含脚本、远程引用、追踪像素或嵌入凭据。

找不到可验证 Logo 时，把 `asset_path`、`source_url` 和 `alt` 写为 `null`、`is_official:false`，并在 `research-completeness.md` 说明缺口；不得生成替代 Logo。

## 产品或业务素材

产品素材只在能明确证明“画面中的对象是什么、与公司有什么关系、可以怎样使用”时取得。官方来源优先；官方没有足够清晰的文件时可使用权利依据清楚的第三方原图。选取对象只基于公司身份与产品代表性，不基于某个平台版面。

canonical 来源清单固定为：

```text
companies/<company-slug>/assets/visual-assets.json
```

最低结构：

```json
{
  "manifest_version": "1.0",
  "company_slug": "example-company",
  "cover_product": {
    "asset_path": "companies/example-company/assets/iconic-product.jpg",
    "asset_sha256": "<64位小写SHA-256>",
    "alt_cn": "可准确识别公司与产品的中文说明",
    "source_url": "https://example.com/original-file",
    "source_page_url": "https://example.com/source-page",
    "source_publisher": "来源发布者",
    "rights_basis": "许可、官方媒体包条款、公共领域或评论性使用依据",
    "is_official": true
  },
  "localized_copy": {}
}
```

`cover_product.alt_cn` 为必填的非空中文身份说明。`display_language` 以及 `localized_copy` 内的中文业务名、产品名和分部名称可以按 system 现有契约保留。不得把研究结论、社媒标题、渠道比例、背景提示词或布局坐标写入该文件。

逐项门禁：

- `company_slug` 与研究包和目标路径一致；
- `asset_path` 位于同一 `companies/<slug>/assets/` 下，不能越界或使用外链；
- 产品文件只接受可直接验证尺寸和解码的高分辨率 PNG 或 JPEG；不接受 SVG、WebP、AVIF 或其他格式；
- `asset_sha256` 与准备提交的本地文件逐字节一致；
- `alt_cn` 是非空中文说明，准确说明画面对象及其与公司的关系；
- `source_url` 和 `source_page_url` 使用公开的 `http/https` URL，不使用带临时 token 或签名的下载链接；
- `source_publisher`、`rights_basis` 非空，`is_official` 与实际来源一致；
- 素材不含文字水印冲突、账号截图、组合拼贴或无法证明身份的对象。

无法满足任何一项时不提交该产品素材；允许 `visual-assets.json` 缺失，但下游正式封面必须 fail closed，只能标记为草案或待补素材，不得用无产品图模板冒充正式封面，也不得由研究 Skill 或下游生成身份替代图。

## 临时交付目录

新增或明确替换的素材放在冻结研究包之外的任务临时目录，文件结构镜像 system 的 `assets/` 目录：

```text
<identity-assets-root>/
├── logo.svg                    # 仅新增 canonical Logo 时
├── visual-assets.json          # 有产品素材时必须存在
└── <declared-cover-product>    # 文件名必须与 asset_path 一致
```

目录只能包含上述已声明文件，不得放入网站截图、社媒成品、背景、生成图或未引用附件。Logo 与产品素材可以分别缺省；但产品文件和 `visual-assets.json` 必须成对出现。

## GitHub 交付

用户明确授权 GitHub 写入后，使用 `prepare_github_archive.py --identity-assets-root <dir>`。只要存在本地素材写入，必须同时提供同一 `main` SHA 的 `--remote-identity-assets-state`：

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
      "sha256": null,
      "size_bytes": null
    }
  ]
}
```

observation 必须逐一覆盖准备写入的精确目标路径。远端不存在时创建；内容相同时 `noop`；同一路径内容不同时默认拒绝，只有用户明确授权替换身份素材并传入 `--confirm-identity-asset-replacement` 才允许更新。规划器从不删除、不改名、不覆盖未声明素材。

所有研究文件和身份素材必须在同一个 Git tree / commit 中原子写入。提交后按 commit SHA 重读并核对素材路径、SHA-256、`company.json` Logo 路径和 `visual-assets.json` 来源清单。此动作只归档数据与身份素材，不渲染图片、不更新网站运行状态，也不发布渠道内容。
