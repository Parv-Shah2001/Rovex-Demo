"""
File: app/services/admin/schemas.py
Description: Pydantic schemas for the Rovex Admin domain. These request and
response contracts are kept separate from the router so the administrative
module remains self-contained and ready for future extraction.
"""

from pydantic import BaseModel, Field


class SandboxQueryPayload(BaseModel):
    """
    Schema for validating DB queries run inside the admin sandbox.
    """
    db_type: str = Field(..., description="Target database engine: 'sql' or 'nosql'.")
    query_string: str = Field(..., description="Read-only SQL statement or PyMongo-style command string.")
