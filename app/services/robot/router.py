"""
File: app/services/robot/router.py
Description: FastAPI Router exposing Robot Management and Route Optimization API endpoints.
Provides routes for telemetry ingestion, robot profile lookups, sanction controls,
A* path planning calculations, and real-time graph edge weight adjustments.

Organization scoping:
  - Admin (Rovex) users can see ALL robots across every organization.
  - Hospital staff (supervisor, sub-supervisor, employee) can only see robots
    belonging to their own organization.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Dict, Any

from app.core.database import MockDatabase, get_nosql_db
from app.core.auth import (
    RBACChecker,
    ensure_organization_access,
    get_current_user_from_cookie_or_header,
    is_admin,
)
from app.services.robot.schemas import (
    AStarPlanRequest,
    FleetResponse,
    RobotTelemetryPayload,
    RobotResponse,
    UpdateEdgeWeightRequest,
    UpdateSanctionRequest,
)
from app.services.robot import service as robot_service

router = APIRouter(prefix="/api/robots", tags=["Robot Management"])


def _get_robot_or_404(db: MockDatabase, robot_id: str) -> Dict[str, Any]:
    """
    Resolves a robot profile or raises a consistent HTTP 404 response.
    """
    robot = robot_service.get_robot_by_id(db, robot_id)
    if not robot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Robot with ID '{robot_id}' was not found."
        )
    return robot


@router.post("/telemetry", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def post_robot_telemetry(payload: RobotTelemetryPayload, db: MockDatabase = Depends(get_nosql_db)):
    """
    Ingestion endpoint for concurrent streaming robot telemetry payloads.
    Validates physical parameters, safety triggers, and diagnostic indicators.
    Saves to the telemetry pool and updates the live robot status.
    """
    try:
        saved_telemetry = robot_service.ingest_robot_telemetry(db, payload)
        return {"status": "success", "detail": "Telemetry processed successfully", "payload": saved_telemetry}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest telemetry payload: {e}"
        )


@router.get("", response_model=List[RobotResponse])
def list_robots(
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header),
    db: MockDatabase = Depends(get_nosql_db)
):
    """
    Lists robot devices visible to the current user.
    - Rovex admins see ALL robots across every organization.
    - Hospital staff see only robots belonging to their own organization.
    """
    if is_admin(current_user):
        return robot_service.get_all_robots(db)
    return robot_service.get_robots_by_organization(db, current_user["organization"])


@router.get("/fleets", response_model=List[FleetResponse])
def list_fleets(
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header),
    db: MockDatabase = Depends(get_nosql_db),
):
    """
    Lists fleet summaries visible to the current user.

    Admins can inspect every hospital fleet, while hospital staff remain scoped
    to fleets inside their own organization.
    """
    if is_admin(current_user):
        return robot_service.get_all_fleets(db)
    return robot_service.get_fleets_by_organization(db, current_user["organization"])


@router.get("/graph/layout", response_model=Dict[str, Any])
def get_graph_layout(current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header)):
    """
    Returns the hospital layout graph, including 2D node coordinates and edge weights.
    Used by the frontend to render the visual corridor network.
    """
    return robot_service.get_graph_layout()


@router.put("/graph/edge", response_model=Dict[str, Any])
def adjust_corridor_weight(
    payload: UpdateEdgeWeightRequest,
    current_user: Dict[str, Any] = Depends(RBACChecker(["supervisor", "sub-supervisor"]))
):
    """
    Dynamically adjusts the weight of a graph edge (e.g. increase weight for crowded corridors).
    Allows supervisors and sub-supervisors to optimize robot fleet routing.
    Admins can also access this via the RBAC hierarchy.
    """
    success = robot_service.adjust_corridor_weight(payload.node_a, payload.node_b, payload.weight)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edge connecting '{payload.node_a}' and '{payload.node_b}' was not found in graph."
        )
    return {
        "status": "success", 
        "detail": f"Corridor weight for {payload.node_a} <-> {payload.node_b} adjusted to {payload.weight}."
    }


@router.post("/path-planning", response_model=Dict[str, Any])
def calculate_optimal_path(
    payload: AStarPlanRequest,
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header)
):
    """
    Runs the A* pathfinding algorithm on the active hospital map.
    Returns the optimal list of nodes, total cost, total distance, and step logs.
    """
    result = robot_service.calculate_path_plan(payload.start_node, payload.goal_node)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not calculate path between '{payload.start_node}' and '{payload.goal_node}'. Check node connections."
        )
    return result


@router.get("/{robot_id}", response_model=RobotResponse)
def get_robot_profile(
    robot_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header),
    db: MockDatabase = Depends(get_nosql_db)
):
    """
    Returns the full detailed biodata profile of a single robot.
    - Rovex admins can view any robot regardless of organization.
    - Hospital staff can only view robots belonging to their own organization.
    """
    robot = _get_robot_or_404(db, robot_id)
    ensure_organization_access(
        current_user,
        robot["organization"],
        detail="Access denied. This robot belongs to another institution.",
    )
    return robot


@router.put("/{robot_id}/sanction", response_model=RobotResponse)
def modify_robot_sanction_status(
    robot_id: str,
    payload: UpdateSanctionRequest,
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin"])),
    db: MockDatabase = Depends(get_nosql_db)
):
    """
    Allows a Rovex Admin to sanction or un-sanction a robot.
    Un-sanctioned robots cannot accept transport tasks.
    This is a platform-level action restricted to Rovex staff only.
    """
    _get_robot_or_404(db, robot_id)
    updated_robot = robot_service.update_robot_sanction(db, robot_id, payload.sanctioned)
    return updated_robot


@router.get("/{robot_id}/telemetry-logs", response_model=List[Dict[str, Any]])
def get_robot_telemetry_history(
    robot_id: str,
    limit: int = Query(15, ge=1, le=200, description="Maximum telemetry records to return."),
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header),
    db: MockDatabase = Depends(get_nosql_db)
):
    """
    Retrieves the historical telemetry stream logs for a single robot.
    - Rovex admins can view any robot's telemetry regardless of organization.
    - Hospital staff can only view telemetry for robots in their own organization.
    """
    robot = _get_robot_or_404(db, robot_id)
    ensure_organization_access(
        current_user,
        robot["organization"],
        detail="Access denied. This robot belongs to another institution.",
    )
    return robot_service.get_recent_telemetry(db, robot_id, limit)
