# GitHub 提交流程

## 目的与权限

把人工接受的当前研究包提交到 `bits-bean/doujiao-value-system` 的唯一公司目录。本地冻结包可继续保存不可变审计快照；GitHub 每家公司只维护一个不带版本号的当前目录，版本历史由 Git commit 保存。

GitHub 写入必须由用户在本次任务中明确授权。“研究某公司”“生成 `company.json`”“冻结研究包”“生成渠道内容”都不构成写入授权；“提交到 GitHub”“合并到 main”等才构成授权。一旦用户授权提交，必须整包更新：

```text
companies/<company-slug>/
```

报告、`company.json`、台账、验证结果与 manifest 全部直接位于该目录；`company.json` 只有这一份正式副本。不得再向 `research/` 写入研究副本。

GitHub 提交不等于网站或渠道发布，不触发网站导入或内容生产；公开仓库会公开披露提交内容。

## 发布前门禁

1. 使用冻结时锁定的 Schema 和当前 Skill v2 信任锁重新验证研究包。
2. 要求 `manifest_version: 2.0`、`status: frozen`、`human_review_status: accepted`、`validation.mode: full`、零错误，并验证 manifest 中全部哈希和文件大小。v1 研究包只能审查。
3. 运行 `prepare_github_archive.py` 生成计划。计划文件只写任务临时目录，不写冻结目录。
4. 通过 GitHub 连接器取得权限和最新 `main` SHA，确认冻结清单锁定的 Schema commit 是其祖先，且 `main:schemas/company.schema.json` 仍为锁定 blob。
5. 在同一最新 `main` SHA 下取得当前公司目录、slug / identity registry 与目录内正式 `company.json` 三项 observation。slug 不存在时还要反向确认同一公司身份未绑定其他 slug。
6. 先运行确定性敏感字符串扫描，再语义复核非公开个人信息、资料保密性和再分发权；任一层失败都阻断提交。
7. 任一预检不可访问、陈旧或含糊时停止，不得用本地缓存、旧聊天或其他来源猜测远端状态。

第一次运行规划器可不带 observation，但只能生成 `ready_for_write: false` 的预检计划。取得精确 `main` SHA 后，把以下 JSON 写入任务临时目录再运行：

- `--remote-company-state`：`companies/<company-slug>/` 是否存在、其直接文件集合、SHA-256 与大小；版本子目录不得存在，也不写入 `files`。
- `--remote-slug-registry-state`：请求 slug、冻结包身份、slug 是否存在、slug 当前身份及该身份反向绑定的全部 slugs。
- `--remote-canonical-state`：同一 `companies/<company-slug>/company.json` 是否存在；存在时包含下载文件路径、SHA-256、大小和身份，不存在时 `content` 为 `null`。该 observation 只承担单调性与身份保护，不产生第二份写入。

三项 observation 的 `repository`、`branch` 和 `base_head` 必须一致。任何写入使用 `--confirm-write-authorization`；同一 `data_as_of` 的修订还需 `--confirm-same-date-revision`；直接 `main` 另需 `--confirm-direct-main-authorization`。只有最终计划 `ready_for_write: true` 才能执行。

## 远端路径与替换语义

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

不得增加 `<date>/`、`<date>-vN/` 或其他版本子目录，也不得再写 `research/<company-slug>/`。本地版本标识只用于冻结、审计和下游交接，不进入 GitHub 路径。

`company-slug` 只允许小写字母、数字和单连字符。必须在同一 `main` SHA 下完成 slug→身份与身份→slug 双向核对。

当前公司目录对受管研究文件采用整包替换语义。受管文件仅包括上方列出的八类研究包文件；Logo、品牌图像及其他非研究资产不属于受管集合，必须保留：

- 目录不存在：创建全部直接研究文件。
- 直接文件集合及内容完全相同：公司目录为幂等 `noop`。
- 任一受管文件缺失或变化：以冻结包完整受管文件集更新；旧的多余受管文件列入 `delete_paths`。
- 非研究资产无论是否存在都不参与 `noop` 比较，不得列入 `delete_paths`。
- 发现版本子目录时停止；清理遗留 `research/` 或历史目录必须由用户明确指定精确路径，不得随本次整包提交自动扩张删除范围。

正式 `company.json` 只允许单调前进：

- 不存在：创建。
- 与研究包中的 `company.json` 完全相同：`noop`。
- 远端 `data_as_of` 或 `valuation_date` 更新：停止，禁止回退。
- 同一 `data_as_of` 但内容不同：默认停止；只有人工接受的修订且用户明确授权该次修复时，使用 `--confirm-same-date-revision`。
- 公司法定身份、ticker、交易所或 `schema_version` 不一致：停止。

## 提交策略

默认使用 pull request：

1. 从预检得到的最新 `main` SHA 创建独立分支。
2. 在同一个 Git tree 中写入当前公司目录全部受管研究文件并删除其多余受管研究文件，保留非研究资产；其中 `company.json` 同时受 canonical 单调性门禁保护。
3. 创建原子 commit 并推送分支。
4. 建立 PR，说明公司、数据日、估值日、manifest SHA-256、验证结果与公司目录。
5. 只有用户已要求合并且检查、权限与分支保护允许时才合并；否则返回 PR 等待审核。

用户要求“合并到 main”时仍先创建 PR 并检查后合并。只有明确说“直接提交到 main”才使用 direct-main：提交前再次确认 `main` 未变化，且只允许非强制、仅快进更新。

最终 diff 只能涉及：

```text
companies/<company-slug>/<直接研究包文件>
```

禁止修改 Schema、其他公司或其他路径。禁止使用逐文件 contents 更新直接写 `main`，避免中途失败留下不完整状态。

## 远端复核与回执

写入后必须按返回的 commit SHA 重新读取：

- 当前公司目录的直接文件集合；
- 每个研究包文件的完整内容或 SHA-256；
- 正式 `company.json` 的完整内容、SHA-256、身份与日期单调性；
- commit 所在分支、PR 或合并状态。

只有全部一致才报告成功。回执至少包含仓库、策略、分支或 PR、commit SHA、公司目录与复核结论。不要把回执写入冻结目录。

## 失败与恢复

- 权限或连接失败：保留本地冻结包和计划，说明未写入。
- 分支保护阻止直接提交：改走 PR；若用户明确禁止 PR，则停止。
- 远端 `main` 并发更新：重新读取并完整重做预检，不得强推。
- 同日修订未获明确确认：停止，不覆盖。
- 部分分支写入：不得合并；修复分支时只操作已确认的目标路径，保持 `main` 不变。
- 遗留 `research/` 或历史版本子目录需要清理：必须由用户明确指定精确目录；不得把“提交当前研究”扩张为批量删除历史记录。
