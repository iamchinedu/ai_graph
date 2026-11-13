---
name: node-dependencies
description: Pull one node (project, model, inference profile, table, database, data platform, observability tool) and everything around it, with SQL templates. Load for single-entity questions.
---

# Node and its dependencies

Find the node first (names are not unique across environments). Then use the matching template. Replace `:x` with the value.

## A project: everything it depends on

Models (through profiles):
```sql
SELECT e.environment, pr.id AS profile, pr.type AS profile_type, m.name AS model, m.deprecated, m.end_of_life_date,
       e.count AS calls, e.last_seen, e.status, e.status_reason
FROM project_profile_edges e
JOIN inference_profiles pr ON pr.id = e.profile_id
LEFT JOIN models m ON m.id = pr.model_id
WHERE e.project_id = ':project_id'
ORDER BY e.environment
```

Tables (with database and platform):
```sql
SELECT e.environment, dp.name AS platform, d.name AS database, t.table_name,
       e.count AS accesses, e.last_seen, e.status, e.status_reason
FROM project_table_edges e
JOIN db_tables t ON t.id = e.table_id
JOIN databases d ON d.id = t.database_id
JOIN data_platforms dp ON dp.id = d.platform_id
WHERE e.project_id = ':project_id'
ORDER BY e.environment, platform, database, t.table_name
```

Observability tools and package health:
```sql
SELECT e.environment, o.name AS tool, e.count AS starts, e.last_seen
FROM project_observability_edges e JOIN observability_tools o ON o.id = e.tool_id
WHERE e.project_id = ':project_id'
```
```sql
SELECT environment, account_id, python_version, packages_valid, packages_reason, packages_checked_at
FROM project_environments WHERE project_id = ':project_id'
```

At-risk summary for a project and environment: failing edges / total edges (profile + table edges only; observability edges never fail). Mention the package flag separately.

## Who depends on a model

```sql
SELECT p.id, p.name, dep.name AS department, e.environment, pr.id AS profile, e.count AS calls, e.status
FROM project_profile_edges e
JOIN inference_profiles pr ON pr.id = e.profile_id
JOIN models m ON m.id = pr.model_id
JOIN projects p ON p.id = e.project_id
JOIN departments dep ON dep.id = p.department_id
WHERE m.name = ':model_name'
ORDER BY e.environment, p.name
```

## Who depends on a table / database / platform

```sql
SELECT p.id, p.name, e.environment, dp.name AS platform, d.name AS database, t.table_name, e.count, e.status, e.status_reason
FROM project_table_edges e
JOIN projects p ON p.id = e.project_id
JOIN db_tables t ON t.id = e.table_id
JOIN databases d ON d.id = t.database_id
JOIN data_platforms dp ON dp.id = d.platform_id
WHERE t.table_name = ':table'          -- or d.name = ':database', or dp.name = ':platform'
ORDER BY e.environment, p.name
```

## Who depends on an observability tool

```sql
SELECT p.id, p.name, e.environment, e.count AS starts, e.last_seen
FROM project_observability_edges e
JOIN observability_tools o ON o.id = e.tool_id
JOIN projects p ON p.id = e.project_id
WHERE o.name = ':tool'
ORDER BY e.environment, p.name
```

## How often is a node used, and when last

Project starts (every `init` adds 1 to `run_count`, and `last_init_at` is the latest start):

```sql
SELECT p.name, pe.environment, pe.run_count, pe.last_init_at
FROM project_environments pe JOIN projects p ON p.id = pe.project_id
ORDER BY pe.run_count DESC
```

Any other node: add up the counts on its edges. Example for models (swap in the table edges or tool edges for those):

```sql
SELECT m.name AS model, SUM(e.count) AS uses, MAX(e.last_seen) AS last_used, COUNT(DISTINCT e.project_id) AS projects
FROM project_profile_edges e
JOIN inference_profiles ip ON ip.id = e.profile_id
JOIN models m ON m.id = ip.model_id
GROUP BY m.name ORDER BY uses DESC
```

These totals are all-time. Counts are cumulative with one `last_seen`, so "uses in the past 7 days" cannot be answered yet.

## Graph shortcuts

To list everything a project depends on, use the SQL above (join the edge tables).
For "who depends on a node", reply with `{"mode":"impact","node":"<name>"}`. Names such as `Snowflake`, `HoneyHive`, `Claude 3 Sonnet` and `invoices` are accepted.

Caveat: table and tool counts are not full usage. Table `count` is tracked accesses; tool `count` is process starts.
