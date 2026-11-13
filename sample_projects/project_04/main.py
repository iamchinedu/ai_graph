"""IT helpdesk assistant: a Strands agent that cleans up ticket descriptions."""
import depmap_sdk as depmap
from strands import Agent
from strands.models import BedrockModel

PROJECT_ID = "prj_ENG_52d9be"

SYSTEM_PROMPT = (
    "You clean up IT helpdesk tickets. Fix grammar and spelling, keep technical terms exactly as written, and return only the corrected ticket text."
)


def run_agent(text: str) -> str:
    depmap.init(
        project_id=PROJECT_ID, environment="test", account_id=depmap.get_identity("account_id"),
        databases=[{"platform": "AWS DynamoDB", "database": "helpdesk-tickets", "tables": ["tickets"]}],
        observability_tools="HoneyHive",
    )

    model_id = depmap.get_model("claude_sonnet_4_6")  # the account's inference profile
    model = depmap.log_model(BedrockModel(model_id=model_id))  # +1 on the profile edge, last_seen = now
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, callback_handler=None)

    return str(agent(text))


if __name__ == "__main__":
    print(run_agent("my laptop wont connects to the vpn since the update yesterday and i cant not access nothing"))
