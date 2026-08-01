"""
File: app/services/admin/router.py
Description: FastAPI Router exposing administrative backend endpoints for Rovex staff.
Provides routes to retrieve aggregated operational statistics, metric drill-down
payloads, sandbox discovery metadata, and advanced query execution across the
modular monolith's SQL and NoSQL data stores.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import RBACChecker
from app.core.database import MockDatabase, get_db, get_nosql_db
from app.services.admin import service as admin_service
from app.services.admin.schemas import MetricDetailResponse, SandboxCatalogResponse, SandboxQueryPayload

router = APIRouter(prefix="/api/admin", tags=["Admin Platform Services"])


@router.get("/stats", response_model=Dict[str, Any])
def get_dashboard_statistics(
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Returns aggregated metrics spanning the entire hospital platform.
    Restricted to Rovex admins only.
    """
    return admin_service.get_admin_dashboard_stats(db_sql, db_nosql)


@router.get("/stats/details", response_model=MetricDetailResponse)
def get_metric_detail(
    metric: str = Query(..., description="Metric key to expand, e.g. total_users or total_robots."),
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db),
):
    """
    Returns a drill-down payload for a clickable admin metric card.
    """
    try:
        return admin_service.get_metric_detail(db_sql, db_nosql, metric)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/sandbox/catalog", response_model=SandboxCatalogResponse)
def get_sandbox_catalog(
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db),
):
    """
    Returns schema-discovery metadata and example queries for the advanced sandbox page.
    """
    return admin_service.get_sandbox_catalog(db_sql, db_nosql)


@router.post("/query", response_model=Dict[str, Any])
def run_database_sandbox_query(
    payload: SandboxQueryPayload,
    current_user: Dict[str, Any] = Depends(RBACChecker(["admin"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Runs a manual query in the secured sandbox environment.
    Supports read-oriented SQL inspection and supported PyMongo-style NoSQL exploration.
    Restricted to Rovex Admins only.
    """
    db_type_lower = payload.db_type.lower().strip()
    query_str = payload.query_string.strip()

    if not query_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query string cannot be empty.")

    try:
        return admin_service.run_sandbox_query(db_sql, db_nosql, db_type_lower, query_str)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
