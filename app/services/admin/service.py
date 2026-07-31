"""
File: app/services/admin/service.py
Description: Administrative database sandbox and query service for Rovex platform operators.
Implements the backend of the secured admin sandbox, allowing Rovex admins to query
live databases across ALL organizations. Executes raw SQL queries against the
SQLAlchemy/SQLite engine, and parses PyMongo-like string queries (e.g., 'db.robots.find(...)')
to execute operations against the Mock PyMongo client.
"""

import json
import logging
import re
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import MockDatabase

logger = logging.getLogger("rovex.admin_service")


def _normalize_sql_query(sql_query: str) -> str:
    """
    Normalizes a raw SQL sandbox query while enforcing single-statement,
    read-only execution rules.

    The helper prevents command chaining and keeps write-capable statements out
    of the admin domain, which makes a future move to a dedicated analytics /
    inspection service safer.
    """
    sql_stripped = sql_query.strip()
    if not sql_stripped:
        raise ValueError("SQL query cannot be empty.")

    statement = sql_stripped[:-1].strip() if sql_stripped.endswith(";") else sql_stripped
    if ";" in statement:
        raise ValueError("Sandbox security policy violation: multiple SQL statements are not allowed.")

    lowered = statement.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("Sandbox security policy violation: Only read-only SELECT/CTE queries are allowed in this SQL workspace.")

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
    
    # Regex pattern: db.<collection>.<method>(<arguments>)
    pattern = r"^db\.([a-zA-Z0-9_-]+)\.(find|find_one)\((.*)\)$"
    match = re.match(pattern, query_stripped)
    
    if not match:
        raise ValueError(
            "NoSQL Sandbox Syntax Error. Supported operations: "
            "db.<collection>.find(<optional_json_filter>) and db.<collection>.find_one(<optional_json_filter>)\n"
            "Example: db.robots.find({\"battery\": {\"$lt\": 50}})"
        )
        
    collection_name = match.group(1)
    method_name = match.group(2)
    filter_args_str = match.group(3).strip()
    
    filter_dict = _parse_nosql_filter(filter_args_str)

    # Execute on mock PyMongo
    try:
        collection = db[collection_name]
        if method_name == "find":
            cursor = collection.find(filter_dict)
            return [document for document in cursor]
        elif method_name == "find_one":
            res = collection.find_one(filter_dict)
            return [res] if res else []
        else:
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
        
        robots = [robot for robot in db_nosql["robots"].find({})]
        robot_count = len(robots)
        online_robots = sum(1 for r in robots if r.get("status") in ["idle", "transit", "charging"] and r.get("sanctioned") is True)
        un_sanctioned_count = sum(1 for r in robots if r.get("sanctioned") is False)
        
        # Calculate average battery
        avg_battery = 0.0
        if robot_count > 0:
            avg_battery = sum(r.get("battery", 0.0) for r in robots) / robot_count
            
        return {
            "total_users": user_count,
            "total_tasks": task_count,
            "pending_tasks": pending_tasks,
            "completed_tasks": completed_tasks,
            "total_robots": robot_count,
            "online_robots": online_robots,
            "un_sanctioned_robots": un_sanctioned_count,
            "average_robot_battery": round(avg_battery, 1)
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard statistics: {e}")
        return {"error": f"Failed to retrieve dashboard stats: {e}"}
