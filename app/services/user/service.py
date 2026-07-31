"""
File: app/services/user/service.py
Description: Contains the SQL-OLTP business logic layer for user accounts and profiles.
Provides standard functions for user lookup, secure credential verification, registration,
and RBAC role updates, integrated directly with SQLAlchemy sessions.
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from app.core.config import VALID_ROLES
from app.core.database import UserSQL
from app.services.user.schemas import UserCreate

logger = logging.getLogger("rovex.user_service")


def get_user_by_username(db: Session, username: str) -> Optional[UserSQL]:
    """
    Retrieves a user record from the SQLite OLTP database by their unique username.
    """
    return db.query(UserSQL).filter(UserSQL.username == username).first()


def authenticate_user(db: Session, username: str, password_raw: str) -> Optional[UserSQL]:
    """
    Verifies user login credentials by checking username existence and raw password.
    Returns the UserSQL record if authenticated, otherwise returns None.
    """
    user = get_user_by_username(db, username)
    if not user:
        logger.warning(f"Failed authentication attempt: user '{username}' not found.")
        return None
        
    # Standard password comparison
    if user.password == password_raw:
        logger.info(f"User '{username}' authenticated successfully.")
        return user
        
    logger.warning(f"Failed authentication attempt for '{username}': password mismatch.")
    return None


def create_user(db: Session, payload: UserCreate) -> UserSQL:
    """
    Inserts a new user record into the OLTP SQL database.
    Raises ValueError if the username is already registered.
    """
    existing_user = get_user_by_username(db, payload.username)
    if existing_user:
        raise ValueError(f"Username '{payload.username}' is already in use.")
        
    if payload.role not in VALID_ROLES:
        raise ValueError(f"Invalid role '{payload.role}'. Must be one of: {list(VALID_ROLES)}")

    db_user = UserSQL(
        username=payload.username,
        password=payload.password, # Plain text for demo simplicity
        role=payload.role,
        organization=payload.organization,
        full_name=payload.full_name,
        email=payload.email
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    logger.info(f"Created new user account: '{payload.username}' with role '{payload.role}' for organization '{payload.organization}'.")
    return db_user


def update_user_role(db: Session, username: str, new_role: str) -> UserSQL:
    """
    Modifies the RBAC role of a user.
    Raises ValueError if the user is not found or the role is invalid.
    """
    if new_role not in VALID_ROLES:
        raise ValueError(f"Invalid role '{new_role}'. Must be one of: {list(VALID_ROLES)}")

    user = get_user_by_username(db, username)
    if not user:
        raise ValueError(f"User '{username}' not found.")
        
    user.role = new_role
    db.commit()
    db.refresh(user)
    logger.info(f"Updated user role: '{username}' is now a '{new_role}'.")
    return user


def get_all_users(db: Session) -> List[UserSQL]:
    """
    Returns all registered users across all organizations.

    Results are ordered deterministically so admin dashboards and tests do not
    depend on database insertion order.
    """
    return db.query(UserSQL).order_by(UserSQL.organization.asc(), UserSQL.full_name.asc()).all()


def get_users_by_organization(db: Session, organization: str) -> List[UserSQL]:
    """
    Filters and returns users belonging to a specific institution.

    Ordering by full name keeps organization-scoped views stable and easier to scan.
    """
    return (
        db.query(UserSQL)
        .filter(UserSQL.organization == organization)
        .order_by(UserSQL.full_name.asc())
        .all()
    )
