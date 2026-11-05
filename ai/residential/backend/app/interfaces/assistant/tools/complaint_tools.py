"""Read-only complaint-centre information tools for the residential assistant."""

from __future__ import annotations

import json
from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from app.domain.complaints.categories import get_categories_for_segment


class ComplaintCategoriesInput(BaseModel):
    """The complaint catalogue is scoped to the authenticated residential assistant."""


class GetResidentialComplaintCategoriesTool(BaseTool):
    """Return the active residential categories and their form fields; does not submit complaints."""

    name: str = "get_residential_complaint_categories"
    description: str = (
        "Read the current residential Complaint Centre category catalogue and required form fields. "
        "Use this to guide a customer reporting an issue. This tool is read-only and cannot file, "
        "submit, or track a complaint."
    )
    args_schema: Type[BaseModel] = ComplaintCategoriesInput

    def _run(self) -> str:
        categories = get_categories_for_segment("RESIDENTIAL")
        return json.dumps(
            [category.model_dump(mode="json") for category in categories],
            ensure_ascii=True,
        )