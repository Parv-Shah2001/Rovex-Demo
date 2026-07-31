"""
File: app/services/notification/service.py
Description: Business logic for the Rovex Notification Service. 
Implements notification logging, categorization, and priority sorting. All alerts
are written to both a persistent local log file ('data_pool_notifications.log') for future
sensor/lidar processing pipelines, and a NoSQL collection for instant querying in frontend dashboards.
"""

import datetime
import os
import logging
from typing import List, Dict, Any, Optional

from app.core.auth import is_admin
from app.core.config import LOG_FILE_PATH
from app.core.database import MockDatabase

logger = logging.getLogger("rovex.notification_service")

# Map categories to numerical priority levels (1 = Highest, 5 = Lowest)
CATEGORY_PRIORITIES = {
    "CRITICAL": 1,
    "GENERAL": 2,
    "ANALYTICS": 3,
    "SUGGESTIONS": 4,
    "MARKETING": 5
}


def resolve_notification_organization(
    db: MockDatabase,
    robot_id: str,
    organization: Optional[str] = None,
) -> str:
    """
    Resolves which organization should own a notification.

    Robot-specific notifications inherit the robot organization automatically.
    Fleet-level alerts may provide an explicit organization, otherwise they fall
    back to a platform-level bucket.
    """
    if organization:
        return organization

    robot = db["robots"].find_one({"robot_id": robot_id})
    if robot:
        return robot.get("organization", "Platform")
    return "Platform"


def log_system_notification(
    db: MockDatabase, 
    robot_id: str, 
    message: str, 
    category: str = "GENERAL",
    organization: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates and logs a system notification with respect to a particular robot.
    Writes to the shared log file on disk and registers it in the NoSQL database.
    """
    category_upper = category.upper()
    priority = CATEGORY_PRIORITIES.get(category_upper, 3) # default to medium priority (3)
    resolved_organization = resolve_notification_organization(db, robot_id, organization)
    
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    
    # 1. Create the database record
    notification_doc = {
        "timestamp": timestamp,
        "robot_id": robot_id,
        "organization": resolved_organization,
        "category": category_upper,
        "priority": priority,
        "message": message
    }
    
    db["notifications"].insert_one(notification_doc)
    
    # 2. Write to the shared file log (representing the central logs pool)
    log_line = f"[{timestamp}] [ALERT] [CAT: {category_upper}] [PRIO: {priority}] Robot {robot_id} -> {message}\n"
    
    try:
        os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
        with open(LOG_FILE_PATH, "a") as f:
            f.write(log_line)
    except Exception as e:
        logger.error(f"Failed to write notification to shared log file: {e}")
        
    logger.info(f"Notification logged: [{category_upper}] {message} for Robot {robot_id}")
    return notification_doc


def query_notifications(
    db: MockDatabase, 
    category: Optional[str] = None, 
    robot_id: Optional[str] = None,
    organization: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Retrieves logged notifications from NoSQL matching filters, sorted by most recent first.
    """
    query_filter = {}
    if category:
        query_filter["category"] = category.upper()
    if robot_id:
        query_filter["robot_id"] = robot_id
    if organization:
        query_filter["organization"] = organization

    cursor = db["notifications"].find(query_filter)
    notifications = [notification for notification in cursor]
    results = sorted(notifications, key=lambda x: x.get("timestamp", ""), reverse=True)
    return results[:limit]


def list_notifications_for_user(
    db: MockDatabase,
    current_user: Dict[str, Any],
    category: Optional[str] = None,
    robot_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Returns notifications visible to the current user.

    Rovex admins can inspect all alerts. Hospital-scoped users are restricted to
    the notifications tagged with their own organization.
    """
    organization = None if is_admin(current_user) else current_user["organization"]
    return query_notifications(
        db=db,
        category=category,
        robot_id=robot_id,
        organization=organization,
        limit=limit,
    )


def get_logs_payload(lines_count: int = 100) -> Dict[str, Any]:
    """
    Returns a normalized response payload for the admin log-stream endpoint.
    """
    return {
        "status": "success",
        "file_path": LOG_FILE_PATH,
        "lines_count": lines_count,
        "logs": get_live_log_stream(lines_count=lines_count),
    }


def get_live_log_stream(lines_count: int = 100) -> str:
    """
    Reads the physical 'data_pool_notifications.log' file from disk.
    Allows administrators to view live consolidated systems logs.
    """
    if not os.path.exists(LOG_FILE_PATH):
        return "No log stream available yet. Trigger some notifications!"
        
    try:
        with open(LOG_FILE_PATH, "r") as f:
            lines = f.readlines()
            # Return the last n lines
            return "".join(lines[-lines_count:])
    except Exception as e:
        logger.error(f"Error reading physical log stream: {e}")
        return f"Error reading log file on disk: {e}"
