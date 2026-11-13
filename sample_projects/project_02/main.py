"""Procurement agent: a Strands agent that tidies purchase-order descriptions."""
import depmap_sdk as depmap
from strands import Agent
from strands.models import BedrockModel

PROJECT_ID = "prj_PRC_9b1d44"

SYSTEM_PROMPT = (
    "You are an editor for purchase-order descriptions. Fix grammar and spelling, and make each description a single clear, professional sentence. Return only the corrected sentence."
)


def run_agent(text: str) -> str:
    depmap.init(
        project_id=PROJECT_ID, environment="dev", account_id=depmap.get_identity("account_id"),
        databases=[
            {"platform": "Databricks", "database": "procurement_catalog", "tables": ["purchase_orders"]},
            {"platform": "Snowflake", "database": "finance_db", "tables": ["invoices"]},
        ],
        observability_tools="Splunk",
    )

    model_id = depmap.get_model("amazon_nova_pro")  # the account's inference profile
    model = depmap.log_model(BedrockModel(model_id=model_id))  # +1 on the profile edge, last_seen = now
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, callback_handler=None)

    return str(agent(text))


if __name__ == "__main__":
    print(run_agent("ordering 50 laptop for the new hires, deliver by end of the month please"))
