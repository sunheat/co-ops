# Week 01 学习小结：构建可观测的 OpenAI-compatible LLM Gateway

> **本周目标**：在 `packages/llm` 中完成一个小型、可审计的 LLM gateway。它用统一接口调用 OpenAI-compatible 的 Chat Completions API，并将 provider 配置、可靠性、错误处理和用量记录从应用代码中抽离出来。

## 本页导航

1. [本周成果与核心结论](#本周成果与核心结论)
2. [系统如何工作](#系统如何工作)
3. [核心学习主题](#核心学习主题)
4. [兼容性实测与 Azure 经验](#兼容性实测与-azure-经验)
5. [可靠性、可观测性与成本](#可靠性可观测性与成本)
6. [踩坑、边界与下一步](#踩坑边界与下一步)
7. [验收自查与延伸阅读](#验收自查与延伸阅读)

---

## 本周成果与核心结论

### 交付物

| 领域 | 交付内容 | 解决的问题 |
| --- | --- | --- |
| 统一调用 | `LLMClient`、模块级 `llm.chat()` | 上层只需按 `provider` 和 `model` 调用，不直接处理 HTTP |
| 路由 | `ModelRouter` | 将 `provider/model` 解析为按 provider 复用的 client |
| 配置 | `ProviderConfig`、`LLMSettings`、`load_settings()` | 将密钥、端点和共享策略从代码移到环境变量 |
| 错误与可靠性 | Typed errors、timeout、retry、backoff | 将可恢复与不可恢复的失败区别处理 |
| 可观测性 | `UsageTracker`、JSONL usage log、成本估算 | 观察 token、延迟、重试和估算成本，而不泄露内容或密钥 |
| 验证 | client、config、reliability、usage、兼容性相关单元测试 | 将关键 URL、重试和日志行为固定为可回归验证的契约 |

### 一句话结论

**“OpenAI-compatible”统一的是请求入口，而不是所有响应语义。** 因此一个可靠的 gateway 不能只会转发请求，还要在配置、响应解析、错误归一化、可靠性策略和日志方面建立明确边界。

### 本周最重要的五点认识

1. LLM 调用首先是 HTTP 调用：网络、限流和超时不是例外，而是需要被设计的正常路径。
2. 同一个 Chat Completions payload 可以发给多个 provider，但 `usage` 与错误响应仍可能不兼容。
3. Azure OpenAI v1 GA 已接近 OpenAI API；主要差异可以放进配置层，而不必污染通用 client。
4. token 与成本记录是工程决策的反馈回路；记录时必须同时保留延迟、重试次数和失败状态。
5. 这个项目的价值在于学习和应用层抽象，不在于复制 LiteLLM 的生产级 provider 覆盖与治理能力。

---

## 系统如何工作

### 调用链

```text
Application / example
        |
        | llm.chat(messages, provider, model)
        v
ModelRouter
        |-- load_settings() reads environment variables
        |-- resolves "provider/model"
        |-- creates and reuses one LLMClient per provider
        v
LLMClient
        |-- POST {base_url}/chat/completions
        |-- timeout, typed errors, retry/backoff
        |-- parses response and usage
        v
UsageLogger / UsageTracker
        |-- JSONL metadata log
        `-- token totals and estimated cost
```

### OpenAI-compatible API 的基本结构

所有目标 provider 共享以下最小 HTTP 契约：

```http
POST {base_url}/chat/completions
Authorization: Bearer <API_KEY>
Content-Type: application/json
```

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Explain RAG."}
  ],
  "temperature": 0.2,
  "max_tokens": 300
}
```

成功响应通常包含 `choices` 和 `usage`。调用方关心的答案通常位于
`choices[0].message.content`，而 `usage` 包含 `prompt_tokens`、
`completion_tokens` 和 `total_tokens`。

```json
{
  "id": "...",
  "model": "gpt-4o-mini",
  "choices": [{"message": {"role": "assistant", "content": "..."}}],
  "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
}
```

通用 client 会把原始响应收敛为 dataclass，并向上层提供更扁平的
`LLMResponse`：文本内容、token、延迟、预估成本和 attempts 可直接读取。

---

## 核心学习主题

### 1. 为什么需要 gateway，而不是在每处直接调用 SDK

后续 RAG、agent、eval 等模块都会调用模型。若每个模块各自处理 endpoint、鉴权、错误、timeout、retry 和成本记录，行为会逐渐不一致，切换 provider 时也会产生重复修改。

本项目将这些横切关注点集中到 `packages/llm`：

- 应用代码依赖统一的 `llm.chat()`，而不是某家 SDK；
- provider 的变化优先通过配置完成；
- 重试、日志和成本记录有单一实现与单元测试；
- 原始响应仍被保留，以便学习和排查真实兼容性差异。

这不是“隐藏一切差异”，而是让应用层获得稳定接口，同时让底层差异可观察、可诊断。

### 2. Provider config 如何管理

配置层与发送请求的 client 分离：`load_settings()` 一次读取环境变量，生成所有 provider 的 `ProviderConfig`，再聚合为 `LLMSettings`。`LLMClient` 不负责读取环境变量，只接收已经解析好的 API key、endpoint 和可靠性参数，因此配置加载和网络调用都可以独立测试。

| 配置类型 | 示例 | 管理原则 |
| --- | --- | --- |
| Provider 密钥 | `OPENAI_API_KEY`、`AZURE_OPENAI_API_KEY` | 只放在 `.env` 或部署环境；不提交、不打印 |
| Provider 地址 | `OPENAI_BASE_URL`、`AZURE_OPENAI_ENDPOINT`、`LOCAL_LLM_BASE_URL` | 优先使用 preset；仅在需要时覆盖 |
| Azure 默认部署 | `AZURE_OPENAI_DEPLOYMENT` | 用于 `azure/` 未显式给出 model 的回退 |
| 共享可靠性策略 | `LLM_TIMEOUT`、`LLM_MAX_RETRIES`、`LLM_RETRY_BASE_DELAY` | 对所有 provider 一致生效，避免分散魔法数字 |
| Usage log | `LLM_USAGE_LOG` | 默认 `logs/usage.jsonl`；留空即可关闭文件日志 |

未满足使用条件的 provider 会被标为未配置；路由器在真正调用前抛出 `ConfigError`，而不是在网络请求后才给出模糊错误。API key 的 dataclass 表示禁用 `repr`，usage log 也只写元数据，不写 key、prompt 或 completion。

### 3. 统一路由与应用层 abstraction

调用方使用 `provider/model` 命名，例如：

```python
response = llm.chat(
    messages=[{"role": "user", "content": "Explain RAG in one paragraph."}],
    provider="openai",
    model="gpt-4o-mini",
    temperature=0.2,
)
```

`ModelRouter` 根据 provider 懒创建 client，并复用已创建的 client。好处是应用层无需管理 HTTP client 生命周期，也能在代码不变的情况下更换 provider。

这层抽象故意保持薄：它约束“本项目需要如何调用模型”，而不是试图定义所有 provider 的所有能力。

### 4. 为什么它不是 LiteLLM 的替代品

| 维度 | 本项目 gateway | LiteLLM 一类生产工具 |
| --- | --- | --- |
| Provider 范围 | OpenAI-compatible endpoint | 大量 provider 与协议转换 |
| 运行范围 | 单进程、仓库内 Python library | SDK / proxy server / 集中式平台能力 |
| 重点 | 学习 HTTP 契约、兼容性和可观测性 | 路由、预算、密钥管理、组织级治理与功能覆盖 |
| 代码取舍 | 小、可审计、为当前项目定制 | 生产功能丰富、集成广泛 |

当项目需要非 OpenAI-compatible provider、组织级预算、多租户密钥管理或成熟代理能力时，正确方向是保持 `llm.chat()` 这个应用层接口，再把 LiteLLM 或类似代理接在接口后面；不应在本项目中逐项重造其能力。

---

## 兼容性实测与 Azure 经验

### “兼容”不等于“完全相同”

本周使用同一份 Chat Completions 请求负载，对 Gemini、OpenRouter 免费层和 Azure OpenAI v1 GA 进行了观察。结论是：**请求侧可以共用，响应侧需要防御性解析。**

| Provider | 请求 schema | `usage` 观察 | 错误响应观察 | 工程启示 |
| --- | --- | --- | --- | --- |
| Azure OpenAI v1 | 与 OpenAI 一致 | 三个基础 token 字段齐全，另有细节与延迟字段 | 最接近 OpenAI 风格 | 适合以配置差异接入 |
| Gemini | 与 OpenAI 一致 | `total_tokens` 可包含 hidden reasoning token | 错误可能是顶层 JSON 数组 | 不可假设 token 等式或错误对象形状 |
| OpenRouter 免费层 | 与 OpenAI 一致 | 额外带 cost、reasoning 等字段 | `code` 可能为数字，未知模型可能返回 400 | 接受超集字段，不能只按状态码推断语义 |

因此 client 的原则是：保留 raw body 供观察，将可用信息归一化为一致的异常和 response 对象，并让缺失 usage 安全地降级为 `None` / 零 token，而不是让调用崩溃。

### Azure OpenAI 的关键差异

Azure v1 GA API 让请求路径和 Bearer 鉴权与 OpenAI 保持一致，但仍有四个必须记住的区别：

1. **`model` 填 deployment name。** OpenAI 中通常填公共模型名；Azure 中应填自己创建的部署名。误把公共模型名当部署名传入，常见结果是 `404 DeploymentNotFound`。
2. **base URL 多出 `/openai/v1`。** 项目允许环境变量仅提供资源地址，再由 `ProviderConfig.endpoint` 幂等地补上后缀。
3. **响应 model 可能是底层模型名。** 它不一定等于请求时的 Azure deployment name；做成本和日志关联时要明确采用哪个标识。
4. **运营约束仍不同。** Azure 的模型可用性与配额受 region 和 deployment 影响，并有内容过滤等额外响应语义。

另一个端点辨析：用于 OpenAI-compatible 调用的是带 `/openai/v1` 的资源端点；Foundry project endpoint 面向 Agents / `azure-ai-projects` 等场景，不应当作 Chat Completions 兼容面。

---

## 可靠性、可观测性与成本

### Timeout 与 retry 为什么重要

LLM 请求可能因慢响应、网络中断、限流或服务端短暂故障而失败。没有 timeout，调用可能无限阻塞；没有有选择的 retry，短暂问题会直接暴露给用户，或无效重试会加剧故障。

本项目的策略如下：

| 情况 | 是否重试 | 原因 |
| --- | --- | --- |
| `401` / `403` 鉴权失败 | 否 | 密钥或权限问题不会靠等待恢复 |
| `429` 限流 | 是 | 优先遵守 provider 的 `Retry-After` |
| timeout / connection error | 是 | 通常属于瞬时网络或服务问题 |
| `408` / `409` / `5xx` | 是 | 请求冲突、服务压力或服务端故障可能短暂恢复 |
| 其他普通 `4xx`、无效 JSON | 否 | 重复相同请求大多不会改变结果 |

默认 timeout 是 60 秒；`LLM_MAX_RETRIES=2` 表示最多共尝试 3 次。存在 `Retry-After` 时使用该等待值（上限 60 秒），否则用 0.5s、1s、2s 的指数退避（单次上限 8 秒）。每个最终成功或失败结果都会记录总延迟与 attempts。

> **重要边界**：timeout 只代表客户端没有及时收到结果，不代表 provider 没有完成该请求。重试可能带来重复生成或重复计费；对有副作用的 API，应采用幂等性策略，而不是直接复用这里的 retry 规则。

### Token、成本和日志如何记录

用量记录由三个部分组成：

1. **每次响应解析**：从 provider 的 `usage` 提取输入、输出和总 token；provider 未提供时允许缺失。
2. **进程内累计**：`UsageTracker` 用于脚本或会话的调用次数与 token 总和。
3. **JSONL 持久日志**：每个成功或最终失败的调用追加一行，适合持续写入，也便于未来导入日志或分析系统。

成功记录示例：

```json
{"provider":"openai","model":"gpt-4o-mini","prompt_tokens":123,"completion_tokens":45,"total_tokens":168,"latency_ms":920.0,"estimated_cost_usd":0.00004545,"status":"success","attempts":1,"error_type":null}
```

成本不使用 `total_tokens × 一个单价` 的简化算法，而是分开计算：

```text
estimated_cost = prompt_tokens × input_rate / 1,000,000
               + completion_tokens × output_rate / 1,000,000
```

价格表是刻意保持很小的手工表：已知 `(provider, model)` 才估算；未知组合返回 `None`。这样避免以不可靠价格制造“看似精确”的成本数字。跨 provider 分析时也不能假设 `total_tokens = prompt_tokens + completion_tokens`，因为 reasoning token 的统计语义可能不同。

---

## 踩坑、边界与下一步

### 本周踩坑清单

| 现象 | 原因 | 应对方式 |
| --- | --- | --- |
| Azure 返回 `DeploymentNotFound` | 将公共模型名当作 deployment name | 在配置中设置并使用 Azure deployment name |
| Azure URL 不正确 | 漏掉 `/openai/v1`，或误用 Foundry project endpoint | 让配置层规范化 endpoint，并以测试保护 URL 行为 |
| Gemini 错误无法按 OpenAI 对象解析 | 错误可能为顶层数组 | 保留 raw body，错误提取逻辑支持多种 JSON 形状 |
| `total_tokens` 不符合加和关系 | 可能计入 hidden reasoning token | 不将该等式作为跨 provider 成本核算前提 |
| 限流后立即重复请求 | 忽略 provider 的退避信号 | 优先使用 `Retry-After`，否则指数退避 |
| 日志泄露或体积失控 | 写入 key、prompt 或 completion | 日志只保留 provider、模型、token、延迟、状态与错误类型 |

### 当前范围与已知限制

- 仅支持同步 client；尚未提供 `AsyncLLMClient`。
- 未实现流式输出（SSE）和 tool calling schema。
- `response_format="json"` 只请求 JSON mode，不会对返回内容做 schema 验证。
- 模型价格表较小且手工维护；上线前需更新价格，或接入 provider 的权威账单数据。
- 路由只按名称解析，不根据成本、健康度或延迟自动选模型。

### 下一步学习建议

1. 增加 streaming，观察各 provider 的结束标记和流式 usage 行为。
2. 在 JSON mode 之上增加 JSON Schema 校验与结构化输出异常。
3. 增加 `AsyncLLMClient`，为未来 API 服务避免阻塞 I/O。
4. 接入更多 provider / 本地模型，并将实测 compatibility matrix 自动化。
5. 在实际生产需求出现时，将 LiteLLM 等代理放在既有抽象之后，而非扩张当前 client 的职责。

---

## 验收自查与延伸阅读

| 验收问题 | 本页对应章节 | 已覆盖 |
| --- | --- | --- |
| OpenAI-compatible API 的基本结构 | [系统如何工作](#系统如何工作) | 是 |
| Azure OpenAI 的差异 | [兼容性实测与 Azure 经验](#兼容性实测与-azure-经验) | 是 |
| provider config 如何管理 | [核心学习主题](#核心学习主题) | 是 |
| timeout / retry 为什么重要 | [可靠性、可观测性与成本](#可靠性可观测性与成本) | 是 |
| token usage 和成本如何记录 | [可靠性、可观测性与成本](#可靠性可观测性与成本) | 是 |
| 为什么不是 LiteLLM 替代品 | [核心学习主题](#核心学习主题) | 是 |

### 相关实现与原始笔记

- [Week 01 交付概览](week-01-llm-gateway.md)
- [LLM Client Design Notes](llm-client-design-notes.md)
- [OpenAI vs Azure OpenAI 调用差异笔记](openai-vs-azure.md)
- [Day 05：Provider 兼容性实测](day-05-provider-compatibility.md)
- [Day 06：Timeout、Retry 与 Usage Logging](day-06-reliability-and-usage.md)
- [Provider 配置模板](../.env.example)
- [模型对比脚本](../examples/compare_models.py)

### 可复现验证命令

```bash
# 配置 .env 中要使用的 provider 后，观察真实兼容性行为
uv run --env-file .env python -m examples.compare_models

# 运行无需真实密钥的单元测试
uv run pytest tests/ -v
```
