"""python -m depmap_sdk account_id   (or: arn, user_id)"""
import runpy

runpy.run_module("depmap_sdk.identity", run_name="__main__")
