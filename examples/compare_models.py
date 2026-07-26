"""Compare answers from multiple models via the ModelRouter.

Usage:
    # Set API keys for the providers you want to compare, e.g.:
    #   OPENAI_API_KEY=sk-...
    #   DEEPSEEK_API_KEY=sk-...
    uv run --env-file .env python -m examples.compare_models
"""

from packages.llm import ChatMessage, LLMError, ModelRouter, UsageTracker

MODELS = [
    "openai/gpt-4o-mini",
    "deepseek/deepseek-chat",
    "local/qwen2.5",
]

QUESTION = "In two sentences, what are the trade-offs of RAG vs fine-tuning?"


def main():
    tracker = UsageTracker()
    messages = [ChatMessage(role="user", content=QUESTION)]

    with ModelRouter() as router:
        for name in MODELS:
            print(f"\n=== {name} ===")
            try:
                response = router.chat(name, messages, temperature=0.7)
            except LLMError as e:
                print(f"[skipped] {e}")
                continue
            print(response.content)
            tracker.record(response.usage)

    print(f"\nTotal: {tracker.calls} calls, {tracker.total.total_tokens} tokens")


if __name__ == "__main__":
    main()
