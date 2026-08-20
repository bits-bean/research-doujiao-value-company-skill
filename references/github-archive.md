# GitHub 归档流程

## 目的与权限

把已经冻结且人工接受的研究快照原样保存到 `bits-bean/doujiao-value-system`。只有用户另外授权提升当前版本时，才让 `companies/<company-slug>/company.json` 使用同一快照中的数据。

GitHub 写入必须由用户在本次任务中明确授权。以下请求只授权研究，不授权归档：“研究某公司”“生成 `company.json`”“冻结研究包”“生成渠道内容”。“提交到 GitHub”“归档到规范仓库”“合并到 main”等才构成写入授权。

GitHub 归档不等于网站或渠道发布，不触发网站导入，也不触发内容生产；但文件可见性取决于 GitHub 仓库权限，公开仓库会公开披露提交内容。支持：

- `archive-only`：只归档不可变快照；
- `archive-and-promote`：归档快照并更新当前正式 `company.json`，需要用户明确授权更新当前版本。

## 发布前门禁

1. 使用冻结时锁定的 Schema 和 Skill 受信锁重新验证研究包。
2. 要求 `status: frozen`、`human_review_status: accepted`、`validation.mode: full`、零错误，并验证全部 manifest 哈希和文件大小。
3. 运行 `prepare_github_archive.py` 生成计划。计划文件只能写入任务临时目录，不能写入冻结目录。
4. 通过 GitHub 连接器取得目标仓库权限和最新 `main` SHA，确认受信规范锚点是其祖先，且锁内全部受保护文件在当前 `main` 上仍是相同 blob。
5. 检查同名快照状态；`archive-and-promote` 还要取得当前正式 `company.json`。
6. 先运行确定性敏感字符串扫描，再语义复核非公开个人信息、资料保密性和再分发权；任一层失败都阻断提交。
7. 任何预检步骤不可访问或结果含糊时停止，不得把 Library 文件、旧聊天或本地缓存当作远端状态。

第一次运行规划器可以不带远端状态，但输出只能是 `ready_for_write: false` 的预检计划。取得连接器返回的精确 `main` SHA、版本目录文件集合、SHA-256 与大小后，把它们写到任务临时目录的 remote-state JSON，再运行规划器。`archive-and-promote` 若 canonical 已存在，还必须把同一 SHA 下载的文件和 `--existing-company-head` 一并提供。最终运行需要与当前请求对应的确认参数：任何写入使用 `--confirm-write-authorization`，提升 canonical 使用 `--confirm-promotion-authorization`，直接 `main` 使用 `--confirm-direct-main-authorization`；最终计划只有 `ready_for_write: true` 才能执行。

## 路径与不可变性

版本快照固定为：

```text
research/<company-slug>/<version>/<manifest 中的冻结文件>
research/<company-slug>/<version>/research-manifest.json
```

当前正式副本固定为：

```text
companies/<company-slug>/company.json
```

`company-slug` 只允许小写字母、数字和单连字符，并必须与公司法定名称、ticker、交易所及仓库已有目录核对。`version` 只允许 `YYYY-MM-DD` 或从 `YYYY-MM-DD-v2` 开始的修订后缀。不得接受绝对路径、`..`、转义分隔符、符号链接或其他目标仓库。

版本目录不可变：

- 目录不存在：可以创建。
- 目录存在且计划中的每个文件逐字节相同，且没有额外文件：幂等成功，不重复提交。
- 目录存在但任一文件缺失、不同或多出文件：停止；创建新的稳定版本后缀后重新计划，不得覆盖。

`archive-and-promote` 的当前正式副本只允许单调前进：

- 不存在：创建。
- 与新快照完全相同：不操作。
- `data_as_of` 更旧：更新。
- 远端 `data_as_of` 更新：停止，不得回退。
- `data_as_of` 相同但内容不同：默认停止；只有新快照使用 `-vN` 且用户明确确认提升修订版时才允许。
- 公司法定身份、ticker、交易所或 `schema_version` 不同：停止。

## 提交策略

默认 `pull-request`：

1. 从预检得到的最新 `main` SHA 创建独立分支。
2. 把整个版本快照和经授权的当前正式副本组成一个 Git tree。
3. 创建单一 commit 并推送分支。
4. 建立 PR，说明研究版本、数据日、估值日、manifest SHA-256、验证结果和目标路径。
5. 只有用户已要求合并且检查、权限和分支保护允许时才合并；否则返回 PR 等待审核。

用户要求“合并到 `main`”时仍先创建 PR，通过检查后再合并。`direct-main` 只在用户明确要求“直接提交到 `main`”时使用：

1. 仍从预检 SHA 构造完整 tree 和单一 commit。
2. 提交前再次确认远端 `main` 仍等于预检 SHA；若已变化，重新预检和重建 commit。
3. 以 `force: false` 更新 `main`；禁止强推。

`archive-only` 的 tree 不得包含当前正式副本。无论哪种模式，最终 diff 都只能新增一个版本目录，并可选创建或更新一个 canonical `company.json`；出现删除、重命名、其他路径或受保护规范文件变化立即阻断。

禁止使用逐文件 contents 更新直接写 `main`，因为中途失败会留下部分版本。无法创建原子 tree/commit 时，退回独立分支和 PR，不得降低完整性门禁。

## 远端复核与回执

写入后必须以返回的 commit SHA 为 ref 重新读取：

- 版本目录文件集合；
- 每个版本文件内容 SHA-256；
- 当前正式 `company.json` SHA-256；
- commit 是否位于预期分支或 PR；
- PR 或合并状态。

只有全部一致才报告成功。回执至少包含仓库、策略、分支或 PR、commit SHA、版本路径、当前正式路径和复核结论。不要把回执写入冻结目录。

## 失败与恢复

- 权限或连接失败：保留本地冻结包和计划，说明未写入。
- 分支保护阻止直接提交：改走 PR；如果用户明确禁止 PR，则停止。
- 远端并发更新：重新读取 `main` 并完整重做预检；不得强推。
- 版本路径冲突：使用新版本后缀重新冻结或重新规划，绝不覆盖。
- 部分分支写入：不得合并；删除或修复分支前先确认目标，主分支保持不变。
