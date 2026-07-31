"""
File: app/core/auth.py
Description: Implements secure cryptographic token issuance and validation alongside 
Role-Based Access Control (RBAC) dependencies. It verifies token signatures via 
HMAC-SHA256 using the system SECRET_KEY, parses user identities, and implements FastAPI 
Dependency Injection checks to enforce the four-tier permission hierarchy:

    admin          — Rovex employee with platform-wide access across ALL organizations.
    supervisor     — Organization supervisor who manages robots and employees within their org.
    sub-supervisor — Organization sub-supervisor who can schedule tasks and view live status.
    employee       — Organization employee who is a viewer and can file service requests.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Iterable, List, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    ROLE_INHERITANCE,
    ROVEX_ORGANIZATION,
    SECRET_KEY,
    VALID_ROLES,
)
from app.core.database import UserSQL, get_db

logger = logging.getLogger("rovex.auth")


def _encode_token_payload(payload: Dict[str, Any]) -> str:
    """
    Serializes a token payload into base64 text.

    JSON encoding avoids delimiter bugs when organization names or future fields
    contain reserved characters such as colons.
    """
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return base64.b64encode(payload_json.encode("utf-8")).decode("utf-8")


def _decode_token_payload(payload_b64: str) -> Optional[Dict[str, Any]]:
    """
    Decodes a base64 token payload.

    The decoder accepts both the current JSON payload structure and the earlier
    colon-delimited legacy format so existing browser sessions can continue to
    function during rolling upgrades.
    """
    payload_str = base64.b64decode(payload_b64.encode("utf-8")).decode("utf-8")
    if payload_str.startswith("{"):
        return json.loads(payload_str)

    username, role, organization, expiration_str = payload_str.split(":", 3)
    return {
        "username": username,
        "role": role,
        "organization": organization,
        "expiration": int(expiration_str),
    }


def extract_bearer_token_from_request(request: Request) -> Optional[str]:
    """
    Extracts a bearer token from either the session cookie or Authorization header.
    """
    if "access_token" in request.cookies:
        token = request.cookies["access_token"]
        if token.startswith("Bearer "):
            return token[7:]
        return token

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def create_access_token(username: str, role: str, organization: str, expires_in_seconds: int = ACCESS_TOKEN_EXPIRE_SECONDS) -> str:
    """
    Creates a secure, signed token representing the user session.
    
    The token structure is: base64(payload) . hmac_signature
    Payload contains username, role, organization, and expiration timestamp.
    """
    expiration = int(time.time()) + expires_in_seconds
    payload_b64 = _encode_token_payload(
        {
            "username": username,
            "role": role,
            "organization": organization,
            "expiration": expiration,
        }
    )
    
    # Compute signature
    sig = hmac.new(
        SECRET_KEY.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    return f"{payload_b64}.{sig}"


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies the cryptographic signature of the token and checks for expiration.
    Returns a dictionary of token contents if valid, otherwise None.
    """
    try:
        if "." not in token:
            return None
        payload_b64, sig = token.split(".", 1)
        
        # Verify HMAC
        expected_sig = hmac.new(
            SECRET_KEY.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected_sig, sig):
            logger.warning("Invalid token signature detected.")
            return None
            
        # Decode and check expiration
        payload = _decode_token_payload(payload_b64)
        if not payload:
            return None

        username = payload.get("username")
        role = payload.get("role")
        organization = payload.get("organization")
        expiration = int(payload.get("expiration", 0))
        
        if time.time() > expiration:
            logger.warning(f"Token expired for user: {username}")
            return None

        if role not in VALID_ROLES:
            logger.warning(f"Token for user '{username}' contained unsupported role '{role}'.")
            return None
            
        return {
            "username": username,
            "role": role,
            "organization": organization
        }
    except Exception as e:
        logger.error(f"Error parsing access token: {e}")
        return None


def get_current_user_from_cookie_or_header(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Resolves the current authenticated user by checking the HTTP request.
    It inspects BOTH the standard Authorization Bearer header AND a session cookie 'access_token'.
    This hybrid setup is perfect for supporting API routes AND HTML frontend rendering seamlessly.
    """
    token = extract_bearer_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or credentials are invalid. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Check if user still exists in DB
    user = db.query(UserSQL).filter(UserSQL.username == payload["username"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The user associated with this session no longer exists.",
        )
        
    return {
        "username": user.username,
        "role": user.role,
        "organization": user.organization,
        "full_name": user.full_name,
        "email": user.email,
        "id": user.id
    }


def is_admin(user: Dict[str, Any]) -> bool:
    """
    Checks whether the given user dictionary represents a Rovex admin.

    The explicit organization check protects future refactors from accidentally
    granting global access to any hospital-scoped user record mislabeled as admin.
    """
    return user.get("role") == "admin" and user.get("organization") == ROVEX_ORGANIZATION


def role_allows_access(user_role: str, allowed_roles: Iterable[str]) -> bool:
    """
    Resolves whether a concrete role satisfies a route requirement.

    The helper centralizes the role-inheritance policy so routers and services do
    not need to duplicate privilege expansion logic whenever modular boundaries
    evolve over time.
    """
    inherited_roles = ROLE_INHERITANCE.get(user_role, ())
    return any(role in inherited_roles for role in allowed_roles)


def can_access_organization(user: Dict[str, Any], organization: str) -> bool:
    """
    Returns True when the current user may inspect or mutate organization-scoped
    resources for the supplied organization.
    """
    return is_admin(user) or user.get("organization") == organization


def ensure_organization_access(user: Dict[str, Any], organization: str, detail: str) -> None:
    """
    Raises HTTP 403 when a user attempts to access another hospital's data.

    The explicit helper keeps organization scoping rules in the shared core layer
    instead of scattering near-duplicate checks across multiple service routers.
    """
    if not can_access_organization(user, organization):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class RBACChecker:
    """
    Enforces route-level access permissions based on a four-tier role hierarchy.
    
    Roles (in descending privilege):
      - admin:          Rovex platform operator — has unrestricted access to ALL endpoints
                        and can see data across ALL organizations (not scoped to one org).
      - supervisor:     Organization supervisor — can manage all robots and employees
                        within their own organization.
      - sub-supervisor: Organization sub-supervisor — can schedule tasks, view live status,
                        and adjust corridor weights within their own organization.
      - employee:       Organization employee — viewer only, can request access and file
                        service tickets.
    
    Hierarchical rules:
      - admin bypasses every role check.
      - supervisor automatically inherits sub-supervisor and employee permissions.
      - sub-supervisor automatically inherits employee permissions.
    """
    def __init__(self, allowed_roles: List[str]):
        """
        Registers which roles are allowed to access the specific endpoint.
        """
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header)) -> Dict[str, Any]:
        """
        Executes the role permission check. Raises HTTP 403 Forbidden if the user's role 
        is not within the allowed_roles list or the hierarchy.
        """
        user_role = current_user["role"]

        if role_allows_access(user_role, self.allowed_roles):
            return current_user

        logger.warning(
            "User %s with role '%s' denied access to resource requiring %s",
            current_user["username"],
            user_role,
            self.allowed_roles,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. This action requires one of these roles: {self.allowed_roles}. Your current role is: '{user_role}'"
        )
