# Rovex Hospital Stretcher Robots Backend Platform

Welcome to the **Rovex Fleet Orchestration Backend**. This prototype is designed as a modular, scalable, production-ready backend system to manage hospital stretcher robots. Built using **Python and FastAPI**, it simulates concurrent robot data streams, provides Role-Based Access Control (RBAC) security, and performs macro-route optimizations.

---

## 🚀 Tech Stack & Tradeoffs

1. **FastAPI & Python 3.11**: Leverages high-performance asynchronous event-loops to serve concurrent REST API requests.
2. **Pydantic v2**: Handles and strictly validates incoming concurrent synthetic telemetry payloads sent by robots.
3. **Dual Mock Storage Engine** (No external database installation required):
   - **Relational SQL Database (SQLite in-memory)**: Emulates a transactional PostgreSQL OLTP system using genuine, production-standard **SQLAlchemy ORM** configurations for users, roles, and scheduled task records.
   - **Document NoSQL Database (Custom PyMongo Mock)**: A thread-safe, in-memory collection-based document database emulating MongoDB/PyMongo. Stores and queries flexible unstructured robot profiles, history log pools, and system alerts.
4. **Lightweight HMAC-SHA256 Token Sessions**: Cryptographically signed access credentials with zero external OAuth library bloat, ensuring maximum system independence and speed.
5. **Tailwind CSS & Canvas JS Frontend**: Serves interactive, responsive administrative panels and an AI chat workspace with zero node/npm dependency overhead. The Core Platform shell also uses a small amount of custom CSS to guarantee a sticky, collapsible Gemini-style sidebar and a fully scrollable main workspace without introducing a frontend build step.

---

## 📐 System Architecture: Modular Monolithic

The directory is structured to represent a **Modular Monolith**, ensuring that each domain is self-contained with its own schemas, database tables, and endpoints. Decoupling and breaking individual services out into separate standalone microservices in the future is a zero-rewrite operation.

```text
app/
├── core/
│   ├── config.py           # Configuration variables, seed user base & layout graph nodes
│   ├── database.py         # Mock SQLAlchemy SQLite engine, PyMongo clients & DB seed engines
│   └── auth.py             # HMAC crypt token sessions & RBAC Dependency Injection
├── services/
│   ├── user/               # User Management Service (SQL, register, login, RBAC shifts)
│   ├── robot/              # Robot Management Service (NoSQL, A* router, telemetry validation)
│   ├── notification/       # Notification Service (Alerts, category priority, physical logs)
│   ├── admin/              # Admin Platform (Dashboard stats, DB queries sandbox, live log terminal)
│   └── core_platform/      # Core Platform (User scheduling, transit simulation, requests)
├── templates/              # HTML Frontend Templates (Served natively by FastAPI Jinja2)
│   ├── index.html          # Dynamic login panel & RBAC account credentials card
│   ├── admin.html          # Sandboxed query browser, log panel, and device sanction controls
│   └── core_platform.html  # Gemini-style chat portal and live 2D canvas navigation map
├── main.py                 # Core application entrypoint and module mounters
tests/
└── test_platform.py        # Complete unit test suite (Seeded auth, A*, NoSQL & SQL operations)
```

---

## 🌟 Key Features & Demonstrations

### 🧑‍💼 1. Hierarchical User Management & RBAC
Three pre-configured profiles represent the institution's personnel:
- **Supervisor (Dr. Mitchell)**: Full administrator rights. Can modify staff member roles, sanction/un-sanction robots, adjust corridor routing costs, and access the Secured Query Sandbox and File Logs.
- **Sub-Supervisor (Nurse Kelly)**: Dispatch rights. Can schedule new transport missions, view live robot tracking coordinates, and adjust traffic corridor priorities.
- **Employee (Orderly John)**: Viewer rights. Can inspect scheduled missions, ETAs, and submit emergency maintenance requests.

### 🤖 2. Telemetry Ingestion (Pydantic Validation)
Supports high-frequency telemetry packets, validating physical speed and steering parameters, battery mah capacities, 2D coordinates, safety proximity obstacles, and camera/lidar diagnostics.

### 🗺️ 3. A* Macro-Routing & Orchestration
Implements the **A\* Search Algorithm** on a 2D graph representing hospital zones (Reception, ICU, Pharmacy, Wards, etc.).
- **Euclidean Heuristic**: Computes straight-line distances.
- **Dynamic Traffic Priority**: Supervisors can increase the cost weight of specific corridors (e.g. to bypass busy hallways during peak periods), dynamically forcing robots onto alternative optimal routes.
- **Diagnostics Output**: Traces A\* computations step-by-step (g-score, h-score, f-score) to display "how the algorithm works" transparently.

### 📢 4. Multi-Priority Notifications Service
Categorizes all alerts into **CRITICAL, GENERAL, ANALYTICS, SUGGESTIONS, and MARKETING** with strict numerical priorities. 
- Alerts are appended to a persistent local log file `data_pool_notifications.log` on disk to simulate a unified data pool (ready for future ELT ingestion).
- Alerts are also written to a MongoDB-like index enabling instant rendering on frontend cards.

### 🛠️ 5. Admin Sandboxed Database Query Workspace
Provides a secure console where administrators can run manual queries:
- **SQL Console**: Executes actual raw SQL commands (e.g. `SELECT * FROM tasks WHERE status='completed'`) against the active OLTP database.
- **NoSQL Console**: Parses and executes PyMongo-style query strings (e.g. `db.robots.find({"battery": {"$lt": 50}})` or `db.notifications.find({"category": "CRITICAL"})`) directly.

### 💬 6. Gemini-Style Chat Assistant & Canvas Visualizer
The face-to-face employee workspace is styled with a sleek **Gemini-like AI Chat Input**. 
- Users can type commands in natural language: e.g. **"schedule from Reception to ICU"** or **"list active robots"**.
- The frontend parses commands programmatically to trigger underlying REST APIs.
- A live **2D HTML5 Canvas** renders the hospital layout, highlighting optimal paths and showing robot movements coordinate-by-coordinate in real-time.
- On desktop screens, the Core Platform behaves like a sticky app shell: a collapsible left operations rail stays pinned while the chat/map workspace scrolls independently.
- On desktop screens, the Core Platform behaves like a sticky app shell: a collapsible left operations rail stays pinned while the chat/map workspace scrolls independently.

---

## 🛠️ Installation & Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt --user --break-system-packages
   ```

2. **Run the Unit Test Suite** (Verifies and validates all sub-modules):
   ```bash
   python3 -m unittest -v
   ```
   *Output showing `OK` confirms that cryptographic, relational, document, routing, file-based template loading, and Core Platform layout checks are all passing.*

3. **Start the FastAPI Application Server**:
   ```bash
   python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Navigate to the Platform**:
   Open your browser and navigate to: `http://localhost:8000/`

5. **When validating frontend HTML/layout changes locally**:
   - restart the active `uvicorn` process after pulling the newest branch updates,
   - then do a hard refresh in the browser (`Ctrl+Shift+R` / `Cmd+Shift+R`).

   This project serves HTML templates directly from FastAPI, so restarting the local process is the safest way to guarantee the browser is testing the newest frontend markup during iteration.

---

## 🔍 Code Reliability & Best Practices
- **DRY & YAGNI**: Modular design keeps components focused on single domains with no unnecessary abstractions.
- **Fully Documented**: Every module, route, and function begins with an extensive descriptive block explaining its role and implementation specs in detail.
- **Error Boundaries**: High defensive programming practices with validation checks on indices, empty values, and non-existing paths.
