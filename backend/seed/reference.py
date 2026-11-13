"""Example reference data. Model IDs and ARNs here are ILLUSTRATIVE, not live Bedrock values."""

DEPARTMENTS = [
    {"id": 1, "name": "Finance", "abbreviation": "FIN"},
    {"id": 2, "name": "Procurement", "abbreviation": "PRC"},
    {"id": 3, "name": "Human Resources", "abbreviation": "HR"},
    {"id": 4, "name": "Engineering", "abbreviation": "ENG"},
    {"id": 5, "name": "Operations", "abbreviation": "OPS"},
]

# Three AWS account IDs, each registered under all three environments (9 records).
ACCT_A, ACCT_B, ACCT_C = "111111111111", "222222222222", "333333333333"
CLOUD_ACCOUNTS = [
    {"aws_account_id": acct, "environment": env}
    for env in ("dev", "test", "prod")
    for acct in (ACCT_A, ACCT_B, ACCT_C)
]

SONNET, CLAUDE3, NOVA = (
    "anthropic.claude-sonnet-4-6-v1:0",
    "anthropic.claude-3-sonnet-20240229-v1:0",
    "amazon.nova-pro-v1:0",
)
MODELS = [
    {"id": SONNET, "name": "Claude Sonnet 4.6", "provider": "anthropic", "deprecated": False, "end_of_life_date": None},
    {"id": CLAUDE3, "name": "Claude 3 Sonnet", "provider": "anthropic", "deprecated": True, "end_of_life_date": "2026-12-01"},
    {"id": NOVA, "name": "Amazon Nova Pro", "provider": "amazon", "deprecated": False, "end_of_life_date": None},
]


def arn(account, name):
    return f"arn:aws:bedrock:us-east-1:{account}:application-inference-profile/{name}"


SYSTEM_SONNET = "us.anthropic.claude-sonnet-4-6-v1:0"


def system_arn(account, short_id):
    return f"arn:aws:bedrock:us-east-1:{account}:inference-profile/{short_id}"


def _profile(pid, account, model, ptype, regions):
    return {"id": pid, "account_id": account, "model_id": model, "type": ptype,
            "regions": regions, "status": "active"}


# Every profile belongs to one account and one model. A system-defined profile exists in each account.
INFERENCE_PROFILES = [
    *[_profile(system_arn(a, SYSTEM_SONNET), a, SONNET, "system_defined", ["us-east-1", "us-east-2", "us-west-2"])
      for a in (ACCT_A, ACCT_B, ACCT_C)],
    _profile(arn(ACCT_B, "finance-sonnet"), ACCT_B, SONNET, "application", ["us-east-1"]),
    _profile(arn(ACCT_A, "finance-sonnet"), ACCT_A, SONNET, "application", ["us-east-1"]),
    _profile(arn(ACCT_A, "procurement-nova"), ACCT_A, NOVA, "application", ["us-east-1", "us-west-2"]),
    _profile(arn(ACCT_C, "hr-claude3"), ACCT_C, CLAUDE3, "application", ["us-east-1"]),
    _profile(arn(ACCT_B, "ops-nova"), ACCT_B, NOVA, "application", ["us-east-1"]),
]

DATA_PLATFORMS = [
    {"id": 1, "name": "AWS S3"},
    {"id": 2, "name": "AWS DynamoDB"},
    {"id": 3, "name": "Databricks"},
    {"id": 4, "name": "Snowflake"},
]

DATABASES = [
    {"id": 1, "name": "finance_db", "platform_id": 4, "environment": "prod"},
    {"id": 2, "name": "finance_db", "platform_id": 4, "environment": "dev"},
    {"id": 3, "name": "procurement_catalog", "platform_id": 3, "environment": "dev"},
    {"id": 4, "name": "hr-policies-bucket", "platform_id": 1, "environment": "test"},
    {"id": 5, "name": "helpdesk-tickets", "platform_id": 2, "environment": "test"},
    {"id": 6, "name": "ops_catalog", "platform_id": 3, "environment": "prod"},
]

_TABLES = [
    (1, "invoices"), (1, "vendors"), (2, "invoices"), (2, "vendors"),
    (3, "purchase_orders"), (4, "handbook/"), (4, "benefits/"),
    (5, "tickets"), (6, "forecasts"),
]
DB_TABLES = [
    {"id": i + 1, "database_id": db, "table_name": t, "last_checked_at": None, "table_exists": True}
    for i, (db, t) in enumerate(_TABLES)
]

OBSERVABILITY_TOOLS = [
    {"id": 1, "name": "HoneyHive"},
    {"id": 2, "name": "Splunk"},
    {"id": 3, "name": "Datadog"},
]

# Sample projects (IDs are fixed so the sample_projects/ folders can hardcode them).
PROJECTS = [
    {"id": "prj_FIN_7f3a2c", "name": "Vendor-spend assistant", "department_id": 1,
     "description": "Summarizes vendor spend from invoices and vendors."},
    {"id": "prj_PRC_9b1d44", "name": "Procurement agent", "department_id": 2,
     "description": "Tracks purchase orders against invoices."},
    {"id": "prj_HR_c04e1a", "name": "HR policy bot", "department_id": 3,
     "description": "Answers questions from the employee handbook and benefits docs."},
    {"id": "prj_ENG_52d9be", "name": "IT helpdesk assistant", "department_id": 4,
     "description": "Triages helpdesk tickets."},
    {"id": "prj_OPS_a81f67", "name": "Ops forecasting assistant", "department_id": 5,
     "description": "Explains demand forecasts and checks them against invoices."},
]
