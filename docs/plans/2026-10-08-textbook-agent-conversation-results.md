# 教材学习会话升级验收记录

日期：2026-10-08。实施分支：`feature/more-to-skills-textbook-refactor`。

## 合并与范围

- 实施前仅提交计划文件 `a312af9ee`，重新确认祖先关系后在 `local-main` 执行快进合并。主仓库包含原开发 HEAD `0431d1878`，最终仍停在 `a312af9ee`。
- 后续实现均在原开发 worktree 完成，未新建分支/worktree、未合并新成果、未 push。
- 两个 checkout 的用户文档、教材 PDF、凭据及其他未跟踪文件保留，未 clean/reset/stash。
- 教材追问沿用 Flash；教材加工继续独立的托管 PTC/job 链路。学生通用 workspace、sandbox、Vault、MCP、Skills 与 PTC 权限未开放，家长查看学生转录仍使用原只读接口。

## 能力与事件处理

| 内容 | 实现与验证 |
|---|---|
| 历史、运行身份、游标、metadata | 授权教育 replay/status 复用通用 checkpoint 投影与 fallback；共享会话处理恢复及稳定身份，不增加事件协议或存储表 |
| 教材、assignment、知识点归属 | 发送、确认、重试与历史按原问题归属校验；学生切换知识点不重连其他知识点运行，另一个未结束运行阻止新追问 |
| HITL | 共享卡片支持批准/拒绝、恢复及稳定请求 key；同步提交锁防同一渲染重复发送；合成浏览器验证拒绝、失败重试、刷新及双页同步 |
| HTML artifact | 共享 iframe 隔离、交互与 actions；浏览器验证刷新恢复与组件交互，沿用来源校验，不新增 allow-same-origin |
| 文件与动态预览 | 保留稳定作品 ID、源回答和历史轮次锚点；家长复用路径路由、只读文件面板及按需预览恢复，失败可重试；学生入口维持权限提示 |
| 后台 PTC 状态与回传 | 共享任务卡片、状态读取和 report-back watch；相关单元回归通过，未真实派发模型任务 |
| 工具、推理与技术事件 | 沿用 Flash 紧凑折叠活动；状态与传输事件内部处理，不逐项堆入教材正文 |
| 用户问题 | 复用 Flash 右侧气泡、当前会话实际作者头像及持久化时间/既有回退，不使用问题大标题 |
| 连续阅读 | 讲义、全部问答、确认及作品同一滚动容器；保留轮次分割线、固定输入栏与减少动态效果偏好 |
| 长代码 | 共享 CodeBlock 按实际溢出限制桌面 320px/手机 240px；内部滚动、展开/收起，短块自然展示，复制与打印保留全文，导出不裁剪 |

## 自动验证

- 后端共 330 项通过：教育权限/学习历史/转录/路由、请求准备、运行与鉴权等 289 项；admission/credit/stamp/mux 40 项；教材重试路由 1 项。289 项运行有 5 个既有 AsyncMock 未 await 警告。相关 Ruff 通过。
- 前端 37 个文件共 348 项通过，涵盖教材、共享 Markdown、Flash/PTC 发送、HITL 去重、report-back、历史幂等、重连、停止与模型状态。异步高亮器加载在测试开始前等待，不屏蔽退出异常。
- `pnpm typecheck` 通过；变更源文件 ESLint 无错误；`git diff --check` 通过。
- `pnpm build` 通过，首屏关键路径 360.5 kB gzip，低于 450 kB 门槛。Vite 仍提示部分懒加载 chunk 较大，未提高门槛。
- 四组教材 Playwright 回归共 45 项通过：conversation、learning、workbench、processing。最后作品身份小改动后 conversation 6 项再次通过。
- 确认同步提交锁与第二轮作品归属有失败复现及修复后通过记录。

本地日志：`/tmp/langalpha-final-frontend-tests.log`、`/tmp/langalpha-final-backend-tests.log`、`/tmp/langalpha-admission-regression.log`、`/tmp/langalpha-final-e2e.log`、`/tmp/langalpha-final-conversation-e2e.log`、`/tmp/langalpha-final-build.log`、`/tmp/langalpha-final-eslint.log`。日志未提交。

## 浏览器与真实数据证据

**真实浏览器，合成 API/SSE 数据：** Playwright 操作实际组件，覆盖 375/390/768/1440px、亮暗主题、长代码、完整复制/打印、HTML、确认刷新/拒绝/重试、文件/预览恢复及失败重试。两张同时打开的教材/Flash 页面通过 feed 更新处理状态，只发出一次确认请求。5177 页面采用 API catch-all 阻断未 mock 请求，没有向真实当前会话发送操作。

截图保存在 `/tmp/langalpha-live5177-{390,1440}-{light,dark}.png`、`/tmp/langalpha-hitl-{375,1440}.png`、`/tmp/langalpha-conversation-{375,390,768,1440}-{light,dark}.png`，已进行视觉检查；不提交截图等生成文件。

**真实数据库，只读双进程：** 两个独立进程分别读取获授权教材 replay/status 三次，均返回 125 个事件及 `interrupted` 状态，摘要一致（`920b9afa4f63899e372cbd89ab601ee11d190597dcaf237db674f9c6bdad2888`）。同时验证持久化上下文恢复及不一致知识点拒绝。未发送、批准、写入或启动 sandbox。

**服务与 LAN：** 保留原前端 PID 50701，监听 `0.0.0.0:5177`；`http://192.168.3.240:5177` 返回 HTTP 200。原后端、容器和数据挂载均保留。

## 未验证及后续范围

- 未执行真实模型回答、真实 workspace 创建、PTC 派发、sandbox 文件生成或真实后台任务结果回传；这些能力的接入以共享实现、单元回归及合成浏览器证据为准。
- 未执行完整双 worker 的 send/reconnect/cancel/report-back 与故障注入门禁。真实双进程读取只证明本次授权投影及状态读取的一致性，不能替代执行门禁；本次没有改写 admission、checkpoint 写入或运行持久化机制。
- 当前用户等待中的真实 HITL 保持待确认。浏览器拒绝及重试仅作用于合成 fixtures，未使用该会话进行有副作用测试。
- 学生受限教育 PTC、跨工作区作品明确授权共享、作品独立归档与版本管理留待后续。学生本次不能通过 UI 文件入口访问家长 sandbox。
- 当前验收不代表高并发长历史或大量 iframe 的负载验收。

## 实施提交

| 提交 | 内容 |
|---|---|
| `a312af9ee` | 单文件提交实施计划，随后快进 local-main |
| `81b87fed1` | 获授权教材结构化会话历史 |
| `12e8842c9` | 共享长代码高度与展开/收起 |
| `fac6a50b7` | 恢复与重试教材归属、授权状态 |
| `7af7b62b8` | 共享 Flash 会话契约与教育适配 |
| `bb04142ac` | 教材确认、作品、气泡与连续问答 UI |
| `02ce53875` | 异步高亮测试稳定性 |

本记录与 Playwright fixtures/spec 作为独立验收提交保存；最终提交号由 git 历史查询。
