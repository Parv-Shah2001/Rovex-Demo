"""
File: app/services/core_platform/router.py
Description: FastAPI Router exposing Core Platform API endpoints for hospital staff.
Enforces Role-Based Access Control (RBAC):
  - admin (Rovex): can perform any action across all organizations (inherits all roles).
  - supervisors: can manage all robots, see staff members, and submit schedules within their org.
  - sub-supervisors: can schedule tasks, view live statuses, and assign corridors within their org.
  - employees: can view tasks and request assistance.
Integrates task storage (SQL OLTP), A* route planning, robot state updates (NoSQL),
and alert streaming.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import (
    RBACChecker,
    ensure_organization_access,
    get_current_user_from_cookie_or_header,
    is_admin,
)
from app.core.database import MockDatabase, TaskSQL, get_db, get_nosql_db
from app.services.core_platform.schemas import ServiceRequestPayload, TaskCreatePayload, TaskResponse
from app.services.notification import service as notification_service
from app.services.robot import service as robot_service
from app.services.robot.astar import hospital_map, plan_astar_path
from app.services.robot.schemas import RobotTelemetryPayload

router = APIRouter(prefix="/api/tasks", tags=["Core Platform Services"])
logger = logging.getLogger("rovex.core_platform_router")


def _get_task_or_404(db_sql: Session, task_id: str) -> TaskSQL:
    """
    Resolves a task record or raises a consistent HTTP 404 response.
    """
    task = db_sql.query(TaskSQL).filter(TaskSQL.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


def _get_eligible_robots(robots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filters robots down to dispatchable candidates and orders them by battery level.
    """
    eligible = [
        robot for robot in robots
        if robot["sanctioned"] and robot["status"] == "idle" and robot["battery"] > 20.0
    ]
    return sorted(eligible, key=lambda robot: robot["battery"], reverse=True)


def _resolve_target_organization(
    payload: TaskCreatePayload,
    current_user: Dict[str, Any],
    target_robot: Optional[Dict[str, Any]],
) -> Optional[str]:
    """
    Resolves which hospital organization should own a task before persistence.

    This keeps task ownership aligned with the actual hospital fleet instead of
    accidentally assigning hospital work to the Rovex admin organization.
    """
    if not is_admin(current_user):
        return current_user["organization"]

    if payload.organization:
        return payload.organization.strip()

    if target_robot:
        return target_robot["organization"]

    return None


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def schedule_transit_task(
    payload: TaskCreatePayload,
    current_user: Dict[str, Any] = Depends(RBACChecker(["supervisor", "sub-supervisor"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Schedules a new stretcher transport assignment from source to destination.

    The task is persisted under the hospital organization that will actually own
    the mission. This prevents cross-cutting admin workflows from leaking Rovex's
    platform organization into hospital task records.
    """
    nodes = hospital_map.get_nodes()
    if payload.source_node not in nodes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Source node '{payload.source_node}' does not exist.")
    if payload.target_node not in nodes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Target node '{payload.target_node}' does not exist.")

    route_details = plan_astar_path(payload.source_node, payload.target_node)
    if not route_details:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No viable path exists between '{payload.source_node}' and '{payload.target_node}'."
        )

    path_nodes = route_details["path"]
    calculated_eta = round(route_details["total_cost"] * 0.5, 1)

    target_robot: Optional[Dict[str, Any]] = None
    target_robot_id = payload.robot_id
    task_organization: Optional[str] = None

    if target_robot_id:
        target_robot = robot_service.get_robot_by_id(db_nosql, target_robot_id)
        if not target_robot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Robot '{target_robot_id}' does not exist.")

        ensure_organization_access(
            current_user,
            target_robot["organization"],
            detail="This robot belongs to another institution.",
        )

        if payload.organization and payload.organization.strip() != target_robot["organization"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The provided organization does not match the selected robot's organization.",
            )
        if not target_robot["sanctioned"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Robot '{target_robot_id}' is un-sanctioned and cannot take on assignments."
            )
        if target_robot["status"] != "idle":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Robot '{target_robot_id}' is currently '{target_robot['status']}' and cannot be assigned to a new mission."
            )

        task_organization = _resolve_target_organization(payload, current_user, target_robot)
    else:
        task_organization = _resolve_target_organization(payload, current_user, None)
        available_robots = (
            robot_service.get_all_robots(db_nosql)
            if is_admin(current_user) and not task_organization
            else robot_service.get_robots_by_organization(db_nosql, task_organization or current_user["organization"])
        )
        if is_admin(current_user) and task_organization and not available_robots:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No robots are registered under organization '{task_organization}'.",
            )
        eligible_robots = _get_eligible_robots(available_robots)

        if eligible_robots:
            target_robot = eligible_robots[0]
            target_robot_id = target_robot["robot_id"]
            task_organization = target_robot["organization"]
            logger.info("Auto-assigned robot '%s' for new task.", target_robot_id)
        else:
            target_robot_id = None
            if not task_organization:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Rovex admins must specify a hospital organization or robot when queuing a task without an immediately available fleet robot.",
                )
            logger.info("No idle robots available. Task will remain in 'pending' status for organization '%s'.", task_organization)

    if not task_organization:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not resolve which hospital organization should own this task.",
        )

    task_id = f"task-{uuid.uuid4().hex[:6]}"
    db_task = TaskSQL(
        id=task_id,
        robot_id=target_robot_id,
        organization=task_organization,
        created_by=current_user["username"],
        status="ongoing" if target_robot_id else "pending",
        source_node=payload.source_node,
        target_node=payload.target_node,
        path=json.dumps(path_nodes),
        scheduled_time=payload.scheduled_time,
        is_recurring=payload.is_recurring,
        recurrence_interval=payload.recurrence_interval,
        eta_minutes=calculated_eta
    )

    db_sql.add(db_task)
    db_sql.commit()
    db_sql.refresh(db_task)

    if target_robot_id:
        start_coord = nodes[payload.source_node]
        robot_service.update_robot_status_and_location(
            db=db_nosql,
            robot_id=target_robot_id,
            status="transit",
            location=payload.source_node,
            x_m=start_coord["x"],
            y_m=start_coord["y"],
            assigned_task_id=task_id
        )

        notification_service.log_system_notification(
            db=db_nosql,
            robot_id=target_robot_id,
            message=f"Dispatched to execute task '{task_id}': traveling {payload.source_node} -> {payload.target_node}.",
            category="GENERAL"
        )
    else:
        notification_service.log_system_notification(
            db=db_nosql,
            robot_id="FLEET",
            message=f"Task '{task_id}' queued in PENDING status for {task_organization}. No idle robots available in network.",
            category="SUGGESTIONS"
        )

    return db_task


@router.get("", response_model=List[TaskResponse])
def list_tasks(
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header),
    db_sql: Session = Depends(get_db)
):
    """
    Lists scheduled, ongoing, and completed tasks visible to the current user.
    - Rovex admins see ALL tasks across every organization.
    - Hospital staff see only tasks within their own organization.
    """
    query = db_sql.query(TaskSQL).order_by(TaskSQL.created_at.desc())
    if is_admin(current_user):
        return query.all()
    return query.filter(TaskSQL.organization == current_user["organization"]).all()


@router.post("/{task_id}/execute", response_model=TaskResponse)
def execute_and_simulate_transit(
    task_id: str,
    current_user: Dict[str, Any] = Depends(RBACChecker(["supervisor", "sub-supervisor"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Triggers execution for pending tasks or simulates step-by-step traversal 
    for ongoing tasks. Automatically generates transit alerts (departure, intermediate nodes, 
    and goal completion) and modifies live coordinates in the NoSQL database.
    Admins can also execute tasks via the RBAC hierarchy.
    """
    task = _get_task_or_404(db_sql, task_id)
    ensure_organization_access(current_user, task.organization, detail="Access denied.")

    # If pending, try to assign an idle robot
    if task.status == "pending" and not task.robot_id:
        available_robots = robot_service.get_robots_by_organization(db_nosql, task.organization)
        eligible = _get_eligible_robots(available_robots)
        if not eligible:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot execute task yet. All fleet robots are currently active, charging, unavailable, or below the safe battery threshold."
            )
        task.robot_id = eligible[0]["robot_id"]
        task.status = "ongoing"
        db_sql.commit()
        db_sql.refresh(task)

    if task.status == "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This task is already completed.")
        
    robot_id = task.robot_id
    path_nodes = json.loads(task.path)
    nodes_layout = hospital_map.get_nodes()
    
    # Start simulating path nodes
    notification_service.log_system_notification(
        db=db_nosql,
        robot_id=robot_id,
        message=f"Starting route traversal for mission {task.id}. Node sequence: {path_nodes}",
        category="GENERAL"
    )
    
    # Traverse through nodes
    for idx, node_name in enumerate(path_nodes):
        node_pos = nodes_layout[node_name]
        
        # Simulate updating NoSQL status and positions
        robot_service.update_robot_status_and_location(
            db=db_nosql,
            robot_id=robot_id,
            status="transit" if idx < len(path_nodes) - 1 else "idle",
            location=node_name,
            x_m=node_pos["x"],
            y_m=node_pos["y"],
            assigned_task_id=task.id if idx < len(path_nodes) - 1 else None
        )
        
        # Simulate sending concurrent telemetry logs
        synthetic_telemetry = {
            "robot_id": robot_id,
            "timestamp": datetime.utcnow(),
            "mission_id": task.id if idx < len(path_nodes) - 1 else None,
            "motion": {
                "speed_mps": 0.45 if idx < len(path_nodes) - 1 else 0.0,
                "steering_angle_rad": 0.05,
                "distance_traveled_m": 12.5 * (idx + 1)
            },
            "battery": {
                "percentage": max(100.0 - (idx * 1.5), 20.0),
                "remaining_capacity_mah": int(28000 * (max(100.0 - (idx * 1.5), 20.0) / 100.0))
            },
            "localization": {
                "x_m": node_pos["x"],
                "y_m": node_pos["y"],
                "heading_rad": 1.2
            },
            "safety": {
                "perception_enabled": True,
                "speed_reduced": False,
                "obstacle_stop": False,
                "emergency_stop": False
            },
            "system_health": {
                "cameras_online": 3,
                "lidar_online": True,
                "controller_connected": True
            }
        }
        
        telemetry_validated = RobotTelemetryPayload(**synthetic_telemetry)
        robot_service.ingest_robot_telemetry(db_nosql, telemetry_validated)
        
        # Trigger notifications
        if idx == 0:
            notification_service.log_system_notification(
                db=db_nosql,
                robot_id=robot_id,
                message=f"Robot departed from {node_name}.",
                category="GENERAL"
            )
        elif idx == len(path_nodes) - 1:
            notification_service.log_system_notification(
                db=db_nosql,
                robot_id=robot_id,
                message=f"Mission complete! Stretcher successfully delivered to {node_name}.",
                category="GENERAL"
            )
        else:
            notification_service.log_system_notification(
                db=db_nosql,
                robot_id=robot_id,
                message=f"In-transit: crossed corridor midpoint at {node_name}.",
                category="ANALYTICS"
            )
            
    # Mark task as completed in SQL
    task.status = "completed"
    task.eta_minutes = 0.0
    db_sql.commit()
    db_sql.refresh(task)
    
    return task


@router.post("/{task_id}/cancel", response_model=TaskResponse)
def cancel_transit_task(
    task_id: str,
    current_user: Dict[str, Any] = Depends(RBACChecker(["supervisor", "sub-supervisor"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Cancels an active or scheduled transit task. Clears assignments and reverts robot states.
    Admins can also cancel tasks via the RBAC hierarchy.
    """
    task = _get_task_or_404(db_sql, task_id)
    ensure_organization_access(current_user, task.organization, detail="Access denied.")

    if task.status in ["completed", "cancelled"]:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot cancel a task that is already '{task.status}'.")
         
    robot_id = task.robot_id
    task.status = "cancelled"
    db_sql.commit()
    db_sql.refresh(task)
    
    if robot_id:
        # Revert robot status in NoSQL
        robot = robot_service.get_robot_by_id(db_nosql, robot_id)
        if robot:
            robot_service.update_robot_status_and_location(
                db=db_nosql,
                robot_id=robot_id,
                status="idle",
                location=robot["location"],
                x_m=robot["x_m"],
                y_m=robot["y_m"],
                assigned_task_id=None
            )
        # Log notification
        notification_service.log_system_notification(
            db=db_nosql,
            robot_id=robot_id,
            message=f"Mission {task_id} has been CANCELLED by staff dispatcher.",
            category="CRITICAL"
        )
        
    return task


@router.post("/service-request")
def submit_robot_service_request(
    payload: ServiceRequestPayload,
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Enables staff members (including Employees) to file a maintenance service request
    for a faulty robot device. Automatically flags a critical event alert.
    - Rovex admins can file requests for any robot regardless of organization.
    - Hospital staff can only file requests for robots in their own organization.
    """
    robot = robot_service.get_robot_by_id(db_nosql, payload.robot_id)
    if not robot:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot not found.")

    ensure_organization_access(current_user, robot["organization"], detail="Access denied.")

    # Update last problem on robot profile
    db_nosql["robots"].update_one(
        {"robot_id": payload.robot_id},
        {"$set": {"last_problem": payload.issue_description, "status": "error", "assigned_task_id": None}}
    )
    
    # Broadcast critical alert
    notification_service.log_system_notification(
        db=db_nosql,
        robot_id=payload.robot_id,
        message=f"MAINTENANCE REQUIRED! Request filed by '{current_user['username']}'. Reason: {payload.issue_description}",
        category="CRITICAL"
    )
    
    return {
        "status": "success",
        "detail": f"Service ticket successfully logged for robot {payload.robot_id}.",
        "ticket_owner": current_user["username"]
    }
