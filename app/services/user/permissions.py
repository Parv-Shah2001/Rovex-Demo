"""
File: app/services/user/permissions.py
Description: Authorization and validation helpers for the user-management domain.
These rules sit beside the user service so account provisioning policy stays
encapsulated within the user module instead of being duplicated in routers.
"""

from typing import Dict

from app.core.config import ROVEX_ORGANIZATION


def validate_role_organization_pair(role: str, organization: str) -> None:
    """
    Validates that the chosen role and organization combination is supported.

    Admin identities belong to Rovex itself, while hospital-scoped roles must
    belong to a non-Rovex organization.
    """
    if role == "admin" and organization != ROVEX_ORGANIZATION:
        raise ValueError("Admin accounts must belong to Rovex Robotics Inc.")
    if role != "admin" and organization == ROVEX_ORGANIZATION:
        raise ValueError("Hospital-scoped roles cannot belong to Rovex Robotics Inc.")


def ensure_user_creation_allowed(actor: Dict[str, str], role: str, organization: str) -> None:
    """
    Validates whether the current actor may create a user with the requested
    role and organization.

    Rovex admins may create any valid account. Hospital supervisors are limited
    to their own organization and may only provision sub-supervisors or employees.
    """
    actor_role = actor["role"]
    actor_org = actor["organization"]

    if actor_role == "admin":
        return

    if actor_role != "supervisor":
        raise ValueError("Only Rovex admins or hospital supervisors can provision users.")
    if organization != actor_org:
        raise ValueError("Supervisors can only create users within their own organization.")
    if role not in {"sub-supervisor", "employee"}:
        raise ValueError("Supervisors can only create sub-supervisor or employee accounts.")
