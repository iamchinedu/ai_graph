"""identity.py: who is this code running as in AWS?

    from depmap_sdk.identity import get_identity
    get_identity("account_id")   # "222222222222"
    get_identity("arn")          # "arn:aws:sts::222222222222:assumed-role/..."
    get_identity("user_id")      # the STS user ID

Run it directly:  python -m depmap_sdk.identity account_id
"""
import os
import sys

# What you can ask for, mapped to the key in the STS response.
FIELDS = {"account_id": "Account", "arn": "Arn", "user_id": "UserId"}

# Optional override for running off AWS (laptop, tests): set this and "account_id" returns it.
ACCOUNT_ID_ENV_VAR = "DEPMAP_ACCOUNT_ID"


def get_caller_identity():
    """Ask AWS STS who we are. Returns {"Account": ..., "UserId": ..., "Arn": ...}.
    Needs valid AWS credentials but no IAM permissions. In SageMaker Studio these are
    the execution role's credentials, so the account is the one the notebook runs in."""
    import boto3
    return boto3.client("sts").get_caller_identity()


def get_identity(field="account_id"):
    """Return one value about the current AWS identity: "account_id", "arn" or "user_id"."""
    if field not in FIELDS:
        raise ValueError(f"unknown identity field {field!r}; use one of {sorted(FIELDS)}")
    override = os.environ.get(ACCOUNT_ID_ENV_VAR)
    if field == "account_id" and override:
        return override
    return get_caller_identity()[FIELDS[field]]


if __name__ == "__main__":
    print(get_identity(sys.argv[1] if len(sys.argv) > 1 else "account_id"))
