"""
File: app/services/user/router.py
Description: FastAPI Router exposing User Management and Authentication API endpoints.
Provides routes for user registration, session logins/logouts, profile queries,
and role configuration (RBAC updates). Endpoints utilize dependency injection for role checks.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.auth import RBACChecker, create_access_token, get_current_user_from_cookie_or_header
from app.core.config import ACCESS_TOKEN_EXPIRE_SECONDS
from app.core.database import get_db
from app.services.user import service as user_service
from app.services.user.responses import build_login_response
from app.services.user.schemas import LoginResponse, RoleUpdatePayload, UserCreate, UserLoginRequest, UserResponse

router = APIRouter(prefix="/api/users", tags=["User Management"])


@router.post("/login", response_model=LoginResponse)
def login_user(payload: UserLoginRequest, response: Response, db: Session = Depends(get_db)):
    """
    Logs in a user, issues a secure token, and configures an 'access_token' cookie 
    for browser compatibility alongside a standard JSON response.
    """
    user = user_service.authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
        
    token = create_access_token(user.username, user.role, user.organization)

    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
        samesite="lax",
        secure=False  # Set to True in production with HTTPS
    )

    return build_login_response(token, user)


@router.post("/logout")
def logout_user(response: Response):
    """
    Clears the access_token session cookies to log out the user.
    """
    response.delete_cookie("access_token")
    return {"status": "success", "detail": "Logged out successfully"}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserCreate,
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin", "supervisor"])),
    db: Session = Depends(get_db),
):
    """
    Registers a new institution user into the OLTP database.

    Account provisioning is intentionally restricted to Rovex admins and
    hospital supervisors so identity management stays aligned with the user
    domain's role and organization boundaries.
    """
    try:
        return user_service.create_user_for_actor(db, payload, current_user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header)):
    """
    Returns profile information of the currently authenticated session user.
    """
    return current_user


@router.get("", response_model=List[UserResponse])
def get_organization_members(
    current_user: Dict[str, Any] = Depends(get_current_user_from_cookie_or_header),
    db: Session = Depends(get_db)
):
    """
    Returns a list of staff members visible to the current user.
    - Rovex admins can see ALL users across every organization.
    - Hospital staff can only see members of their own organization.
    """
    return user_service.get_visible_users(db, current_user)


@router.put("/{username}/role", response_model=UserResponse)
def change_user_role(
    username: str,
    payload: RoleUpdatePayload,
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin"])),
    db: Session = Depends(get_db)
):
    """
    Allows a Rovex Admin to modify a user's role (RBAC level).
    Restricted to Rovex Admins only — this is a platform-level action.
    """
    try:
        # Prevent admins from self-demoting to keep system active in demo
        if current_user["username"] == username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Admins cannot demote themselves to ensure system remains manageable."
            )
            
        updated_user = user_service.update_user_role(db, username, payload.role)
        return updated_user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
