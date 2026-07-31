"""
File: app/services/user/responses.py
Description: Small response-construction helpers for the user-management domain.
These helpers keep router responses consistent while avoiding transport-layer
boilerplate scattered across future login and session endpoints.
"""

from typing import Any, Dict

from app.core.database import UserSQL


def build_login_response(token: str, user: UserSQL) -> Dict[str, Any]:
    """
    Builds the canonical login response payload returned by the authentication
    endpoint.
    """
    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user.username,
            "role": user.role,
            "organization": user.organization,
            "full_name": user.full_name,
        },
    }
