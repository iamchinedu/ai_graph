"""The orchestrator agent (AWS Strands Agents on Amazon Bedrock).

    agent = create_agent()                     # once per chat (one per browser tab in the app)
    reply = ask(agent, "What breaks if ...?")  # once per user message

The same Agent object is reused for every turn, so its earlier messages, queries and loaded skills stay in its context
and follow-up questions work. Strands keeps the most recent part of a long conversation and drops the oldest.
"""
from strands import Agent
from strands.models import BedrockModel

from agent.config import CLAUDE_MODEL_ID
from agent.prompt import ORCHESTRATOR_PROMPT
from agent.tools import TOOLS


def create_agent():
    """A new orchestrator with an empty conversation. AWS credentials and region come from the normal AWS settings
    (AWS_PROFILE, AWS_REGION or the profile's default region); nothing is called until the first question."""
    model = BedrockModel(model_id=CLAUDE_MODEL_ID, temperature=0)
    return Agent(model=model, system_prompt=ORCHESTRATOR_PROMPT, tools=TOOLS, callback_handler=None)


def ask(agent, prompt):
    """Send one user message to the agent and return its answer as text. Failures come back as a short sentence."""
    try:
        return str(agent(prompt))
    except Exception as exc:  # noqa: BLE001  the person should read a sentence, not a stack trace
        return friendly_error(exc)


def friendly_error(exc):
    text = f"{type(exc).__name__}: {exc}"
    low = text.lower()
    if "nocredentials" in low or "unable to locate credentials" in low:
        return "No AWS credentials found. Sign in (for example `aws sso login --profile <profile>`), set AWS_PROFILE, and try again."
    if "expiredtoken" in low or "token has expired" in low or ("security token" in low and "expired" in low):
        return "Your AWS session has expired. Run `aws sso login --profile <profile>` and try again."
    if "accessdenied" in low or "not authorized" in low:
        return "AWS refused the request. Check that your role may call this Bedrock model and inference profile (agent/config.py)."
    if "throttl" in low or "too many requests" in low:
        return "Bedrock is limiting requests right now. Wait a moment and try again."
    if "validationexception" in low and "model" in low:
        return "Bedrock does not accept the model ID in agent/config.py. Check it with `aws bedrock list-inference-profiles`."
    if "region" in low and ("must be specified" in low or "not provided" in low):
        return "No AWS region is set. Set AWS_REGION (or choose a default region in your AWS profile) and try again."
    return f"Sorry, I couldn't answer that. ({text[:300]})"
