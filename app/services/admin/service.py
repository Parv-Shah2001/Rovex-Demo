"""
File: app/services/admin/service.py
Description: Administrative database sandbox and query service.
Implements the backend of the secured admin sandbox, allowing live database querying.
Executes raw SQL queries against the SQLAlchemy/SQLite engine, and parses PyMongo-like
string queries (e.g., 'db.robots.find(...)') to execute operations against the Mock PyMongo client.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import MockDatabase, nosql_db

logger = logging.getLogger("rovex.admin_service")


def execute_sandbox_sql(db: Session, sql_query: str) -> List[Dict[str, Any]]:
    """
    Executes raw SQL statements against the OLTP SQL database.
    Only allows read-only (SELECT) statements in the sandbox to enforce security.
    """
    sql_stripped = sql_query.strip()
    
    # Simple read-only validation
    if not sql_stripped.lower().startswith("select"):
        raise ValueError("Sandbox security policy violation: Only 'SELECT' queries are allowed in this SQL workspace.")
        
    try:
        result = db.execute(text(sql_stripped))
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
    
    # Parse filter string to python dictionary
    filter_dict = {}
    if filter_args_str:
        try:
            # Replace single quotes with double quotes for valid JSON parsing if needed
            cleaned_args = filter_args_str.replace("'", '"')
            filter_dict = json.loads(cleaned_args)
        except Exception as e:
            raise ValueError(f"JSON Filter syntax error: could not parse '{filter_args_str}'. Error: {e}")
            
    # Execute on mock PyMongo
    try:
        collection = db[collection_name]
        if method_name == "find":
            cursor = collection.find(filter_dict)
            return cursor._data
        elif method_name == "find_one":
            res = collection.find_one(filter_dict)
            return [res] if res else []
        else:
            raise ValueError(f"Method '{method_name}' is not supported in the sandbox.")
    except Exception as e:
        logger.error(f"NoSQL Sandbox Exception: {e}")
        raise ValueError(f"NoSQL execution error: {e}")


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
        
        robots = db_nosql["robots"].find({})._data
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
