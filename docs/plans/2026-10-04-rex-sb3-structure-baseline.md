# REX 3e SB3 首轮结构实测

## 范围与身份

- 仅分析已完成任务，未修改代码、模型配置、生成物，未重复加工。
- 代码版本：7de17dd0b；trace revision带dirty标记，不将其称为完全干净版本。
- 教材：83bd38ff-56b3-42ac-84ce-575015727712。
- 结构任务：018b9a95-701e-4bd2-a5c1-76deb2bea912；attempt 1，succeeded。
- PTC run/trace：17dc073f-87b2-432f-815d-5a7400dee6bf。
- PTC thread：0edafb86-b2fc-41f1-a337-59b96a3b9d43。
- 冻结Skill SHA256：e02b3a9d3017ab2f45415ae57414732035155a07d83ea2306b2f874ff7456c2c；schema版本2.1.0。

## 实际模型参数

计划使用low，但本轮32个LLM span的invocation_params均为：

```json
{
  "model": "deepseek-flash",
  "thinking": {"type": "enabled"},
  "output_config": {"effort": "high"}
}
```

元数据reasoning_effort亦全部high。该证据确认客户端请求参数，不代表服务商内部计算量可被独立验证。本轮必须标记high，不可作为low基线。

链路：education_managed_runs.resolve_managed_education_agent_config不传单次reasoning_effort，读取家长持久化模型偏好；resolve_turn_tuning读取模型profile/账号设置，没有覆盖时由模型默认值补齐。分析时账号当前偏好中未见reasoning_effort，manifest的deepseek-flash默认high。聊天输入框的单次选择不随教材请求传入。当前偏好不等同于任务开始时的历史快照，但请求trace已经独立确认high。

## 时间与用量

所有时间为UTC，2026-10-04；不得与外层或子span重复相加。

| 区间 | 起止 | 秒 |
| --- | --- | ---: |
| 任务受理到成功提交 | 11:34:13.654584–11:40:20.238701 | 366.584 |
| 排队 | 受理–11:34:17.657299 | 4.003 |
| worker开始到graph开始 | 11:34:17.657299–11:34:29.626653 | 11.969 |
| PTC graph | 11:34:29.626653–11:40:20.038656 | 350.412 |
| graph结束到成功提交 | 11:40:20.038656–11:40:20.238701 | 0.200 |

trace preparation_ms：sandbox_preparation 2262.460ms、input_staging 9457.466ms，属于准备区间内部，不能再加到总耗时中。

- LLM调用32次，串行span累计339.907秒，占graph约97.0%；其余约10.505秒包含工具、middleware及轮次衔接。
- 工具38次：Bash 27、Read 7、Write 2、Edit 1、report_progress 1。工具span累计8.052秒，存在并行，不能将其当作独占墙钟再相加。
- 累计input 3,490,472 tokens，output 83,303 tokens，总计3,573,775 tokens；input cache_read 3,376,384 tokens（约96.7%）。这是32轮上下文累计，不是一次读取357万tokens教材，也不能直接按非缓存单价估算费用。
- 31轮记录到first_token_time，首token延迟约0.148–1.062秒；一轮缺失，不补造数据。

最慢模型调用：

| 开始时间 | 秒 | 输出tokens | 可核验的后续动作 |
| --- | ---: | ---: | --- |
| 11:35:37.532842 | 75.892 | 18,542 | Bash核对后附内容的定位 |
| 11:36:53.710004 | 79.656 | 21,534 | report_progress(structure_reading) |
| 11:38:13.452547 | 28.902 | 10,906 | Write约33.8KB结构构建脚本 |
| 11:38:58.305700 | 22.383 | 5,237 | Read知识点构建工具 |
| 11:39:20.867778 | 22.788 | 6,275 | Write约9.1KB知识点切分脚本 |

最慢两轮合计155.547秒，占graph约44.4%，输出合计40,076 tokens。两轮输出以thinking块为主；此处只记录类型/用量和可观察工具动作，不复述模型内部推演。首token很快，因此主要是持续生成而非响应等待。结构代码与切分代码的实际执行均不到1秒；模型判断、代码参数生成与多轮交互是本轮主要成本。

## 来源与结构结果

- 原PDF 33,027,005 bytes；复用图书馆旧解析job-KVIZjMQU4iTd。该解析在2026-09-20完成，不属于本轮计时；本轮没有重跑PDF解析。
- 结构source.total_lines 6305；wc -l计数6304是末尾换行差异，不将其自动判定为截断。
- 扫描584个候选，470个Markdown标题，208个页标记；split_blocks输出2414块、125处figure和91条脚注定义。
- 已入库308个递归结构节点、12个单元、108个知识点，每单元9个；content_file均null，没有生成讲义。
- 首次校验发现level_names仅3级而树深4级，Agent修改后重跑通过；最终持久validation_warnings为空，最后工具报告L1/L2/L3均0，jsonschema通过。
- coverage声明图片内文字缺失及阅读理解答案来源缺口。它们是Agent声明，不能代替独立核查。
- 本trace未见图片文件Read或多模态图片块的工具读取证据，不能宣称125张图都被视觉分析。结构识别使用解析文字、标题和图片描述，与讲义阶段多模态阅读需分别验收。
- 格式校验、单元计数和入库成功不证明全部语义拆分正确。每单元统一9条值得抽样检查是否合理，但仅凭数量一致不能判定错误。本轮尚未独立逐条对照全文，也未验收讲义、批量任务、取消重试或长期负载。

## 业务活动问题

持久79条活动：74条tool事件（37次非report工具的开始/结束），1条Agent语义进度、2条服务进度、2条成功终态。activity_status available，没有本轮明细投影失败证据。

Agent唯一语义事件是11:38:13.411090的“正在阅读教材结构线索”，距graph开始223.784秒，距worker开始235.754秒。此前已经运行扫描、读取单元与标题等工具。因此该标签不应理解为阅读刚开始；“整理章节层级”“切分知识点”等阶段未上报，不能从现有timeline计算它们的准确独立耗时。

本轮仍存在上报迟到/稀疏问题，且工具事件之间两次长间隔对应75.9/79.7秒LLM调用：工具活动不是模型持续生成期间的固定频率心跳。先记录，不在基线过程中修改实现。

## 下一轮

先明确保存deepseek-flash的持久profile reasoning_effort=low，再用下一次真实请求trace确认output_config.effort=low。已完成的high任务不改写为low、不无授权自动重做结构。可先从同一教材选择代表性知识点生成讲义low样本；若要量化结构high/low差异，需要相同来源和冻结身份的独立结构重做，并记录质量/耗时对照。原始上传及“添加并分析”冻结发生在任务受理前的耗时目前没有本轮完整请求证据，不能纳入上述366.584秒。
