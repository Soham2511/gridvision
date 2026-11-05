"""Notification and email dispatch service for complaint status lifecycle events."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional
from flask import current_app

from app.ai.email_delivery import send_status_email
from app.domain.complaints.entities import Complaint

logger = logging.getLogger("gridvision.services.complaint_notification")


def dispatch_complaint_status_change(
    complaint: Complaint,
    new_status: str,
    old_status: Optional[str] = None,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """Dispatch persistent in-app notifications and email alert when a complaint status changes.

    Args:
        complaint: The updated complaint aggregate.
        new_status: The new status string (e.g. 'RESOLVED', 'REJECTED', 'REGISTERED').
        old_status: The prior status string if known.
        note: Optional administrative notes detailing the resolution or reason for rejection.

    Returns:
        Summary dict containing notification IDs and email delivery outcome.
    """
    clean_new = str(new_status).strip().upper()
    clean_old = str(old_status).strip().upper() if old_status else "PENDING"
    result: dict[str, Any] = {
        "complaint_id": complaint.id,
        "new_status": clean_new,
        "old_status": clean_old,
        "notification_contexts": [],
        "notification_id": None,
        "email_recipient": None,
        "email_sent": False,
    }

    # -------------------------------------------------------------
    # 1. In-App Persistent Notifications
    # -------------------------------------------------------------
    try:
        store = current_app.extensions.get("ai_application_store")
        if store:
            store.initialize()

            sev_level = complaint.severity_result.severity_level.value if complaint.severity_result else "Normal"
            notif_title = f"Complaint #{complaint.id} Status: {clean_new}"
            note_clause = f" Resolution Note: {note}." if note else ""
            notif_body = (
                f"Your complaint \"{complaint.title}\" has been marked as {clean_new} by Grid Authority.{note_clause} "
                f"Account/Meter: {complaint.meter_id}. Category: {complaint.category_label}. Severity: {sev_level}."
            )
            event_key = f"complaint-status:{complaint.id}:{clean_new.lower()}:{uuid.uuid4().hex[:8]}"

            # Determine recipient contexts based on persona / segment
            seg = complaint.customer_segment.value.upper()
            contexts: list[str] = []
            if seg in ("RESIDENTIAL", "HOUSEHOLD"):
                contexts.append(f"demo:household:entity:{complaint.customer_id}")
                contexts.append(f"demo:household:entity:{complaint.meter_id}")
                contexts.append("demo:household")
            elif seg in ("COMMERCIAL", "COMMERCIAL_BUILDING"):
                contexts.append(f"demo:commercial:entity:{complaint.customer_id}")
                contexts.append(f"demo:commercial:entity:{complaint.meter_id}")
                contexts.append("demo:commercial")
            else:
                contexts.append("demo:government")

            unique_contexts = list(dict.fromkeys(contexts))
            persisted_id = None
            for ctx in unique_contexts:
                try:
                    record = store.notify(
                        recipient_context=ctx,
                        event_key=event_key,
                        notification_type="complaint_status_update",
                        title=notif_title,
                        body=notif_body,
                    )
                    if record and not persisted_id:
                        persisted_id = record.get("notification_id")
                    result["notification_contexts"].append(ctx)
                except Exception as ctx_err:
                    logger.warning("Could not persist notification for context '%s': %s", ctx, ctx_err)

            result["notification_id"] = persisted_id
            logger.info(
                "Persisted complaint status notification for complaint %s to contexts %s",
                complaint.id,
                result["notification_contexts"],
            )
    except Exception as notif_err:
        logger.error("Failed to generate in-app notification for complaint %s: %s", complaint.id, notif_err)

    # -------------------------------------------------------------
    # 2. Email Delivery
    # -------------------------------------------------------------
    try:
        config = current_app.config
        # Resolve recipient email address
        recipient = (
            complaint.category_data.get("email")
            or complaint.category_data.get("contact_email")
            or (complaint.registration_metadata or {}).get("email")
            or str(config.get("REPORT_EMAIL_DEFAULT_RECIPIENT", "")).strip()
            or f"customer-{complaint.customer_id}@gridvision.internal"
        )
        result["email_recipient"] = recipient

        email_subject = f"[GridVision] Complaint #{complaint.id} Status Updated to {clean_new}"
        email_body = f"""Dear GridVision Customer,

This is an automated advisory regarding your electricity service grievance ticket.

Ticket Reference: {complaint.id}
Subject: {complaint.title}
Service Account / Meter: {complaint.meter_id}
Category: {complaint.category_label}
New Status: {clean_new}
Prior Status: {clean_old}
{f"Resolution Note: {note}" if note else ""}

You can view the full engineering assessment, telemetry evidence, and status audit trail directly on your GridVision portal:
Complaint Centre: /app/complaints
Notifications: /app/notifications

Sincerely,
GridVision Customer Grievance & Network Operations
"""

        email_sent = send_status_email(
            config=config,
            recipient=recipient,
            subject=email_subject,
            body=email_body,
        )
        result["email_sent"] = email_sent
        logger.info(
            "Complaint status email dispatch for %s to %s completed (delivered=%s)",
            complaint.id,
            recipient,
            email_sent,
        )
    except Exception as email_err:
        logger.error("Failed to dispatch status email for complaint %s: %s", complaint.id, email_err)

    return result

