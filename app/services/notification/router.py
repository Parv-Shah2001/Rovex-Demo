"""
File: app/services/notification/router.py
Description: FastAPI Router exposing Notification Service API endpoints.
Provides routes to broadcast new notifications, filter historical alerts by category
or robot, and stream raw consolidated log outputs directly from the local log file.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.core.database import MockDatabase, get_nosql_db
from app.core.auth import get_current_user_from_cookie_or_header, RBACChecker
from app.services.notification import service as notification_service

router = APIRouter(prefix="/api/notifications", tags=["Notification Service"])


class NotificationCreatePayload(BaseModel):
    """
    Schema for validating notification trigger inputs.
    """
    robot_id: str = Field(..., description="The robot ID associated with this alert")
    message: str = Field(..., description="The descriptive alert message")
    category: str = Field("GENERAL", description="CRITICAL, GENERAL, ANALYTICS, SUGGESTIONS, or MARKETING")


@router.post("", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def trigger_notification(
    payload: NotificationCreatePayload,
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin", "supervisor", "sub-supervisor"])),
    db: MockDatabase = Depends(get_nosql_db)
):
    """
    Allows admins, supervisors, and sub-supervisors to trigger and broadcast a new manual notification.
    Automated telemetry systems can also post directly to this endpoint.
    """
    alert = notification_service.log_system_notification(
        db=db,
        robot_id=payload.robot_id,
        message=payload.message,
        category=payload.category
    )
    return {"status": "success", "notification": alert}


@router.get("", response_model=List[Dict[str, Any]])
def list_notifications(
    category: Optional[str] = Query(None, description="Filter by category: CRITICAL, GENERAL, etc."),
    robot_id: Optional[str] = Query(None, description="Filter by a specific robot identifier"),
    limit: int = Query(50, ge=1, le=100, description="Retrieve last n records"),
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header),
    db: MockDatabase = Depends(get_nosql_db)
):
    """
    Retrieves historical alerts and system notifications from the NoSQL database.
    Supports filtering by category or robot ID.
    """
    alerts = notification_service.query_notifications(
        db=db,
        category=category,
        robot_id=robot_id,
        limit=limit
    )
    return alerts


@router.get("/logs", response_model=Dict[str, Any])
def stream_system_logs(
    lines: int = Query(100, ge=10, le=500),
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin"]))
):
    """
    Reads and streams the physical 'data_pool_notifications.log' file on disk.
    Restricted to Rovex Admins to ensure platform audit logs remain highly secure.
    """
    log_content = notification_service.get_live_log_stream(lines_count=lines)
    return {
        "status": "success",
        "file_path": notification_service.LOG_FILE_PATH,
        "lines_count": lines,
        "logs": log_content
    }
