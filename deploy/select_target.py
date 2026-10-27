"""C2-4, D-6, D-8: choose where a merge to the release branch deploys. Run: python deploy/select_target.py.

It reads `deploy/environment.json`. A declared UAT environment is the target. With none, the target is the local
compose path of this folder. The tool that deploys to a cloud UAT is an open decision (OD-2). This script does not
choose one. It names the target, prints a warning for a UAT it cannot reach, and never prints a credential."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def select() -> dict:
    plan = json.loads((ROOT / "deploy/environment.json").read_text())
    uat = (plan.get("environment") or {}).get("uat")
    if uat:
        return {"target": "uat", "uat": uat, "deploys": False,
                "reason": "The Precord declares a UAT environment. The deploy tool for it is not chosen (OD-2)."}
    return {"target": "local", "deploys": True, "reason": "No UAT environment is declared. CI checks the compose path of deploy/."}


if __name__ == "__main__":
    chosen = select()
    print(json.dumps(chosen, sort_keys=True))
    if not chosen["deploys"]:
        print(f"::warning::{chosen['reason']}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"target={chosen['target']}\n")
    sys.exit(0)
