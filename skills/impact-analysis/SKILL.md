---
name: impact-analysis
description: What-if analysis and risk reports - what breaks or is affected if a model is deprecated, a profile retired, a table dropped, a data platform left, or an observability tool dropped. Load for decision questions.
---

# Impact analysis

Goal: help a business leader decide. Answer "how many projects, which ones, in which environments, how heavily used, and how sure are we".

## Procedure

1. Identify the thing under change and its type (model, inference profile, table, database, data platform, observability tool).
2. Reply with `{"mode":"impact","node":"<thing>","environment":"<dev|test|prod or empty>"}`. It returns one row per project and environment, the path that links them,
   the current edge status, and usage count. Run once per environment if the user named none.
3. Add context with SQL when useful (department, last_seen, other failing edges). See `node-dependencies` templates.
4. Separate:
   - Already failing now: edge `status = fail` (e.g. a model already deprecated).
   - Would be affected if: edge currently passes but depends on the thing.
5. Report using the structure below.

## What each change means

| Change | Affected projects are those that depend on... |
| --- | --- |
| Model deprecated / retired | any inference profile pointing at that model |
| Inference profile removed | that profile (other profiles of the same model are unaffected) |
| Table dropped | that table |
| Data platform exit (e.g. leave Databricks) | any table in any database on that platform |
| Observability tool dropped (e.g. end HoneyHive contract) | any project that declares the tool |
| Cloud account closed | profiles hosted in that account, and projects running in it |

Also check upcoming risk: models with a non-null `end_of_life_date` are a warning even when `deprecated` is false.
```sql
SELECT m.name, m.end_of_life_date, COUNT(DISTINCT e.project_id) AS projects
FROM models m
JOIN inference_profiles pr ON pr.model_id = m.id
JOIN project_profile_edges e ON e.profile_id = pr.id
WHERE m.end_of_life_date IS NOT NULL
GROUP BY m.name, m.end_of_life_date
```

## Risk report structure

1. Headline: number of distinct projects affected, and of how many total (by environment).
2. Table of affected projects: id, name, department, environment, link path, status now, usage count, last seen.
3. Severity cues from the data only: already failing, heavily used (high count), recently active (recent last_seen), production vs dev.
4. What is not known (always include): column-level impact, dependencies the project never declared, and that table/tool counts are declarations and tracked accesses.
5. Decision-relevant takeaway in two or three sentences. No invented mitigations.

Package validity: a project with `project_environments.packages_valid = false` is at risk independent of the change under discussion. Mention it only when relevant.
