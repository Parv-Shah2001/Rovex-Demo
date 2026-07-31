"""
File: app/main.py
Description: Main entry point for the Rovex Hospital Stretcher Robots Backend Platform.
This file initializes the FastAPI application, sets up the HTML template rendering engine,
triggers database schema generation and initial seed loading, and mounts all the service
sub-routers (Users, Robots, Notifications, Core Platform, and Admin Dashboard).
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.core import config
from app.core.database import init_db

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

# Pre-load HTML templates from disk at module import time.
# This avoids any Jinja2/Starlette cache compatibility issues with newer versions
# while keeping the frontend rendering simple and dependency-free.
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

_html_cache: dict[str, tuple[int, str]] = {}
HTML_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _load_template(name: str) -> str:
    """
    Loads an HTML template directly from disk and records the latest snapshot.

    The templates in this demo are small, so prioritizing correctness over an
    aggressive cache avoids stale frontend markup when HTML files are edited
    while the application process remains alive.
    """
    template_path = TEMPLATES_DIR / name
    last_modified_ns = template_path.stat().st_mtime_ns
    template_content = template_path.read_text(encoding="utf-8")
    _html_cache[name] = (last_modified_ns, template_content)
    return template_content


def _html_response(name: str) -> HTMLResponse:
    """
    Returns an HTML response with explicit no-cache headers so browser reloads
    always fetch the newest dashboard markup during rapid UI iteration.
    """
    return HTMLResponse(content=_load_template(name), headers=HTML_NO_CACHE_HEADERS)


class NoCacheStaticFiles(StaticFiles):
    """
    Static files wrapper that disables browser caching for frontend assets.

    During active prototype iteration this ensures updated JavaScript bundles are
    re-fetched immediately, which keeps the plain-HTML frontend predictable even
    without a formal asset pipeline.
    """
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers.update(HTML_NO_CACHE_HEADERS)
        return response


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
app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")

# Enable CORS for frontend and API accessibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return _html_response("index.html")


@app.get("/core", response_class=HTMLResponse)
def serve_core_platform_page(request: Request):
    """
    Renders the face-to-face Core Platform dashboard for hospital staff.
    Uses browser client guard to verify authentications, but can also inspect cookies.
    """
    return _html_response("core_platform.html")


@app.get("/admin", response_class=HTMLResponse)
def serve_admin_platform_page(request: Request):
    """
    Renders the Admin Sandbox and database query tool.
    Restricted to Rovex Admins only. Client-side JS blocks non-admins, but we can also guard here.
    """
    return _html_response("admin.html")


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
