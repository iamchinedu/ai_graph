"""depmap_sdk: log an AI project's dependencies (models, tables, observability tools) to the dependency map.

    import depmap_sdk as depmap
    depmap.init(project_id="prj_FIN_7f3a2c", environment="prod", account_id=depmap.get_identity("account_id"),
                databases=[{"platform": "Snowflake", "database": "finance_db", "tables": ["invoices"]}],
                observability_tools="HoneyHive")
    model = depmap.log_model(BedrockModel(model_id=depmap.get_model("claude_sonnet_4_6")))
    conn = depmap.log_connection(conn, "Snowflake", "finance_db", "invoices")

The functions above belong to one shared DepMap object. Make your own with `DepMap()` if you need a second.
"""
from depmap_sdk.depmap import DepMap
from depmap_sdk.registry import ModelNotFoundError

_default = DepMap()
init = _default.init
get_identity = _default.get_identity
get_model = _default.get_model
log_model = _default.log_model
log_connection = _default.log_connection

__all__ = ["DepMap", "ModelNotFoundError", "init", "get_identity", "get_model", "log_model", "log_connection"]
