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

import hmac
import hashlib
import base64
import time
import logging
from typing import Iterable, List, Dict, Any, Optional
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import SECRET_KEY, ROLE_INHERITANCE, ROVEX_ORGANIZATION, VALID_ROLES
from app.core.database import get_db, UserSQL

logger = logging.getLogger("rovex.auth")

def create_access_token(username: str, role: str, organization: str, expires_in_seconds: int = 7200) -> str:
    """
    Creates a secure, signed token representing the user session.
    
    The token structure is: base64(payload) . hmac_signature
    Payload contains username, role, organization, and expiration timestamp.
    """
    expiration = int(time.time()) + expires_in_seconds
    payload_str = f"{username}:{role}:{organization}:{expiration}"
    payload_b64 = base64.b64encode(payload_str.encode("utf-8")).decode("utf-8")
    
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
        payload_str = base64.b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        username, role, organization, expiration_str = payload_str.split(":", 3)
        expiration = int(expiration_str)
        
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
    token = None
    
    # 1. Try resolving from cookie (useful for HTML templates and web UI)
    if "access_token" in request.cookies:
        token = request.cookies["access_token"]
        if token.startswith("Bearer "):
            token = token[7:]
            
    # 2. Try resolving from Authorization header (useful for API clients)
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            
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
