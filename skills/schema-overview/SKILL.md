---
name: schema-overview
description: Every table in the dependency map, its columns, types and meaning. Load this before writing any SQL.
---

# Schema overview

All tables are queryable by name in SQL (DuckDB over `data/<table>.json`).

Conventions
- Timestamps are ISO-8601 UTC strings (VARCHAR), e.g. `2026-11-11T21:14:02Z`. Compare them as strings, or `CAST(x AS TIMESTAMP)`.
- Edge tables hold IDs only. Join to the node tables to get names.
- `environment` is one of `dev`, `test`, `prod`. Every project edge carries one. Filter on it whenever the question names an environment.
- `status` on an edge is `pass`, `fail`, or `pending` (not yet checked). `status_reason` explains a `fail`.
- `count` meanings differ by edge (see each table). Never present a count as more than what it measures.
- Observability edges have no status and never fail.
- Columns are NOT tracked anywhere. Do not answer column-level questions.


## Node tables

### departments

Company departments. The abbreviation is used inside project IDs.

Key: `id`

| column | type |
| --- | --- |
| id | INTEGER |
| name | VARCHAR |
| abbreviation | VARCHAR |

### cloud_accounts

AWS workload accounts. The same account ID can appear once per environment (dev, test, prod).

Key: `aws_account_id, environment`

| column | type |
| --- | --- |
| aws_account_id | VARCHAR |
| environment | VARCHAR |

### models

Canonical foundation models. deprecated=true means projects using it are at risk now; end_of_life_date (YYYY-MM-DD, nullable) is an early warning.

Key: `id`

| column | type |
| --- | --- |
| id | VARCHAR |
| name | VARCHAR |
| provider | VARCHAR |
| deprecated | BOOLEAN |
| end_of_life_date | VARCHAR |

### inference_profiles

How a model is reached. Every profile belongs to one account and points at one model. type is system_defined or application. id is the profile ARN. regions is a JSON list.

Key: `id`

| column | type |
| --- | --- |
| id | VARCHAR |
| account_id | VARCHAR |
| model_id | VARCHAR |
| type | VARCHAR |
| regions | JSON |
| status | VARCHAR |

### data_platforms

Preselected list of data platforms (AWS S3, AWS DynamoDB, Databricks, Snowflake).

Key: `id`

| column | type |
| --- | --- |
| id | INTEGER |
| name | VARCHAR |

### databases

Generic data container: a database, bucket, or catalog, per environment.

Key: `id`

| column | type |
| --- | --- |
| id | INTEGER |
| name | VARCHAR |
| platform_id | INTEGER |
| environment | VARCHAR |

### db_tables

Tables (or object prefixes) inside a database. table_exists=false means the table is gone; every project edge pointing at it then fails. Nothing sets it automatically yet (no sync job).

Key: `id`

| column | type |
| --- | --- |
| id | INTEGER |
| database_id | INTEGER |
| table_name | VARCHAR |
| last_checked_at | VARCHAR |
| table_exists | BOOLEAN |

### observability_tools

Preselected list of observability tools (HoneyHive, Splunk, ...). No status.

Key: `id`

| column | type |
| --- | --- |
| id | INTEGER |
| name | VARCHAR |

### projects

AI projects. Created through the create-project flow; the ID is handed to the developer.

Key: `id`

| column | type |
| --- | --- |
| id | VARCHAR |
| name | VARCHAR |
| department_id | INTEGER |
| description | VARCHAR |
| created_at | VARCHAR |

### project_environments

One row per project and environment: account, installed packages, the package validity flag, and how many times (run_count) and when last (last_init_at) it started.

Key: `project_id, environment`

| column | type |
| --- | --- |
| project_id | VARCHAR |
| environment | VARCHAR |
| account_id | VARCHAR |
| python_version | VARCHAR |
| packages | JSON |
| packages_hash | VARCHAR |
| packages_valid | BOOLEAN |
| packages_reason | VARCHAR |
| packages_checked_at | VARCHAR |
| last_init_at | VARCHAR |
| run_count | INTEGER |

## Edge tables

### project_profile_edges

Project -> inference profile (and through it, the model). count = model calls.

Key: `project_id, profile_id, environment`

| column | type |
| --- | --- |
| project_id | VARCHAR |
| profile_id | VARCHAR |
| environment | VARCHAR |
| count | BIGINT |
| last_seen | VARCHAR |
| status | VARCHAR |
| status_reason | VARCHAR |
| status_checked_at | VARCHAR |

### project_table_edges

Project -> table. Created when the project declares the table at init; count = tracked accesses.

Key: `project_id, table_id, environment`

| column | type |
| --- | --- |
| project_id | VARCHAR |
| table_id | INTEGER |
| environment | VARCHAR |
| count | BIGINT |
| last_seen | VARCHAR |
| status | VARCHAR |
| status_reason | VARCHAR |
| status_checked_at | VARCHAR |

### project_observability_edges

Project -> observability tool. count = number of times the project started with this tool declared. No status: the edge never fails.

Key: `project_id, tool_id, environment`

| column | type |
| --- | --- |
| project_id | VARCHAR |
| tool_id | INTEGER |
| environment | VARCHAR |
| count | BIGINT |
| last_seen | VARCHAR |
