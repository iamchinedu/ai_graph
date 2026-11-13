---
name: relationships
description: How every table joins to every other, and the direction of each dependency. Load when writing joins or reasoning about what depends on what.
---

# Relationships

Direction = "depends on". `project -> profile -> model` means the project depends on the profile, which depends on the model.
So when a node breaks, everything UPSTREAM of it (the things that depend on it) is affected.

```
project -> cloud account (where it runs, per environment)
project -> packages (valid / invalid, per environment)
project -> inference profile -> model
project -> table -> database -> data platform
project -> observability tool
project -> project_environment (its account, installed packages, package flag)
project -> department
```

## Join map

| From | To | Join |
| --- | --- | --- |
| project_profile_edges | projects | `project_profile_edges.project_id = projects.id` |
| project_profile_edges | inference_profiles | `project_profile_edges.profile_id = inference_profiles.id` |
| inference_profiles | models | `inference_profiles.model_id = models.id` |
| inference_profiles | cloud_accounts | `inference_profiles.account_id = cloud_accounts.aws_account_id` (every profile has an account) |
| project_table_edges | projects | `project_table_edges.project_id = projects.id` |
| project_table_edges | db_tables | `project_table_edges.table_id = db_tables.id` |
| db_tables | databases | `db_tables.database_id = databases.id` |
| databases | data_platforms | `databases.platform_id = data_platforms.id` |
| project_observability_edges | observability_tools | `project_observability_edges.tool_id = observability_tools.id` |
| project_observability_edges | projects | `project_observability_edges.project_id = projects.id` |
| project_environments | projects | `project_environments.project_id = projects.id` |
| projects | departments | `projects.department_id = departments.id` |

Edges also match `environment`. A project can have different dependencies per environment, and a database with the same name in two environments is two rows in `databases`.

## The three edge families

1. Project -> inference profile (`project_profile_edges`): `count` = model calls made. `fail` when the profile is not active/registered or its model is deprecated.
2. Project -> table (`project_table_edges`): `count` = tracked accesses (0 means declared but not yet accessed through a tracked connection). `fail` when the table no longer exists (`db_tables.table_exists = false`).
3. Project -> observability tool (`project_observability_edges`): `count` = times the project started with the tool declared. No status.

Structural links (profile->model, table->database, database->platform) are plain foreign keys, not edge tables.

## Package flag

`project_environments.packages_valid` is a per-project, per-environment flag from a requirements check of the installed packages
(`false` means some package's requirement is not met by another installed package; `packages_reason` says which). In the graph it appears as a `packages` node per project and environment (green = valid, red = invalid). It is NOT an edge table,
but a project with `packages_valid = false` is at risk.
