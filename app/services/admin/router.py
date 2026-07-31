"""
File: app/services/admin/router.py
Description: FastAPI Router exposing administrative backend endpoints.
Provides routes to retrieve aggregated operational statistics and execute queries
against relational SQL and document NoSQL databases in a secured sandbox environment.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.core.database import get_db, get_nosql_db, MockDatabase
from app.core.auth import RBACChecker
from app.services.admin import service as admin_service

router = APIRouter(prefix="/api/admin", tags=["Admin Platform Services"])


class SandboxQueryPayload(BaseModel):
    """
    Schema for validating DB queries run inside the admin sandbox.
    """
    db_type: str = Field(..., description="'sql' or 'nosql'")
    query_string: str = Field(..., description="Raw SELECT statement or PyMongo command")


@router.get("/stats", response_model=Dict[str, Any])
def get_dashboard_statistics(
    current_user: Dict[str, Any] = Depends(RBACChecker(["supervisor"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Returns aggregated metrics spanning the entire hospital platform (robots, tasks, users).
    Restricted to Supervisors.
    """
    return admin_service.get_admin_dashboard_stats(db_sql, db_nosql)


@router.post("/query", response_model=Dict[str, Any])
def run_database_sandbox_query(
    payload: SandboxQueryPayload,
    current_user: Dict[str, Any] = Depends(RBACChecker(["supervisor"])),
    db_sql: Session = Depends(get_db),
    db_nosql: MockDatabase = Depends(get_nosql_db)
):
    """
    Runs a manual query in the secured sandbox environment.
    Supports standard SQL SELECT queries on SQLite (simulating Postgres OLTP),
    and PyMongo search commands on MongoDB.
    Restricted to Supervisors.
    """
    db_type_lower = payload.db_type.lower().strip()
    query_str = payload.query_string.strip()
    
    if not query_str:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query string cannot be empty.")
         
    try:
        if db_type_lower == "sql":
            results = admin_service.execute_sandbox_sql(db_sql, query_str)
            return {
                "status": "success",
                "db_type": "SQL (Postgres Simulated)",
                "record_count": len(results),
                "data": results
            }
        elif db_type_lower == "nosql":
            results = admin_service.execute_sandbox_nosql(db_nosql, query_str)
            return {
                "status": "success",
                "db_type": "NoSQL (MongoDB Mocked)",
                "record_count": len(results),
                "data": results
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid database type. Must be either 'sql' or 'nosql'."
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
