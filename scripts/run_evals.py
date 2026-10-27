"""C2-5: the CI eval gate. It loads evals/runner.py and checks the deterministic gate.

A runner that is missing, or that accepts an empty case, fails the gate."""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    path = ROOT / "evals" / "runner.py"
    if not path.is_file():
        print("evals/runner.py is missing")
        return 1
    runner = runpy.run_path(str(path))
    for name in ("CASES", "THRESHOLDS", "evaluate"):
        if name not in runner:
            print(f"evals/runner.py has no {name}")
            return 1
    calls: list[object] = []
    result = runner["evaluate"]({}, lambda prompt: calls.append(prompt) or True)
    if result.get("passed") is not False or calls:
        print("The deterministic gate accepted an empty case")
        return 1
    print(f"eval gate ok: {len(runner['CASES'])} cases, {len(runner['THRESHOLDS'])} thresholds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
