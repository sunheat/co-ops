"""Request and validate an LLM investigation plan in a JSON-only format."""

from packages.prompt import ContextBlock, MessageBuilder
from packages.structured_output import (
    investigation_plan_output_instruction,
    parse_investigation_plan,
)


def main() -> None:
    """Build a JSON request and validate representative LLM output."""
    messages = MessageBuilder().build(
        system=(
            "You are an enterprise support assistant. Base conclusions only on "
            "the supplied evidence."
        ),
        task="Investigate the margin mismatch for client ACME-102.",
        context=[
            ContextBlock(
                label="runbook.md",
                content="Delayed trade imports can cause reconciliation failures.",
            ),
            ContextBlock(
                label="incident-102.md",
                content="The mismatch began after the overnight batch job.",
            ),
        ],
        output_instruction=investigation_plan_output_instruction(),
    )

    # In a live call, pass response.content from llm.chat(..., response_format="json")
    # to parse_investigation_plan instead of this representative model output.
    raw_llm_output = """
    {
      "summary": "The mismatch is likely linked to delayed overnight trade imports.",
      "likely_causes": [
        "The overnight batch did not import all trades before reconciliation.",
        "The reconciliation job ran against incomplete position data."
      ],
      "evidence": [
        "runbook.md says delayed trade imports can cause reconciliation failures.",
        "incident-102.md records that the mismatch began after the overnight batch."
      ],
      "next_steps": [
        "Check the overnight batch job status and logs.",
        "Compare imported trade counts with the source system.",
        "Re-run reconciliation after missing trades are imported."
      ],
      "confidence": "medium"
    }
    """

    plan = parse_investigation_plan(raw_llm_output)

    print("Request messages:")
    for message in messages:
        print(f"[{message.role}] {message.content}\n")
    print("Validated investigation plan:")
    print(plan.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
