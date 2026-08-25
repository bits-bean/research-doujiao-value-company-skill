# GitHub 研究归档流程

## 目的与权限

把人工接受的当前研究包提交到 `bits-bean/doujiao-value-system` 的唯一公司目录。本地冻结包可继续保存不可变审计快照；GitHub 每家公司只维护一个不带版本号的当前研究目录，版本历史由 Git commit 保存。

GitHub 写入必须由用户在本次任务中明确授权。“研究某公司”“生成 `company.json`”“冻结研究包”或“生成渠道内容”都不构成写入授权；“提交到 GitHub”“合并到 main”等才构成授权。授权范围仅是受管研究文件，不包含任何视觉素材。

## 发布前门禁

1. 使用冻结时锁定的 Schema 和当前 Skill v2 信任锁重新验证研究包。
2. 要求 `manifest_version: 2.0`、`status: frozen`、`human_review_status: accepted`、`validation.mode: full`、零错误，并验证 manifest 中全部哈希和文件大小。v1 研究包只能审查。
3. 运行 `prepare_github_archive.py` 生成计划。计划文件只写任务临时目录，不写冻结目录。
4. 通过 GitHub 连接器取得权限和最新 `main` SHA，确认冻结清单锁定的 Schema commit 是其祖先，且 `main:schemas/company.schema.json` 仍为锁定 blob。
5. 在同一最新 `main` SHA 下取得当前公司目录、slug / identity registry 与目录内正式 `company.json` 三项 observation。slug 不存在时还要反向确认同一公司身份未绑定其他 slug。
6. 先运行确定性敏感字符串扫描，再语义复核非公开个人信息、资料保密性和再分发权；任一层失败都阻断提交。
7. 确认最终计划没有任何 `assets/`、`images/`、Logo、产品图、图片 manifest、网站截图、社媒成品、背景或渠道模板。任一出现都阻断提交。
8. 任一预检不可访问、陈旧或含糊时停止，不得用本地缓存、旧聊天或其他来源猜测远端状态。

第一次运行规划器可不带 observation，但只能生成 `ready_for_write: false` 的预检计划。取得精确 `main` SHA 后，把以下 JSON 写入任务临时目录再运行：

- `--remote-company-state`：`companies/<company-slug>/` 是否存在、其直接受管研究文件集合、SHA-256 与大小；版本子目录不得存在，非研究资产不写入 `files`。
- `--remote-slug-registry-state`：请求 slug、冻结包身份、slug 是否存在、slug 当前身份及该身份反向绑定的全部 slugs。
- `--remote-canonical-state`：同一 `companies/<company-slug>/company.json` 是否存在；存在时包含下载文件路径、SHA-256、大小和身份，不存在时 `content` 为 `null`。

三项 observation 的 `repository`、`branch` 和 `base_head` 必须一致。任何写入使用 `--confirm-write-authorization`；同一 `data_as_of` 的修订还需 `--confirm-same-date-revision`；直接 `main` 另需 `--confirm-direct-main-authorization`。只有最终计划 `ready_for_write: true` 才能执行。

远端 canonical 为 Schema 1.x、冻结包为 2.0 时，另须 `--confirm-schema-migration`。只允许 1.x → 2.0 升级，且公司法定身份、ticker、交易所、数据日和估值日仍通过全部门禁；同一数据日还必须同时使用 `--confirm-same-date-revision`。禁止 Schema 降级、2.x 横向换版或仅改版本号。

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
- 所有非研究文件与子目录都不参与比较，不得进入 `files` 或 `delete_paths`，必须原样保留。
- 研究归档没有素材 staging、素材 observation、素材替换确认或素材附加写入能力。
- 发现版本子目录时停止；清理遗留 `research/` 或历史目录必须由用户明确指定精确路径，不得随本次整包提交自动扩张删除范围。

正式 `company.json` 只允许单调前进：不存在时创建；相同内容为 `noop`；远端日期更新时停止，禁止回退；同一数据日但内容不同时默认停止，只有人工接受的修订且用户明确授权才使用 `--confirm-same-date-revision`；公司法定身份、ticker、交易所或不允许的 Schema 变化一律停止。

## 提交策略

默认使用 pull request：从最新预检 SHA 创建独立分支，在同一个 Git tree 中写入全部受管研究文件并删除多余受管研究文件，保留全部非研究资产；创建原子 commit 和 PR。只有用户已经要求合并且检查、权限与分支保护允许时才合并。只有明确说“直接提交到 main”才允许原子、非强制、仅快进直写。

最终差异白名单只有：

```text
companies/<company-slug>/<直接研究包文件>
```

禁止修改 Schema、其他公司或其他路径，禁止包含任何素材，禁止使用逐文件 contents 更新直接写 `main`。

## 远端复核与回执

写入后必须按返回的 commit SHA 重新读取并核对当前公司目录的受管文件集合、每个研究文件的完整内容或 SHA-256、正式 `company.json` 的身份与日期单调性，以及分支、PR 或合并状态。还要确认 diff 中没有任何非研究路径。只有全部一致才报告成功；不要把回执写入冻结目录。

## 失败与恢复

- 权限或连接失败：保留本地冻结包和计划，说明未写入。
- 分支保护阻止直接提交：改走 PR；若用户明确禁止 PR，则停止。
- 远端 `main` 并发更新：重新读取并完整重做预检，不得强推。
- 同日修订或 Schema 迁移未获明确确认：停止，不覆盖。
- 计划或实际 diff 含素材或其他非研究路径：停止，不提交或不合并。
- 部分分支写入：不得合并；修复分支时只操作已确认的受管研究路径，保持 `main` 不变。
- 遗留 `research/` 或历史版本子目录需要清理：必须由用户明确指定精确目录；不得把“提交当前研究”扩张为批量删除历史记录。
