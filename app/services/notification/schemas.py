"""
File: app/services/notification/schemas.py
Description: Request and response schemas for the Rovex Notification domain.
These models keep the notification module self-contained and reduce transport
contract duplication inside the router layer.
"""

from typing import Optional

from pydantic import BaseModel, Field


class NotificationCreatePayload(BaseModel):
    """
    Schema for validating notification trigger inputs.
    """
    robot_id: str = Field(..., description="The robot ID associated with this alert.")
    message: str = Field(..., description="The descriptive alert message.")
    category: str = Field("GENERAL", description="CRITICAL, GENERAL, ANALYTICS, SUGGESTIONS, or MARKETING")
    organization: Optional[str] = Field(
        None,
        description="Optional organization override used when creating fleet-wide alerts without a concrete robot.",
    )
