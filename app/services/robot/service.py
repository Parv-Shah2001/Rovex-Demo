"""
File: app/services/robot/service.py
Description: Contains the NoSQL document-based business logic layer for Rovex robots.
Handles CRUD operations on the 'robots' collection, saves telemetry records, and manages
robot administrative state changes (such as sanction status, battery updates, and charging status).
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.core.database import MockDatabase
from app.services.robot.astar import hospital_map, plan_astar_path
from app.services.robot.schemas import RobotTelemetryPayload

logger = logging.getLogger("rovex.robot_service")


def _build_fleet_summary(fleet_doc: Dict[str, Any], robots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Builds a derived fleet summary document from fleet metadata and its robots.
    """
    return {
        **fleet_doc,
        "robot_ids": [robot["robot_id"] for robot in robots],
        "total_robot_count": len(robots),
        "active_robot_count": sum(1 for robot in robots if robot.get("status") in {"idle", "transit", "charging"}),
        "sanctioned_robot_count": sum(1 for robot in robots if robot.get("sanctioned") is True),
        "unsanctioned_robot_count": sum(1 for robot in robots if robot.get("sanctioned") is False),
        "idle_robot_count": sum(1 for robot in robots if robot.get("status") == "idle" and robot.get("sanctioned") is True),
    }


def synchronize_fleets(db: MockDatabase) -> List[Dict[str, Any]]:
    """
    Recomputes fleet membership summaries from the current robot registry.

    A fleet is the organization-scoped grouping of multiple robots, so this
    helper keeps fleet aggregate data aligned whenever robot assignments or
    sanction states change.
    """
    fleet_collection = db["fleets"]
    fleets = [fleet for fleet in fleet_collection.find({})]
    robots = get_all_robots(db)
    robots_by_fleet: Dict[str, List[Dict[str, Any]]] = {}
    for robot in robots:
        robots_by_fleet.setdefault(robot.get("fleet_id"), []).append(robot)

    synchronized_fleets = []
    for fleet in fleets:
        summarized = _build_fleet_summary(fleet, robots_by_fleet.get(fleet["fleet_id"], []))
        fleet_collection.update_one(
            {"fleet_id": fleet["fleet_id"]},
            {"$set": {
                "robot_ids": summarized["robot_ids"],
                "total_robot_count": summarized["total_robot_count"],
                "active_robot_count": summarized["active_robot_count"],
                "sanctioned_robot_count": summarized["sanctioned_robot_count"],
                "unsanctioned_robot_count": summarized["unsanctioned_robot_count"],
                "idle_robot_count": summarized["idle_robot_count"],
            }}
        )
        synchronized_fleets.append(summarized)

    return sorted(synchronized_fleets, key=lambda fleet: (fleet["organization"], fleet["fleet_name"]))


def get_all_fleets(db: MockDatabase) -> List[Dict[str, Any]]:
    """
    Returns all fleet summaries across every organization.
    """
    return synchronize_fleets(db)


def get_fleets_by_organization(db: MockDatabase, organization: str) -> List[Dict[str, Any]]:
    """
    Returns fleet summaries for a single hospital organization.
    """
    return [fleet for fleet in synchronize_fleets(db) if fleet["organization"] == organization]


def get_fleet_by_id(db: MockDatabase, fleet_id: str) -> Optional[Dict[str, Any]]:
    """
    Resolves a single fleet summary by ID after refreshing aggregate state.
    """
    fleets = synchronize_fleets(db)
    return next((fleet for fleet in fleets if fleet["fleet_id"] == fleet_id), None)


def get_graph_layout() -> Dict[str, Any]:
    """
    Returns the active hospital routing layout in a frontend-friendly shape.

    Keeping graph serialization in the service layer prevents routers from
    depending directly on the pathfinding singleton implementation.
    """
    return {
        "nodes": hospital_map.get_nodes(),
        "edges": hospital_map.get_edges(),
    }


def adjust_corridor_weight(node_a: str, node_b: str, weight: float) -> bool:
    """
    Updates the active routing graph weight for a corridor edge.
    """
    return hospital_map.update_edge_weight(node_a, node_b, weight)


def calculate_path_plan(start_node: str, goal_node: str) -> Optional[Dict[str, Any]]:
    """
    Runs the active A* planner and returns the resulting route payload.
    """
    return plan_astar_path(start_node, goal_node, hospital_map)


def get_all_robots(db: MockDatabase) -> List[Dict[str, Any]]:
    """
    Retrieves all robot document records from NoSQL database.
    """
    cursor = db["robots"].find({})
    return sorted([doc for doc in cursor], key=lambda doc: doc["robot_id"])


def get_robots_by_organization(db: MockDatabase, organization: str) -> List[Dict[str, Any]]:
    """
    Returns only the robot devices belonging to a specific hospital/institution.
    """
    cursor = db["robots"].find({"organization": organization})
    return sorted([doc for doc in cursor], key=lambda doc: doc["robot_id"])


def get_robot_by_id(db: MockDatabase, robot_id: str) -> Optional[Dict[str, Any]]:
    """
    Looks up a robot profile by its unique ID. Returns None if not found.
    """
    return db["robots"].find_one({"robot_id": robot_id})


def ingest_robot_telemetry(db: MockDatabase, telemetry: RobotTelemetryPayload) -> Dict[str, Any]:
    """
    Simulates the telemetry ingestion service.
    
    This function performs two tasks:
    1. Logs the telemetry payload to the 'telemetry' collection for historical and analytics querying.
    2. Updates the live 'robots' collection with the latest coordinate status, battery level, 
       and active mission ID from the incoming stream.
    """
    # 1. Convert payload to dictionary
    payload_dict = telemetry.model_dump()
    
    # Standardize timestamp to string for MongoDB compatibility
    if isinstance(payload_dict["timestamp"], datetime):
        payload_dict["timestamp"] = payload_dict["timestamp"].isoformat()
        
    db["telemetry"].insert_one(payload_dict)
    
    # 2. Identify and update active robot profile
    robot = get_robot_by_id(db, telemetry.robot_id)
    if robot:
        # Determine status based on safety hazards or battery
        status = robot["status"]
        if telemetry.safety.emergency_stop:
            status = "error"
        elif telemetry.battery.percentage < 15.0 and status != "charging":
            status = "error" # Low battery emergency
            
        update_data = {
            "battery": round(telemetry.battery.percentage, 1),
            "x_m": round(telemetry.localization.x_m, 2),
            "y_m": round(telemetry.localization.y_m, 2),
            "status": status,
            "assigned_task_id": telemetry.mission_id,
        }
        
        # If running a mission and the robot is still healthy, keep sync
        if telemetry.mission_id and status != "error":
            update_data["status"] = "transit"
            
        db["robots"].update_one(
            {"robot_id": telemetry.robot_id},
            {"$set": update_data}
        )
        logger.info(f"Ingested telemetry for robot '{telemetry.robot_id}': battery={telemetry.battery.percentage}%, (x={telemetry.localization.x_m}, y={telemetry.localization.y_m})")
    else:
        logger.warning(f"Telemetry received for unknown robot ID: '{telemetry.robot_id}'. Creating ad-hoc record.")
        # If unknown, create basic biodata entry
        new_robot = {
            "robot_id": telemetry.robot_id,
            "organization": "Unknown",
            "fleet_id": "unassigned",
            "serial_number": f"SN-UNKNOWN-{telemetry.robot_id.upper()}",
            "last_serviced": datetime.utcnow().isoformat(),
            "last_problem": "Ad-hoc initialization",
            "sanctioned": True,
            "battery": telemetry.battery.percentage,
            "status": "error" if telemetry.safety.emergency_stop or telemetry.battery.percentage < 15.0 else "idle",
            "assigned_task_id": telemetry.mission_id,
            "location": "Reception",
            "x_m": telemetry.localization.x_m,
            "y_m": telemetry.localization.y_m
        }
        db["robots"].insert_one(new_robot)

    synchronize_fleets(db)
    return payload_dict


def update_robot_sanction(db: MockDatabase, robot_id: str, sanctioned: bool) -> Optional[Dict[str, Any]]:
    """
    Toggles a robot's sanction approval status. Un-sanctioning a robot immediately 
    stops it from accepting tasks and transitions its status to 'idle' / 'error'.
    """
    robot = get_robot_by_id(db, robot_id)
    if not robot:
        return None
        
    update_fields = {"sanctioned": sanctioned}
    if not sanctioned:
        update_fields["status"] = "idle"
        update_fields["assigned_task_id"] = None
        
    db["robots"].update_one({"robot_id": robot_id}, {"$set": update_fields})
    synchronize_fleets(db)
    return get_robot_by_id(db, robot_id)


def update_robot_status_and_location(
    db: MockDatabase, 
    robot_id: str, 
    status: str, 
    location: str, 
    x_m: float, 
    y_m: float,
    assigned_task_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Updates the operational details of a robot after executing a task or arriving at nodes.
    """
    robot = get_robot_by_id(db, robot_id)
    if not robot:
        return None
        
    update_fields = {
        "status": status,
        "location": location,
        "x_m": x_m,
        "y_m": y_m,
        "assigned_task_id": assigned_task_id
    }
    
    db["robots"].update_one({"robot_id": robot_id}, {"$set": update_fields})
    synchronize_fleets(db)
    return get_robot_by_id(db, robot_id)


def get_recent_telemetry(db: MockDatabase, robot_id: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Retrieves the historical telemetry logs recorded for a specific robot.
    Sorted in descending chronological order.
    """
    cursor = db["telemetry"].find({"robot_id": robot_id})
    telemetry_records = [record for record in cursor]
    results = sorted(telemetry_records, key=lambda x: x.get("timestamp", ""), reverse=True)
    return results[:limit]
