"""Ops forecasting assistant: a Strands agent that fixes grammar in forecast commentary."""
import depmap_sdk as depmap
from strands import Agent
from strands.models import BedrockModel

PROJECT_ID = "prj_OPS_a81f67"

SYSTEM_PROMPT = (
    "You are a copy editor for operations reports. Fix grammar, spelling and punctuation, keep numbers and units unchanged, and return only the corrected text."
)


def run_agent(text: str) -> str:
    depmap.init(
        project_id=PROJECT_ID, environment="prod", account_id=depmap.get_identity("account_id"),
        databases=[
            {"platform": "Databricks", "database": "ops_catalog", "tables": ["forecasts"]},
            {"platform": "Snowflake", "database": "finance_db", "tables": ["invoices"]},
        ],
        observability_tools="Splunk",
    )

    model_id = depmap.get_model("amazon_nova_pro")  # the account's inference profile
    model = depmap.log_model(BedrockModel(model_id=model_id))  # +1 on the profile edge, last_seen = now
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, callback_handler=None)

    return str(agent(text))


if __name__ == "__main__":
    print(run_agent("forecast for next month are lower then expected, mainly because of the delays in shipment's"))
