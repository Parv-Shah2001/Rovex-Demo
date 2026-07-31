"""
File: app/services/user/schemas.py
Description: Defines the Pydantic data schemas for validating user management requests and responses,
including authentication payloads, user registration data, role configurations, and profiles.
"""

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

class UserLoginRequest(BaseModel):
    """
    Schema for validating login requests.
    """
    username: str = Field(..., description="The unique username of the institution user")
    password: str = Field(..., description="The user's password")


class UserCreate(BaseModel):
    """
    Schema for creating a new user within the database.
    """
    username: str = Field(..., min_length=3, max_length=50, description="Unique username for the login credentials")
    password: str = Field(..., min_length=6, description="User password (will be stored securely)")
    role: str = Field(..., description="RBAC Role: 'admin', 'supervisor', 'sub-supervisor', or 'employee'")
    organization: str = Field(..., description="The hospital/institution organization name (e.g., 'St. Jude Hospital')")
    full_name: str = Field(..., description="Full name of the staff member")
    email: EmailStr = Field(..., description="Valid work email address")


class UserResponse(BaseModel):
    """
    Schema representing user profile metadata returned by endpoints.
    Does not expose sensitive credentials.
    """
    id: int
    username: str
    role: str
    organization: str
    full_name: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


class RoleUpdatePayload(BaseModel):
    """
    Schema representing user RBAC role policy updates.
    """
    role: str = Field(..., description="The new RBAC target role: 'admin', 'supervisor', 'sub-supervisor', or 'employee'")
