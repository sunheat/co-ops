# Week 02 Day 05: Prompt Quality Mini-Benchmark

## 目标

本练习用相同的 10 个可核验证据题，比较 `naive`、`structured`、`context_engineered` 三种 prompt 强度。每一题都有合成的、短小的来源文档和可自动检查的预期结论，因此可把格式、引用、已知矛盾答案、token、延迟和成本记录在同一份结果中。

这不是通用知识问答榜单。三种策略取得相同的源材料，避免将“模型本来就知道某事”误判为 prompt 质量；改变的只有指令的明确程度、上下文边界和可审计输出约束。

## 公开 Prompt 资料

三档 prompt 的递进方式参考了以下公开资料，而非直接复制某一个完整 prompt：

| 资料 | 用到的做法 |
| --- | --- |
| [OpenAI Prompt Engineering](https://platform.openai.com/docs/guides/prompt-engineering) | 用消息角色区分系统行为和用户任务；用 Markdown/XML 边界组织 instructions、context 和 task；为 prompt 建立可重复的评估。 |
| [Anthropic Prompting Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct) | 明确、直接的任务要求；结构化标签；从长文档中提取可引用证据；用清晰格式约束输出。 |
| [OpenAI Cookbook: Data Extraction and Transformation](https://cookbook.openai.com/examples/data_extraction_transformation) | JSON 输出、缺失信息不编造、使用 `null` 或明确状态而非猜测的抽取/转换模式。 |

## 三层 Prompt

| 层级 | 保持不变的内容 | 新增的约束 |
| --- | --- | --- |
| `naive` | 问题和原始 notes | 只有“阅读 notes 并回答”，没有角色、来源引用或 JSON 要求。 |
| `structured` | 相同问题和相同证据 | 分析角色、仅使用 notes、严格 `answer` / `evidence` JSON 合同、要求填写来源 ID。 |
| `context_engineered` | 相同问题和相同证据 | 系统角色、开发者级的证据与不猜测政策、每份文档的显式边界、防止把文档内容当指令、缺证据的降级答案、来源 ID 合同。 |

`examples/context_engineering_compare.py` 会把 30 条唯一的展开 prompt 写进 `artifacts/context_engineering_compare/prompts.md`。稳定性重复不会复制该目录；每一次实际发送的请求仍会完整记录在 `requests.jsonl`。因此不需要通过阅读 Python 模板来猜测真实发送内容。

## 10 个题目

| ID | 场景 | 可验证结论 |
| --- | --- | --- |
| 01 | 夜间对账故障 | trade import 在 reconciliation 之后完成。 |
| 02 | 发布门禁 | staging test 尚未完成，不能部署。 |
| 03 | 月度预算 | USD 120 - USD 35 - USD 45 = USD 40。 |
| 04 | API 失败时间线 | database migration 后出现的 schema mismatch。 |
| 05 | 身份文件政策 | national identity card 不符合只接受 passport / driver license 的规则。 |
| 06 | 事故定级 | 87 名无 workaround 的生产用户受影响，属于 P1。 |
| 07 | Feature flag | `ENABLE_NEW_BILLING=false` 禁用了新账单流程。 |
| 08 | 账户锁定 | 第五次失败在 10:05 UTC，30 分钟后为 10:35 UTC。 |
| 09 | 数据保留期 | 2025-02-10 后 30 个日历日是 2025-03-12。 |
| 10 | 运费规则 | USD 60 - USD 15 = USD 45，适用 USD 6.99 标准运费。 |

## 自动评估定义

| 指标 | 定义 |
| --- | --- |
| 格式符合 | 响应必须是一个 JSON object，且恰好有非空字符串 `answer` 与字符串数组 `evidence` 两个字段。不会修复 Markdown code fence 或额外字段。 |
| 引用证据 | `evidence` 必须列出该题所有必要来源，并且不允许虚构 source ID。 |
| 减少幻觉代理指标 | `grounded` 同时要求答案含预期关键结论、必要引用均有效、答案不含该题预置的矛盾结论。预期结论和矛盾结论都按完整字词、数值或日期/时间 token 匹配，并忽略紧邻的否定表达，避免把 `140`、`P10`、`16.99` 或 “not P1” 误判为 `40`、`P1` 或 `6.99`。release-gate 额外验证“当前不能部署”及明确未完成的 staging 状态，或未来 staging 门禁；已完成且通过的 staging 不会被视为 blocker。identity-policy 额外验证明确拒绝及文件不被接受的政策理由。P2 等政策对照不会使正确的 P1 结论失效。事实性输入（如锁定开始时间）不会被配置为矛盾结论。它是固定题集的可复核代理指标，不能证明模型在任意任务中都不会幻觉。 |
| 稳定性 | 同一 case + prompt style 的每一次重复都满足 `grounded` 的比例。需要至少 `--repeats 2`；单次 30 调用不会产生真正的稳定性数据。 |
| token / latency / cost | 直接读取统一 LLM client 的 provider 返回 usage、延迟、成本估计。未知模型价格不会伪造为 USD 0。 |

## 运行

先离线检查 30 条展开 prompt：

```bash
uv run python -m examples.context_engineering_compare --dry-run
```

单次比较会执行 30 次调用，并得到格式、证据、grounded、token、延迟与成本数据：

```bash
uv run --env-file .env python -m examples.context_engineering_compare \
  --provider gemini --model gemini-flash-latest --repeats 1 \
  --max-tokens 512 --request-delay-seconds 6
```

为了得到真实的稳定性指标，每个组合至少执行两次，即 60 次调用：

```bash
uv run --env-file .env python -m examples.context_engineering_compare \
  --provider gemini --model gemini-flash-latest --repeats 2 \
  --max-tokens 512 --request-delay-seconds 6
```

如果 provider/client 没有已知价格表，可以从当前 provider 的定价页查到输入与输出每百万 token 单价后，显式提供它们；脚本只在两个价格同时提供时才估算，避免混用不完整数据：

```bash
uv run --env-file .env python -m examples.context_engineering_compare \
  --provider gemini --model gemini-flash-latest --repeats 2 \
  --max-tokens 512 --request-delay-seconds 6 \
  --input-price-per-million INPUT_USD \
  --output-price-per-million OUTPUT_USD
```

输出文件：

| 文件 | 内容 |
| --- | --- |
| `artifacts/context_engineering_compare/prompts.md` | 所有完整 prompt，适合人工审阅。 |
| `artifacts/context_engineering_compare/requests.jsonl` | 精确的 role/message 请求清单。 |
| `artifacts/context_engineering_compare/results.jsonl` | 每一条调用的原始响应、判定、usage、延迟、成本和错误。 |
| `artifacts/context_engineering_compare/summary.md` | 题目要求的汇总对比表。 |

若只修改了自动评分规则，使用下列命令重评分现有结果而不增加任何 API 调用：

```bash
uv run python -m examples.context_engineering_compare \
  --provider azure --model model-router --repeats 2 \
  --regrade-results artifacts/context_engineering_compare/results.jsonl
```

## 实测对比表

**运行配置**：2026-08-05 UTC，`azure/model-router`，探测请求实际路由到 `gpt-5.5-2026-04-24`；`temperature=0`、`max_tokens=512`、`max_retries=0`。10 个 case、每种 prompt 各重复 2 次，共 60 次调用，全部成功。

| Prompt | 格式符合 | 引用证据 | Grounded / 无已知矛盾 | Grounded 稳定性 | 平均输入 token | 平均输出 token | 平均总 token | 平均延迟 (ms) | 总成本 |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| naive | 0% (0/20) | 0% (0/20) | 0% (0/20) | 0% (0/10) | 80.5 | 72.5 | 152.9 | 2421.8 | n/a |
| structured | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (10/10) | 126.5 | 89.7 | 216.2 | 2434.9 | n/a |
| context_engineered | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (10/10) | 240.5 | 114.2 | 354.8 | 2834.5 | n/a |

Provider 返回的累计 usage 为 8,950 输入 token、5,527 输出 token、14,477 总 token。`model-router` 本身不是固定 SKU，项目的价格表也没有此 Azure 实际路由模型的可靠条目，因此成本记录为 `n/a`，没有把未知成本错误显示为 USD 0。

## 结论

1. `naive` 的 20 条文本答案均包含预期结论，但它从不提供约定的 JSON 或 source ID。因此在“可审计、有证据支持”的任务定义下，它的 grounded 为 0%。这说明仅凭答案表面正确不足以用于下游自动化。
2. 为这个短小、事实完整的闭卷数据集增加明确 JSON 合同和来源 ID 后，`structured` 已达到 100% 的格式、引用、grounded 和重复稳定性。`context_engineered` 没有在正确性上继续提升，不能据此声称“上下文越多越好”。
3. 与 `structured` 相比，`context_engineered` 的平均输入 token 增加约 90%，总 token 增加约 64%，平均延迟增加约 16%。当任务所需证据本来就很小且边界明确时，应优先选择更便宜的 structured prompt；更复杂或来源不可信的任务才更可能值得使用额外的系统政策和上下文隔离。
4. 原始逐条结果、完整 30 条 prompt 和自动生成表都保留在 `artifacts/context_engineering_compare/`；它们被忽略出版本库，避免每次模型运行都制造无关 diff。`summary.md` 是这张表的机器生成版本。
