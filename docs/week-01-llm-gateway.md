# Week 01 — LLM Gateway

本周目标：搭建一个通用的 LLM 网关层（`packages/llm`），用统一的接口访问任意 OpenAI 兼容的模型服务。

## 模块结构

| 文件 | 职责 |
| --- | --- |
| `client.py` | `LLMClient`：面向 OpenAI Chat Completions API 的 HTTP 客户端 |
| `config.py` | `ProviderConfig` / `LLMSettings` / `load_settings()`：从环境变量加载各 provider 配置（含 Azure、本地端点） |
| `providers.py` | 常见 provider 预设（OpenAI、OpenRouter、DeepSeek、Gemini、Ollama） |
| `schemas.py` | 请求 / 响应的 dataclass（`ChatMessage`、`ChatChoice`、`ChatResponse`） |
| `usage.py` | `Usage` 统计与 `UsageTracker` 累计 |
| `errors.py` | 统一异常体系（`LLMError` 及其子类） |
| `router.py` | `ModelRouter`：按 `provider/model` 命名路由到对应客户端 |

## 快速开始

```bash
# 1. 复制环境变量模板并填入密钥
cp .env.example .env

# 2. 运行测试
uv run pytest tests/ -v

# 3. 运行示例（-m 保证仓库根目录在 sys.path，--env-file 加载 .env）
uv run --env-file .env python -m examples.chat_basic
uv run --env-file .env python -m examples.compare_models
```

## 本周产出

- [x] 通用 `LLMClient`（httpx，支持任意 OpenAI 兼容端点）
- [x] 统一错误处理（401 / 429 / 4xx-5xx 分类）
- [x] Provider 预设与环境变量配置解析（OpenAI / Azure / Gemini / OpenRouter / DeepSeek / 本地端点）
- [x] API key 不进 repr / 日志（dataclass `repr=False`）
- [x] `provider/model` 格式的简单路由
- [x] 单元测试（client + config）

## 下一步

- 流式输出（SSE）支持
- 重试与退避策略
- 按模型的成本核算（结合 `usage.py`）
