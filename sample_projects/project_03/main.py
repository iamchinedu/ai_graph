"""HR policy bot: a Strands agent that polishes policy wording."""
import depmap_sdk as depmap
from strands import Agent
from strands.models import BedrockModel

PROJECT_ID = "prj_HR_c04e1a"

SYSTEM_PROMPT = (
    "You are an HR communications editor. Correct grammar and spelling in the policy text and use a warm, plain tone. Return only the revised text."
)


def run_agent(text: str) -> str:
    depmap.init(
        project_id=PROJECT_ID, environment="test", account_id=depmap.get_identity("account_id"),
        databases=[{"platform": "AWS S3", "database": "hr-policies-bucket", "tables": ["handbook/", "benefits/"]}],
        observability_tools="Splunk",
    )

    model_id = depmap.get_model("claude_3_sonnet")  # the account's inference profile
    model = depmap.log_model(BedrockModel(model_id=model_id))  # +1 on the profile edge, last_seen = now
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, callback_handler=None)

    return str(agent(text))


if __name__ == "__main__":
    print(run_agent("employees is entitled to 15 days of vacation, they must submits the request two week before"))
