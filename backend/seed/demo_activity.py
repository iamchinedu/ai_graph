"""python -m backend.seed.demo_activity  -> log runs for the 5 sample projects (no AWS needed), check edges, build the graph.

Uses the DepMap class directly with the same init/log calls the sample agents make, minus the Bedrock call,
so the data files and the graph have realistic content to look at.
"""
from backend.checks import run_checks
from backend.graph import build_and_save
from depmap_sdk import DepMap

# project_id, environment, account, model, databases, observability tool, runs
RUNS = [
    ("prj_FIN_7f3a2c", "prod", "222222222222", "claude_sonnet_4_6",
     [("Snowflake", "finance_db", ["invoices", "vendors"])], "HoneyHive", 12),
    ("prj_FIN_7f3a2c", "dev", "111111111111", "claude_sonnet_4_6",
     [("Snowflake", "finance_db", ["invoices"])], "HoneyHive", 30),
    ("prj_PRC_9b1d44", "dev", "111111111111", "amazon_nova_pro",
     [("Databricks", "procurement_catalog", ["purchase_orders"]), ("Snowflake", "finance_db", ["invoices"])], "Splunk", 9),
    ("prj_HR_c04e1a", "test", "333333333333", "claude_3_sonnet",
     [("AWS S3", "hr-policies-bucket", ["handbook/", "benefits/"])], "Splunk", 4),
    ("prj_ENG_52d9be", "test", "333333333333", "claude_sonnet_4_6",
     [("AWS DynamoDB", "helpdesk-tickets", ["tickets"])], "HoneyHive", 15),
    ("prj_OPS_a81f67", "prod", "222222222222", "amazon_nova_pro",
     [("Databricks", "ops_catalog", ["forecasts"]), ("Snowflake", "finance_db", ["invoices"])], "Splunk", 7),
]

if __name__ == "__main__":
    for project, env, account, model, dbs, tool, runs in RUNS:
        dm = DepMap()
        for _ in range(runs):
            dm.init(project_id=project, environment=env, account_id=account,
                    databases=[{"platform": p, "database": d, "tables": t} for p, d, t in dbs],
                    observability_tools=tool)
            dm.log_model(dm.get_model(model, account_id=account))
            for p, d, tables in dbs:
                dm.log_connection(None, p, d, tables)
    # one simulated package conflict, so the graph has a red packages node to look at
    from backend.seed.simulate_break import _set
    _set("project_environments", {"project_id": "prj_PRC_9b1d44", "environment": "dev"},
         packages_valid=False, packages_reason="boto3 1.40.0 requires botocore<1.41,>=1.40, but botocore 1.38.2 is installed")
    print("edge checks:", run_checks())
    print("graph:", build_and_save())
