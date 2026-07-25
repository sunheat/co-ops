# LLM Client 设计笔记

## 设计原则

1. **只依赖 HTTP 协议，不依赖官方 SDK。**
   所有主流服务（OpenAI、DeepSeek、Gemini、OpenRouter、Ollama）都提供 OpenAI 兼容端点，
   直接用 `httpx` 调用 `/chat/completions` 即可覆盖全部场景，避免多套 SDK 的依赖冲突。

2. **数据模型用 dataclass，而不是裸 dict。**
   `ChatResponse.content` / `.message` 这类便捷访问器让调用方不必关心
   `choices[0]["message"]["content"]` 的嵌套结构；`raw` 字段保留原始响应用于调试。

3. **配置与客户端分离。**
   `load_settings()` 一次性从环境变量读出所有 provider 的 `ProviderConfig`（汇总为 `LLMSettings`），
   `LLMClient` 只负责"怎么发请求"。两者可独立测试（`load_settings(env=...)` 支持注入 mapping）。

4. **API key 永不进日志。**
   `ProviderConfig.api_key` 声明为 `field(repr=False)`，repr/str 中不会出现密钥，
   整个包内也不打印任何密钥。

5. **异常分类而不是裸抛 HTTPError。**
   - `AuthenticationError`（401）：密钥问题，重试无意义
   - `RateLimitError`（429）：可退避重试
   - `APIError`（其他 4xx/5xx + 网络错误）：携带 `status_code` 和 `body` 便于排查
   - `ConfigError` / `UnknownProviderError`：启动期配置错误，尽早失败

## 关键决策

### 为什么用 `provider/model` 命名？

与 OpenRouter / LiteLLM 的惯例一致（如 `deepseek/deepseek-chat`），
`ModelRouter` 据此惰性创建并复用各 provider 的客户端，调用方无需管理多个 client 实例。

### 为什么 `Usage` 单独放在 `usage.py`？

用量统计后续会承载成本核算（token 单价、按模型聚合），职责会持续膨胀，
提前从 schema 中拆出，避免 `schemas.py` 变成大杂烩。

### 同步 vs 异步

当前只提供同步 `httpx.Client`，学习阶段够用；
后续若接入 Web 服务（`apps/api`），再补 `AsyncLLMClient`（httpx 天然支持）。

## 已知限制

- 不支持流式输出（SSE）
- 不支持工具调用（function calling）schema
- 无重试 / 退避机制
- `ModelRouter` 无成本感知，只是命名路由
