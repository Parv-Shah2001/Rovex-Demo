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
from app.services.robot.schemas import RobotTelemetryPayload, RobotResponse

logger = logging.getLogger("rovex.robot_service")


def get_all_robots(db: MockDatabase) -> List[Dict[str, Any]]:
    """
    Retrieves all robot document records from NoSQL database.
    """
    cursor = db["robots"].find({})
    return [doc for doc in cursor]


def get_robots_by_organization(db: MockDatabase, organization: str) -> List[Dict[str, Any]]:
    """
    Returns only the robot devices belonging to a specific hospital/institution.
    """
    cursor = db["robots"].find({"organization": organization})
    return [doc for doc in cursor]


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
            "status": status
        }
        
        # If running a mission, keep sync
        if telemetry.mission_id:
            update_data["assigned_task_id"] = telemetry.mission_id
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
            "serial_number": f"SN-UNKNOWN-{telemetry.robot_id.upper()}",
            "last_serviced": datetime.utcnow().isoformat(),
            "last_problem": "Ad-hoc initialization",
            "sanctioned": True,
            "battery": telemetry.battery.percentage,
            "status": "idle",
            "assigned_task_id": telemetry.mission_id,
            "location": "Reception",
            "x_m": telemetry.localization.x_m,
            "y_m": telemetry.localization.y_m
        }
        db["robots"].insert_one(new_robot)
        
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
    return get_robot_by_id(db, robot_id)


def get_recent_telemetry(db: MockDatabase, robot_id: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Retrieves the historical telemetry logs recorded for a specific robot.
    Sorted in descending chronological order.
    """
    cursor = db["telemetry"].find({"robot_id": robot_id})
    # Since our cursor is basic, we sort and limit manually
    results = sorted(cursor._data, key=lambda x: x.get("timestamp", ""), reverse=True)
    return results[:limit]
