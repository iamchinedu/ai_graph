"""Registry lookups: which inference profile should an account use for a model?"""
import re

from depmap_sdk import store


class ModelNotFoundError(Exception):
    """The model is unknown, or the account has no active inference profile for it."""


def model_key(name):
    """'Claude Sonnet 4.6' and 'claude_sonnet_4_6' both become 'claude_sonnet_4_6'."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def find_profile(account_id, model_name):
    """The account's active inference profile for the model; its own application profile beats the
    shared system-defined one. Raises ModelNotFoundError if there is none."""
    model = next((m for m in store.read("models") if model_key(m["name"]) == model_key(model_name)), None)
    if model is None:
        raise ModelNotFoundError(f"unknown model {model_name!r}")
    profiles = [p for p in store.find("inference_profiles", account_id=account_id, model_id=model["id"])
                if p["status"] == "active"]
    if not profiles:
        raise ModelNotFoundError(f"no active inference profile for {model_name!r} in account {account_id}")
    profiles.sort(key=lambda p: (p["type"] != "application", p["id"]))
    return profiles[0]
