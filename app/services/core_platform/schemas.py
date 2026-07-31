"""
File: app/services/core_platform/schemas.py
Description: Defines the validation schemas for user interactions in the Rovex Core Platform.
Validates scheduled transit assignments, recurrence controls, coordinate nodes, and service requests.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskCreatePayload(BaseModel):
    """
    Schema for scheduling a new robot transport task.

    Hospital-scoped users submit tasks inside their own organization automatically.
    Rovex admins may optionally provide an organization when dispatching on behalf
    of a specific hospital without pre-selecting a robot.
    """
    robot_id: Optional[str] = Field(None, description="Target robot ID. If omitted, the system auto-assigns an idle robot.")
    organization: Optional[str] = Field(None, description="Optional hospital organization override for Rovex admins.")
    source_node: str = Field(..., description="Starting node in the hospital layout (e.g. 'Reception')")
    target_node: str = Field(..., description="Target node in the hospital layout (e.g. 'ICU')")
    scheduled_time: str = Field("now", description="Time of execution. Enter 'now' for immediate dispatch, or HH:MM for scheduling.")
    is_recurring: bool = Field(False, description="Whether this is a recurring transport assignment")
    recurrence_interval: str = Field("none", description="Recurrence frequency: 'none', 'hourly', or 'daily'")


class TaskResponse(BaseModel):
    """
    Schema representing scheduled/ongoing transit tasks inside the system.
    """
    id: str
    robot_id: Optional[str]
    organization: str
    created_by: str
    status: str  # pending, ongoing, completed, cancelled
    source_node: str
    target_node: str
    path: str  # JSON representation of optimal path list
    scheduled_time: str
    is_recurring: bool
    recurrence_interval: str
    eta_minutes: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ServiceRequestPayload(BaseModel):
    """
    Schema representing user service and support tickets filed for specific robots.
    """
    robot_id: str = Field(..., description="ID of the robot requiring service")
    issue_description: str = Field(..., description="A detailed explanation of the hardware/sensor issue")
