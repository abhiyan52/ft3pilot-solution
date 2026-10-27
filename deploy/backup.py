"""C1-6: back up the case database and remove old backups, as runtime.yaml.data_management declares.

Run from the Solution folder: python deploy/backup.py <backup-directory>. It needs pg_dump and DATABASE_URL.
It reads `src/solution/data_management.json`. A retention value that it cannot read is an error. It does not guess."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def retention_days(value: object) -> int | None:
    """Read a number of days from 30, "30", "30d" or "30 days". Any other text is not understood."""
    match = re.fullmatch(r"\s*(\d+)\s*(d|day|days)?\s*", str(value))
    return int(match.group(1)) if match else None


def main(argv: list[str]) -> int:
    plan = json.loads((ROOT / "src/solution/data_management.json").read_text())
    if not plan.get("declared"):
        print("runtime.yaml declares no data management. Nothing was backed up.")
        return 2
    target = Path(argv[0]) if argv else ROOT / "backups"
    url = os.environ.get("DATABASE_URL", "")
    if not url or shutil.which("pg_dump") is None:
        print("Set DATABASE_URL and install pg_dump to back up the database.")
        return 2
    days = retention_days(plan["retention"]) if plan.get("retention") not in (None, "") else None
    if plan.get("retention") not in (None, "") and days is None:
        print(f"The retention value {plan['retention']!r} is not a number of days. Fix runtime.yaml.")
        return 2
    target.mkdir(parents=True, exist_ok=True)
    name = target / f"solution-{time.strftime('%Y%m%dT%H%M%S')}.sql"
    subprocess.run(["pg_dump", "--file", str(name), url], check=True)
    if days is not None:
        for old in target.glob("solution-*.sql"):
            if time.time() - old.stat().st_mtime > days * 86400:
                old.unlink()
    print(f"Backup written to {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
