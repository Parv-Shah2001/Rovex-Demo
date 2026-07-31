"""
File: tests/test_platform.py
Description: Full test suite for the Rovex hospital backend platform.
Validates:
  1. Cryptographic token signing and validation (HMAC-SHA256).
  2. SQL user account creation, verification, and RBAC updates.
  3. Admin vs Supervisor role separation and access scoping.
  4. NoSQL robot profile queries and live battery/localization updates.
  5. A* pathfinding calculations, distances, and edge weight modifiers.
  6. Notification logging and raw physical system log retrieval.
"""

import os
import uuid
import unittest
import json
from datetime import datetime
from sqlalchemy.orm import Session

from app.core import config
from app.core.auth import create_access_token, verify_access_token, is_admin
from app.core.database import SessionLocal, TaskSQL, Base, engine, init_db, nosql_db
from app.services.user import service as user_service
from app.services.user.schemas import UserCreate
from app.services.robot import service as robot_service
from app.services.robot.schemas import RobotTelemetryPayload
from app.services.robot.astar import HospitalGraph, plan_astar_path, hospital_map
from app.services.notification import service as notification_service
from app.services.admin import service as admin_service
from app.services.core_platform.router import schedule_transit_task
from app.services.core_platform.schemas import TaskCreatePayload
from app.main import (
    serve_core_platform_page,
    serve_index_page,
    serve_admin_platform_page,
    _load_template,
    _html_cache,
    TEMPLATES_DIR,
    HTML_NO_CACHE_HEADERS,
)


class TestRovexPlatform(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """
        Executes once before starting tests. Initializes the SQLite schemas and seeds.
        """
        init_db()

    def setUp(self):
        """
        Executes before every individual test to open an active SQL transaction.
        """
        self.db_sql = SessionLocal()

    def tearDown(self):
        """
        Executes after every individual test to clean up SQL resources.
        """
        self.db_sql.close()

    # =====================================================================
    # 1. AUTHENTICATION & CRYPTOGRAPHY TESTS
    # =====================================================================
    def test_cryptographic_tokens(self):
        """
        Tests HMAC-SHA256 signature token creation and verifying mechanism.
        Checks that expired or modified payloads are correctly invalidated.
        """
        username = "rovex_admin"
        role = "admin"
        org = "Rovex Robotics Inc."
        
        # Create a valid token (expires in 2 hours)
        token = create_access_token(username, role, org, expires_in_seconds=7200)
        self.assertTrue(len(token) > 0)
        self.assertIn(".", token)
        
        # Verify token
        payload = verify_access_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["username"], username)
        self.assertEqual(payload["role"], role)
        self.assertEqual(payload["organization"], org)
        
        # Test expiration invalidation
        expired_token = create_access_token(username, role, org, expires_in_seconds=-10)
        self.assertIsNone(verify_access_token(expired_token))
        
        # Test signature tampering invalidation
        tampered_token = token + "modified"
        self.assertIsNone(verify_access_token(tampered_token))

        # JSON payload format should safely preserve organizations containing delimiters.
        colon_org_token = create_access_token("triage_bot", "supervisor", "St. Jude Hospital: Wing A")
        colon_org_payload = verify_access_token(colon_org_token)
        self.assertIsNotNone(colon_org_payload)
        self.assertEqual(colon_org_payload["organization"], "St. Jude Hospital: Wing A")


    # =====================================================================
    # 2. ADMIN VS SUPERVISOR ROLE SEPARATION TESTS
    # =====================================================================
    def test_admin_vs_supervisor_role_separation(self):
        """
        Validates that the admin role belongs to Rovex (platform-wide access)
        while the supervisor role belongs to a hospital organization (org-scoped access).
        Tests the is_admin helper function and organization scoping.
        """
        # Admin user — belongs to Rovex
        admin_user = {"username": "rovex_admin", "role": "admin", "organization": "Rovex Robotics Inc."}
        self.assertTrue(is_admin(admin_user))
        
        # Supervisor user — belongs to a hospital
        supervisor_user = {"username": "sup_sarah", "role": "supervisor", "organization": "St. Jude Hospital"}
        self.assertFalse(is_admin(supervisor_user))
        
        # Admin sees all robots across organizations
        all_robots = robot_service.get_all_robots(nosql_db)
        admin_visible = len(all_robots)
        
        # Supervisor sees only robots in their own organization
        st_jude_robots = robot_service.get_robots_by_organization(nosql_db, "St. Jude Hospital")
        supervisor_visible = len(st_jude_robots)
        
        # Admin should see more robots than a single-org supervisor
        self.assertGreater(admin_visible, supervisor_visible)
        self.assertEqual(admin_visible, 4)  # All 4 seed robots
        self.assertEqual(supervisor_visible, 3)  # St. Jude has 3 robots


    # =====================================================================
    # 3. USER SQL OLTP & RBAC TESTS
    # =====================================================================
    def test_sql_user_creation_and_rbac(self):
        """
        Verifies adding users, authenticating credentials, and applying role shifts (RBAC).
        """
        unique_username = "test_nurse_33"
        user_payload = UserCreate(
            username=unique_username,
            password="securepassword123",
            role="employee",
            organization="St. Jude Hospital",
            full_name="Nurse Sarah Connor",
            email="sarah.connor@stjude.org"
        )
        
        # Create user
        user = user_service.create_user(self.db_sql, user_payload)
        self.assertEqual(user.username, unique_username)
        self.assertEqual(user.role, "employee")
        
        # Double creation should fail (username unique constraint)
        with self.assertRaises(ValueError):
            user_service.create_user(self.db_sql, user_payload)
            
        # Authenticate
        authenticated = user_service.authenticate_user(self.db_sql, unique_username, "securepassword123")
        self.assertIsNotNone(authenticated)
        self.assertEqual(authenticated.username, unique_username)
        
        # Wrong password should fail authentication
        failed = user_service.authenticate_user(self.db_sql, unique_username, "wrongpass")
        self.assertIsNone(failed)
        
        # Change User Role (RBAC shift)
        updated = user_service.update_user_role(self.db_sql, unique_username, "sub-supervisor")
        self.assertEqual(updated.role, "sub-supervisor")

        # Invalid organization/role combinations should be rejected.
        with self.assertRaises(ValueError):
            user_service.create_user(
                self.db_sql,
                UserCreate(
                    username="invalid_hq_employee",
                    password="securepassword123",
                    role="employee",
                    organization=config.ROVEX_ORGANIZATION,
                    full_name="Invalid HQ Employee",
                    email="invalid.hq@rovexrobotics.com",
                ),
            )

    def test_supervisor_provisioning_is_scoped_to_own_hospital(self):
        """
        Verifies supervisor-driven provisioning stays within the supervisor's own
        organization and cannot create elevated platform-wide accounts.
        """
        supervisor_actor = {
            "username": "sup_sarah",
            "role": "supervisor",
            "organization": "St. Jude Hospital",
        }

        created_user = user_service.create_user_for_actor(
            self.db_sql,
            UserCreate(
                username="ward_clerk_jane",
                password="securepassword123",
                role="employee",
                organization="St. Jude Hospital",
                full_name="Ward Clerk Jane",
                email="ward.clerk.jane@stjude.org",
            ),
            supervisor_actor,
        )
        self.assertEqual(created_user.organization, "St. Jude Hospital")

        with self.assertRaises(ValueError):
            user_service.create_user_for_actor(
                self.db_sql,
                UserCreate(
                    username="cross_org_user",
                    password="securepassword123",
                    role="employee",
                    organization="City General Hospital",
                    full_name="Cross Org User",
                    email="cross.org@citygeneral.org",
                ),
                supervisor_actor,
            )

        with self.assertRaises(ValueError):
            user_service.create_user_for_actor(
                self.db_sql,
                UserCreate(
                    username="rogue_admin",
                    password="securepassword123",
                    role="admin",
                    organization=config.ROVEX_ORGANIZATION,
                    full_name="Rogue Admin",
                    email="rogue.admin@rovexrobotics.com",
                ),
                supervisor_actor,
            )


    # =====================================================================
    # 4. ROBOT PROFILE & INGESTION TELEMETRY (NOSQL) TESTS
    # =====================================================================
    def test_nosql_robot_biodata_and_telemetry(self):
        """
        Verifies retrieving robot biodata from Mock MongoDB and checks that
        concurrent telemetry ingestion updates live status parameters and coordinates.
        """
        robot_id = "rovi-01"
        
        # Retrieve robot profile
        robot = robot_service.get_robot_by_id(nosql_db, robot_id)
        self.assertIsNotNone(robot)
        self.assertEqual(robot["robot_id"], robot_id)
        self.assertEqual(robot["organization"], "St. Jude Hospital")
        
        # Simulate concurrent telemetry packet ingestion
        telemetry_data = {
            "robot_id": robot_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "mission_id": "test-mission-104",
            "motion": {
                "speed_mps": 0.35,
                "steering_angle_rad": -0.1,
                "distance_traveled_m": 420.5
            },
            "battery": {
                "percentage": 82.5,
                "remaining_capacity_mah": 25500
            },
            "localization": {
                "x_m": 10.0,
                "y_m": 5.0,
                "heading_rad": 0.8
            },
            "safety": {
                "perception_enabled": True,
                "speed_reduced": False,
                "obstacle_stop": False,
                "emergency_stop": False
            },
            "system_health": {
                "cameras_online": 3,
                "lidar_online": True,
                "controller_connected": True
            }
        }
        
        # Validate using Pydantic
        payload = RobotTelemetryPayload(**telemetry_data)
        
        # Ingest telemetry
        ingested = robot_service.ingest_robot_telemetry(nosql_db, payload)
        self.assertEqual(ingested["robot_id"], robot_id)
        
        # Confirm live parameters updated in parent robot profile
        updated_robot = robot_service.get_robot_by_id(nosql_db, robot_id)
        self.assertEqual(updated_robot["battery"], 82.5)
        self.assertEqual(updated_robot["x_m"], 10.0)
        self.assertEqual(updated_robot["y_m"], 5.0)
        self.assertEqual(updated_robot["assigned_task_id"], "test-mission-104")
        self.assertEqual(updated_robot["status"], "transit")

    def test_nosql_robot_emergency_telemetry_preserves_error_status(self):
        """
        Verifies emergency-stop telemetry does not get overwritten back to a
        transit state simply because the payload still contains a mission ID.
        """
        telemetry_data = {
            "robot_id": "rovi-02",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "mission_id": "task-emergency-1",
            "motion": {
                "speed_mps": 0.0,
                "steering_angle_rad": 0.0,
                "distance_traveled_m": 12.0
            },
            "battery": {
                "percentage": 81.0,
                "remaining_capacity_mah": 24000
            },
            "localization": {
                "x_m": 5.0,
                "y_m": 5.0,
                "heading_rad": 0.0
            },
            "safety": {
                "perception_enabled": True,
                "speed_reduced": True,
                "obstacle_stop": True,
                "emergency_stop": True
            },
            "system_health": {
                "cameras_online": 3,
                "lidar_online": True,
                "controller_connected": True
            }
        }

        robot_service.ingest_robot_telemetry(nosql_db, RobotTelemetryPayload(**telemetry_data))
        updated_robot = robot_service.get_robot_by_id(nosql_db, "rovi-02")

        self.assertEqual(updated_robot["status"], "error")
        self.assertEqual(updated_robot["assigned_task_id"], "task-emergency-1")


    # =====================================================================
    # 5. A* PATHFINDING & ROUTING TESTS
    # =====================================================================
    def test_astar_route_planning(self):
        """
        Validates optimal route solver accuracy (A*) and checks edge weight modifiers.
        """
        # Run standard pathfinding from Reception to ICU
        result = plan_astar_path("Reception", "ICU", hospital_map)
        self.assertIsNotNone(result)
        self.assertIn("Reception", result["path"])
        self.assertIn("ICU", result["path"])
        self.assertEqual(result["path"][0], "Reception")
        self.assertEqual(result["path"][-1], "ICU")
        
        original_cost = result["total_cost"]
        
        # Modify the corridor weight between Reception and Nursing Station
        # Making it extremely high to simulate traffic jams
        success = hospital_map.update_edge_weight("Reception", "Nursing Station", 50.0)
        self.assertTrue(success)
        
        # Re-run pathfinding. The A* solver should bypass this corridor
        # for a cheaper path, altering the node sequence or increasing total cost.
        rerouted_result = plan_astar_path("Reception", "ICU", hospital_map)
        self.assertIsNotNone(rerouted_result)
        self.assertTrue(rerouted_result["total_cost"] > original_cost)
        
        # Restore weight
        hospital_map.update_edge_weight("Reception", "Nursing Station", 5.0)

    def test_astar_reopens_nodes_when_better_path_is_found(self):
        """
        Validates the planner can reconsider a node when a cheaper route is
        discovered later, which is required for optimal A* behavior.
        """
        custom_graph = HospitalGraph(
            nodes={
                "Start": {"x": 0.0, "y": 0.0, "description": "Start"},
                "Near": {"x": 5.0, "y": 0.0, "description": "Near but expensive branch"},
                "Mid": {"x": 0.0, "y": 1.0, "description": "Intermediate hop"},
                "Goal": {"x": 6.0, "y": 0.0, "description": "Goal"},
            },
            edges=[
                {"from": "Start", "to": "Near", "weight": 10.0},
                {"from": "Start", "to": "Mid", "weight": 1.0},
                {"from": "Mid", "to": "Near", "weight": 1.0},
                {"from": "Near", "to": "Goal", "weight": 1.0},
            ],
        )

        result = plan_astar_path("Start", "Goal", custom_graph)
        self.assertIsNotNone(result)
        self.assertEqual(result["path"], ["Start", "Mid", "Near", "Goal"])
        self.assertEqual(result["total_cost"], 3.0)


    # =====================================================================
    # 6. NOTIFICATION SERVICE & FILE LOG TESTS
    # =====================================================================
    def test_notification_and_logs(self):
        """
        Confirms notification categorization, priorities, and physical file stream logging.
        """
        # Log critical alert w.r.t robot rovi-03
        robot_id = "rovi-03"
        message = "Obstacle collision safety trigger activated!"
        
        alert = notification_service.log_system_notification(
            db=nosql_db,
            robot_id=robot_id,
            message=message,
            category="CRITICAL"
        )
        
        # Validate priority matching
        self.assertEqual(alert["category"], "CRITICAL")
        self.assertEqual(alert["priority"], 1) # Priority 1 is critical
        
        # Check NoSQL retrieval
        alerts_queried = notification_service.query_notifications(nosql_db, category="CRITICAL", robot_id=robot_id)
        self.assertTrue(len(alerts_queried) > 0)
        self.assertEqual(alerts_queried[0]["message"], message)
        
        # Check physical log file reading
        live_logs = notification_service.get_live_log_stream(lines_count=10)
        self.assertIn("rovi-03", live_logs)
        self.assertIn("CRITICAL", live_logs)
        self.assertIn("collision safety trigger", live_logs.lower())

    def test_notification_queries_are_scoped_by_organization_for_hospital_staff(self):
        """
        Verifies notification feeds remain organization-scoped for hospital users
        while Rovex admins retain global visibility.
        """
        notification_service.log_system_notification(
            db=nosql_db,
            robot_id="rovi-01",
            message="St. Jude scoped alert",
            category="GENERAL",
        )
        notification_service.log_system_notification(
            db=nosql_db,
            robot_id="rovi-03",
            message="City General scoped alert",
            category="GENERAL",
        )
        notification_service.log_system_notification(
            db=nosql_db,
            robot_id="FLEET",
            message="Queued St. Jude fleet alert",
            category="SUGGESTIONS",
            organization="St. Jude Hospital",
        )

        supervisor_user = {
            "username": "sup_sarah",
            "role": "supervisor",
            "organization": "St. Jude Hospital",
        }
        admin_user = {
            "username": "rovex_admin",
            "role": "admin",
            "organization": config.ROVEX_ORGANIZATION,
        }

        st_jude_alerts = notification_service.list_notifications_for_user(nosql_db, supervisor_user)
        admin_alerts = notification_service.list_notifications_for_user(nosql_db, admin_user)

        self.assertTrue(any(alert["message"] == "St. Jude scoped alert" for alert in st_jude_alerts))
        self.assertTrue(any(alert["message"] == "Queued St. Jude fleet alert" for alert in st_jude_alerts))
        self.assertFalse(any(alert["message"] == "City General scoped alert" for alert in st_jude_alerts))
        self.assertTrue(any(alert["message"] == "City General scoped alert" for alert in admin_alerts))

    def test_admin_scheduled_tasks_resolve_to_hospital_organization(self):
        """
        Verifies Rovex admins do not accidentally create tasks inside the Rovex
        organization namespace when dispatching hospital work without explicitly
        choosing a target robot first.
        """
        admin_user = {
            "username": "rovex_admin",
            "role": "admin",
            "organization": config.ROVEX_ORGANIZATION,
            "full_name": "James Whitfield",
        }
        payload = TaskCreatePayload(source_node="Reception", target_node="ICU")

        task = schedule_transit_task(payload, admin_user, self.db_sql, nosql_db)
        assigned_robot = robot_service.get_robot_by_id(nosql_db, task.robot_id)

        self.assertIsNotNone(task.robot_id)
        self.assertIsNotNone(assigned_robot)
        self.assertEqual(task.organization, assigned_robot["organization"])
        self.assertNotEqual(task.organization, config.ROVEX_ORGANIZATION)

        self.db_sql.query(TaskSQL).filter(TaskSQL.id == task.id).delete()
        self.db_sql.commit()
        robot_service.update_robot_status_and_location(
            db=nosql_db,
            robot_id=task.robot_id,
            status="idle",
            location="Reception",
            x_m=0.0,
            y_m=0.0,
            assigned_task_id=None,
        )

    def test_core_platform_template_uses_desktop_shell_layout(self):
        """
        Verifies the core platform template keeps the desktop shell in a horizontal
        layout so the sidebar stays on the left while the main content scrolls independently.
        """
        response = serve_core_platform_page(None)
        html = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("core-shell", html)
        self.assertIn("core-main", html)
        self.assertIn("core-main-header", html)
        self.assertIn("core-content-split", html)
        self.assertIn("core-content-panel", html)
        self.assertIn("core-sidebar", html)
        self.assertIn("sidebar-scrim", html)
        self.assertIn("sidebar-collapsed", html)
        self.assertIn("toggleSidebar()", html)
        self.assertIn("@media (min-width: 768px)", html)

    def test_admin_sandbox_rejects_mutating_sql_and_allows_read_only_ctes(self):
        """
        Verifies the admin SQL sandbox blocks mutating statements and still allows
        read-only common-table-expression queries used by analysts.
        """
        with self.assertRaises(ValueError):
            admin_service.execute_sandbox_sql(self.db_sql, "SELECT * FROM users; DELETE FROM users")

        cte_result = admin_service.execute_sandbox_sql(
            self.db_sql,
            "WITH scoped_users AS (SELECT username FROM users WHERE role = 'supervisor') SELECT * FROM scoped_users"
        )
        self.assertTrue(any(row["username"] == "sup_sarah" for row in cte_result))

    def test_html_dashboard_routes_disable_browser_caching(self):
        """
        Verifies the HTML dashboard responses explicitly disable caching so local
        browser refreshes pull the latest template markup during UI iteration.
        """
        for route_response in (
            serve_index_page(None),
            serve_core_platform_page(None),
            serve_admin_platform_page(None),
        ):
            self.assertEqual(route_response.status_code, 200)
            for header_name, header_value in HTML_NO_CACHE_HEADERS.items():
                self.assertEqual(route_response.headers.get(header_name), header_value)

    def test_template_loader_refreshes_changed_html_files(self):
        """
        Verifies the lightweight HTML loader refreshes cached content after a file
        changes so the running application does not keep serving stale templates.
        """
        template_name = f"_test_template_{uuid.uuid4().hex}.html"
        template_path = TEMPLATES_DIR / template_name

        try:
            template_path.write_text("version-one", encoding="utf-8")
            first_render = _load_template(template_name)

            template_path.write_text("version-two", encoding="utf-8")
            second_render = _load_template(template_name)

            self.assertEqual(first_render, "version-one")
            self.assertEqual(second_render, "version-two")
        finally:
            _html_cache.pop(template_name, None)
            if template_path.exists():
                template_path.unlink()


if __name__ == "__main__":
    unittest.main()
