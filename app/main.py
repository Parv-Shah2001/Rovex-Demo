"""
File: app/main.py
Description: Main entry point for the Rovex Hospital Stretcher Robots Backend Platform.
This file initializes the FastAPI application, sets up the HTML template rendering engine 
via Jinja2, triggers database schema generation and initial seed loading, and mounts all 
the service sub-routers (Users, Robots, Notifications, Core Platform, and Admin Dashboard).
"""

import os
import logging
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from app.core import config
from app.core.database import init_db, get_db
from app.core.auth import verify_access_token

# Import routers from the distinct monolithic modules
from app.services.user.router import router as user_router
from app.services.robot.router import router as robot_router
from app.services.notification.router import router as notification_router
from app.services.admin.router import router as admin_router
from app.services.core_platform.router import router as core_platform_router

# Configure global application logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("rovex.main")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """
    FastAPI lifespan context manager. Triggers SQL and NoSQL memory database 
    tables creation and applies seed mock records.
    """
    logger.info("Starting up Rovex Platform Backend...")
    init_db()
    logger.info("Databases and seeds initialized successfully.")
    yield

app = FastAPI(
    title="Rovex Hospital Robotics Backend Platform",
    description="A modular, production-ready backend prototype for hospital stretcher robots.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend and API accessibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure Jinja2 templates directory
templates = Jinja2Templates(directory="app/templates")

# Initialize database schemas immediately to guarantee tables exist across all threads/sessions
init_db()


# =====================================================================
# FRONTEND TEMPLATE ROUTERS (Serving Web Dashboards)
# =====================================================================

@app.get("/", response_class=HTMLResponse)
def serve_index_page(request: Request):
    """
    Renders the unified landing page and login panel.
    """
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/core", response_class=HTMLResponse)
def serve_core_platform_page(request: Request):
    """
    Renders the face-to-face Core Platform dashboard for hospital staff.
    Uses browser client guard to verify authentications, but can also inspect cookies.
    """
    # Simply render template; client-side JS handles token decoding and RBAC verification
    return templates.TemplateResponse(request=request, name="core_platform.html")


@app.get("/admin", response_class=HTMLResponse)
def serve_admin_platform_page(request: Request):
    """
    Renders the Admin Sandbox and database query tool.
    Restricted to Supervisors. Client-side JS blocks non-admins, but we can also guard here.
    """
    return templates.TemplateResponse(request=request, name="admin.html")


# =====================================================================
# HEALTH AND SYSTEM DIAGNOSTICS ENDPOINTS
# =====================================================================

@app.get("/api/health", tags=["Diagnostics"])
def check_platform_health():
    """
    Diagnostic healthcheck route. Confirms app is active and logs configuration stats.
    """
    summary = config.get_config_summary()
    return {
        "status": "healthy",
        "timestamp": "2026-07-31T00:00:00Z",
        "system_summary": summary
    }


# =====================================================================
# MOUNT SERVICE MODULE SUB-ROUTERS
# =====================================================================

app.include_router(user_router)
app.include_router(robot_router)
app.include_router(notification_router)
app.include_router(admin_router)
app.include_router(core_platform_router)
