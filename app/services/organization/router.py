"""
File: app/services/organization/router.py
Description: FastAPI Router exposing organization-scoped management views.
The endpoints power admin organization pages and supervisor-facing organization
popups without duplicating hospital/fleet aggregation logic across portals.
"""

from typing import Any, Dict, List
from urllib.parse import unquote

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import RBACChecker, get_current_user_from_cookie_or_header
from app.core.database import MockDatabase, get_db, get_nosql_db
from app.services.organization import service as organization_service
from app.services.organization.schemas import OrganizationDetail, OrganizationSummary

router = APIRouter(prefix="/api/organizations", tags=["Organization Management"])


@router.get("", response_model=List[OrganizationSummary])
def list_visible_organizations(
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin", "supervisor", "sub-supervisor", "employee"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db),
):
    """
    Returns organization summaries visible to the current authenticated user.
    """
    return organization_service.get_visible_organizations(db_sql, db_nosql, current_user)


@router.get("/{organization_name}", response_model=OrganizationDetail)
def get_organization_detail(
    organization_name: str,
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin", "supervisor", "sub-supervisor", "employee"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db),
):
    """
    Returns a full organization detail payload, including controller tree,
    fleet details, and recent robot activity.
    """
    decoded_name = unquote(organization_name)
    return organization_service.get_organization_detail(db_sql, db_nosql, current_user, decoded_name)
