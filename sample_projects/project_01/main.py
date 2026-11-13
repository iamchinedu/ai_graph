"""Vendor-spend assistant: a Strands agent that fixes grammar in vendor notes."""
import depmap_sdk as depmap
from strands import Agent
from strands.models import BedrockModel

PROJECT_ID = "prj_FIN_7f3a2c"

SYSTEM_PROMPT = (
    "You are a proofreader. Rewrite the user's text with all grammar, spelling and punctuation errors fixed. Keep the meaning and tone. Return only the corrected text."
)


def run_agent(text: str) -> str:
    depmap.init(
        project_id=PROJECT_ID, environment="prod", account_id=depmap.get_identity("account_id"),
        databases=[{"platform": "Snowflake", "database": "finance_db", "tables": ["invoices", "vendors"]}],
        observability_tools="HoneyHive",
    )

    model_id = depmap.get_model("claude_sonnet_4_6")  # the account's inference profile
    model = depmap.log_model(BedrockModel(model_id=model_id))  # +1 on the profile edge, last_seen = now
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, callback_handler=None)

    return str(agent(text))


if __name__ == "__main__":
    print(run_agent("me and him goes to the store yesterday, there was alot of peoples"))
