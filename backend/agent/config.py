"""Settings for the agents: read .env, build the model (Gemini or OpenAI).

Put your key in .env (copy .env.example if it is missing). Pick the provider with LLM_PROVIDER:
    LLM_PROVIDER=gemini                  # or openai
    GEMINI_API_KEY=...                   # https://aistudio.google.com/apikey
    GEMINI_MODEL=gemini-3.5-flash-lite        # orchestrator and answer writing
    GEMINI_WRITER_MODEL=gemini-3.5-flash-lite # the query writer (defaults to GEMINI_MODEL)
    OPENAI_API_KEY=sk-...                # https://platform.openai.com/api-keys
    OPENAI_MODEL=gpt-4o-mini
    OPENAI_WRITER_MODEL=gpt-4o-mini
"""
import os
from pathlib import Path

from depmap_sdk.paths import ROOT

PLACEHOLDERS = {"your-openai-api-key-here", "your-gemini-api-key-here"}
LINKS = {"gemini": "https://aistudio.google.com/apikey", "openai": "https://platform.openai.com/api-keys"}


def load_env(path=None):
    """Read KEY=value lines from .env into os.environ. Variables already set in the shell win."""
    f = Path(path or ROOT / ".env")
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def provider():
    load_env()
    return os.environ.get("LLM_PROVIDER", "gemini").strip().lower()


def api_key(name=None):
    load_env()
    name = name or provider()
    var = f"{name.upper()}_API_KEY"
    key = os.environ.get(var, "").strip()
    if not key or key in PLACEHOLDERS:
        raise RuntimeError(f"{var} is not set. Get a key at {LINKS.get(name, '')} and put it in .env.")
    return key


def build_model(writer=False):
    """A Gemini or OpenAI model for a Strands agent."""
    name = provider()
    if name == "gemini":
        from strands.models.gemini import GeminiModel
        default = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        model_id = os.environ.get("GEMINI_WRITER_MODEL", default) if writer else default
        return GeminiModel(client_args={"api_key": api_key("gemini"), "http_options": {"api_version": "v1beta"}},   # tool calls need v1beta
                           model_id=model_id, params={"temperature": 0})
    if name == "openai":
        from strands.models.openai import OpenAIModel
        default = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        model_id = os.environ.get("OPENAI_WRITER_MODEL", default) if writer else default
        params = {"temperature": 0} if model_id.startswith("gpt-4") else {}   # reasoning models reject temperature
        return OpenAIModel(client_args={"api_key": api_key("openai")}, model_id=model_id, params=params)
    raise RuntimeError(f"LLM_PROVIDER must be gemini or openai, got {name!r}")
