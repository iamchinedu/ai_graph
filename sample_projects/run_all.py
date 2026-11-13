"""Run every sample project once (needs AWS credentials and Bedrock access), then recompute edge status.

    python -m sample_projects.run_all
"""
import depmap_sdk as depmap
from backend.checks import run_checks
from sample_projects.project_01 import main as p1
from sample_projects.project_02 import main as p2
from sample_projects.project_03 import main as p3
from sample_projects.project_04 import main as p4
from sample_projects.project_05 import main as p5

for module in (p1, p2, p3, p4, p5):
    text = "this are a test sentence with alot of mistake"
    print(f"[{module.PROJECT_ID}]", module.run_agent(text))
    depmap.flush()
print("edge checks:", run_checks())
