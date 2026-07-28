# OpenAI vs Azure OpenAI 调用差异笔记

Week 1 Day 4 学习笔记：让同一个 `LLMClient` 支持 Azure endpoint 时踩到 / 理解的差异点。

## 核心坑：model name vs deployment name

这是 Azure OpenAI 最经典的坑。

| | OpenAI | Azure OpenAI |
| --- | --- | --- |
| `model` 字段填什么 | **模型名**，来自官方模型列表（`gpt-4o-mini`） | **部署名（deployment name）**，是你自己创建部署时起的名字 |
| 谁决定这个名字 | OpenAI | 你（在 Azure Portal / AI Foundry 里建部署时） |
| 典型错误 | 拼错模型名 → 404 model not found | 把 OpenAI 模型名当 `model` 传 → 404 `DeploymentNotFound` |

在 Azure 中，"部署（deployment）"是模型的一个实例化：你选定某个模型 + 版本，
起一个名字（比如 `my-gpt4o`），配上配额（TPM），之后所有调用都通过这个部署名进行。
部署名可以和模型名一样（很多人直接叫 `gpt-4o`），这反而掩盖了两者的区别——
直到某天换了个部署名，代码就 404 了。

另一个细节：**响应里的 `model` 字段回显的是底层模型名**（如 `gpt-4o-2024-08-06`），
不是你请求时传的部署名。两边不对称，做日志/成本统计时要注意用哪一个。

## Endpoint 与 URL 结构

| | OpenAI | Azure（旧版 API） | Azure（v1 GA API，本项目采用） |
| --- | --- | --- | --- |
| Base URL | `https://api.openai.com/v1` | `https://<res>.openai.azure.com` | `https://<res>.openai.azure.com/openai/v1` |
| 请求路径 | `/chat/completions` | `/openai/deployments/<deployment>/chat/completions` | `/chat/completions` |
| `api-version` 查询参数 | 不需要 | **必须**（如 `?api-version=2024-06-01`） | 不需要 |
| deployment 放哪 | 无此概念 | **拼在 URL 路径里** | 放在请求体 `model` 字段 |

旧版 API 下，同一个 OpenAI 兼容 client 根本没法直接复用：URL 结构不同、
还要维护一个不断变化的 `api-version` 日期。v1 GA API 把这些都抹平了——
deployment 回到 `model` 字段，URL 和 OpenAI 完全同构，只是 base URL 多了 `/openai/v1` 前缀。

## 认证方式

| | OpenAI | Azure（旧版） | Azure（v1 GA） |
| --- | --- | --- | --- |
| Header | `Authorization: Bearer <key>` | `api-key: <key>` | `Authorization: Bearer <key>`（也支持 Entra ID token） |

v1 GA 之后认证也统一成标准 Bearer，`LLMClient` 里不需要为 Azure 做任何 header 特判。

## 本项目的适配方式

得益于 v1 GA API，`LLMClient` 完全不感知 Azure，差异全部收敛在配置层：

1. **`ProviderConfig.endpoint`**（`config.py`）：自动把 `AZURE_OPENAI_ENDPOINT`
   拼成 `.../openai/v1`（幂等，已带后缀不重复拼）。用户在 `.env` 里只填资源地址。
2. **`ModelRouter._resolve`**（`router.py`）：model 为空时回退到
   `AZURE_OPENAI_DEPLOYMENT`，所以 `router.chat("azure/", ...)` 也能跑。
3. **httpx 的 base_url 行为**：`httpx.Client(base_url=".../openai/v1")` 会保留
   base URL 中的路径段，`post("/chat/completions")` 最终请求
   `.../openai/v1/chat/completions`，`/openai/v1` 不会被吞掉
   （`test_llm_client.py` 有专门测试）。这点不是所有 HTTP 库都一样，换库前要验证。

## 其他值得记住的差异

- **模型可用性按区域（region）走**：OpenAI 全球一套模型列表；Azure 每个 region
  可部署的模型和版本不同，新模型往往先在少数 region 上线。
- **配额挂在部署上**：Azure 的 TPM/RPM 配额按部署分配，多个部署共享资源配额；
  OpenAI 的 rate limit 挂在账号/组织的 tier 上。
- **模型版本管理**：Azure 部署锁定具体模型版本，可配自动升级策略；
  OpenAI 的别名（如 `gpt-4o`）由官方随时指到新快照。
- **内容过滤**：Azure 默认启用 content filter，可能返回 OpenAI 不会有的
  `content_filter` finish_reason 或 400 错误。
- **数据边界**：Azure 承诺请求数据不用于训练（对所有部署类型都成立），这是企业选 Azure 的主因。
  <small>注：「数据不出所选区域」只对 Standard（区域）部署成立——Global 部署的 prompt/completion
  可能在资源区域之外处理，Data Zone 部署则是限定在一个地理分区（如 EU/US）而非单一 region；
  做合规决策时要按部署类型区分。另按作者实际使用经验，手上订阅的 Global 部署 TPM 配额很低，
  agent 场景基本不够用（官方文档称 Global Standard 默认配额最高，实际额度以自己订阅为准）。</small>

## 验证方式

```bash
# .env 里配好 AZURE_OPENAI_API_KEY / ENDPOINT / DEPLOYMENT 后：
uv run --env-file .env python -m examples.chat_azure

# 不依赖真实密钥的部分（endpoint 拼接、URL 保留、deployment 回退）：
uv run pytest tests/ -v -k "azure or url"
```

## 参考

- [Azure OpenAI API version lifecycle（v1 GA API）](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle)
- [Azure OpenAI deployment 概念](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/create-resource)
