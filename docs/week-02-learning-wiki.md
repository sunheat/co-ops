# Week 2 Learning Wiki

这份 Wiki 是 Week 2 的复盘和验收答案。它把已经完成的 Day 1--6 交付物串起来，并补充 Day 7 重构后的模块边界。已有实验不重复实现，直接引用原始文档和代码。

## 1. Week 2 的模块边界

| 模块 | 责任 | 不负责什么 |
| --- | --- | --- |
| [`packages/llm`](../packages/llm) | HTTP chat completion、provider config、routing、typed errors、retry、usage | 不负责业务 prompt、检索上下文组织或领域 schema |
| [`packages/prompt`](../packages/prompt) | `PromptTemplate`、`ContextBlock`、`MessageBuilder`，构造标准 messages | 不发 HTTP 请求、不选择 provider |
| [`packages/context`](../packages/context) | 组织 System / Retrieved / Memory / Task 四层 context | Week 2 暂时不实现真实 retrieval |
| [`packages/structured_output`](../packages/structured_output) | JSON instruction、`json.loads`、Pydantic 校验、一次 correction retry | 不处理 provider/network retry |
| [`packages/rag`](../packages/rag) | 未来的 RAG 组件；当前只保留旧 context import 的兼容 facade | 不再作为 Week 2 ContextBuilder 的实现位置 |

数据流可以概括为：

```text
ContextBuilder
    -> context payload
PromptTemplate / MessageBuilder
    -> system + user messages
LLM gateway
    -> raw response
structured_output parser
    -> JSON parse + Pydantic validation
```

这样划分的关键是：底层 gateway 可以被 LiteLLM 替换，而 prompt、context 和领域输出契约仍由 application layer 控制。

## 2. 六个验收问题

### 2.1 如何构造标准化 messages？

使用 [`MessageBuilder`](../packages/prompt/__init__.py)。它接收 `system`、`task`、可选的 developer instruction、context blocks 和 output instruction，输出统一的 `ChatMessage` 列表：

1. 第一条是 `system` message；
2. developer instruction 合并进 system，避免依赖不支持的 `developer` role；
3. context、task 和 output instruction 按固定顺序组合成一条 `user` message；
4. 所有内容在发请求前检查不能为空。

可运行示例是 [`examples/prompt_building.py`](../examples/prompt_building.py)，行为契约在 [`tests/test_prompt.py`](../tests/test_prompt.py)。这回答了“标准化”不仅是把字符串放进 list，也包括 role contract、顺序和输入校验。

### 2.2 什么是 Context Engineering？

Context Engineering 是有意识地设计“模型在这次任务中看到什么、以什么结构看到、哪些信息优先”的过程。它不等于把 prompt 写得更长；重点是信息选择、来源标识、层次、顺序、约束和可验证性。

本周采用四层结构：

- **System Context**：身份、全局行为和可信度规则；
- **Retrieved Context**：当前任务检索出的、带 source 的证据；
- **Memory Context**：用户偏好或此前对话中仍然有效的约束；
- **Task Context**：当前要完成的具体问题。

[`ContextBuilder`](../packages/context/__init__.py) 先把四层变成稳定的 JSON-serializable payload，再由 `MessageBuilder` 转成模型 messages。这样以后替换 mock retrieval 时，prompt 组装和模型调用接口不必一起改。示例见 [`examples/context_engineered_prompt.py`](../examples/context_engineered_prompt.py)。

### 2.3 如何用 Pydantic 校验 LLM 输出？

[`InvestigationPlan`](../packages/structured_output/__init__.py) 声明 `summary`、`likely_causes`、`evidence`、`next_steps` 和限定值为 `low | medium | high` 的 `confidence`。

流程是：

```text
InvestigationPlan.model_json_schema()
    -> 写入 output instruction
LLM response.content
    -> json.loads()
    -> InvestigationPlan.model_validate(payload)
    -> typed InvestigationPlan
```

`model_json_schema()` 让请求约束和本地校验使用同一份 schema；`model_validate()` 才是可信边界，不能因为模型返回了“看起来像 JSON”的文本就直接当作业务对象使用。示例见 [`examples/structured_output.py`](../examples/structured_output.py)。

### 2.4 如何处理 JSON 输出失败？

[`request_investigation_plan()`](../packages/structured_output/__init__.py) 只对模型输出层做一次 correction retry：

```text
第一次 LLM output
    -> JSON parse
    -> Pydantic validate
    -> 失败：把原始输出和错误放入 correction prompt
    -> 第二次 LLM output
    -> 再次 parse + validate
    -> 仍失败：向调用方抛出最终错误
```

非法 JSON、非字符串 content、缺字段和非法枚举值都会进入这条路径。网络超时、限流和 provider error 仍由 [`packages/llm`](../packages/llm) 的 transport/reliability 层处理；不能把两种 retry 混成一个无限重试循环。相关测试覆盖了首次成功、非法 JSON、缺字段、错误枚举和第二次仍失败的情况，见 [`tests/test_structured_output.py`](../tests/test_structured_output.py)。

### 2.5 naive prompt 和 context-engineered prompt 有什么区别？

naive prompt 通常只有一条宽泛任务描述；context-engineered prompt 会明确 system policy、带来源的 retrieved evidence、memory 约束、task 和 output contract。后者增加输入设计成本，但更容易审计“答案依据了什么”。

本项目的 Day 5 实验不是凭感觉比较，而是对十个固定 case 使用 typed answer、citation 和 stability rubric。完整结果见 [`docs/week-02-day-05-prompt-quality-benchmark.md`](week-02-day-05-prompt-quality-benchmark.md)：在当前 fixture 中三种 prompt 的可评分质量都达到 100%，所以它不能证明 context engineering 在所有模型和任务上必然提高准确率；它证明了比较流程、格式约束、证据引用和稳定性可以被记录和复核。

该 fixture 中，context-engineered 风格的平均输入 token 为 345.2，高于 naive 的 303.2；平均输出 token 为 151.1，略低于 naive 的 154.3；平均 latency 为 3889.5 ms，接近 naive 的 3932.0 ms。结论应是“结构化 context 带来更明确的可控性，但有输入 token 成本”，而不是简单宣称它总是更快或更准。

### 2.6 LiteLLM 和自写 wrapper 的边界是什么？

已有的 [`docs/litellm-comparison.md`](litellm-comparison.md) 已完成 Day 6 对比；本周的结论是分层，而不是二选一：

| 位置 | 适合保留的责任 |
| --- | --- |
| LiteLLM 或其他底层 adapter | provider protocol translation、更多 provider、streaming、tool-call adapter、fallback/router、集中式 cost governance |
| 本项目 application layer | prompt/context 组织、消息 role policy、Pydantic schema、JSON correction retry、领域工具安全、citation/grounding 和 benchmark rubric |
| 当前自写 `packages.llm` | 学习 OpenAI-compatible HTTP contract、配置、typed errors、有限 retry、usage logging 和本项目所需的薄接口 |

因此，未来如果需要原生 provider API、streaming 或组织级预算，可以把 LiteLLM 放到 `llm.chat()` 后面，保持上层调用契约。LiteLLM 不能替应用决定什么证据可信、输出 schema 是什么，或业务失败后是否应该拒答。

## 3. 运行和验证

从仓库根目录运行：

```bash
uv sync
uv run pytest -q -p no:cacheprovider
uv run python -m examples.prompt_building
uv run python -m examples.context_engineered_prompt
uv run python -m examples.structured_output
```

Day 5 的离线 catalog：

```bash
uv run python -m examples.context_engineering_compare --dry-run --repeats 2 --seed 42
```

LiteLLM spike 需要用户自己提供 API key，并且会产生真实 provider 调用；它不是离线测试的一部分：

```bash
uv run --env-file .env python -m examples.litellm_spike
```

## 4. Week 2 验收映射

| 验收能力 | 实现/证据 | 状态 |
| --- | --- | --- |
| 构造标准化 messages | `packages.prompt.MessageBuilder`、`tests/test_prompt.py` | 已覆盖 |
| 解释 Context Engineering | 本文 2.2、`packages.context.ContextBuilder` | 已覆盖 |
| 用 Pydantic 校验输出 | `packages.structured_output.InvestigationPlan`、`model_validate()` | 已覆盖 |
| 处理 JSON 输出失败 | `request_investigation_plan()` 一次 correction retry、结构化输出测试 | 已覆盖 |
| 比较 naive 与 context-engineered prompt | Day 5 benchmark artifact 和本文 2.5 | 已覆盖 |
| 解释 LiteLLM / 自写 wrapper 边界 | [`docs/litellm-comparison.md`](litellm-comparison.md)、本文 2.6、README | 已覆盖 |

## 5. 当前限制和下一步

- Week 2 的 retrieved context 仍是 mock；真实 retrieval 和 citation validator 放到后续 RAG 阶段。
- 当前自写 gateway 是同步、buffered client，没有完整 streaming 或 tool execution loop。
- benchmark fixture 的三种风格都达到质量上限，后续应使用更有区分度的任务或失败案例，而不是把这组结果泛化成模型结论。
- LiteLLM spike 只验证 SDK 形态和能力边界，不做未经授权的付费 live comparison。
