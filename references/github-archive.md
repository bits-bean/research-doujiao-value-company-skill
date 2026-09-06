# GitHub 研究归档流程

## 目的与权限

把人工接受的当前研究包提交到 `bits-bean/doujiao-value-system` 的唯一公司目录。本地冻结包可继续保存不可变审计快照；GitHub 每家公司只维护一个不带版本号的当前研究目录，版本历史由 Git commit 保存。

GitHub 写入必须由用户在本次任务中明确授权。“研究某公司”“生成 `company.json`”“冻结研究包”或“生成渠道内容”都不构成写入授权；“提交到 GitHub”“合并到 main”等才构成授权。授权范围是受管研究文件，以及本次按 [identity-assets.md](identity-assets.md) 显式暂存并验证的单一公司 Logo。替换远端不同内容的 Logo、清除远端既有 Logo 引用，或首次提交一个仍缺 Logo 的新公司，都需要用户分别另行明确授权，三种授权不能互相替代。普通“提交到 GitHub”绝不等于“允许无 Logo 提交”。

## 发布前门禁

1. 使用冻结时锁定的 Schema 和当前 Skill v2 信任锁重新验证研究包；重新验证必须确认桑基 `color_audit` 不是 `blocked`，`matched` 逐节点色与 `company.json` 一致，或 `not_found` 已穷尽规范身份与官方可验证别名并绑定 System 默认版本。
2. 要求 `manifest_version: 2.0`、`status: frozen`、`human_review_status: accepted`、`validation.mode: full`、零错误，并验证 manifest 与验证报告锁定的 `company_slug` 等于本次交付 slug、manifest 中全部哈希和文件大小。v1 研究包只能审查。
3. 运行 `prepare_github_archive.py` 生成计划。计划文件只写冻结目录外的任务工作目录，不写冻结目录。
4. 通过 GitHub 连接器取得权限和最新 `main` SHA，确认冻结清单锁定的 Schema commit 是其祖先，且 `main:schemas/company.schema.json` 仍为锁定 blob。
5. 在同一最新 `main` SHA 下取得当前公司目录、slug / identity registry 与目录内正式 `company.json` 三项 observation。slug 不存在时还要反向确认同一公司身份未绑定其他 slug。
6. 先运行确定性敏感字符串扫描，再语义复核非公开个人信息、资料保密性和再分发权；任一层失败都阻断提交。
7. 完整读取 `identity-assets.md`。`company.json` 声明非空 Logo 时，取得同一 `main` SHA 的精确远端素材 observation，并把每个 `exists:true` 的文件下载到临时 `source_path` 校验实际字节；沿用时验证内容可渲染，新增或替换时优先暂存唯一官方原始正方形 `logo.svg` / `logo.png`。只有穷尽官方正方形候选后，才允许使用精确三文件模式 `logo.png` + `logo-original.png` + `logo-provenance.json`；规划器必须解码两个 PNG、证明输出是 `center-square-crop-v1` 逐像素精确中心裁剪，且只把 canonical `logo.png` 纳入计划。不得跨格式转换、拉伸、补边、重采样、改色、清洗、描摹或重绘。路径 / 元数据切换时 observation 同时覆盖旧路径和新路径，且需要明确替换授权。新包使用精确空哨兵、远端 canonical 却声明旧 Logo 时，同样观察所有安全旧路径并要求独立清除引用授权。除最终单一 canonical Logo 例外外，计划中出现任何 `assets/`、`images/`、产品图、图片 manifest、网站截图、社媒成品、背景或渠道模板都阻断提交。
8. 若 canonical observation 证明该公司尚不存在，而新包使用 Logo 空哨兵，默认停止。只有用户明确说“允许无 Logo 提交”或语义完全等价的话，才可使用 `--confirm-new-company-without-logo`；普通写入授权、人工接受或 warning 确认均不能推导该参数。
9. 任一预检不可访问、陈旧或含糊时停止，不得用本地缓存、旧聊天或其他来源猜测远端状态。

第一次运行规划器可不带 observation，但只能生成 `ready_for_write: false` 的预检计划。取得精确 `main` SHA 后，把以下 JSON 写入冻结目录外的任务工作目录再运行：

- `--remote-company-state`：`companies/<company-slug>/` 是否存在、其直接受管研究文件集合、SHA-256 与大小；版本子目录不得存在，非研究资产不写入 `files`。
- `--remote-slug-registry-state`：请求 slug、冻结包身份、slug 是否存在、slug 当前身份及该身份反向绑定的全部 slugs。
- `--remote-canonical-state`：同一 `companies/<company-slug>/company.json` 是否存在；存在时包含下载文件路径、SHA-256、大小和身份，不存在时 `content` 为 `null`。
- `--remote-identity-assets-state`：只要新 `company.json` 声明非空 Logo 路径，或远端 canonical 声明的旧 Logo 将被替换 / 清除引用，就必须使用；逐项说明精确路径是否存在、临时下载 `source_path`、SHA-256 与大小。`exists:true` 必须提供匹配的非符号链接文件，`exists:false` 使用 `source_path:null`；替换路径时必须同时观察旧 / 新路径。

全部 observation 的 `repository`、`branch` 和 `base_head` 必须一致。任何写入使用 `--confirm-write-authorization`；同一 `data_as_of` 的修订还需 `--confirm-same-date-revision`；直接 `main` 另需 `--confirm-direct-main-authorization`；替换远端不同 Logo 字节另需 `--confirm-identity-asset-replacement`；把远端既有 Logo 引用改为空哨兵另需 `--confirm-identity-asset-clear`；首次归档仍缺 Logo 的新公司另需 `--confirm-new-company-without-logo`。只有最终计划 `ready_for_write: true` 才能执行。

远端 canonical 使用较旧 Schema、冻结包使用当前锁定 Schema 2.3.0 时，另须 `--confirm-schema-migration`。只允许已知旧版本 1.x、精确 2.0.0、2.1.0 或 2.2.0 单调升级到当前 2.3.0；公司法定身份、ticker、交易所、数据日和估值日仍须通过全部门禁，同一数据日还必须同时使用 `--confirm-same-date-revision`。禁止其他旧版本、Schema 降级、跳到非当前锁定版本或仅改版本号。

## 受管路径与替换语义

当前研究包固定直接位于：

```text
companies/<company-slug>/research-report.md
companies/<company-slug>/company.json
companies/<company-slug>/research-completeness.md
companies/<company-slug>/evidence-ledger.json
companies/<company-slug>/calculation-ledger.json
companies/<company-slug>/validation-report.json
companies/<company-slug>/schema-gap-report.md        # 仅 manifest 列出时
companies/<company-slug>/research-manifest.json
```

不得增加 `<date>/`、`<date>-vN/` 或其他版本子目录，也不得再写 `research/<company-slug>/`。`company-slug` 只允许小写字母、数字和单连字符；必须在同一 `main` SHA 下完成 slug→身份与身份→slug 双向核对。

当前公司目录只对上述受管研究文件采用整包替换语义：

- 目录不存在：创建全部直接研究文件。
- 受管文件集合及内容完全相同：幂等 `noop`。
- 任一受管文件缺失或变化：以冻结包完整受管文件集更新；旧的多余受管研究文件列入 `delete_paths`。
- 所有非研究文件与子目录都不参与研究包比较，不得进入研究包的 `files` 或 `delete_paths`，必须原样保留。
- 唯一例外是显式暂存的 `companies/<slug>/assets/logo.svg` 或 `companies/<slug>/assets/logo.png`（二选一）：路径必须与 `company.json` 完全一致，由独立 observation 和 SHA-256 门禁决定 `create`、`noop` 或经明确授权的 `update`。官方原始正方形文件保持原字节；已证明的 PNG 中心裁剪标记 `official_source_derived:true`，但仍只写入一个 canonical PNG。从不跨格式转换或删除 Logo。App Economy Insights 原始 PNG 只存在于私有研究证据目录，任何路径或字节出现在冻结包、计划或最终 diff 都必须阻断。
- 新公司若声明非空 Logo 路径而没有暂存已验证文件，停止。更新现有公司时，非暂存 Logo 的路径与元数据必须与远端 canonical `company.json` 一致；不得静默清空、换路径或制造悬空引用。
- 已确认没有可验证官方 Logo 时，只有新四元组为精确空哨兵、完整度说明列明官方来源尝试 / 网站 ticker 回退影响 / 待补条件、远端安全旧路径均有精确 observation，且另获清除引用授权，才允许 `clear-reference`。它只取消 `company.json` 引用并保留旧文件；远端本来没有 Logo 记录且新包仍为空时不需要该授权。
- 远端本来不存在的新公司若仍为空哨兵，不属于 `clear-reference`，但首次归档默认阻断。只有独立的无 Logo 交付授权才能得到 `missing-explicitly-authorized`；通用 warning 或写入授权不能复用，且该状态必须写入计划和 PR 说明。
- 发现版本子目录时停止；清理遗留 `research/` 或历史目录必须由用户明确指定精确路径，不得随本次整包提交自动扩张删除范围。

正式 `company.json` 只允许单调前进：不存在时创建；相同内容为 `noop`；远端日期更新时停止，禁止回退；同一数据日但内容不同时默认停止，只有人工接受的修订且用户明确授权才使用 `--confirm-same-date-revision`；公司法定身份、ticker、交易所或不允许的 Schema 变化一律停止。

## 提交策略

默认使用 pull request：从最新预检 SHA 创建独立分支，在同一个 Git tree 中写入全部受管研究文件、删除多余受管研究文件，并按计划写入可选单一 Logo；保留全部其他非研究资产，创建原子 commit 和 PR。只有用户已经要求合并且检查、权限与分支保护允许时才合并。只有明确说“直接提交到 main”才允许原子、非强制、仅快进直写。

最终差异白名单只有：

```text
companies/<company-slug>/<直接研究包文件>
companies/<company-slug>/assets/logo.svg    # 与下一行二选一，仅本次显式暂存并验证时
companies/<company-slug>/assets/logo.png
```

禁止修改 Schema、其他公司或其他路径，禁止包含 Logo 之外的任何素材，禁止使用逐文件 contents 更新直接写 `main`。

## 远端复核与回执

写入后必须按返回的 commit SHA 重新读取并核对当前公司目录的受管文件集合、每个研究文件的完整内容或 SHA-256、正式 `company.json` 的身份与日期单调性，以及分支、PR 或合并状态。新公司未获无 Logo 交付授权时，最终 diff 必须实际包含计划中的 `assets/logo.svg` 或 `assets/logo.png`；不能只看 `company.json` 元数据或 PR 文案。如写入 Logo，还要核对文件 SHA-256、四个 Logo 字段和实际路径；计划标记 `official_source_derived:true` 时，还要将远端 canonical SHA-256 与持久保留的 provenance 输出摘要相互核对，并确认原件 / provenance 未进入最终 diff。如清除引用，还要核对精确空哨兵且旧文件未被删除；如明确接受新公司无 Logo，则复核计划回执和 PR 都清楚披露 ticker 回退。最终 diff 只能包含受管研究文件与计划中的可选 Logo。只有全部一致才报告成功；不要把回执写入冻结目录。

## 失败与恢复

- 权限或连接失败：保留本地冻结包和计划，说明未写入。
- 分支保护阻止直接提交：改走 PR；若用户明确禁止 PR，则停止。
- 远端 `main` 并发更新：重新读取并完整重做预检，不得强推。
- 同日修订或 Schema 迁移未获明确确认：停止，不覆盖。
- 计划或实际 diff 含未获准的 Logo 替换、Logo 之外的素材或其他非研究路径：停止，不提交或不合并。
- 部分分支写入：不得合并；修复分支时只操作已确认的受管研究路径，保持 `main` 不变。
- 遗留 `research/` 或历史版本子目录需要清理：必须由用户明确指定精确目录；不得把“提交当前研究”扩张为批量删除历史记录。
