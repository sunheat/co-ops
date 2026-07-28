"""Azure OpenAI chat example: deployment name goes in the model field.

The #1 Azure OpenAI gotcha:

    OpenAI:  model = model name ("gpt-4o-mini") -- chosen from a public list
    Azure:   model = *deployment name* -- whatever YOU named the deployment
             when creating it in Azure Portal / AI Foundry ("my-gpt4o", ...)

With Azure's v1 GA API (base URL ending in /openai/v1) the deployment name
is passed via the "model" field, exactly like OpenAI. Our config appends
/openai/v1 to AZURE_OPENAI_ENDPOINT automatically (see ProviderConfig.endpoint).

Usage:
    # In .env (see .env.example):
    #   AZURE_OPENAI_API_KEY=...
    #   AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
    #   AZURE_OPENAI_DEPLOYMENT=<your-deployment-name>
    uv run --env-file .env python -m examples.chat_azure
"""

import os

from packages import llm


def main():
    # For Azure, "model" is the deployment name, NOT the OpenAI model name.
    # Passing model="" makes the router fall back to AZURE_OPENAI_DEPLOYMENT.
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")

    response = llm.chat(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "In one sentence: what is an Azure OpenAI deployment?"},
        ],
        provider="azure",
        model=deployment,
        temperature=0.2,
    )

    print(f"Provider:   {response.provider}")
    print(f"Deployment: {deployment or '(from AZURE_OPENAI_DEPLOYMENT)'}")
    # The response echoes the *underlying* model, which may differ from the
    # deployment name -- e.g. deployment "my-gpt4o" backed by model "gpt-4o".
    print(f"Model:      {response.model}")
    print(f"Answer:     {response.content}")
    print(
        f"Tokens:     {response.total_tokens} "
        f"(prompt {response.prompt_tokens}, completion {response.completion_tokens})"
    )
    if response.latency_ms is not None:
        print(f"Latency:    {response.latency_ms:.0f} ms")


if __name__ == "__main__":
    main()
