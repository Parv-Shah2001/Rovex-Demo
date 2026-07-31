"""
File: app/core/config.py
Description: Configuration and settings for the Rovex backend platform. This file defines
constants, configuration variables, and default seed datasets (such as users, roles, default
hospital layouts, and path graph nodes/edges) that are utilized across the modular monolith.
"""

import os
from typing import Dict, Any, List, Tuple

# Security Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "rovex_super_secret_interview_key_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
ACCESS_TOKEN_EXPIRE_SECONDS = ACCESS_TOKEN_EXPIRE_MINUTES * 60

# RBAC / Organization Configuration
ROVEX_ORGANIZATION = "Rovex Robotics Inc."
VALID_ROLES: Tuple[str, ...] = ("admin", "supervisor", "sub-supervisor", "employee")
ROLE_INHERITANCE: Dict[str, Tuple[str, ...]] = {
    "admin": VALID_ROLES,
    "supervisor": ("supervisor", "sub-supervisor", "employee"),
    "sub-supervisor": ("sub-supervisor", "employee"),
    "employee": ("employee",),
}

# Logger Configuration
LOG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data_pool_notifications.log")

# Hospital Map / Graph Seed Nodes
# Represents coordinates in meters (x, y) for a typical hospital floor.
DEFAULT_NODES = {
    "Reception": {"x": 0.0, "y": 0.0, "description": "Main hospital entrance and lobby area"},
    "Pharmacy": {"x": 8.0, "y": 1.0, "description": "Central pharmacy for prescription retrieval"},
    "Nursing Station": {"x": 5.0, "y": 5.0, "description": "Central nurses hub and dispatcher zone"},
    "Emergency Room": {"x": 1.0, "y": 6.0, "description": "ER zone for high-priority cases"},
    "ICU": {"x": 4.0, "y": 10.0, "description": "Intensive Care Unit with strict sanitation rules"},
    "Elevator Lobby": {"x": 7.0, "y": 6.5, "description": "Elevator access point for multi-floor transport"},
    "Operating Room A": {"x": 10.0, "y": 10.0, "description": "Main surgical theatre A"},
    "Operating Room B": {"x": 10.0, "y": 7.5, "description": "Surgical theatre B"},
    "Ward 1": {"x": 2.0, "y": 12.0, "description": "General Patient Ward 1"},
    "Ward 2": {"x": 5.0, "y": 14.0, "description": "General Patient Ward 2"}
}

# Hospital Map / Graph Seed Edges with default weights (representing distances or transit costs)
DEFAULT_EDGES = [
    {"from": "Reception", "to": "Nursing Station", "weight": 5.0},
    {"from": "Reception", "to": "Pharmacy", "weight": 8.0},
    {"from": "Nursing Station", "to": "Emergency Room", "weight": 3.0},
    {"from": "Nursing Station", "to": "ICU", "weight": 6.0},
    {"from": "Nursing Station", "to": "Elevator Lobby", "weight": 4.0},
    {"from": "Elevator Lobby", "to": "Pharmacy", "weight": 5.0},
    {"from": "Elevator Lobby", "to": "ICU", "weight": 4.5},
    {"from": "Elevator Lobby", "to": "Operating Room A", "weight": 7.0},
    {"from": "Elevator Lobby", "to": "Operating Room B", "weight": 5.5},
    {"from": "ICU", "to": "Ward 1", "weight": 3.5},
    {"from": "ICU", "to": "Ward 2", "weight": 5.0},
    {"from": "Ward 1", "to": "Ward 2", "weight": 3.0},
    {"from": "Operating Room A", "to": "Operating Room B", "weight": 2.5}
]

# Seed Users (SQL Database Seed)
# Structure: Username -> { password, role, organization, full_name, email }
#
# RBAC Role Hierarchy:
#   admin        : Rovex employee — platform-wide access across ALL organizations,
#                  admin dashboard, sandbox queries, live logs, sanction controls.
#   supervisor   : Hospital org supervisor — manages all robots and employees
#                  within their own organization only.
#   sub-supervisor : Hospital org sub-supervisor — can schedule tasks, view live
#                    status, adjust corridor weights within their own organization.
#   employee     : Hospital org employee — viewer only, can request access and
#                  file service tickets.
SEED_USERS = [
    {
        "id": 1,
        "username": "rovex_admin",
        "password": "rovexadminpassword",
        "role": "admin",
        "organization": ROVEX_ORGANIZATION,
        "full_name": "James Whitfield",
        "email": "j.whitfield@rovexrobotics.com"
    },
    {
        "id": 2,
        "username": "sup_sarah",
        "password": "suppassword",
        "role": "supervisor",
        "organization": "St. Jude Hospital",
        "full_name": "Dr. Sarah Mitchell",
        "email": "sarah.mitchell@stjude.org"
    },
    {
        "id": 3,
        "username": "sub_thomas",
        "password": "subpassword",
        "role": "sub-supervisor",
        "organization": "St. Jude Hospital",
        "full_name": "Nurse Thomas Kelly",
        "email": "thomas.kelly@stjude.org"
    },
    {
        "id": 4,
        "username": "emp_john",
        "password": "emppassword",
        "role": "employee",
        "organization": "St. Jude Hospital",
        "full_name": "Orderly John Doe",
        "email": "john.doe@stjude.org"
    },
    {
        "id": 5,
        "username": "sup_alan",
        "password": "univpassword",
        "role": "supervisor",
        "organization": "City General Hospital",
        "full_name": "Dr. Alan Grant",
        "email": "alan.grant@citygeneral.org"
    }
]

# Seed Robots (NoSQL Database Seed)
SEED_ROBOTS = [
    {
        "robot_id": "rovi-01",
        "organization": "St. Jude Hospital",
        "serial_number": "SN-R2D2-100412",
        "last_serviced": "2026-05-12T09:00:00Z",
        "last_problem": "Lidar recalibration required",
        "sanctioned": True,
        "battery": 87.4,
        "status": "idle", # idle, transit, charging, error
        "assigned_task_id": None,
        "location": "Reception",
        "x_m": 0.0,
        "y_m": 0.0
    },
    {
        "robot_id": "rovi-02",
        "organization": "St. Jude Hospital",
        "serial_number": "SN-C3PO-330419",
        "last_serviced": "2026-06-20T10:15:00Z",
        "last_problem": "Slight wheel motor slipping - fixed",
        "sanctioned": True,
        "battery": 92.1,
        "status": "transit",
        "assigned_task_id": "task-203",
        "location": "Nursing Station",
        "x_m": 5.0,
        "y_m": 5.0
    },
    {
        "robot_id": "rovi-03",
        "organization": "City General Hospital",
        "serial_number": "SN-BB8-991200",
        "last_serviced": "2026-07-01T14:00:00Z",
        "last_problem": "None",
        "sanctioned": True,
        "battery": 45.0,
        "status": "charging",
        "assigned_task_id": None,
        "location": "Pharmacy",
        "x_m": 8.0,
        "y_m": 1.0
    },
    {
        "robot_id": "rovi-04",
        "organization": "St. Jude Hospital",
        "serial_number": "SN-BENDER-404404",
        "last_serviced": "2026-03-10T11:30:00Z",
        "last_problem": "Overheating issues - maintenance scheduled",
        "sanctioned": False,  # Un-sanctioned, cannot take tasks
        "battery": 12.0,
        "status": "error",
        "assigned_task_id": None,
        "location": "Elevator Lobby",
        "x_m": 7.0,
        "y_m": 6.5
    }
]

def get_config_summary() -> Dict[str, Any]:
    """
    Returns a dictionary summarizing the configuration status.
    
    This helper is useful for healthcheck purposes to confirm configurations are active.
    """
    return {
        "secret_key_configured": len(SECRET_KEY) > 0,
        "algorithm": ALGORITHM,
        "token_expire_minutes": ACCESS_TOKEN_EXPIRE_MINUTES,
        "rovex_organization": ROVEX_ORGANIZATION,
        "valid_roles": list(VALID_ROLES),
        "log_path": LOG_FILE_PATH,
        "seed_users_count": len(SEED_USERS),
        "seed_robots_count": len(SEED_ROBOTS)
    }
