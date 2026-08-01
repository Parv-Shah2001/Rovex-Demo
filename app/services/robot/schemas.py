"""
File: app/services/robot/schemas.py
Description: Defines the Pydantic telemetry models and validation schemas for 
the Rovex hospital robots. Validates concurrent incoming sensor, speed, battery, safety, 
and health payloads (synthetic robot telemetries) as well as administrative robot profiles.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# =====================================================================
# 1. SYNTHETIC PAYLOAD TELEMETRY SCHEMAS (As requested by the prompt)
# =====================================================================

class MotionTelemetry(BaseModel):
    """
    Validates physical dynamics telemetry.
    """
    speed_mps: float = Field(..., ge=0.0, le=5.0, description="Speed in meters per second")
    steering_angle_rad: float = Field(..., ge=-3.15, le=3.15, description="Steering angle in radians")
    distance_traveled_m: float = Field(..., ge=0.0, description="Cumulative distance traveled in meters")


class BatteryTelemetry(BaseModel):
    """
    Validates onboard power reserve telemetry.
    """
    percentage: float = Field(..., ge=0.0, le=100.0, description="Battery state of charge as a percentage")
    remaining_capacity_mah: int = Field(..., ge=0, description="Remaining battery capacity in milliampere-hours (mAh)")


class LocalizationTelemetry(BaseModel):
    """
    Validates localization and mapping telemetry.
    """
    x_m: float = Field(..., description="Local coordinates x-coordinate in meters")
    y_m: float = Field(..., description="Local coordinates y-coordinate in meters")
    heading_rad: float = Field(..., ge=-3.15, le=3.15, description="Yaw angle / heading orientation in radians")


class SafetyTelemetry(BaseModel):
    """
    Validates safety sensor status and emergency stops.
    """
    perception_enabled: bool = Field(..., description="Indicates if safety sensors / cameras are active")
    speed_reduced: bool = Field(..., description="True if speed is throttled due to obstacle proximity")
    obstacle_stop: bool = Field(..., description="True if robot is currently stopped due to blocking obstacle")
    emergency_stop: bool = Field(..., description="True if mechanical or software emergency stop is active")


class SystemHealthTelemetry(BaseModel):
    """
    Validates general internal system and peripheral health.
    """
    cameras_online: int = Field(..., ge=0, description="Count of cameras functioning online")
    lidar_online: bool = Field(..., description="Status of the primary laser lidar scanner")
    controller_connected: bool = Field(..., description="Status of connection to the low-level motor controller")


class RobotTelemetryPayload(BaseModel):
    """
    Main synthetic telemetry payload schema sent concurrently by hospital stretcher robots.
    Matches the required payload structure exactly.
    """
    robot_id: str = Field(..., description="Unique hardware identifier of the sending robot")
    timestamp: datetime = Field(..., description="ISO 8601 UTC timestamp of the telemetry reading")
    mission_id: Optional[str] = Field(None, description="Active task identifier if currently executing a transit")
    motion: MotionTelemetry = Field(..., description="Real-time motion parameters")
    battery: BatteryTelemetry = Field(..., description="Real-time power storage statistics")
    localization: LocalizationTelemetry = Field(..., description="Calculated coordinate points")
    safety: SafetyTelemetry = Field(..., description="Safety and proximity flags")
    system_health: SystemHealthTelemetry = Field(..., description="Onboard diagnostic system flags")


# =====================================================================
# 2. ROBOT PROFILE & MANAGEMENT SCHEMAS
# =====================================================================

class RobotResponse(BaseModel):
    """
    Represents the full biodata profile of a robot stored inside the NoSQL collection.
    """
    robot_id: str
    organization: str
    fleet_id: str
    serial_number: str
    last_serviced: str
    last_problem: str
    sanctioned: bool
    battery: float
    status: str  # idle, transit, charging, error
    assigned_task_id: Optional[str]
    location: str
    x_m: float
    y_m: float


class FleetResponse(BaseModel):
    """
    Represents an organization-scoped fleet summary that groups multiple robots.
    """
    fleet_id: str
    organization: str
    fleet_name: str
    fleet_type: str
    dispatch_zone: str
    notes: str
    robot_ids: list[str]
    total_robot_count: int
    active_robot_count: int
    sanctioned_robot_count: int
    unsanctioned_robot_count: int
    idle_robot_count: int


class RobotCreateRequest(BaseModel):
    """
    Schema for onboarding a new robot into an existing organization fleet.
    """
    robot_id: str = Field(..., description="Unique robot identifier")
    organization: str = Field(..., description="Owning hospital organization")
    fleet_id: str = Field(..., description="Fleet assignment within the organization")
    serial_number: str = Field(..., description="Hardware serial number")
    last_serviced: str = Field(..., description="Most recent service timestamp")
    last_problem: str = Field("None", description="Latest known maintenance note")
    sanctioned: bool = Field(True, description="Whether the robot is approved for dispatch")
    battery: float = Field(..., ge=0.0, le=100.0, description="Current battery percentage")
    status: str = Field(..., description="Current robot state such as idle, transit, charging, or error")
    location: str = Field(..., description="Named map location where the robot is parked")
    x_m: float = Field(..., description="Current x-coordinate in meters")
    y_m: float = Field(..., description="Current y-coordinate in meters")


class UpdateSanctionRequest(BaseModel):
    """
    Schema to sanction or un-sanction a robot device. Un-sanctioning blocks tasks.
    """
    sanctioned: bool = Field(..., description="Set to False to take robot offline from accepting tasks")


class UpdateEdgeWeightRequest(BaseModel):
    """
    Schema to dynamically alter graph edge costs (e.g. adjust corridor congestion).
    """
    node_a: str = Field(..., description="First endpoint of the edge")
    node_b: str = Field(..., description="Second endpoint of the edge")
    weight: float = Field(..., gt=0.0, description="New cost weight metric for this corridor")


class AStarPlanRequest(BaseModel):
    """
    Request payload to calculate optimal routes between layout coordinates.
    """
    start_node: str = Field(..., description="The starting location in the hospital")
    goal_node: str = Field(..., description="The target destination")
