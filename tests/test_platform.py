"""
File: tests/test_platform.py
Description: Full test suite for the Rovex hospital backend platform.
Validates:
  1. Cryptographic token signing and validation (HMAC-SHA256).
  2. SQL user account creation, verification, and RBAC updates.
  3. NoSQL robot profile queries and live battery/localization updates.
  4. A* pathfinding calculations, distances, and edge weight modifiers.
  5. Notification logging and raw physical system log retrieval.
"""

import os
import unittest
import json
from datetime import datetime
from sqlalchemy.orm import Session

from app.core import config
from app.core.auth import create_access_token, verify_access_token
from app.core.database import SessionLocal, Base, engine, init_db, nosql_db
from app.services.user import service as user_service
from app.services.user.schemas import UserCreate
from app.services.robot import service as robot_service
from app.services.robot.schemas import RobotTelemetryPayload
from app.services.robot.astar import plan_astar_path, hospital_map
from app.services.notification import service as notification_service


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
        username = "admin"
        role = "supervisor"
        org = "St. Jude Hospital"
        
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


    # =====================================================================
    # 2. USER SQL OLTP & RBAC TESTS
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


    # =====================================================================
    # 3. ROBOT PROFILE & INGESTION TELEMETRY (NOSQL) TESTS
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


    # =====================================================================
    # 4. A* PATHFINDING & ROUTING TESTS
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


    # =====================================================================
    # 5. NOTIFICATION SERVICE & FILE LOG TESTS
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


if __name__ == "__main__":
    unittest.main()
