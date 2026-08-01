"""
File: app/services/organization/service.py
Description: Organization-domain business logic for the Rovex modular monolith.
This module composes organization metadata, controller trees, fleets, robots,
and recent logs into reusable views that power both the admin control center
and hospital-scoped supervisor popups.
"""

from typing import Any, Dict, List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import ensure_organization_access, is_admin
from app.core.database import MockDatabase, UserSQL
from app.services.notification import service as notification_service
from app.services.robot import service as robot_service


def _serialize_controller(user: UserSQL) -> Dict[str, str]:
    """
    Converts a SQL user record into a tree node payload.
    """
    return {
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "email": user.email,
    }


def _build_controller_tree(users: List[UserSQL]) -> Dict[str, List[Dict[str, str]]]:
    """
    Groups organization users into role-aware controller tree buckets.
    """
    supervisors = [_serialize_controller(user) for user in users if user.role == "supervisor"]
    sub_supervisors = [_serialize_controller(user) for user in users if user.role == "sub-supervisor"]
    employees = [_serialize_controller(user) for user in users if user.role == "employee"]
    return {
        "supervisors": supervisors,
        "sub-supervisors": sub_supervisors,
        "employees": employees,
    }


def _build_robot_activity_view(db_nosql: MockDatabase, robot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produces a robot detail payload enriched with recent notifications and
    telemetry timestamps.
    """
    recent_notifications = notification_service.query_notifications(
        db_nosql,
        robot_id=robot["robot_id"],
        organization=robot["organization"],
        limit=5,
    )
    recent_telemetry = robot_service.get_recent_telemetry(db_nosql, robot["robot_id"], limit=5)
    return {
        "robot_id": robot["robot_id"],
        "fleet_id": robot["fleet_id"],
        "serial_number": robot["serial_number"],
        "sanctioned": robot["sanctioned"],
        "battery": robot["battery"],
        "status": robot["status"],
        "assigned_task_id": robot.get("assigned_task_id"),
        "location": robot["location"],
        "x_m": robot["x_m"],
        "y_m": robot["y_m"],
        "last_problem": robot["last_problem"],
        "recent_notification_messages": [entry["message"] for entry in recent_notifications],
        "recent_telemetry_timestamps": [str(entry.get("timestamp")) for entry in recent_telemetry],
    }


def _build_organization_summary(db_nosql: MockDatabase, organization_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produces a lightweight organization summary for selectors and metric cards.
    """
    fleets = robot_service.get_fleets_by_organization(db_nosql, organization_doc["organization"])
    total_robots = sum(fleet["total_robot_count"] for fleet in fleets)
    dispatchable_robots = sum(fleet["idle_robot_count"] for fleet in fleets)
    unsanctioned_robots = sum(fleet["unsanctioned_robot_count"] for fleet in fleets)
    return {
        "organization": organization_doc["organization"],
        "service_tier": organization_doc["service_tier"],
        "fleet_controller_device": organization_doc["fleet_controller_device"],
        "deployed_since": organization_doc["deployed_since"],
        "total_fleets": len(fleets),
        "total_robots": total_robots,
        "dispatchable_robots": dispatchable_robots,
        "unsanctioned_robots": unsanctioned_robots,
        "location": organization_doc["location"],
    }


def get_visible_organizations(db_sql: Session, db_nosql: MockDatabase, current_user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Returns organization summaries visible to the supplied user.
    """
    organizations = [organization for organization in db_nosql["organizations"].find({})]
    if not is_admin(current_user):
        organizations = [org for org in organizations if org["organization"] == current_user["organization"]]
    summaries = [_build_organization_summary(db_nosql, organization) for organization in organizations]
    return sorted(summaries, key=lambda org: org["organization"])


def get_organization_detail(
    db_sql: Session,
    db_nosql: MockDatabase,
    current_user: Dict[str, Any],
    organization_name: str,
) -> Dict[str, Any]:
    """
    Returns a full organization management payload for an admin or supervisor.
    """
    organization = db_nosql["organizations"].find_one({"organization": organization_name})
    if not organization:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    ensure_organization_access(current_user, organization_name, detail="Access denied.")

    users = (
        db_sql.query(UserSQL)
        .filter(UserSQL.organization == organization_name)
        .order_by(UserSQL.role.asc(), UserSQL.full_name.asc())
        .all()
    )
    fleets = robot_service.get_fleets_by_organization(db_nosql, organization_name)
    robots = robot_service.get_robots_by_organization(db_nosql, organization_name)
    robot_index = {robot["robot_id"]: robot for robot in robots}

    expanded_fleets = []
    for fleet in fleets:
        fleet_robot_docs = [robot_index[robot_id] for robot_id in fleet["robot_ids"] if robot_id in robot_index]
        expanded_fleets.append({
            "fleet_id": fleet["fleet_id"],
            "fleet_name": fleet["fleet_name"],
            "fleet_type": fleet["fleet_type"],
            "dispatch_zone": fleet["dispatch_zone"],
            "notes": fleet["notes"],
            "total_robot_count": fleet["total_robot_count"],
            "active_robot_count": fleet["active_robot_count"],
            "sanctioned_robot_count": fleet["sanctioned_robot_count"],
            "unsanctioned_robot_count": fleet["unsanctioned_robot_count"],
            "idle_robot_count": fleet["idle_robot_count"],
            "robots": [_build_robot_activity_view(db_nosql, robot) for robot in fleet_robot_docs],
        })

    detail = _build_organization_summary(db_nosql, organization)
    detail.update({
        "contract_owner": organization["contract_owner"],
        "notes": organization["notes"],
        "rovex_history": organization["rovex_history"],
        "controller_tree": _build_controller_tree(users),
        "fleets": expanded_fleets,
    })
    return detail
