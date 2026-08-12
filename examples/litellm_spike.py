"""Make one provider-neutral completion with LiteLLM.

Run from the repository root after setting OPENAI_API_KEY in .env:

    uv run --env-file .env python -m examples.litellm_spike
"""

from litellm import completion


def main() -> None:
    """Request one short completion through LiteLLM's OpenAI-shaped interface."""
    response = completion(
        model="openai/gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": "Explain why a unified LLM interface is useful in one sentence.",
            }
        ],
    )
    print(response.choices[0].message.content)
    print(f"Total tokens: {response.usage.total_tokens}")


if __name__ == "__main__":
    main()
