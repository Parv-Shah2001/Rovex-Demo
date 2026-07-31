"""
File: app/services/user/router.py
Description: FastAPI Router exposing User Management and Authentication API endpoints.
Provides routes for user registration, session logins/logouts, profile queries,
and role configuration (RBAC updates). Endpoints utilize dependency injection for role checks.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.core.database import get_db
from app.core.auth import (
    create_access_token, 
    get_current_user_from_cookie_or_header, 
    RBACChecker,
    is_admin
)
from app.services.user.schemas import UserLoginRequest, UserCreate, UserResponse, RoleUpdatePayload
from app.services.user import service as user_service

router = APIRouter(prefix="/api/users", tags=["User Management"])


@router.post("/login", response_model=Dict[str, Any])
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
        
    # Generate cryptographic token (expires in 2 hours)
    token = create_access_token(user.username, user.role, user.organization)
    
    # Configure session cookie for HTML frontend views
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        max_age=7200,
        samesite="lax",
        secure=False  # Set to True in production with HTTPS
    )
    
    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": user.username,
            "role": user.role,
            "organization": user.organization,
            "full_name": user.full_name
        }
    }


@router.post("/logout")
def logout_user(response: Response):
    """
    Clears the access_token session cookies to log out the user.
    """
    response.delete_cookie("access_token")
    return {"status": "success", "detail": "Logged out successfully"}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    """
    Registers a new institution user into the OLTP database.
    This route can be accessed by anyone in the demo, but is typically constrained.
    """
    try:
        new_user = user_service.create_user(db, payload)
        return new_user
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
    if is_admin(current_user):
        return user_service.get_all_users(db)
    return user_service.get_users_by_organization(db, current_user["organization"])


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
