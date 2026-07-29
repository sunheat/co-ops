# Day 06 — Timeout、Retry 与 Usage Logging

今天给 LLM gateway 补上最小但完整的可靠性与可观测性闭环：

- 每次请求都有 timeout；
- 超时、连接错误、HTTP 408/409/429/5xx 自动 retry；
- 401/403 和其他普通 4xx 立即失败；
- retry 使用 `Retry-After` 或指数退避（0.5s、1s、2s……，最多 8s）；
- 成功和最终失败都会记录端到端 latency 与 attempts；
- 成功请求记录 token usage，并按手写价格表估算成本；
- 日志只记录元数据，不记录 API key、prompt 或 completion 内容。

## 配置

```dotenv
LLM_TIMEOUT=60
LLM_MAX_RETRIES=2
LLM_RETRY_BASE_DELAY=0.5
LLM_USAGE_LOG=logs/usage.jsonl
```

`LLM_MAX_RETRIES=2` 表示最多请求 3 次（首次请求 + 2 次重试）。
将 `LLM_USAGE_LOG` 留空可关闭文件日志。

## 成功日志

每行是一个独立 JSON 对象，便于流式追加和后续导入日志系统：

```json
{"provider":"openai","model":"gpt-4o-mini","prompt_tokens":123,"completion_tokens":45,"total_tokens":168,"latency_ms":920.0,"estimated_cost_usd":0.00004545,"status":"success","attempts":1,"error_type":null}
```

最终失败也会写一条记录，但 token 数为 0、成本为 `null`，并带有
`error_type`。完整示例见
[`examples/usage_log.jsonl`](../examples/usage_log.jsonl)。

## 成本估算边界

`usage.py` 中的 `PRICE_TABLE` 是手写价格表。成本按 input/output token
分别计算，而不是用 `total_tokens` 乘一个统一价格：

```text
cost = prompt_tokens × input_rate / 1,000,000
     + completion_tokens × output_rate / 1,000,000
```

当前只为明确列入价格表的 OpenAI `gpt-4o-mini` 别名估算。未知
provider/model 返回 `None`，避免产生看似精确但错误的费用数字。价格会变化，
上线前应更新价格表或改为读取 provider 的账单数据。

## 错误类型

| 类型 | 是否重试 | 含义 |
| --- | --- | --- |
| `AuthenticationError` | 否 | 401/403，认证失败 |
| `RateLimitError` | 是 | 429，触发限流 |
| `LLMTimeoutError` | 是 | 请求超时 |
| `LLMConnectionError` | 是 | DNS、连接等 transport 错误 |
| `APIError` | 视状态码 | 408/409/5xx 重试，其他 HTTP 错误不重试 |
| `InvalidResponseError` | 否 | 2xx 响应不是合法 JSON |

所有最终抛出的 `LLMError` 都带 `attempts` 与 `latency_ms`，调用方可以直接
记录或展示。

## Retry 的现实边界

请求超时只说明客户端没有及时收到结果，不代表 provider 一定没有完成请求。
因此超时后重试可能产生重复生成或重复计费；当前成本日志只能估算最终收到的
成功响应，无法看到 provider 已处理但客户端未收到的那一次。对有副作用的 API
不应直接复用这套 retry 策略；若 provider 支持 idempotency key，应优先使用。
