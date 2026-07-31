"""
File: app/services/core_platform/service.py
Description: Business-logic service layer for the Rovex Core Platform domain.
This module keeps hospital task orchestration, fleet assignment, transit execution,
and robot maintenance request logic outside the FastAPI router so the modular
monolith remains ready for future extraction into separate application services.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import ensure_organization_access, is_admin
from app.core.database import MockDatabase, TaskSQL
from app.services.core_platform.schemas import ServiceRequestPayload, TaskCreatePayload
from app.services.notification import service as notification_service
from app.services.robot import service as robot_service
from app.services.robot.astar import hospital_map, plan_astar_path
from app.services.robot.schemas import RobotTelemetryPayload

logger = logging.getLogger("rovex.core_platform_service")


def get_task_or_404(db_sql: Session, task_id: str) -> TaskSQL:
    """
    Resolves a task record by primary key or raises a consistent HTTP 404 error.

    Centralizing this lookup keeps transport-task lifecycle endpoints aligned on
    one not-found contract while making it easier to move the task aggregate into
    a dedicated service boundary later.
    """
    task = db_sql.query(TaskSQL).filter(TaskSQL.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


def get_eligible_robots(robots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filters a fleet list down to dispatchable robots ordered by highest battery.

    Eligibility rules are shared between scheduling and execution flows so task
    assignment remains consistent regardless of where the orchestration request
    originates from.
    """
    eligible = [
        robot for robot in robots
        if robot["sanctioned"] and robot["status"] == "idle" and robot["battery"] > 20.0
    ]
    return sorted(eligible, key=lambda robot: robot["battery"], reverse=True)


def resolve_target_organization(
    payload: TaskCreatePayload,
    current_user: Dict[str, Any],
    target_robot: Optional[Dict[str, Any]],
) -> Optional[str]:
    """
    Determines which hospital organization should own a newly scheduled task.

    Hospital-scoped users always create tasks for their own institution. Rovex
    admins may either specify an organization directly or let the selected /
    auto-assigned robot determine which hospital owns the mission.
    """
    if not is_admin(current_user):
        return current_user["organization"]

    if payload.organization:
        return payload.organization.strip()

    if target_robot:
        return target_robot["organization"]

    return None


def schedule_transit_task(
    payload: TaskCreatePayload,
    current_user: Dict[str, Any],
    db_sql: Session,
    db_nosql: MockDatabase,
) -> TaskSQL:
    """
    Creates a transport task, assigns an eligible robot when possible, and emits
    the matching fleet notification side effects.

    The task is persisted under the hospital organization that actually owns the
    mission. This prevents Rovex-wide admin activity from leaking platform-level
    organization metadata into hospital-scoped task records.
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

        task_organization = resolve_target_organization(payload, current_user, target_robot)
    else:
        task_organization = resolve_target_organization(payload, current_user, None)
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
        eligible_robots = get_eligible_robots(available_robots)

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


def list_tasks_for_user(current_user: Dict[str, Any], db_sql: Session) -> List[TaskSQL]:
    """
    Returns tasks visible to the current user ordered by most recent creation.

    The helper gives the router a single service-level entry point today and a
    clean seam for promoting task reads into a dedicated query module later.
    """
    query = db_sql.query(TaskSQL).order_by(TaskSQL.created_at.desc())
    if is_admin(current_user):
        return query.all()
    return query.filter(TaskSQL.organization == current_user["organization"]).all()


def execute_transit_task(
    task_id: str,
    current_user: Dict[str, Any],
    db_sql: Session,
    db_nosql: MockDatabase,
) -> TaskSQL:
    """
    Executes a scheduled transport mission by assigning a robot when needed,
    simulating its route traversal, and updating SQL/NoSQL state accordingly.
    """
    task = get_task_or_404(db_sql, task_id)
    ensure_organization_access(current_user, task.organization, detail="Access denied.")

    if task.status == "pending" and not task.robot_id:
        available_robots = robot_service.get_robots_by_organization(db_nosql, task.organization)
        eligible = get_eligible_robots(available_robots)
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

    notification_service.log_system_notification(
        db=db_nosql,
        robot_id=robot_id,
        message=f"Starting route traversal for mission {task.id}. Node sequence: {path_nodes}",
        category="GENERAL"
    )

    for idx, node_name in enumerate(path_nodes):
        node_pos = nodes_layout[node_name]
        robot_service.update_robot_status_and_location(
            db=db_nosql,
            robot_id=robot_id,
            status="transit" if idx < len(path_nodes) - 1 else "idle",
            location=node_name,
            x_m=node_pos["x"],
            y_m=node_pos["y"],
            assigned_task_id=task.id if idx < len(path_nodes) - 1 else None
        )

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

    task.status = "completed"
    task.eta_minutes = 0.0
    db_sql.commit()
    db_sql.refresh(task)
    return task


def cancel_transit_task(
    task_id: str,
    current_user: Dict[str, Any],
    db_sql: Session,
    db_nosql: MockDatabase,
) -> TaskSQL:
    """
    Cancels a pending or active transit task and releases any assigned robot.
    """
    task = get_task_or_404(db_sql, task_id)
    ensure_organization_access(current_user, task.organization, detail="Access denied.")

    if task.status in ["completed", "cancelled"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot cancel a task that is already '{task.status}'.")

    robot_id = task.robot_id
    task.status = "cancelled"
    db_sql.commit()
    db_sql.refresh(task)

    if robot_id:
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
        notification_service.log_system_notification(
            db=db_nosql,
            robot_id=robot_id,
            message=f"Mission {task_id} has been CANCELLED by staff dispatcher.",
            category="CRITICAL"
        )

    return task


def submit_robot_service_request(
    payload: ServiceRequestPayload,
    current_user: Dict[str, Any],
    db_nosql: MockDatabase,
) -> Dict[str, Any]:
    """
    Records a maintenance request for a robot and immediately flags it as errored.
    """
    robot = robot_service.get_robot_by_id(db_nosql, payload.robot_id)
    if not robot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot not found.")

    ensure_organization_access(current_user, robot["organization"], detail="Access denied.")

    db_nosql["robots"].update_one(
        {"robot_id": payload.robot_id},
        {"$set": {"last_problem": payload.issue_description, "status": "error", "assigned_task_id": None}}
    )

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
