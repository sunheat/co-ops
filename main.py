"""Example usage of the universal LLM client."""

import os

from packages.llm import ChatMessage, LLMClient


def main():
    """Demonstrate basic LLM client usage."""
    # Initialize client - configure for your provider
    # OpenAI: base_url="https://api.openai.com/v1"
    # DeepSeek: base_url="https://api.deepseek.com/v1"
    # Ollama: base_url="http://localhost:11434/v1"
    client = LLMClient(
        api_key=os.getenv("OPENAI_API_KEY", "your-api-key-here"),
        base_url="https://api.openai.com/v1",
    )

    # Simple chat completion
    response = client.chat(
        model="gpt-4o-mini",
        messages=[
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="Hello! What can you do?"),
        ],
        temperature=0.7,
    )

    print("Response:")
    print(response.content)
    print(f"\nModel: {response.model}")
    if response.usage:
        print(f"Tokens: {response.usage.total_tokens}")

    # JSON response format
    json_response = client.chat(
        model="gpt-4o-mini",
        messages=[
            ChatMessage(
                role="user",
                content="Return a JSON object with 'name' and 'age' fields.",
            ),
        ],
        response_format="json",
    )

    print("\nJSON Response:")
    print(json_response.content)

    client.close()


if __name__ == "__main__":
    main()
