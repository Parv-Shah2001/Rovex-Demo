"""
File: app/services/core_platform/router.py
Description: FastAPI Router exposing Core Platform API endpoints for hospital staff.
The router stays intentionally thin: it validates request wiring, enforces RBAC,
and delegates orchestration behavior to the dedicated core_platform service layer.
This keeps the modular monolith aligned with future extraction into a dedicated
mission-orchestration application service.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import RBACChecker, get_current_user_from_cookie_or_header
from app.core.database import MockDatabase, get_db, get_nosql_db
from app.services.core_platform import service as core_platform_service
from app.services.core_platform.schemas import ServiceRequestPayload, TaskCreatePayload, TaskResponse

router = APIRouter(prefix="/api/tasks", tags=["Core Platform Services"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def schedule_transit_task(
    payload: TaskCreatePayload,
    current_user: Dict[str, Any] = Depends(RBACChecker(["supervisor", "sub-supervisor"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Schedules a new stretcher transport assignment for an allowed user.

    Business rules such as task ownership, fleet selection, and side-effect
    notifications are delegated to the service layer.
    """
    return core_platform_service.schedule_transit_task(payload, current_user, db_sql, db_nosql)


@router.get("", response_model=List[TaskResponse])
def list_tasks(
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header),
    db_sql: Session = Depends(get_db)
):
    """
    Lists scheduled, ongoing, and completed tasks visible to the current user.
    """
    return core_platform_service.list_tasks_for_user(current_user, db_sql)


@router.post("/{task_id}/execute", response_model=TaskResponse)
def execute_and_simulate_transit(
    task_id: str,
    current_user: Dict[str, Any] = Depends(RBACChecker(["supervisor", "sub-supervisor"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Executes a queued mission or simulates an in-progress route traversal.
    """
    return core_platform_service.execute_transit_task(task_id, current_user, db_sql, db_nosql)


@router.post("/{task_id}/cancel", response_model=TaskResponse)
def cancel_transit_task(
    task_id: str,
    current_user: Dict[str, Any] = Depends(RBACChecker(["supervisor", "sub-supervisor"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Cancels an active or scheduled transport task and releases any assigned robot.
    """
    return core_platform_service.cancel_transit_task(task_id, current_user, db_sql, db_nosql)


@router.post("/service-request")
def submit_robot_service_request(
    payload: ServiceRequestPayload,
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Files a maintenance/service request for a robot visible to the current user.
    """
    return core_platform_service.submit_robot_service_request(payload, current_user, db_nosql)
