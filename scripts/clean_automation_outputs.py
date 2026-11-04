"""Preview or remove generated outputs from a default automation.py run.
Created clean_automation_outputs.py. It previews the default automation-generated outputs without deleting anything:
-----> python scripts/clean_automation_outputs.py
To delete the listed outputs, explicitly run:
-----> python scripts/clean_automation_outputs.py --apply
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_TREES = (
    "data/airflow/government",
    "data/bronze",
    "data/gold",
    "data/metadata",
    "data/mlflow",
    "data/segmentation",
    "data/silver",
    "docs/customer_segmentation/reports",
    "logs",
    "reports",
    "models/anomaly_prediction",
    "models/commercial",
    "models/segmentation",
)

MODEL_ROOT_PATTERNS = ("*.pkl", "*.metadata.json")
MODEL_JOBLIB_DIRECTORIES = (
    "models/anomaly_prediction",
    "models/commercial",
    "models/segmentation",
)


def _is_preserved(path: Path, tree_root: Path) -> bool:
    if path.name == ".gitkeep":
        return True
    return (
        tree_root == PROJECT_ROOT / "logs"
        and path == tree_root / "README.md"
    )


def _plan_tree_cleanup(
    path: Path, tree_root: Path, *, remove_root: bool
) -> tuple[list[Path], bool]:
    """Return minimal paths to remove and whether this path will be removed."""
    if path.is_symlink() or not path.is_dir():
        if path.exists() or path.is_symlink():
            return [path], True
        return [], True

    removals: list[Path] = []
    all_children_removed = True
    for child in path.iterdir():
        if _is_preserved(child, tree_root):
            all_children_removed = False
            continue
        child_removals, child_removed = _plan_tree_cleanup(
            child, tree_root, remove_root=False
        )
        removals.extend(child_removals)
        all_children_removed &= child_removed

    if all_children_removed and (path != tree_root or remove_root):
        return [path], True
    return removals, False


def _repo_path(relative_path: str) -> Path:
    path = PROJECT_ROOT / relative_path
    if not path.is_relative_to(PROJECT_ROOT):
        raise ValueError(f"Cleanup path is outside the project: {relative_path}")
    current = path
    while current != PROJECT_ROOT:
        if current.is_symlink():
            raise RuntimeError(
                f"Refusing to clean through symlink {current.relative_to(PROJECT_ROOT)}"
            )
        current = current.parent
    return path


def _removal_plan() -> list[Path]:
    removals: set[Path] = set()
    for relative_path in OUTPUT_TREES:
        tree_root = _repo_path(relative_path)
        if tree_root == PROJECT_ROOT / "logs":
            remove_root = False
        elif tree_root == PROJECT_ROOT / "docs/customer_segmentation/reports":
            remove_root = False
        else:
            remove_root = True
        tree_removals, _ = _plan_tree_cleanup(
            tree_root, tree_root, remove_root=remove_root
        )
        removals.update(tree_removals)

    for pattern in MODEL_ROOT_PATTERNS:
        removals.update((PROJECT_ROOT / "models").glob(pattern))

    for relative_path in MODEL_JOBLIB_DIRECTORIES:
        model_directory = _repo_path(relative_path)
        if not model_directory.exists():
            continue
        for path in model_directory.rglob("*.joblib"):
            if path.is_symlink() or path.is_file():
                removals.add(path)

    minimal_removals: list[Path] = []
    for path in sorted(removals, key=lambda item: (len(item.parts), item.as_posix())):
        if any(parent in minimal_removals for parent in path.parents):
            continue
        minimal_removals.append(path)
    return minimal_removals


def _remove(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preview generated outputs from the default automation.py paths. "
            "Source datasets and project code are preserved. Environment-variable "
            "output overrides outside these default paths are not followed."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the listed generated outputs (default is preview only).",
    )
    arguments = parser.parse_args(argv)

    removals = _removal_plan()
    if not removals:
        print("No generated automation outputs were found.")
        return 0

    verb = "Deleting" if arguments.apply else "Would delete"
    for path in removals:
        print(f"{verb}: {path.relative_to(PROJECT_ROOT)}")

    if not arguments.apply:
        print("\nPreview only. Re-run with --apply to delete these outputs.")
        return 0

    for path in removals:
        _remove(path)
    print(f"\nRemoved {len(removals)} generated file(s)/folder(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
