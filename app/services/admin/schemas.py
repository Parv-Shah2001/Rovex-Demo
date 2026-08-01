"""
File: app/services/admin/schemas.py
Description: Pydantic schemas for the Rovex Admin domain. These request and
response contracts are kept separate from the router so the administrative
module remains self-contained and ready for future extraction.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SandboxQueryPayload(BaseModel):
    """
    Schema for validating DB queries run inside the admin sandbox.
    """
    db_type: str = Field(..., description="Target database engine: 'sql' or 'nosql'.")
    query_string: str = Field(..., description="Read-only SQL statement or PyMongo-style command string.")


class MetricDetailResponse(BaseModel):
    """
    Drill-down payload for an admin dashboard metric card.
    """
    metric_key: str
    title: str
    description: str
    summary: Dict[str, Any]
    items: List[Dict[str, Any]]


class SandboxCatalogResponse(BaseModel):
    """
    Discoverability payload for the advanced sandbox page.
    """
    sql_tables: List[str]
    sql_examples: List[str]
    nosql_collections: List[str]
    nosql_examples: List[str]
