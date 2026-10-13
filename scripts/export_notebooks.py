"""Export substantive model-review notebook code to compile-checked Python."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

NOTEBOOKS = (
    "04_residential_model_review.ipynb",
    "05_commercial_model_review.ipynb",
    "06_government_model_review.ipynb",
)


def export_notebooks(project_root: Path, overwrite: bool = False) -> list[Path]:
    """Export code cells without changing notebook files or running the code."""
    source_dir = project_root / "notebooks"
    output_dir = project_root / "scripts" / "notebook_exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for notebook_name in NOTEBOOKS:
        notebook_path = source_dir / notebook_name
        if not notebook_path.is_file():
            raise FileNotFoundError(f"Notebook not found: {notebook_path}")
        output_path = output_dir / f"{notebook_path.stem}.py"
        if output_path.exists() and not overwrite:
            raise FileExistsError(
                f"Export already exists: {output_path}. Use --overwrite."
            )
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        lines = [
            "# Generated from the corresponding notebook's code cells.",
            "# Review before execution; notebook cells were not all executed.",
            "# Notebook shell commands are retained as comments, not run.",
            "# ruff: noqa",
            "from __future__ import annotations",
            "",
        ]
        code_cell_count = 0
        for index, cell in enumerate(notebook.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            source = cell.get("source", "")
            cell_source = "".join(source) if isinstance(source, list) else source
            if not cell_source.strip():
                continue
            code_cell_count += 1
            lines.extend((f"# %% Notebook code cell {index}",))
            for line in cell_source.splitlines():
                stripped = line.lstrip()
                if stripped.startswith(("!", "%")):
                    lines.append(f"# Notebook-only command omitted: {stripped}")
                else:
                    lines.append(line)
            lines.append("")
        if not code_cell_count:
            raise ValueError(f"No code cells found in {notebook_path}")
        source_text = "\n".join(lines) + "\n"
        compile(source_text, str(output_path), "exec")
        temporary = output_path.with_suffix(".py.tmp")
        try:
            temporary.write_text(source_text, encoding="utf-8")
            temporary.replace(output_path)
        finally:
            temporary.unlink(missing_ok=True)
        generated.append(output_path)
    return generated


def main() -> None:
    """Run the notebook exporter from the project root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    for path in export_notebooks(args.project_root.resolve(), args.overwrite):
        print(path.relative_to(args.project_root.resolve()))


if __name__ == "__main__":
    main()
