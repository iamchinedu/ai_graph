"""The DepMap class: the one object a project talks to. It only LOGS; it never wraps or runs anything.

    depmap = DepMap()
    depmap.init(project_id="prj_FIN_7f3a2c", environment="prod", account_id=depmap.get_identity("account_id"),
                databases=[{"platform": "Snowflake", "database": "finance_db", "tables": ["invoices"]}],
                observability_tools="HoneyHive")
    model_id = depmap.get_model("claude_sonnet_4_6")
    model = depmap.log_model(BedrockModel(model_id=model_id))                  # any LLM, not just Bedrock
    conn = depmap.log_connection(conn, "Snowflake", "finance_db", "invoices")  # one database, one or more tables

The methods are thin: the work lives in identity.py, registry.py, packages.py and recorder.py (which
writes through store.py). Nothing here raises into the host app, except get_identity / get_model,
which must answer or fail clearly.
"""
import logging
import os
from datetime import datetime, timezone

from depmap_sdk import identity, packages, recorder, registry
from depmap_sdk.schema import ENVIRONMENTS

log = logging.getLogger("depmap")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DepMap:
    def __init__(self):
        self.project_id = None
        self.environment = None

    # ---- lookups (these may raise) -------------------------------------------------------------
    def get_identity(self, field="account_id"):
        """Who we are in AWS: "account_id", "arn" or "user_id"."""
        return identity.get_identity(field)

    def get_model(self, model_name, account_id=None):
        """The inference profile ID/ARN this account should use for the model."""
        account_id = account_id or self.get_identity("account_id")
        return registry.find_profile(account_id, model_name)["id"]

    # ---- logging (these never raise) -----------------------------------------------------------
    def init(self, project_id=None, environment=None, account_id=None, databases=None,
             observability_tools=None, check_packages=True):
        """Register this project in this environment: its account, tables, observability tools, packages."""
        try:
            project_id = project_id or os.environ.get("DEPMAP_PROJECT_ID")
            environment = environment or os.environ.get("DEPMAP_ENVIRONMENT", "dev")
            if not project_id or environment not in ENVIRONMENTS:
                return
            self.project_id, self.environment = project_id, environment
            tools = [observability_tools] if isinstance(observability_tools, str) else (observability_tools or [])
            event = {"type": "project.init", "project_id": project_id, "environment": environment, "ts": _now(),
                     "account_id": account_id, "databases": databases or [], "observability": tools}
            if check_packages:
                event.update(packages=packages.collect(), python_version=packages.python_version(),
                             marker_env=packages.marker_env())
            self._send(event)
        except Exception as exc:  # noqa: BLE001
            log.debug("depmap init failed: %s", exc)

    def log_model(self, model):
        """Log that this LLM was used: +1 on this project's edge to it, last_seen = now. Returns the model."""
        try:
            name = model if isinstance(model, str) else (
                getattr(model, "config", {}).get("model_id") or getattr(model, "model_id", None)
                or getattr(model, "model_name", None) or getattr(model, "model", None) or str(model))
            self._log("model.call", model_id=name)
        except Exception as exc:  # noqa: BLE001
            log.debug("depmap log_model failed: %s", exc)
        return model

    def log_connection(self, connection, platform, database, tables):
        """Log that this connection used these tables (one name or a list) of one database. Returns the connection."""
        for table in ([tables] if isinstance(tables, str) else tables):
            self._log("table.access", platform=platform, database=database, table=table)
        return connection

    # ---- internals -----------------------------------------------------------------------------
    def _log(self, kind, **fields):
        if self.project_id is None:
            return
        try:
            self._send({"type": kind, "project_id": self.project_id, "environment": self.environment,
                        "ts": _now(), "n": 1, **fields})
        except Exception as exc:  # noqa: BLE001
            log.debug("depmap %s failed: %s", kind, exc)

    def _send(self, event):
        """Apply one event to the data. Replace this to send over HTTP later."""
        result = recorder.handle_event(event)
        if not result.get("accepted", True):
            log.debug("depmap event rejected: %s", result.get("warnings"))
