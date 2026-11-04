"""Use cases for querying customer complaints."""

from __future__ import annotations

from typing import List, Optional
from app.domain.complaints.entities import Complaint
from app.infrastructure.repositories.complaint_repository import ComplaintRepository


class GetCustomerComplaintsUseCase:
    """Retrieve all complaints belonging to an authorized customer."""

    def __init__(self, repository: Optional[ComplaintRepository] = None) -> None:
        self.repository = repository or ComplaintRepository()

    def execute(
        self,
        customer_id: str,
        status_filter: Optional[str] = None,
    ) -> List[Complaint]:
        """Fetch customer complaints with optional status filtering."""
        return self.repository.list_by_customer(customer_id=customer_id, status_filter=status_filter)


class GetComplaintDetailUseCase:
    """Retrieve a single complaint ensuring customer ownership enforcement."""

    def __init__(self, repository: Optional[ComplaintRepository] = None) -> None:
        self.repository = repository or ComplaintRepository()

    def execute(
        self,
        complaint_id: str,
        customer_id: str,
    ) -> Complaint:
        """Fetch single complaint and enforce tenant data ownership."""
        complaint = self.repository.get_by_id(complaint_id)
        if not complaint:
            raise KeyError(f"Complaint '{complaint_id}' was not found.")

        # Strict customer ownership boundary
        if complaint.customer_id != customer_id:
            raise PermissionError("Access denied: You do not have authorization to view this complaint.")

        return complaint

