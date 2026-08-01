"""
File: app/services/organization/schemas.py
Description: Pydantic contracts for organization-scoped management views.
These schemas shape controller trees, organization metadata, fleet summaries,
and robot/log rollups used by both the admin and hospital-facing dashboards.
"""

from typing import List

from pydantic import BaseModel, Field


class ControllerNode(BaseModel):
    """
    Represents a staff member inside an organization controller tree.
    """
    username: str
    full_name: str
    role: str
    email: str


class OrganizationControllerTree(BaseModel):
    """
    Role-grouped view of an organization's staff structure.
    """
    supervisors: List[ControllerNode]
    sub_supervisors: List[ControllerNode] = Field(alias="sub-supervisors")
    employees: List[ControllerNode]


class RobotActivitySummary(BaseModel):
    """
    Rich robot detail used inside fleet and organization management views.
    """
    robot_id: str
    fleet_id: str
    serial_number: str
    sanctioned: bool
    battery: float
    status: str
    assigned_task_id: str | None
    location: str
    x_m: float
    y_m: float
    last_problem: str
    recent_notification_messages: List[str]
    recent_telemetry_timestamps: List[str]


class FleetStatusView(BaseModel):
    """
    Expanded fleet detail containing its member robots.
    """
    fleet_id: str
    fleet_name: str
    fleet_type: str
    dispatch_zone: str
    notes: str
    total_robot_count: int
    active_robot_count: int
    sanctioned_robot_count: int
    unsanctioned_robot_count: int
    idle_robot_count: int
    robots: List[RobotActivitySummary]


class OrganizationLocation(BaseModel):
    """
    Physical location block for a hospital organization.
    """
    campus: str
    address: str
    city: str
    state: str
    country: str


class OrganizationSummary(BaseModel):
    """
    Lightweight organization summary used in selectors and overview cards.
    """
    organization: str
    service_tier: str
    fleet_controller_device: str
    deployed_since: str
    total_fleets: int
    total_robots: int
    dispatchable_robots: int
    unsanctioned_robots: int
    location: OrganizationLocation


class OrganizationDetail(OrganizationSummary):
    """
    Full organization detail payload used by admin and supervisor detail views.
    """
    contract_owner: str
    notes: str
    rovex_history: List[str]
    controller_tree: OrganizationControllerTree
    fleets: List[FleetStatusView]
