"""A held-out set's first run is a measurement, not a draft: once committed it is never edited.
Fails if any reports/heldout/<set>/first_run.json was changed by a later commit, if a set has no
STATUS, or if a set's world was edited after its first run was recorded."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def commits(path: Path) -> list[str]:
    out = subprocess.run(["git", "log", "--format=%H", "--", str(path)], cwd=ROOT, capture_output=True, text=True, check=True)  # noqa: S603, S607
    return out.stdout.split()


def is_ancestor(a: str, b: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=ROOT, check=False).returncode == 0  # noqa: S603, S607


def main() -> int:
    problems = []
    for d in sorted((ROOT / "heldout").iterdir()):
        if not d.is_dir():
            continue
        status = (d / "STATUS").read_text().strip() if (d / "STATUS").exists() else ""
        if status not in ("blind", "regression"):
            problems.append(f"{d.name}: STATUS must be 'blind' or 'regression', is {status!r}")
        first = ROOT / "reports" / "heldout" / d.name / "first_run.json"
        if not first.exists():
            print(f"{d.name}: {status}, first run not recorded yet")
            continue
        fr = commits(first)
        if len(fr) > 1:
            problems.append(f"{d.name}: first_run.json was changed after it was recorded ({len(fr)} commits)")
        if fr:
            recorded = fr[-1]
            later = [c for c in commits(d / "world.yaml") if c != recorded and is_ancestor(recorded, c)]
            if later:
                problems.append(f"{d.name}: world.yaml was edited after its first run ({later[0][:8]})")
        print(f"{d.name}: {status}, first run recorded in {fr[-1][:8] if fr else 'working tree (uncommitted)'}")
    for p in problems:
        print("FAIL", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
