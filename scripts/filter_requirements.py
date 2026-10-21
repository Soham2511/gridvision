"""Extract selected groups from the single root requirements manifest."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--groups", nargs="+", required=True)
    arguments = parser.parse_args()

    selected: list[str] = []
    active_group: str | None = None
    for raw_line in arguments.source.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("# group:"):
            active_group = line.partition(":")[2].strip()
        elif line and not line.startswith("#") and active_group in arguments.groups:
            selected.append(line)
    if not selected:
        raise ValueError(f"No dependency entries found for groups: {arguments.groups}")
    arguments.destination.write_text("\n".join(selected) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
