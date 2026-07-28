# Day 05 — 接入低成本 Provider 与 OpenAI 兼容性实测

本篇目标：至少接入一个非 OpenAI 的低成本 provider，并**观察**所谓 "OpenAI-compatible" 到底有多兼容。
重点观察三个维度：**request schema 是否一致**、**response `usage` 字段是否存在**、**error 格式是否一致**。
（流式输出与 tool calling 本次不做。）

本次实际接入并跑通对比的是：**Gemini**、**OpenRouter（免费层）**、**Azure OpenAI（v1 GA）**。
观察脚本：[`examples/compare_models.py`](../examples/compare_models.py)，纯 log 输出，不生成报表。

## 实测环境

| Provider | Base URL（OpenAI 兼容面） | 模型 / 部署 | 备注 |
| --- | --- | --- | --- |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-flash-latest` | 新 key 上 `gemini-2.5-flash(-lite)` 返回 404「no longer available to new users」 |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-oss-20b:free` | 免费模型用 `:free` 后缀；免费层延迟高 |
| Azure OpenAI | `https://<resource>.openai.azure.com/openai/v1` | 部署名 `model-router` | `AZURE_OPENAI_ENDPOINT` 只填主机名，config 自动追加 `/openai/v1` |

运行方式：

```bash
uv run --env-file .env python -m examples.compare_models
```

## 横向对比（以原厂 OpenAI 为基准）

| 维度 | OpenAI 基准 | Azure (v1) | Gemini | OpenRouter (free) |
| --- | --- | --- | --- | --- |
| Request schema | 标准 | ✅ 一致 | ✅ 一致 | ✅ 一致 |
| `usage` 三字段 | 有 | ✅ 有 | ✅ 有 | ✅ 有 |
| `total = prompt + completion` | ✅ | ✅ 正确 | ❌ 含隐藏 thinking token，total 远大于二者之和 | ✅ 正确 |
| `usage` 额外字段 | 少量 | ⚠️ `*_tokens_details`、`latency_checkpoint` | 无 | ⚠️ `cost`、`is_byok`、`*_details` |
| 顶层额外键 | `system_fingerprint` | ⚠️ `prompt_filter_results`、`system_fingerprint` | 无 | ⚠️ `provider`、`service_tier`、`system_fingerprint` |
| error 结构 | `{"error":{message,type,code}}` | ✅ 几乎一致（`code` 为字符串） | ❌ 顶层 **数组** `[{"error":{...}}]` | ⚠️ 对象但 `code` 为**数字**、含 `user_id` |
| 未知模型/部署状态码 | 404 | ✅ 404 `DeploymentNotFound` | 404（数组体） | ⚠️ **400**「not a valid model ID」 |

## 各 Provider 观察详情

### Gemini
- **Request schema**：标准 `/chat/completions` 负载可直接使用，无需改造。
- **`usage`**：三字段齐全，但 `total_tokens` 把隐藏的 **thinking / reasoning tokens** 也算进去，导致
  `total ≠ prompt + completion`（实测出现过 `prompt=19, completion=75, total=933` 的巨大差值）。
- **error 格式**：**不兼容**。返回顶层 **JSON 数组** `[{"error":{code,message,status}}]`，用 `status` 字段与数字 `code`，
  而非 OpenAI 的对象 `{"error":{message,type,code}}`。
- **坑**：新建的 API key 上 `gemini-2.5-flash` / `gemini-2.5-flash-lite` 返回 404「no longer available to new users」；
  应使用 `gemini-flash-latest` 或 `gemini-3.6-flash`。

### OpenRouter（免费层）
- **Request schema**：完全一致。免费模型以 `:free` 结尾（如 `openai/gpt-oss-20b:free`）。
- **`usage`**：是 OpenAI 的**超集**——三字段齐全且 `total = prompt + completion`（正确），
  额外附带 `cost`、`is_byok`、`prompt_tokens_details`、`cost_details`、`completion_tokens_details`（含 `reasoning_tokens`）。
- **顶层响应**：多出 `provider`、`service_tier`、`system_fingerprint`。
- **error 格式**：接近 OpenAI 对象 `{"error":{message,code}}`，但 `code` 是**数字**且含额外 `user_id`；
  未知模型返回 **400**「not a valid model ID」（而非 404）。
- **注意**：免费层延迟偏高（`gpt-oss-20b` 约 1 分钟，且大量 reasoning tokens），适合学习对比，不适合延迟敏感场景。

### Azure OpenAI（v1 GA）
- **Request schema**：完全一致；`Bearer` 认证；**部署名走 `model` 字段**。
- **model-router**：请求 `model=model-router` 时会自动路由，响应 `model` 字段回显实际被路由到的模型（实测 `gpt-5.5-2026-04-24`）。
- **`usage`**：三字段齐全且 `total = prompt + completion`（正确），额外含
  `completion_tokens_details`、`prompt_tokens_details`、`latency_checkpoint`（Azure 特有的延迟遥测）。
- **顶层响应**：多出 `prompt_filter_results`（内容过滤结果）、`system_fingerprint`。
- **error 格式**：三家中**最接近原厂 OpenAI**——`{"error":{type,code,message}}`，`type="invalid_request_error"`、
  `code="DeploymentNotFound"`（字符串 code），未知部署返回 404。
- **端点辨析**：`https://<resource>.services.ai.azure.com/api/projects/<project>` 是 **Foundry 项目端点**（给 Foundry Agents /
  `azure-ai-projects` SDK 用），**不是** OpenAI 兼容面；做兼容性对比要认准 `/openai/v1` 后缀。
  `openai.azure.com` 与 `services.ai.azure.com` 只是同一资源的主机名别名，两者的 `/openai/v1` 都可用。

## 结论与教训

1. **请求侧四家完全一致**——"OpenAI-compatible" 在**发请求**这一层是名副其实的：同一份 payload 可跨 provider 复用。
2. **差异集中在响应侧的两处**：
   - **`usage` 语义/字段**：Gemini 把思考 token 算进 `total`，破坏了 `total = prompt + completion` 的等式；
     OpenRouter / Azure 是加字段的**超集**，等式仍成立。跨 provider 做成本核算时不能盲目相信 `total_tokens` 的语义一致。
   - **error 格式各不相同**：Gemini 是数组、OpenRouter 用数字 `code` 且给 400、Azure 最标准。
     这正是项目里 [`_extract_error_message`](../packages/llm/client.py) 必须做**多格式容错**的原因。
3. **兼容度排序（响应/错误侧）**：`Azure ≈ OpenAI > OpenRouter > Gemini`。
4. **端点选择教训**：Azure 的 Foundry 项目端点不可用于 OpenAI 兼容对比；务必用 `/openai/v1` 那个面。

## 下一步（可选）

- 补接 DeepSeek 与本地 Ollama（脚本已预留，配好 key / base_url 即自动加入对比）。
- 观察流式输出（SSE）下各家 `usage` 与结束标记的差异。
- 基于 `usage.py` 做按模型的成本核算，并处理「`total` 语义不一致」的归一化问题。
