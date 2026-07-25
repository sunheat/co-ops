"""Minimal chat example using the unified llm.chat() interface.

Usage:
    # Configure a provider in .env / environment (see .env.example), e.g.:
    #   LOCAL_LLM_BASE_URL=http://localhost:11434/v1
    #   LLM_PROVIDER=local
    #   LLM_MODEL=qwen2.5
    python examples/chat_basic.py
"""

import os

from packages import llm


def main():
    provider = os.environ.get("LLM_PROVIDER", "openai")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    response = llm.chat(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Explain RAG in one paragraph."},
        ],
        provider=provider,
        model=model,
        temperature=0.2,
    )

    print(f"Provider: {response.provider}")
    print(f"Model:    {response.model}")
    print(f"Answer:   {response.content}")
    print(
        f"Tokens:   {response.total_tokens} "
        f"(prompt {response.prompt_tokens}, completion {response.completion_tokens})"
    )
    if response.latency_ms is not None:
        print(f"Latency:  {response.latency_ms:.0f} ms")


if __name__ == "__main__":
    main()
