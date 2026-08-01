"""
File: app/services/admin/service.py
Description: Administrative database sandbox and query service for Rovex platform operators.
Implements the backend of the secured admin sandbox, allowing Rovex admins to query
live databases across ALL organizations. Executes raw SQL queries against the
SQLAlchemy/SQLite engine, and parses PyMongo-like string queries (e.g., 'db.robots.find(...)')
to execute operations against the Mock PyMongo client.
"""

import ast
import json
import logging
import re
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import ROVEX_ORGANIZATION
from app.core.database import MockDatabase, TaskSQL, UserSQL
from app.services.organization import service as organization_service
from app.services.robot import service as robot_service

logger = logging.getLogger("rovex.admin_service")


def _normalize_sql_query(sql_query: str) -> str:
    """
    Normalizes a raw SQL sandbox query while enforcing single-statement,
    inspection-only execution rules.

    The helper allows SELECT/CTE/PRAGMA style inspection plus convenience admin
    commands such as SHOW TABLES and DESCRIBE, while blocking write-capable or
    schema-mutating commands.
    """
    sql_stripped = sql_query.strip()
    if not sql_stripped:
        raise ValueError("SQL query cannot be empty.")

    statement = sql_stripped[:-1].strip() if sql_stripped.endswith(";") else sql_stripped
    if ";" in statement:
        raise ValueError("Sandbox security policy violation: multiple SQL statements are not allowed.")

    lowered = statement.lower()
    forbidden_prefixes = ("delete", "alter", "drop", "truncate", "insert", "update", "replace", "create")
    if lowered.startswith(forbidden_prefixes):
        raise ValueError("Sandbox security policy violation: destructive or mutating SQL commands are not allowed.")

    if lowered == "show tables":
        return "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    if lowered.startswith("describe "):
        table_name = statement.split(None, 1)[1].strip().strip('`"')
        if not table_name:
            raise ValueError("DESCRIBE requires a table name.")
        return f"PRAGMA table_info('{table_name}')"
    if lowered.startswith("show columns from "):
        table_name = statement.split("from", 1)[1].strip().strip('`"')
        if not table_name:
            raise ValueError("SHOW COLUMNS FROM requires a table name.")
        return f"PRAGMA table_info('{table_name}')"

    if not (lowered.startswith("select") or lowered.startswith("with") or lowered.startswith("pragma")):
        raise ValueError("Sandbox security policy violation: only inspection-oriented SQL queries are allowed in this workspace.")

    return statement


def _parse_nosql_filter(filter_args_str: str) -> Dict[str, Any]:
    """
    Parses a PyMongo-style filter string into a Python dictionary.
    """
    if not filter_args_str:
        return {}

    try:
        cleaned_args = filter_args_str.replace("'", '"')
        return json.loads(cleaned_args)
    except Exception as e:
        raise ValueError(f"JSON Filter syntax error: could not parse '{filter_args_str}'. Error: {e}")


def execute_sandbox_sql(db: Session, sql_query: str) -> List[Dict[str, Any]]:
    """
    Executes raw SQL statements against the OLTP SQL database.
    Only allows read-only (SELECT) statements in the sandbox to enforce security.
    """
    normalized_query = _normalize_sql_query(sql_query)

    try:
        result = db.execute(text(normalized_query))
        # Parse mappings to key-value dicts
        columns = result.keys()
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return rows
    except Exception as e:
        logger.error(f"SQL Sandbox Exception: {e}")
        raise ValueError(f"SQL execution error: {e}")


def _normalize_nosql_literal(value: str) -> Any:
    """
    Parses a simple JavaScript/Python-like literal used in sandbox commands.
    """
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return ast.literal_eval(candidate)
    except Exception:
        return _parse_nosql_filter(candidate)


def _split_method_arguments(argument_string: str) -> List[str]:
    """
    Splits a method argument string while respecting nested brackets and quotes.
    """
    arguments: List[str] = []
    current: List[str] = []
    depth = 0
    quote_char = None
    escape = False

    for char in argument_string:
        if escape:
            current.append(char)
            escape = False
            continue
        if char == "\\":
            current.append(char)
            escape = True
            continue
        if quote_char:
            current.append(char)
            if char == quote_char:
                quote_char = None
            continue
        if char in {'\"', "'"}:
            current.append(char)
            quote_char = char
            continue
        if char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        if char == "," and depth == 0:
            arguments.append("".join(current).strip())
            current = []
            continue
        current.append(char)

    tail = "".join(current).strip()
    if tail:
        arguments.append(tail)
    return arguments


def execute_sandbox_nosql(db: MockDatabase, query_str: str) -> List[Dict[str, Any]]:
    """
    Parses and executes PyMongo-style string queries against the mock NoSQL database.
    Supported format: db.<collection>.<method>(<json_filter>)
    Examples:
       db.robots.find()
       db.robots.find({"battery": {"$lt": 50}})
       db.notifications.find_one({"category": "CRITICAL"})
    """
    query_stripped = query_str.strip()

    if query_stripped == "db.listCollections()":
        return [{"name": name} for name in sorted(db._collections.keys())]

    # Regex pattern: db.<collection>.<method>(<arguments>)
    pattern = r"^db\.([a-zA-Z0-9_-]+)\.(find|find_one|distinct|aggregate|countDocuments)\((.*)\)$"
    match = re.match(pattern, query_stripped)

    if not match:
        raise ValueError(
            "NoSQL Sandbox Syntax Error. Supported operations: "
            "db.listCollections(), db.<collection>.find(...), find_one(...), distinct(...), aggregate(...), and countDocuments(...)."
        )

    collection_name = match.group(1)
    method_name = match.group(2)
    raw_arguments = match.group(3).strip()
    arguments = _split_method_arguments(raw_arguments) if raw_arguments else []

    try:
        collection = db[collection_name]
        if method_name == "find":
            filter_dict = _parse_nosql_filter(arguments[0]) if arguments else {}
            return [document for document in collection.find(filter_dict)]
        if method_name == "find_one":
            filter_dict = _parse_nosql_filter(arguments[0]) if arguments else {}
            result = collection.find_one(filter_dict)
            return [result] if result else []
        if method_name == "distinct":
            if not arguments:
                raise ValueError("distinct requires at least a field name.")
            field_name = str(_normalize_nosql_literal(arguments[0]))
            filter_dict = _parse_nosql_filter(arguments[1]) if len(arguments) > 1 else {}
            return [{field_name: value} for value in collection.distinct(field_name, filter_dict)]
        if method_name == "aggregate":
            if len(arguments) != 1:
                raise ValueError("aggregate requires a single pipeline argument.")
            pipeline = _normalize_nosql_literal(arguments[0])
            if not isinstance(pipeline, list):
                raise ValueError("aggregate pipeline must be a list of stages.")
            return [document for document in collection.aggregate(pipeline)]
        if method_name == "countDocuments":
            filter_dict = _parse_nosql_filter(arguments[0]) if arguments else {}
            return [{"count": collection.count_documents(filter_dict)}]
        raise ValueError(f"Method '{method_name}' is not supported in the sandbox.")
    except Exception as e:
        logger.error(f"NoSQL Sandbox Exception: {e}")
        raise ValueError(f"NoSQL execution error: {e}")


def run_sandbox_query(
    db_sql: Session,
    db_nosql: MockDatabase,
    db_type: str,
    query_str: str,
) -> Dict[str, Any]:
    """
    Executes a sandbox query and returns a normalized response payload.

    Centralizing the branching keeps the router transport-focused and leaves the
    admin service responsible for domain-specific query semantics.
    """
    db_type_lower = db_type.lower().strip()
    if db_type_lower == "sql":
        results = execute_sandbox_sql(db_sql, query_str)
        return {
            "status": "success",
            "db_type": "SQL (Postgres Simulated)",
            "record_count": len(results),
            "data": results,
        }
    if db_type_lower == "nosql":
        results = execute_sandbox_nosql(db_nosql, query_str)
        return {
            "status": "success",
            "db_type": "NoSQL (MongoDB Mocked)",
            "record_count": len(results),
            "data": results,
        }
    raise ValueError("Invalid database type. Must be either 'sql' or 'nosql'.")


def get_sandbox_catalog(db_sql: Session, db_nosql: MockDatabase) -> Dict[str, Any]:
    """
    Returns database discovery metadata and example queries for the advanced sandbox page.
    """
    sql_tables_result = db_sql.execute(text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
    sql_tables = [row[0] for row in sql_tables_result.fetchall()]
    nosql_collections = sorted(db_nosql._collections.keys())
    return {
        "sql_tables": sql_tables,
        "sql_examples": [
            "SHOW TABLES",
            "DESCRIBE users",
            "SELECT * FROM users",
            "WITH supervisors AS (SELECT username FROM users WHERE role='supervisor') SELECT * FROM supervisors",
        ],
        "nosql_collections": nosql_collections,
        "nosql_examples": [
            "db.listCollections()",
            "db.robots.find({\"battery\": {\"$lt\": 50}})",
            "db.fleets.aggregate([{\"$match\": {\"organization\": \"St. Jude Hospital\"}}])",
            "db.notifications.countDocuments({\"category\": \"CRITICAL\"})",
        ],
    }


def get_metric_detail(db_sql: Session, db_nosql: MockDatabase, metric_key: str) -> Dict[str, Any]:
    """
    Builds a drill-down payload for a specific admin dashboard metric.
    """
    organizations = organization_service.get_visible_organizations(
        db_sql,
        db_nosql,
        {"role": "admin", "organization": ROVEX_ORGANIZATION},
    )
    fleets = robot_service.get_all_fleets(db_nosql)
    robots = robot_service.get_all_robots(db_nosql)
    tasks = db_sql.query(TaskSQL).order_by(TaskSQL.created_at.desc()).all()
    users = db_sql.query(UserSQL).order_by(UserSQL.organization.asc(), UserSQL.full_name.asc()).all()

    metrics = {
        "total_users": {
            "title": "Connected Users",
            "description": "All SQL-backed platform users grouped by organization and role.",
            "summary": {"count": len(users)},
            "items": [
                {
                    "username": user.username,
                    "full_name": user.full_name,
                    "role": user.role,
                    "organization": user.organization,
                }
                for user in users
            ],
        },
        "total_organizations": {
            "title": "Organizations",
            "description": "Hospital organizations currently represented in the platform.",
            "summary": {"count": len(organizations)},
            "items": organizations,
        },
        "total_fleets": {
            "title": "Registered Fleets",
            "description": "Organization-scoped fleets and their readiness totals.",
            "summary": {"count": len(fleets)},
            "items": fleets,
        },
        "total_robots": {
            "title": "Fleet Robots",
            "description": "All robots currently attached to fleets across organizations.",
            "summary": {"count": len(robots)},
            "items": robots,
        },
        "online_robots": {
            "title": "Online Robots",
            "description": "Robots currently in idle, transit, or charging states and still sanctioned.",
            "summary": {"count": sum(1 for robot in robots if robot.get("status") in {"idle", "transit", "charging"} and robot.get("sanctioned"))},
            "items": [robot for robot in robots if robot.get("status") in {"idle", "transit", "charging"} and robot.get("sanctioned")],
        },
        "pending_tasks": {
            "title": "Pending Tasks",
            "description": "Tasks waiting for a fleet robot assignment or execution slot.",
            "summary": {"count": sum(1 for task in tasks if task.status == "pending")},
            "items": [
                {"task_id": task.id, "organization": task.organization, "source": task.source_node, "target": task.target_node}
                for task in tasks if task.status == "pending"
            ],
        },
        "completed_tasks": {
            "title": "Completed Tasks",
            "description": "Historical tasks already completed by hospital fleets.",
            "summary": {"count": sum(1 for task in tasks if task.status == "completed")},
            "items": [
                {"task_id": task.id, "organization": task.organization, "robot_id": task.robot_id, "source": task.source_node, "target": task.target_node}
                for task in tasks if task.status == "completed"
            ],
        },
        "average_robot_battery": {
            "title": "Average Fleet Battery",
            "description": "Battery state for each robot contributing to the fleet-wide average.",
            "summary": {"average_battery": round(sum(robot.get("battery", 0.0) for robot in robots) / len(robots), 1) if robots else 0.0},
            "items": [
                {"robot_id": robot["robot_id"], "fleet_id": robot["fleet_id"], "organization": robot["organization"], "battery": robot["battery"]}
                for robot in sorted(robots, key=lambda item: item["battery"], reverse=True)
            ],
        },
        "un_sanctioned_robots": {
            "title": "Unsanctioned Robots",
            "description": "Robots currently blocked from dispatch until sanction is restored.",
            "summary": {"count": sum(1 for robot in robots if robot.get("sanctioned") is False)},
            "items": [robot for robot in robots if robot.get("sanctioned") is False],
        },
    }

    if metric_key not in metrics:
        raise ValueError(f"Unsupported metric key '{metric_key}'.")

    payload = metrics[metric_key]
    return {
        "metric_key": metric_key,
        **payload,
    }


def get_admin_dashboard_stats(db_sql: Session, db_nosql: MockDatabase) -> Dict[str, Any]:
    """
    Retrieves global statistics for the Admin Platform dashboard, consolidating
    counts and ratios across SQL and NoSQL sources.
    """
    try:
        from app.core.database import UserSQL, TaskSQL
        
        user_count = db_sql.query(UserSQL).count()
        task_count = db_sql.query(TaskSQL).count()
        pending_tasks = db_sql.query(TaskSQL).filter(TaskSQL.status == "pending").count()
        completed_tasks = db_sql.query(TaskSQL).filter(TaskSQL.status == "completed").count()
        
        organizations = [organization for organization in db_nosql["organizations"].find({})]
        fleets = [fleet for fleet in db_nosql["fleets"].find({})]
        robots = [robot for robot in db_nosql["robots"].find({})]
        organization_count = len(organizations)
        fleet_count = len(fleets)
        robot_count = len(robots)
        online_robots = sum(1 for r in robots if r.get("status") in ["idle", "transit", "charging"] and r.get("sanctioned") is True)
        un_sanctioned_count = sum(1 for r in robots if r.get("sanctioned") is False)

        avg_battery = 0.0
        if robot_count > 0:
            avg_battery = sum(r.get("battery", 0.0) for r in robots) / robot_count
            
        return {
            "total_users": user_count,
            "total_organizations": organization_count,
            "total_tasks": task_count,
            "pending_tasks": pending_tasks,
            "completed_tasks": completed_tasks,
            "total_fleets": fleet_count,
            "total_robots": robot_count,
            "online_robots": online_robots,
            "un_sanctioned_robots": un_sanctioned_count,
            "average_robot_battery": round(avg_battery, 1)
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard statistics: {e}")
        return {"error": f"Failed to retrieve dashboard stats: {e}"}
