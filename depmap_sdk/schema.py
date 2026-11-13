"""Single source of truth for every table: columns, types, key, and meaning.

Each table lives in data/<table>.json as a JSON array of records.
Timestamps are ISO-8601 UTC strings (VARCHAR) like 2026-11-11T10:00:00Z.
"""

ENVIRONMENTS = ["dev", "test", "prod"]

TABLES = {
    # ---- nodes -------------------------------------------------------
    "departments": {
        "kind": "node",
        "key": ["id"],
        "columns": {"id": "INTEGER", "name": "VARCHAR", "abbreviation": "VARCHAR"},
        "doc": "Company departments. The abbreviation is used inside project IDs.",
    },
    "cloud_accounts": {
        "kind": "node",
        "key": ["aws_account_id", "environment"],
        "columns": {"aws_account_id": "VARCHAR", "environment": "VARCHAR"},
        "doc": "AWS workload accounts. The same account ID can appear once per environment (dev, test, prod).",
    },
    "models": {
        "kind": "node",
        "key": ["id"],
        "columns": {
            "id": "VARCHAR", "name": "VARCHAR", "provider": "VARCHAR",
            "deprecated": "BOOLEAN", "end_of_life_date": "VARCHAR",
        },
        "doc": "Canonical foundation models. deprecated=true means projects using it are at risk now; "
               "end_of_life_date (YYYY-MM-DD, nullable) is an early warning.",
    },
    "inference_profiles": {
        "kind": "node",
        "key": ["id"],
        "columns": {
            "id": "VARCHAR", "account_id": "VARCHAR", "model_id": "VARCHAR",
            "type": "VARCHAR", "regions": "JSON", "status": "VARCHAR",
        },
        "doc": "How a model is reached. Every profile belongs to one account and points at one model. "
               "type is system_defined or application. id is the profile ARN. regions is a JSON list.",
    },
    "data_platforms": {
        "kind": "node",
        "key": ["id"],
        "columns": {"id": "INTEGER", "name": "VARCHAR"},
        "doc": "Preselected list of data platforms (AWS S3, AWS DynamoDB, Databricks, Snowflake).",
    },
    "databases": {
        "kind": "node",
        "key": ["id"],
        "columns": {"id": "INTEGER", "name": "VARCHAR", "platform_id": "INTEGER", "environment": "VARCHAR"},
        "doc": "Generic data container: a database, bucket, or catalog, per environment.",
    },
    "db_tables": {
        "kind": "node",
        "key": ["id"],
        "columns": {
            "id": "INTEGER", "database_id": "INTEGER", "table_name": "VARCHAR",
            "last_checked_at": "VARCHAR", "table_exists": "BOOLEAN",
        },
        "doc": "Tables (or object prefixes) inside a database. table_exists=false means the table is gone; "
               "every project edge pointing at it then fails. Nothing sets it automatically yet (no sync job).",
    },
    "observability_tools": {
        "kind": "node",
        "key": ["id"],
        "columns": {"id": "INTEGER", "name": "VARCHAR"},
        "doc": "Preselected list of observability tools (HoneyHive, Splunk, ...). No status.",
    },
    "projects": {
        "kind": "node",
        "key": ["id"],
        "columns": {
            "id": "VARCHAR", "name": "VARCHAR", "department_id": "INTEGER",
            "description": "VARCHAR", "created_at": "VARCHAR",
        },
        "doc": "AI projects. Created through the create-project flow; the ID is handed to the developer.",
    },
    "project_environments": {
        "kind": "node",
        "key": ["project_id", "environment"],
        "columns": {
            "project_id": "VARCHAR", "environment": "VARCHAR", "account_id": "VARCHAR",
            "python_version": "VARCHAR", "packages": "JSON", "packages_hash": "VARCHAR",
            "packages_valid": "BOOLEAN", "packages_reason": "VARCHAR",
            "packages_checked_at": "VARCHAR", "last_init_at": "VARCHAR", "run_count": "INTEGER",
        },
        "doc": "One row per project and environment: account, installed packages, the package validity flag, and how many times (run_count) and when last (last_init_at) it started.",
    },
    # ---- edges -------------------------------------------------------
    "project_profile_edges": {
        "kind": "edge",
        "key": ["project_id", "profile_id", "environment"],
        "columns": {
            "project_id": "VARCHAR", "profile_id": "VARCHAR", "environment": "VARCHAR",
            "count": "BIGINT", "last_seen": "VARCHAR",
            "status": "VARCHAR", "status_reason": "VARCHAR", "status_checked_at": "VARCHAR",
        },
        "doc": "Project -> inference profile (and through it, the model). count = model calls.",
    },
    "project_table_edges": {
        "kind": "edge",
        "key": ["project_id", "table_id", "environment"],
        "columns": {
            "project_id": "VARCHAR", "table_id": "INTEGER", "environment": "VARCHAR",
            "count": "BIGINT", "last_seen": "VARCHAR",
            "status": "VARCHAR", "status_reason": "VARCHAR", "status_checked_at": "VARCHAR",
        },
        "doc": "Project -> table. Created when the project declares the table at init; count = tracked accesses.",
    },
    "project_observability_edges": {
        "kind": "edge",
        "key": ["project_id", "tool_id", "environment"],
        "columns": {
            "project_id": "VARCHAR", "tool_id": "INTEGER", "environment": "VARCHAR",
            "count": "BIGINT", "last_seen": "VARCHAR",
        },
        "doc": "Project -> observability tool. count = number of times the project started with this tool declared. "
               "No status: the edge never fails.",
    },
}
