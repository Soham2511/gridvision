"""Load the maintained specialist skill documents used by the Groq planner."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ai.commercial.schemas.communication import SpecialistName

_SKILL_FILES: dict[SpecialistName, str] = {
    "peak_prediction": "peak_prediction/skills.md",
    "operations": "operations/skills.md",
    "renewable": "renewable/skills.md",
    "cost_optimization": "cost_optimization/skills.md",
}

_SKILLS_DIRECTORY = Path(__file__).resolve().parents[1] / "skills"


@lru_cache(maxsize=1)
def load_specialist_skills() -> dict[SpecialistName, str]:
    """Read each allow-listed skill file; missing or empty files are errors."""
    skills: dict[SpecialistName, str] = {}
    for specialist, filename in _SKILL_FILES.items():
        path = _SKILLS_DIRECTORY / filename
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(
                f"Commercial skill file {filename!r} could not be read."
            ) from exc
        if not content:
            raise RuntimeError(f"Commercial skill file {filename!r} is empty.")
        skills[specialist] = content
    return skills


def build_skills_prompt() -> str:
    """Render the fixed skill set for intent routing without granting tools."""
    sections = [
        "Available agent skill files (consult these to select the necessary "
        "specialist; selected specialist names map to these exact skills):"
    ]
    for specialist, content in load_specialist_skills().items():
        sections.append(f"\n--- {specialist} ---\n{content}")
    return "\n".join(sections)
