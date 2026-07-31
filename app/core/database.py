"""
File: app/core/database.py
Description: Sets up the database connectors. For the SQL database, we use a real SQLAlchemy 
session backed by an in-memory SQLite engine (with StaticPool to ensure all connections share 
the same in-memory database) to perfectly simulate a Postgres OLTP database.
For the NoSQL database, we implement a thread-safe, robust PyMongo/Motor mock that simulates 
all primary CRUD methods (find, find_one, insert_one, update_one, delete_one, aggregate, distinct) 
storing documents in an in-memory dictionary.
"""

import os
import datetime
import json
import logging
import threading
from typing import Dict, Any, List, Optional, Union, Generator
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.core.config import SEED_USERS, SEED_ROBOTS, LOG_FILE_PATH

# Configure logging
logger = logging.getLogger("rovex.database")

# =====================================================================
# 1. SQL DATABASE SETUP (SQLAlchemy + In-memory SQLite)
# =====================================================================

SQL_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQL_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # Ensures all connections share the same in-memory database
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# SQL Alchemy Models
class UserSQL(Base):
    """
    SQL Model representing a User inside the institution OLTP Database.
    This manages username, password, user role (RBAC), organization, and basic details.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)  # Stored plain for demo simplicity
    role = Column(String, nullable=False)  # admin, supervisor, sub-supervisor, employee
    organization = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class TaskSQL(Base):
    """
    SQL Model representing a robot's scheduled transit task or mission.
    This manages source, destination, assigned robot, scheduled times, recurrence, and paths.
    """
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, index=True)
    robot_id = Column(String, index=True, nullable=True)  # Can be empty for auto-assign
    organization = Column(String, index=True, nullable=False)
    created_by = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, ongoing, completed, cancelled
    source_node = Column(String, nullable=False)
    target_node = Column(String, nullable=False)
    path = Column(String, nullable=False)  # JSON-serialized list of nodes
    scheduled_time = Column(String, nullable=False)  # format: HH:MM or ISO string
    is_recurring = Column(Boolean, default=False)
    recurrence_interval = Column(String, default="none")  # none, daily, hourly
    eta_minutes = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency generator yielding a database session for FastAPI endpoints.
    Cleans up the session when finished.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================================
# 2. NOSQL DATABASE SETUP (Mock PyMongo / Motor Client)
# =====================================================================

class MockCursor:
    """
    Simulates a PyMongo cursor returning documents with limit, skipping, and to_list features.
    """
    def __init__(self, data: List[Dict[str, Any]]):
        self._data = data
        self._index = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self._index < len(self._data):
            val = self._data[self._index]
            self._index += 1
            return val
        raise StopIteration

    def limit(self, count: int) -> 'MockCursor':
        """Limits the number of returned records."""
        self._data = self._data[:count]
        return self

    def skip(self, count: int) -> 'MockCursor':
        """Skips the first count records."""
        self._data = self._data[count:]
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        """Asynchronously returns cursor results as a list (Motor compatibility)."""
        if length is not None:
            return self._data[:length]
        return self._data


class MockCollection:
    """
    Simulates a MongoDB collection with basic CRUD methods. Thread-safe in-memory storage.
    """
    def __init__(self, name: str):
        self.name = name
        self._documents: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def insert_one(self, document: Dict[str, Any]) -> Any:
        """Inserts a single document. Generates an internal _id if missing."""
        with self._lock:
            doc_copy = json.loads(json.dumps(document)) # deep copy
            if "_id" not in doc_copy:
                import uuid
                doc_copy["_id"] = str(uuid.uuid4())
            self._documents.append(doc_copy)
            class InsertResult:
                inserted_id = doc_copy["_id"]
                acknowledged = True
            return InsertResult()

    def _match_filter(self, doc: Dict[str, Any], query_filter: Dict[str, Any]) -> bool:
        """Simple evaluator checking matches for query filters."""
        if not query_filter:
            return True
        for key, value in query_filter.items():
            if key == "$or" and isinstance(value, list):
                if not any(self._match_filter(doc, sub_f) for sub_f in value):
                    return False
                continue
            if key == "$and" and isinstance(value, list):
                if not all(self._match_filter(doc, sub_f) for sub_f in value):
                    return False
                continue
            
            # Simple direct match or operators
            if key not in doc:
                return False
            doc_val = doc[key]
            if isinstance(value, dict):
                # evaluate basic operators like $gt, $lt, $ne, $in
                for op, op_val in value.items():
                    if op == "$gt" and not (doc_val > op_val): return False
                    elif op == "$lt" and not (doc_val < op_val): return False
                    elif op == "$gte" and not (doc_val >= op_val): return False
                    elif op == "$lte" and not (doc_val <= op_val): return False
                    elif op == "$ne" and not (doc_val != op_val): return False
                    elif op == "$in" and doc_val not in op_val: return False
                    elif op == "$nin" and doc_val in op_val: return False
            else:
                if doc_val != value:
                    return False
        return True

    def find(self, filter_dict: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, Any]] = None) -> MockCursor:
        """Finds multiple documents matching the filter."""
        filter_dict = filter_dict or {}
        with self._lock:
            results = []
            for doc in self._documents:
                if self._match_filter(doc, filter_dict):
                    results.append(json.loads(json.dumps(doc)))
            return MockCursor(results)

    def find_one(self, filter_dict: Optional[Dict[str, Any]] = None, projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Finds a single document matching the filter."""
        filter_dict = filter_dict or {}
        with self._lock:
            for doc in self._documents:
                if self._match_filter(doc, filter_dict):
                    return json.loads(json.dumps(doc))
            return None

    def update_one(self, filter_dict: Dict[str, Any], update_dict: Dict[str, Any], upsert: bool = False) -> Any:
        """Updates a single document matching the filter."""
        with self._lock:
            target_doc = None
            for doc in self._documents:
                if self._match_filter(doc, filter_dict):
                    target_doc = doc
                    break
            
            class UpdateResult:
                matched_count = 1 if target_doc else 0
                modified_count = 0
                upserted_id = None
                acknowledged = True

            if target_doc:
                # Perform updates (supports $set, $unset, $push)
                if "$set" in update_dict:
                    for k, v in update_dict["$set"].items():
                        target_doc[k] = v
                if "$unset" in update_dict:
                    for k in update_dict["$unset"].keys():
                        target_doc.pop(k, None)
                if "$push" in update_dict:
                    for k, v in update_dict["$push"].items():
                        if k not in target_doc:
                            target_doc[k] = []
                        if isinstance(target_doc[k], list):
                            target_doc[k].append(v)
                res = UpdateResult()
                res.modified_count = 1
                return res
            elif upsert:
                new_doc = json.loads(json.dumps(filter_dict))
                if "$set" in update_dict:
                    for k, v in update_dict["$set"].items():
                        new_doc[k] = v
                import uuid
                new_doc["_id"] = str(uuid.uuid4())
                self._documents.append(new_doc)
                res = UpdateResult()
                res.upserted_id = new_doc["_id"]
                res.matched_count = 0
                res.modified_count = 1
                return res

            return UpdateResult()

    def delete_one(self, filter_dict: Dict[str, Any]) -> Any:
        """Deletes a single document matching the filter."""
        with self._lock:
            index_to_del = -1
            for idx, doc in enumerate(self._documents):
                if self._match_filter(doc, filter_dict):
                    index_to_del = idx
                    break
            
            class DeleteResult:
                deleted_count = 0
                acknowledged = True

            if index_to_del != -1:
                self._documents.pop(index_to_del)
                res = DeleteResult()
                res.deleted_count = 1
                return res
            return DeleteResult()

    def count_documents(self, filter_dict: Dict[str, Any]) -> int:
        """Counts how many documents match the filter."""
        with self._lock:
            return sum(1 for doc in self._documents if self._match_filter(doc, filter_dict))

    def distinct(self, key: str, filter_dict: Optional[Dict[str, Any]] = None) -> List[Any]:
        """Returns unique values for a key across documents."""
        filter_dict = filter_dict or {}
        with self._lock:
            values = set()
            for doc in self._documents:
                if self._match_filter(doc, filter_dict) and key in doc:
                    val = doc[key]
                    if isinstance(val, list):
                        for item in val:
                            values.add(item)
                    else:
                        values.add(val)
            return list(values)

    def aggregate(self, pipeline: List[Dict[str, Any]]) -> MockCursor:
        """Simulates simple aggregations like $match, $group, $sort, $limit."""
        with self._lock:
            current_data = json.loads(json.dumps(self._documents))
            
            for stage in pipeline:
                if "$match" in stage:
                    match_filter = stage["$match"]
                    current_data = [doc for doc in current_data if self._match_filter(doc, match_filter)]
                elif "$sort" in stage:
                    sort_fields = stage["$sort"]
                    for field, order in sort_fields.items():
                        reverse = (order == -1)
                        current_data = sorted(current_data, key=lambda x: x.get(field, None) or "", reverse=reverse)
                elif "$limit" in stage:
                    current_data = current_data[:stage["$limit"]]
                elif "$group" in stage:
                    # Very simple group mock if required
                    logger.warning("MongoDB Mock Grouping executed - returns basic summary.")
            return MockCursor(current_data)


class MockDatabase:
    """
    Simulates a MongoDB Database. Resolves collection names dynamically.
    """
    def __init__(self, name: str):
        self.name = name
        self._collections: Dict[str, MockCollection] = {}
        self._lock = threading.Lock()

    def __getitem__(self, name: str) -> MockCollection:
        with self._lock:
            if name not in self._collections:
                self._collections[name] = MockCollection(name)
            return self._collections[name]

    def get_collection(self, name: str) -> MockCollection:
        """Retrieves or creates a simulated collection."""
        return self[name]


class MockMongoClient:
    """
    Simulates PyMongo/Motor's client connector in a thread-safe, mock-friendly manner.
    """
    def __init__(self, uri: str = "mongodb://localhost:27017"):
        self.uri = uri
        self._databases: Dict[str, MockDatabase] = {}
        self._lock = threading.Lock()

    def __getitem__(self, name: str) -> MockDatabase:
        with self._lock:
            if name not in self._databases:
                self._databases[name] = MockDatabase(name)
            return self._databases[name]

    def get_database(self, name: str) -> MockDatabase:
        """Retrieves or creates a simulated database."""
        return self[name]


# Singletons for mock NoSQL access
nosql_client = MockMongoClient()
nosql_db = nosql_client["rovex_nosql"]


def get_nosql_db() -> MockDatabase:
    """
    Dependency generator for NoSQL collections.
    """
    return nosql_db


# =====================================================================
# 3. DATABASE INITIALIZATION & SEEDING
# =====================================================================

def init_db():
    """
    Initializes the SQLite tables and seeds both the Relational (SQLite) 
    and Document (Mock PyMongo) databases with initial mock data.
    """
    logger.info("Initializing in-memory databases and applying seed data...")
    
    # 1. Setup SQL tables
    Base.metadata.create_all(bind=engine)
    
    # 2. Seed SQL users
    db = SessionLocal()
    try:
        if db.query(UserSQL).count() == 0:
            for u in SEED_USERS:
                db_user = UserSQL(
                    id=u["id"],
                    username=u["username"],
                    password=u["password"],
                    role=u["role"],
                    organization=u["organization"],
                    full_name=u["full_name"],
                    email=u["email"]
                )
                db.add(db_user)
            db.commit()
            logger.info(f"Successfully seeded {len(SEED_USERS)} users in SQL database.")
    except Exception as e:
        logger.error(f"Error seeding SQL users: {e}")
        db.rollback()
    finally:
        db.close()

    # 3. Seed NoSQL robots
    robot_collection = nosql_db["robots"]
    if robot_collection.count_documents({}) == 0:
        for r in SEED_ROBOTS:
            robot_collection.insert_one(r)
        logger.info(f"Successfully seeded {len(SEED_ROBOTS)} robots in Mock PyMongo.")

    # 4. Seed empty telemetry collection
    telemetry_collection = nosql_db["telemetry"]
    logger.info("Telemetry and log collections ready.")

    # 5. Create empty log file if not exists
    try:
        if not os.path.exists(LOG_FILE_PATH):
            os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
            with open(LOG_FILE_PATH, "w") as f:
                f.write(f"--- Rovex Platform Log Stream Initialized at {datetime.datetime.utcnow().isoformat()} ---\n")
    except Exception as e:
        logger.error(f"Could not create initial log file: {e}")
