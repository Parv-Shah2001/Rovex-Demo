"""
File: app/services/notification/service.py
Description: Business logic for the Rovex Notification Service. 
Implements notification logging, categorization, and priority sorting. All alerts
are written to both a persistent local log file ('data_pool_notifications.log') for future
sensor/lidar processing pipelines, and a NoSQL collection for instant querying in frontend dashboards.
"""

import os
import datetime
import logging
from typing import List, Dict, Any, Optional

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


def log_system_notification(
    db: MockDatabase, 
    robot_id: str, 
    message: str, 
    category: str = "GENERAL"
) -> Dict[str, Any]:
    """
    Creates and logs a system notification with respect to a particular robot.
    Writes to the shared log file on disk and registers it in the NoSQL database.
    """
    category_upper = category.upper()
    priority = CATEGORY_PRIORITIES.get(category_upper, 3) # default to medium priority (3)
    
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    
    # 1. Create the database record
    notification_doc = {
        "timestamp": timestamp,
        "robot_id": robot_id,
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
        
    cursor = db["notifications"].find(query_filter)
    notifications = [notification for notification in cursor]
    results = sorted(notifications, key=lambda x: x.get("timestamp", ""), reverse=True)
    return results[:limit]


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
